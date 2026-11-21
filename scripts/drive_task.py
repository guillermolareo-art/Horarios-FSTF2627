"""Sincroniza el PDF semanal y las semanas cerradas con una carpeta de Drive."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from scripts.drive_files import (
    ConfiguracionDriveIncompleta,
    descargar_archivo,
    listar_archivos,
    obtener_configuracion,
    obtener_servicio_drive,
    subir_archivo,
)
from scripts.excel_control import actualizar_excel_control
from scripts.excel_control import ErrorExcelControl
from googleapiclient.errors import HttpError

RUTA_DATOS = Path("data/fstf-2627.json")
PATRON_VERSION = re.compile(
    r"^Plantilla Control firma FSTF 1 cuat 2026-2027 s(\d+)\.xlsx$",
    re.IGNORECASE,
)


def _semana_numero(etiqueta: str) -> int | None:
    coincidencia = re.match(r"\s*(\d+)", etiqueta)
    return int(coincidencia.group(1)) if coincidencia else None


def _versiones_excel(archivos: list[dict]) -> list[tuple[int, dict]]:
    versiones = [
        (int(m.group(1)), archivo)
        for archivo in archivos
        if (m := PATRON_VERSION.fullmatch(archivo.get("name", "")))
    ]
    numeros = [numero for numero, _ in versiones]
    if len(numeros) != len(set(numeros)):
        raise ValueError("Hay varias versiones del mismo numero de semana en la carpeta.")
    return versiones


def _codigo_semana(datos: dict) -> str:
    coincidencia = re.search(r"_(\d{1,2}[A-Za-z])_", datos.get("archivo", ""))
    if not coincidencia:
        raise ValueError("No se puede determinar el codigo de semana del horario actual.")
    return coincidencia.group(1)


def _hash_horario(datos: dict) -> str:
    contenido = json.dumps(datos, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _necesita_pdf(datos: dict, archivos: list[dict]) -> tuple[bool, str, dict | None]:
    codigo = _codigo_semana(datos)
    nombre = f"Horario_FABRIC_Semana{codigo}.pdf"
    coincidencias = [f for f in archivos if f.get("name") == nombre]
    if len(coincidencias) > 1:
        raise ValueError("Hay varias copias del PDF semanal en la carpeta compartida.")
    huella = _hash_horario(datos)
    existente = coincidencias[0] if coincidencias else None
    return not existente or existente.get("appProperties", {}).get("scheduleHash") != huella, nombre, existente


def _pendientes_excel(datos: dict, archivos: list[dict]) -> list[tuple[int, dict]]:
    versiones = _versiones_excel(archivos)
    if not datos.get("historial"):
        return []
    if not versiones:
        raise ValueError("No se encuentra una version numerada del Excel de control en la carpeta.")

    ultima_version = max(n for n, _ in versiones)
    pendientes = []
    for entrada in datos["historial"]:
        numero = _semana_numero(entrada.get("semana", ""))
        if numero and numero > ultima_version:
            pendientes.append((numero, entrada))
    return sorted(pendientes, key=lambda par: par[0])


def _validar_excel_existente(
    contenido: bytes,
    historial: list[dict],
    etiqueta: str,
    numero_maximo: int,
) -> None:
    for entrada in historial:
        numero = _semana_numero(entrada.get("semana", ""))
        if not numero or numero > numero_maximo:
            continue
        actualizado = actualizar_excel_control(
            contenido,
            numero_semana=numero,
            etiqueta_responsable=etiqueta,
            teoria=int(entrada["teoria"]),
            laboratorio=int(entrada["laboratorio"]),
            seminario=int(entrada["seminario"]),
        )
        if actualizado is not None:
            raise ValueError(
                f"El Excel existente no tiene registrados los datos esperados de la semana {numero}."
            )


def _emitir_outputs(pdf: bool, excel: bool) -> None:
    salida = os.environ.get("GITHUB_OUTPUT")
    lineas = f"pdf_needed={str(pdf).lower()}\nexcel_needed={str(excel).lower()}\n"
    if salida:
        with open(salida, "a", encoding="utf-8") as archivo:
            archivo.write(lineas)
    else:
        print(lineas, end="")


def planificar() -> tuple[bool, bool]:
    try:
        obtener_configuracion()
    except ConfiguracionDriveIncompleta as exc:
        print(f"::notice::{exc}")
        _emitir_outputs(False, False)
        return False, False

    datos = json.loads(RUTA_DATOS.read_text(encoding="utf-8"))
    servicio = obtener_servicio_drive()
    _, carpeta_id = obtener_configuracion()
    archivos = listar_archivos(servicio, carpeta_id)
    pdf, _, _ = _necesita_pdf(datos, archivos)
    pendientes = _pendientes_excel(datos, archivos)
    etiqueta = os.environ.get("CONTROL_OWNER_LABEL", "").strip()
    identificador = os.environ.get("SCHEDULE_OWNER_ID", "").strip()
    excel = bool(pendientes and etiqueta and identificador)
    if pendientes and (not etiqueta or not identificador):
        print("::warning::Faltan CONTROL_OWNER_LABEL o SCHEDULE_OWNER_ID; se aplaza el Excel.")
    if etiqueta and identificador and datos.get("historial"):
        versiones = _versiones_excel(archivos)
        if versiones:
            numero_ultima, ultima = max(versiones, key=lambda par: par[0])
            contenido = descargar_archivo(servicio, ultima["id"])
            _validar_excel_existente(
                contenido,
                datos["historial"],
                etiqueta,
                numero_maximo=numero_ultima,
            )
    _emitir_outputs(pdf, excel)
    return pdf, excel


async def _crear_pdf(destino: Path) -> None:
    from playwright.async_api import async_playwright
    from pypdf import PdfReader

    async with async_playwright() as playwright:
        navegador = await playwright.chromium.launch()
        try:
            pagina = await navegador.new_page()
            await pagina.goto("http://127.0.0.1:8000/artifact.html", wait_until="networkidle")
            await pagina.wait_for_function(
                "document.querySelectorAll('#print-sheet tbody tr').length > 0",
                timeout=30000,
            )
            await pagina.emulate_media(media="print")
            await pagina.pdf(
                path=str(destino),
                format="A4",
                print_background=True,
                margin={"top": "12mm", "bottom": "12mm", "left": "12mm", "right": "12mm"},
            )
        finally:
            await navegador.close()

    if len(PdfReader(str(destino)).pages) != 1:
        destino.unlink(missing_ok=True)
        raise ValueError("El PDF semanal no cabe en una pagina; no se ha subido.")


def sincronizar() -> None:
    pdf, excel = planificar()
    if not pdf and not excel:
        return

    datos = json.loads(RUTA_DATOS.read_text(encoding="utf-8"))
    servicio = obtener_servicio_drive()
    _, carpeta_id = obtener_configuracion()
    archivos = listar_archivos(servicio, carpeta_id)

    if pdf:
        necesita_pdf, nombre_pdf, existente = _necesita_pdf(datos, archivos)
        if necesita_pdf:
            with tempfile.TemporaryDirectory(prefix="fstf-pdf-") as temporal:
                ruta_pdf = Path(temporal) / "Horario_FABRIC.pdf"
                asyncio.run(_crear_pdf(ruta_pdf))
                subir_archivo(
                    servicio,
                    carpeta_id,
                    nombre_pdf,
                    ruta_pdf.read_bytes(),
                    "application/pdf",
                    archivo_id=existente.get("id") if existente else None,
                    app_properties={"scheduleHash": _hash_horario(datos)},
                )

    if excel:
        etiqueta = os.environ["CONTROL_OWNER_LABEL"]
        versiones = _versiones_excel(archivos)
        if not versiones:
            raise ValueError("No se encuentra una version numerada del Excel de control en la carpeta.")
        _, ultima = max(versiones, key=lambda par: par[0])
        contenido_excel = descargar_archivo(servicio, ultima["id"])
        pendientes = _pendientes_excel(datos, archivos)
        for numero, semana in pendientes:
            actualizado = actualizar_excel_control(
                contenido_excel,
                numero_semana=numero,
                etiqueta_responsable=etiqueta,
                teoria=int(semana["teoria"]),
                laboratorio=int(semana["laboratorio"]),
                seminario=int(semana["seminario"]),
            )
            if actualizado is None:
                continue
            nombre = f"Plantilla Control firma FSTF 1 cuat 2026-2027 s{numero}.xlsx"
            subida = subir_archivo(
                servicio,
                carpeta_id,
                nombre,
                actualizado,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            contenido_excel = actualizado
            archivos.append({"id": subida["id"], "name": nombre})


def main() -> int:
    modo = sys.argv[1] if len(sys.argv) > 1 else "sync"
    try:
        if modo == "plan":
            planificar()
        elif modo == "sync":
            sincronizar()
        else:
            print("Uso: python -m scripts.drive_task [plan|sync]", file=sys.stderr)
            return 2
    except ConfiguracionDriveIncompleta as exc:
        print(f"Configuracion Drive incompleta: {exc}", file=sys.stderr)
        return 1
    except HttpError as exc:
        print(f"Sincronizacion Drive detenida: error de API HTTP {exc.status_code}.", file=sys.stderr)
        return 1
    except (ValueError, OSError, ErrorExcelControl) as exc:
        print(f"Sincronizacion Drive detenida: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
