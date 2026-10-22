"""
Acceso a Gmail para GitHub Actions, usando el OAuth propio del usuario
(proyecto "FABRIC-Horarios-2627", alcance de solo lectura
https://www.googleapis.com/auth/gmail.readonly) -- NO el conector MCP de
Claude, que solo existe dentro de una sesion de Claude y no esta disponible
en un workflow de Actions.

Credenciales: se leen de variables de entorno (GitHub Secrets en el
workflow), nunca de un fichero ni de un argumento en texto plano, y nunca se
imprimen ni se incluyen en ningun mensaje de log o de commit:
  GMAIL_CLIENT_ID
  GMAIL_CLIENT_SECRET
  GMAIL_REFRESH_TOKEN

Separacion deliberada entre I/O y logica:
  - Las funciones que hablan con la API de Gmail (``obtener_servicio``,
    ``listar_mensajes_candidatos``, ``descargar_adjunto``) necesitan red y
    credenciales reales; no se pueden probar en esta sesion sin acceso a tu
    cuenta real de Gmail v3 (eso es distinto del conector Gmail de Claude
    usado en esta conversacion, que es solo para esta sesion).
  - Las funciones que SI se prueban aqui con datos de verdad son las que
    construyen la query y las que interpretan el JSON que devuelve la API
    (``construir_query`` y ``extraer_candidato``): no dependen de la red,
    solo de la forma exacta del recurso "Message" de la API de Gmail
    (https://developers.google.com/gmail/api/reference/rest/v1/users.messages),
    que es publica y estable, y se fijan con tests contra un mensaje de
    ejemplo con la misma forma que devuelve la API real.
"""
from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone

from scripts.sabana_mail import CorreoCandidato, REMITENTE_ESPERADO

SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)


class ConfiguracionIncompleta(Exception):
    """Falta alguna variable de entorno/secreto necesaria. Nunca se
    continua con una credencial parcial ni se inventa un valor por defecto."""


def leer_credenciales_de_entorno() -> dict:
    valores = {
        "client_id": os.environ.get("GMAIL_CLIENT_ID", ""),
        "client_secret": os.environ.get("GMAIL_CLIENT_SECRET", ""),
        "refresh_token": os.environ.get("GMAIL_REFRESH_TOKEN", ""),
    }
    faltantes = [nombre for nombre, valor in valores.items() if not valor]
    if faltantes:
        raise ConfiguracionIncompleta(
            "Faltan variables de entorno (secretos de GitHub Actions): "
            + ", ".join(f"GMAIL_{n.upper()}" for n in faltantes)
            + ". No se continua sin todas ellas."
        )
    return valores


