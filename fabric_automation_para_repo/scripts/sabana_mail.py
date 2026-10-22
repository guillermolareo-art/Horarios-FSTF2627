"""
Reglas deterministas (sin IA) para detectar y clasificar correos con sabanas de
horarios de coordinacion.horarios.espacios@cud.uvigo.es.

Nada de esto llama a ningun modelo. Toda la logica es pura y, por tanto,
comprobable con tests unitarios reales (ver tests/test_sabana_mail.py).

Separacion de responsabilidades:
  - sabana_mail.py        -> que correos cuentan, que semana destino tienen,
                             cual es definitiva vs provisional, deduplicacion.
  - import_fabric.py      -> (siguiente paso) parseo del Excel una vez
                             descargado el adjunto real.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

REMITENTE_ESPERADO = "coordinacion.horarios.espacios@cud.uvigo.es"

# Adjuntos reales de sabana: solo estas extensiones cuentan como "adjunto real".
EXTENSIONES_SABANA = (".xlsx", ".xlsm")

# Frases que delatan un correo de aviso/error sin adjunto nuevo real (se reenviara
# despues en otro mensaje, que si se procesara cuando llegue).
PATRONES_AVISO_SIN_ADJUNTO = (
    re.compile(r"\bhay un error\b", re.I),
    re.compile(r"\bno es la (?:última )?versión\b", re.I),
    re.compile(r"\ben cuanto lo consiga\b", re.I),
)

# Palabras que marcan una sabana como DEFINITIVA (no provisional).
PATRONES_DEFINITIVA = (
    re.compile(r"\bdefinitiv", re.I),
    re.compile(r"\bfinal\b", re.I),
    re.compile(r"\bse va a publicar\b", re.I),
)

PATRONES_PROVISIONAL = (
    re.compile(r"\bprovisional", re.I),
    re.compile(r"\bborrador\b", re.I),
)


class SabanaAmbigua(Exception):
    """Se lanza cuando un mensaje es contradictorio y el proceso debe detenerse
    en vez de adivinar (requisito: "ante una contradiccion, detener el proceso")."""


@dataclass(frozen=True)
class CorreoCandidato:
    message_id: str
    thread_id: str
    fecha_envio: datetime          # UTC, con tzinfo
    remitente: str
    asunto: str
    cuerpo_texto: str
    adjuntos: tuple[str, ...] = field(default_factory=tuple)   # nombres de archivo


@dataclass(frozen=True)
class SabanaClasificada:
    message_id: str
    thread_id: str
    fecha_envio: datetime
    archivo: str
    es_definitiva: bool
    semana_envio_lunes: date       # lunes (sabado->viernes) de la semana en que se envio
    semana_destino_lunes: date     # lunes de la semana (sabado->viernes) a la que apunta


def semana_lunes(d: date) -> date:
    """Lunes de la semana academica sabado->viernes que contiene ``d``.

    Replica exactamente la regla ya usada para la pagina del horario: la
    semana academica va de sabado a viernes, asi que si ``d`` es sabado o
    domingo ya pertenece a la semana que empieza ese sabado.
    """
    dow = d.weekday()  # Mon=0..Sun=6
    dias_desde_sabado = (dow - 5) % 7
    sabado = d - timedelta(days=dias_desde_sabado)
    return sabado + timedelta(days=2)


def tiene_adjunto_real(correo: CorreoCandidato) -> bool:
    return any(a.lower().endswith(EXTENSIONES_SABANA) for a in correo.adjuntos)


def es_respuesta_de_hilo(correo: CorreoCandidato, remitente_sabanas: str = REMITENTE_ESPERADO) -> bool:
    """Respuestas de Guillermo u otros profesores al hilo: nunca cuentan como
    sabana nueva, aunque por error llevaran algun adjunto."""
    return correo.remitente.strip().lower() != remitente_sabanas.strip().lower()


def clasificar_definitiva_o_provisional(asunto: str, cuerpo_texto: str) -> bool:
    """True si es definitiva, False si es provisional (o si no hay evidencia
    explicita -- el valor por defecto es "no definitiva", nunca al reves: no
    se asciende un documento a definitivo salvo que lo diga el propio correo).

    Lanza SabanaAmbigua solo cuando el texto afirma a la vez "definitiva" y
    "provisional" de forma contradictoria (evidencia mixta) -- en ese caso no
    se adivina, se detiene el proceso para revision humana.
    """
    texto = f"{asunto}\n{cuerpo_texto}"
    es_def = any(p.search(texto) for p in PATRONES_DEFINITIVA)
    es_prov = any(p.search(texto) for p in PATRONES_PROVISIONAL)
    if es_def and es_prov:
        raise SabanaAmbigua(
            f"El correo afirma a la vez 'definitiva' y 'provisional': {asunto!r}. "
            "No se resuelve por intuicion; requiere revision manual."
        )
    return es_def


def candidatos_validos(correos: Iterable[CorreoCandidato]) -> list[CorreoCandidato]:
    """Filtra la bandeja de entrada a solo los correos que son sabanas nuevas
    reales: del remitente esperado, con adjunto xlsx/xlsm real, que no son
    respuestas de hilo ni avisos de error sin adjunto."""
    validos = []
    for correo in correos:
        if es_respuesta_de_hilo(correo):
            continue
        if not tiene_adjunto_real(correo):
            continue
        validos.append(correo)
    return validos


def clasificar(correo: CorreoCandidato) -> SabanaClasificada:
    adjuntos_sabana = [a for a in correo.adjuntos if a.lower().endswith(EXTENSIONES_SABANA)]
    if len(adjuntos_sabana) != 1:
        raise SabanaAmbigua(
            f"El mensaje {correo.message_id} tiene {len(adjuntos_sabana)} adjuntos "
            f"xlsx/xlsm (se esperaba exactamente 1): {adjuntos_sabana!r}."
        )
    fecha = correo.fecha_envio.date()
    semana_envio = semana_lunes(fecha)
    semana_destino = semana_envio + timedelta(days=7)
    es_definitiva = clasificar_definitiva_o_provisional(correo.asunto, correo.cuerpo_texto)
    return SabanaClasificada(
        message_id=correo.message_id,
        thread_id=correo.thread_id,
        fecha_envio=correo.fecha_envio,
        archivo=adjuntos_sabana[0],
        es_definitiva=es_definitiva,
        semana_envio_lunes=semana_envio,
        semana_destino_lunes=semana_destino,
    )


def ultima_por_semana_destino(clasificadas: Iterable[SabanaClasificada]) -> dict[date, SabanaClasificada]:
    """De varios candidatos apuntando a la misma semana destino, se queda con
    el de fecha de envio mas reciente (la ultima revision conocida)."""
    por_semana: dict[date, SabanaClasificada] = {}
    for c in clasificadas:
        actual = por_semana.get(c.semana_destino_lunes)
        if actual is None or c.fecha_envio > actual.fecha_envio:
            por_semana[c.semana_destino_lunes] = c
    return por_semana


# --- Deduplicacion de mensajes/adjuntos ya procesados --------------------------

@dataclass
class EstadoProcesados:
    """Estado persistido entre ejecuciones (se guarda como JSON en el repo o en
    un artefacto de Actions) para no reprocesar nunca el mismo mensaje/adjunto."""
    message_ids: set[str] = field(default_factory=set)

    def ya_procesado(self, message_id: str) -> bool:
        return message_id in self.message_ids

    def marcar_procesado(self, message_id: str) -> None:
        self.message_ids.add(message_id)

    def to_json(self) -> dict:
        return {"message_ids": sorted(self.message_ids)}

    @classmethod
    def from_json(cls, data: dict) -> "EstadoProcesados":
        return cls(message_ids=set(data.get("message_ids", [])))


def pendientes_de_procesar(
    clasificadas: Iterable[SabanaClasificada], estado: EstadoProcesados
) -> list[SabanaClasificada]:
    return [c for c in clasificadas if not estado.ya_procesado(c.message_id)]
