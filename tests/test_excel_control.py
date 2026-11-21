import io
import zipfile

import pytest

from scripts.excel_control import ErrorExcelControl, actualizar_excel_control


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _libro(semana=1, valores=None, etiqueta="RESPONSABLE DE PRUEBA"):
    fila = 11 + 10 * ((semana - 1) // 2)
    columnas = ("B", "C", "D") if semana % 2 else ("F", "G", "H")
    valores = valores or {}
    celdas = f'<c r="A{fila}" t="s"><v>0</v></c>'
    for columna in columnas:
        valor = valores.get(columna)
        celdas += f'<c r="{columna}{fila}"><v>{valor}</v></c>' if valor is not None else f'<c r="{columna}{fila}" s="1"/>'

    archivos = {
        "xl/workbook.xml": (
            f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>'
            '<sheet name="Ordinario" sheetId="2" r:id="rId3"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            f'<Relationships xmlns="{PKG_REL}">'
            '<Relationship Id="rId3" Target="worksheets/sheet2.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
            "</Relationships>"
        ),
        "xl/sharedStrings.xml": (
            f'<sst xmlns="{MAIN}" count="1" uniqueCount="1">'
            f"<si><t>{etiqueta}</t></si></sst>"
        ),
        "xl/worksheets/sheet2.xml": (
            f'<worksheet xmlns="{MAIN}"><sheetData><row r="{fila}">{celdas}'
            f"</row></sheetData></worksheet>"
        ),
        "custom/untouched.xml": "<untouched/>",
    }
    destino = io.BytesIO()
    with zipfile.ZipFile(destino, "w") as archivo:
        for nombre, contenido in archivos.items():
            archivo.writestr(nombre, contenido)
    return destino.getvalue()


def _leer_celdas(xlsx, semana):
    fila = 11 + 10 * ((semana - 1) // 2)
    with zipfile.ZipFile(io.BytesIO(xlsx)) as archivo:
        contenido = archivo.read("xl/worksheets/sheet2.xml").decode()
    import re

    return {
        columna: re.search(rf'<c r="{columna}{fila}"[^>]*><v>(.*?)</v></c>', contenido).group(1)
        for columna in (("B", "C", "D") if semana % 2 else ("F", "G", "H"))
    }


def test_actualiza_semana_impar_y_preserva_archivos_no_tocados():
    salida = actualizar_excel_control(
        _libro(), numero_semana=1, etiqueta_responsable="RESPONSABLE DE PRUEBA",
        teoria=4, laboratorio=2, seminario=3,
    )
    assert salida is not None
    assert _leer_celdas(salida, 1) == {"B": "4", "C": "2", "D": "3"}
    with zipfile.ZipFile(io.BytesIO(salida)) as archivo:
        assert archivo.read("custom/untouched.xml") == b"<untouched/>"
        assert b'fullCalcOnLoad="1"' in archivo.read("xl/workbook.xml")


def test_actualiza_semana_par_en_sus_columnas():
    salida = actualizar_excel_control(
        _libro(semana=2), numero_semana=2, etiqueta_responsable="RESPONSABLE DE PRUEBA",
        teoria=5, laboratorio=1, seminario=7,
    )
    assert _leer_celdas(salida, 2) == {"F": "5", "G": "1", "H": "7"}


def test_no_reescribe_si_los_datos_ya_coinciden():
    assert actualizar_excel_control(
        _libro(valores={"B": 4, "C": 2, "D": 3}), numero_semana=1,
        etiqueta_responsable="RESPONSABLE DE PRUEBA", teoria=4, laboratorio=2, seminario=3,
    ) is None


def test_rechaza_conflictos_o_etiqueta_de_fila_incorrecta():
    with pytest.raises(ErrorExcelControl, match="distintos o parciales"):
        actualizar_excel_control(
            _libro(valores={"B": 4}), numero_semana=1,
            etiqueta_responsable="RESPONSABLE DE PRUEBA", teoria=4, laboratorio=2, seminario=3,
        )
    with pytest.raises(ErrorExcelControl, match="no coincide"):
        actualizar_excel_control(
            _libro(), numero_semana=1, etiqueta_responsable="OTRA ETIQUETA",
            teoria=4, laboratorio=2, seminario=3,
        )