def obtener_servicio():
    """Construye el cliente de la API de Gmail a partir de las credenciales
    del entorno. Requiere red real; no se llama en los tests."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    valores = leer_credenciales_de_entorno()
    credenciales = Credentials(
        token=None,
        refresh_token=valores["refresh_token"],
        client_id=valores["client_id"],
        client_secret=valores["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=credenciales, cache_discovery=False)


def construir_query(remitente: str = REMITENTE_ESPERADO, dias: int = 14) -> str:
    """Query de busqueda de Gmail: correos del remitente esperado, con
    adjunto, de los ultimos ``dias`` dias. Se restringe por adjunto en la
    propia query (como ya se hacia a mano en la auditoria anterior) para no
    descargar de mas, aunque la clasificacion fina de que adjunto es un
    xlsx/xlsm real se hace despues, en sabana_mail.candidatos_validos."""
    return f"from:{remitente} has:attachment newer_than:{dias}d"


def _texto_de_parte(parte: dict) -> str:
    """Decodifica el cuerpo de texto plano de una parte MIME (formato
    "full" de la API de Gmail: body.data en base64url)."""
    datos = parte.get("body", {}).get("data")
    if not datos:
        return ""
    try:
        return base64.urlsafe_b64decode(datos + "=" * (-len(datos) % 4)).decode("utf-8", "replace")
    except Exception:
        return ""


def _recorrer_partes(payload: dict):
    """Generador que recorre recursivamente payload["parts"] (los mensajes
    multipart anidan partes dentro de partes)."""
    yield payload
    for sub in payload.get("parts", []) or []:
        yield from _recorrer_partes(sub)


def extraer_candidato(mensaje: dict) -> CorreoCandidato:
    """Convierte un recurso Message (formato "full") de la API de Gmail en
    un ``CorreoCandidato`` de sabana_mail.py. Pura: no hace red."""
    payload = mensaje.get("payload", {})
    headers = {h["name"].strip().lower(): h["value"] for h in payload.get("headers", [])}
    asunto = headers.get("subject", "")
    remitente_cabecera = headers.get("from", "")
    # La cabecera "From" suele venir como 'Nombre <correo@dominio>'; nos
    # interesa solo la direccion para comparar con REMITENTE_ESPERADO.
    remitente = remitente_cabecera
    if "<" in remitente_cabecera and ">" in remitente_cabecera:
        remitente = remitente_cabecera.split("<", 1)[1].split(">", 1)[0].strip()
    fecha_header = headers.get("date")
    if "internalDate" in mensaje:
        fecha_envio = datetime.fromtimestamp(int(mensaje["internalDate"]) / 1000, tz=timezone.utc)
    elif fecha_header:
        from email.utils import parsedate_to_datetime

        fecha_envio = parsedate_to_datetime(fecha_header)
        if fecha_envio.tzinfo is None:
            fecha_envio = fecha_envio.replace(tzinfo=timezone.utc)
    else:
        raise ValueError(f"El mensaje {mensaje.get('id')} no tiene fecha (ni internalDate ni cabecera Date).")

    cuerpo_texto = ""
    adjuntos: list[str] = []
    for parte in _recorrer_partes(payload):
        nombre_archivo = parte.get("filename")
        if nombre_archivo:
            adjuntos.append(nombre_archivo)
            continue
        mime = parte.get("mimeType", "")
        if mime == "text/plain" and not cuerpo_texto:
            cuerpo_texto = _texto_de_parte(parte)
    return CorreoCandidato(
        message_id=mensaje["id"],
        thread_id=mensaje.get("threadId", mensaje["id"]),
        fecha_envio=fecha_envio,
        remitente=remitente,
        asunto=asunto,
        cuerpo_texto=cuerpo_texto,
        adjuntos=tuple(adjuntos),
    )


def id_de_adjunto(mensaje: dict, nombre_archivo: str) -> str:
    """Busca el attachmentId de un adjunto por su nombre dentro del mismo
    recurso Message ya descargado (evita una llamada de red adicional: el
    id ya viene en el "full" que trajo extraer_candidato). Falla de forma
    explicita si no lo encuentra o si hay mas de uno con el mismo nombre
    (dos adjuntos con el mismo nombre en un mensaje es justo el tipo de
    ambiguedad que no se resuelve por intuicion)."""
    payload = mensaje.get("payload", {})
    coincidencias = [
        parte["body"]["attachmentId"]
        for parte in _recorrer_partes(payload)
        if parte.get("filename") == nombre_archivo and parte.get("body", {}).get("attachmentId")
    ]
    if not coincidencias:
        raise ValueError(f"No se encuentra el adjunto {nombre_archivo!r} en el mensaje {mensaje.get('id')}.")
    if len(coincidencias) > 1:
        raise ValueError(
            f"Hay {len(coincidencias)} adjuntos llamados {nombre_archivo!r} en el mensaje "
            f"{mensaje.get('id')}; es ambiguo, se revisa a mano."
        )
    return coincidencias[0]


def listar_candidatos(
    servicio, remitente: str = REMITENTE_ESPERADO, dias: int = 14
) -> list[tuple[CorreoCandidato, dict]]:
    """Lista mensajes candidatos via la API real y devuelve, junto a cada
    ``CorreoCandidato``, el recurso Message completo (para poder llamar
    despues a id_de_adjunto sin otra llamada de red). Requiere red; no se
    prueba en esta sesion (ver extraer_candidato para la parte probada)."""
    query = construir_query(remitente, dias)
    candidatos = []
    peticion = servicio.users().messages().list(userId="me", q=query)
    while peticion is not None:
        respuesta = peticion.execute()
        for item in respuesta.get("messages", []):
            mensaje = servicio.users().messages().get(userId="me", id=item["id"], format="full").execute()
            candidatos.append((extraer_candidato(mensaje), mensaje))
        peticion = servicio.users().messages().list_next(peticion, respuesta)
    return candidatos


def descargar_adjunto(servicio, message_id: str, attachment_id: str) -> bytes:
    """Descarga el contenido binario de un adjunto. Requiere red; no se
    imprime nunca el contenido ni metadatos sensibles en logs."""
    parte = servicio.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    datos = parte["data"]
    return base64.urlsafe_b64decode(datos + "=" * (-len(datos) % 4))
