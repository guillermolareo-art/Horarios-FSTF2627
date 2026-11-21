"""Importador conservador de las tablas PDF de la sábana FABRIC."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from scripts.import_fabric import ClaseFabric, ErrorImportacion, agrupar

_HORA = re.compile(r"^\d{1,2}:\d{2}$")
_AULA = re.compile(r"^\d{1,3}$")
_TIPOS_CLASE = {"TEORIA", "SEMINARIO", "LABORATORIO", "ESTUDIO", "CURSO_SUSPENSOS"}


def _texto(celda: object) -> str:
    return celda.strip() if isinstance(celda, str) else ""


def _hora_anterior(filas: list[list[object]], indice: int) -> str | None:
    for r in range(indice, -1, -1):
        if len(filas[r]) > 2:
            valor = _texto(filas[r][2])
            if _HORA.fullmatch(valor):
                return valor.zfill(5) if len(valor) == 4 else valor
    return None


def _hora_siguiente(filas: list[list[object]], indice: int) -> str | None:
    for r in range(indice, len(filas)):
        if len(filas[r]) > 2:
            valor = _texto(filas[r][2])
            if _HORA.fullmatch(valor):
                return valor.zfill(5) if len(valor) == 4 else valor
    return None


def _dia_anterior(filas: list[list[object]], indice: int) -> str | None:
    for r in range(indice, -1, -1):
        if filas[r]:
            valor = _texto(filas[r][0]).capitalize()
            if valor in {"Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"}:
                return valor
    return None


def _leer_tabla(filas: list[list[object]]) -> list[ClaseFabric]:
    filas = [list(fila or []) for fila in filas]
    cabeceras_grupo = [
        r for r, fila in enumerate(filas)
        if len(fila) > 2 and _texto(fila[2]).casefold() == "grupo"
    ]
    if len(cabeceras_grupo) != 1:
        raise ErrorImportacion("No se pudo identificar una unica fila de cabecera de grupos en la tabla PDF.")

    fila_grupos = filas[cabeceras_grupo[0]]
    hallazgos = [
        (r, c)
        for r, fila in enumerate(filas)
        for c, valor in enumerate(fila)
        if _texto(valor).upper() == "FABRIC"
    ]
    clases: list[ClaseFabric] = []
    for r, c in hallazgos:
        if r == 0 or r + 1 >= len(filas) or c >= len(fila_grupos):
            raise ErrorImportacion("Una franja FABRIC esta incompleta en la tabla PDF.")

        tipo = _texto(filas[r - 1][c]) if c < len(filas[r - 1]) else ""
        grupo = _texto(fila_grupos[c])
        dia = _dia_anterior(filas, r)
        inicio = _hora_anterior(filas, r - 1)
        fin = _hora_siguiente(filas, r + 1)
        if not tipo or not grupo or not dia or not inicio or not fin:
            raise ErrorImportacion("Una franja FABRIC tiene datos incompletos en la tabla PDF.")
        siguiente_inicio = None
        for siguiente_r in range(r + 1, len(filas)):
            if c < len(filas[siguiente_r]) and _texto(filas[siguiente_r][c]).upper() in _TIPOS_CLASE:
                siguiente_inicio = _hora_anterior(filas, siguiente_r)
                break
        if fin <= inicio or (siguiente_inicio and fin >= siguiente_inicio):
            raise ErrorImportacion("Una franja FABRIC tiene horas ambiguas en la tabla PDF.")

        aula_texto = _texto(filas[r + 1][c]) if c < len(filas[r + 1]) else ""
        aula = int(aula_texto) if _AULA.fullmatch(aula_texto) else None
        profesor = (aula_texto,) if re.fullmatch(r"[A-Z]{4,10}", aula_texto) else ()
        clases.append(
            ClaseFabric(
                dia=dia,
                inicio=inicio,
                fin=fin,
                tipo=tipo,
                aula=aula,
                grupos=(grupo,),
                profesores=profesor,
                fila_origen=r + 1,
                columna_origen=c + 1,
            )
        )

    return clases


def parse_fabric_pdf(ruta: str | Path, identificador_responsable: str | None = None) -> list[dict]:
    """Extrae y seudonimiza clases FABRIC solo si la lectura no es ambigua."""
    clases: list[ClaseFabric] = []
    with pdfplumber.open(ruta) as documento:
        for pagina in documento.pages:
            tablas = pagina.find_tables()
            if not tablas:
                raise ErrorImportacion("No se encontro una tabla en una pagina de la sabana PDF.")
            clases.extend(_leer_tabla(tablas[0].extract()))

    if not 2 <= len(clases) <= 20:
        raise ErrorImportacion("El numero de franjas FABRIC del PDF queda fuera del rango esperado.")
    clases_agrupadas, avisos = agrupar(
        clases,
        identificador_responsable=identificador_responsable,
    )
    if avisos:
        raise ErrorImportacion("La tabla PDF contiene anotaciones o repeticiones que requieren revision.")
    return clases_agrupadas
