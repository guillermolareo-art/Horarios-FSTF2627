"""Edicion segura de las tres celdas semanales del Excel de control."""
from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)


class ErrorExcelControl(Exception):
    """El libro no coincide con la estructura esperada o contiene conflictos."""


def _columna_numero(referencia: str) -> int:
    letras = re.match(r"[A-Z]+", referencia)
    if not letras:
        raise ErrorExcelControl("Una celda del libro tiene una referencia invalida.")
    numero = 0
    for letra in letras.group(0):
        numero = numero * 26 + ord(letra) - ord("A") + 1
    return numero


def _texto_celda(celda: ET.Element, compartidas: list[str]) -> str:
    tipo = celda.get("t")
    if tipo == "s":
        valor = celda.find(f"{{{MAIN_NS}}}v")
        if valor is None or valor.text is None:
            return ""
        indice = int(valor.text)
        if not 0 <= indice < len(compartidas):
            raise ErrorExcelControl("El libro referencia una cadena compartida inexistente.")
        return compartidas[indice]
    if tipo == "inlineStr":
        return "".join(n.text or "" for n in celda.iter(f"{{{MAIN_NS}}}t"))
    valor = celda.find(f"{{{MAIN_NS}}}v")
    return valor.text if valor is not None and valor.text else ""


