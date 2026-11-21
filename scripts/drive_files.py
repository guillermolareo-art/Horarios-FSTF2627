"""Acceso limitado a la carpeta compartida con la cuenta de servicio."""
from __future__ import annotations

import io
import json
import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


class ConfiguracionDriveIncompleta(Exception):
    """Faltan secretos necesarios para acceder a la carpeta compartida."""


def obtener_configuracion() -> tuple[str, str]:
    clave = os.environ.get("DRIVE_SERVICE_ACCOUNT_JSON", "")
    carpeta = os.environ.get("DRIVE_FOLDER_ID", "")
    if not clave or not carpeta:
        raise ConfiguracionDriveIncompleta(
            "Configura DRIVE_SERVICE_ACCOUNT_JSON y DRIVE_FOLDER_ID en GitHub Secrets."
        )
    return clave, carpeta


def obtener_servicio_drive():
    clave_json, _ = obtener_configuracion()
    try:
        info = json.loads(clave_json)
    except json.JSONDecodeError as exc:
        raise ConfiguracionDriveIncompleta(
            "DRIVE_SERVICE_ACCOUNT_JSON no contiene un JSON valido."
        ) from exc
    credenciales = Credentials.from_service_account_info(info, scopes=[DRIVE_SCOPE])
    return build("drive", "v3", credentials=credenciales, cache_discovery=False)


def listar_archivos(servicio, carpeta_id: str) -> list[dict]:
    archivos = []
    token = None
    while True:
        respuesta = servicio.files().list(
            q=f"'{carpeta_id}' in parents and trashed = false",
            pageSize=1000,
            pageToken=token,
            fields="nextPageToken,files(id,name,mimeType,size,appProperties)",
        ).execute()
        archivos.extend(respuesta.get("files", []))
        token = respuesta.get("nextPageToken")
        if not token:
            return archivos


def descargar_archivo(servicio, archivo_id: str) -> bytes:
    destino = io.BytesIO()
    solicitud = servicio.files().get_media(fileId=archivo_id)
    descargador = MediaIoBaseDownload(destino, solicitud)
    terminado = False
    while not terminado:
        _, terminado = descargador.next_chunk()
    return destino.getvalue()


def subir_archivo(
    servicio,
    carpeta_id: str,
    nombre: str,
    contenido: bytes,
    mime_type: str,
    archivo_id: str | None = None,
    app_properties: dict[str, str] | None = None,
) -> dict:
    media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mime_type, resumable=True)
    if archivo_id:
        parametros = {"fileId": archivo_id, "media_body": media, "fields": "id,name"}
        if app_properties:
            parametros["body"] = {"appProperties": app_properties}
        return servicio.files().update(**parametros).execute()
    body = {"name": nombre, "parents": [carpeta_id]}
    if app_properties:
        body["appProperties"] = app_properties
    return servicio.files().create(
        body=body,
        media_body=media,
        fields="id,name",
    ).execute()