def _cargar_cadenas(contenido: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in contenido.namelist():
        return []
    root = ET.fromstring(contenido.read("xl/sharedStrings.xml"))
    return [
        "".join(n.text or "" for n in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _ruta_hoja(contenido: zipfile.ZipFile, nombre: str) -> str:
    workbook = ET.fromstring(contenido.read("xl/workbook.xml"))
    relaciones = ET.fromstring(contenido.read("xl/_rels/workbook.xml.rels"))
    destinos = {
        rel.get("Id"): rel.get("Target")
        for rel in relaciones.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    for hoja in workbook.findall(f".//{{{MAIN_NS}}}sheet"):
        if hoja.get("name") != nombre:
            continue
        rid = hoja.get(f"{{{REL_NS}}}id")
        destino = destinos.get(rid)
        if not destino:
            break
        destino = destino.lstrip("/")
        return destino if destino.startswith("xl/") else f"xl/{destino}"
    raise ErrorExcelControl("No se encuentra la hoja esperada en el libro.")


def _buscar_celda(fila: ET.Element, referencia: str) -> ET.Element | None:
    return next(
        (celda for celda in fila.findall(f"{{{MAIN_NS}}}c") if celda.get("r") == referencia),
        None,
    )


def _valor_numerico(celda: ET.Element | None, compartidas: list[str]) -> int | None:
    if celda is None:
        return None
    if celda.find(f"{{{MAIN_NS}}}f") is not None:
        raise ErrorExcelControl("Una celda de destino contiene una formula inesperada.")
    valor = _texto_celda(celda, compartidas).strip()
    if not valor:
        return None
    if celda.get("t") not in (None, "n"):
        raise ErrorExcelControl("Una celda de destino contiene un valor no numerico.")
    try:
        numero = int(float(valor))
    except ValueError as exc:
        raise ErrorExcelControl("Una celda de destino contiene un valor no numerico.") from exc
    if str(numero) != valor:
        raise ErrorExcelControl("Una celda de destino contiene un valor no entero.")
    return numero


def _crear_o_actualizar_celda(fila: ET.Element, columna: str, numero_fila: int, valor: int) -> None:
    referencia = f"{columna}{numero_fila}"
    celda = _buscar_celda(fila, referencia)
    if celda is None:
        celda = ET.Element(f"{{{MAIN_NS}}}c", {"r": referencia})
        columna_numero = _columna_numero(referencia)
        indice = len(fila)
        for i, existente in enumerate(list(fila)):
            if existente.tag != f"{{{MAIN_NS}}}c":
                indice = i
                break
            if _columna_numero(existente.get("r", "")) > columna_numero:
                indice = i
                break
        fila.insert(indice, celda)
    celda.attrib.pop("t", None)
    for hijo in list(celda):
        if hijo.tag in (f"{{{MAIN_NS}}}v", f"{{{MAIN_NS}}}is", f"{{{MAIN_NS}}}f"):
            celda.remove(hijo)
    elemento = ET.SubElement(celda, f"{{{MAIN_NS}}}v")
    elemento.text = str(valor)


def actualizar_excel_control(
    xlsx: bytes,
    *,
    numero_semana: int,
    etiqueta_responsable: str,
    teoria: int,
    laboratorio: int,
    seminario: int,
) -> bytes | None:
    """Rellena la semana solo si las celdas están vacías; None si ya coincide."""
    if numero_semana < 1:
        raise ErrorExcelControl("El numero de semana debe ser positivo.")
    if not etiqueta_responsable.strip():
        raise ErrorExcelControl("Falta la etiqueta de control configurada como secreto.")

    fila_numero = 11 + 10 * ((numero_semana - 1) // 2)
    columnas = (
        {"B": teoria, "C": laboratorio, "D": seminario}
        if numero_semana % 2
        else {"F": teoria, "G": laboratorio, "H": seminario}
    )
    try:
        origen = zipfile.ZipFile(io.BytesIO(xlsx))
    except zipfile.BadZipFile as exc:
        raise ErrorExcelControl("El archivo de control no es un libro xlsx valido.") from exc
    with origen:
        compartidas = _cargar_cadenas(origen)
        ruta = _ruta_hoja(origen, "Ordinario")
        workbook_xml = ET.fromstring(origen.read("xl/workbook.xml"))
        sheet_xml = ET.fromstring(origen.read(ruta))

        hoja_datos = sheet_xml.find(f"{{{MAIN_NS}}}sheetData")
        if hoja_datos is None:
            raise ErrorExcelControl("La hoja de control no contiene filas.")
        fila = next(
            (r for r in hoja_datos.findall(f"{{{MAIN_NS}}}row") if r.get("r") == str(fila_numero)),
            None,
        )
        if fila is None:
            raise ErrorExcelControl("No se encuentra la fila de la semana en la hoja de control.")

        celda_responsable = _buscar_celda(fila, f"A{fila_numero}")
        if celda_responsable is None or _texto_celda(celda_responsable, compartidas).strip().casefold() != etiqueta_responsable.strip().casefold():
            raise ErrorExcelControl("La fila de control no coincide con la etiqueta configurada.")

        existentes = {
            columna: _valor_numerico(_buscar_celda(fila, f"{columna}{fila_numero}"), compartidas)
            for columna in columnas
        }
        valores_esperados = dict(columnas)
        if existentes == valores_esperados:
            return None
        if any(valor is not None for valor in existentes.values()):
            raise ErrorExcelControl("Las celdas de la semana ya contienen datos distintos o parciales.")

        for columna, valor in columnas.items():
            _crear_o_actualizar_celda(fila, columna, fila_numero, valor)

        calculo = workbook_xml.find(f"{{{MAIN_NS}}}calcPr")
        if calculo is None:
            calculo = ET.Element(f"{{{MAIN_NS}}}calcPr")
            ext = workbook_xml.find(f"{{{MAIN_NS}}}extLst")
            workbook_xml.insert(list(workbook_xml).index(ext) if ext is not None else len(workbook_xml), calculo)
        calculo.set("fullCalcOnLoad", "1")
        calculo.set("forceFullCalc", "1")

        reemplazos = {
            "xl/workbook.xml": ET.tostring(workbook_xml, encoding="utf-8", xml_declaration=True),
            ruta: ET.tostring(sheet_xml, encoding="utf-8", xml_declaration=True),
        }
        destino = io.BytesIO()
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as salida:
            salida.comment = origen.comment
            for info in origen.infolist():
                salida.writestr(info, reemplazos.get(info.filename, origen.read(info.filename)))
        return destino.getvalue()
