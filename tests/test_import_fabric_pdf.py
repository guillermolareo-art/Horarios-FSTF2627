import pytest

from scripts.import_fabric import ErrorImportacion
from scripts.import_fabric_pdf import _leer_tabla


def _tabla_pdf(fin_primera="09:05"):
    return [
        ["", "", "Grupo", "", "G1 (curso)"],
        ["Lunes", "", "08:15", "", ""],
        ["", "", "", "", "TEORIA"],
        ["", "", "", "", "FABRIC"],
        ["", "", fin_primera, "", "40"],
        ["", "", "", "", ""],
        ["", "", "09:55", "", "TEORIA"],
        ["", "", "", "", "FABRIC"],
        ["", "", "10:45", "", "45"],
    ]


def test_lee_dos_franjas_y_conserva_dia_horas_tipo_y_aula():
    clases = _leer_tabla(_tabla_pdf())
    assert [(c.dia, c.inicio, c.fin, c.tipo, c.aula) for c in clases] == [
        ("Lunes", "08:15", "09:05", "TEORIA", 40),
        ("Lunes", "09:55", "10:45", "TEORIA", 45),
    ]


def test_rechaza_hora_fin_que_es_en_realidad_el_inicio_siguiente():
    with pytest.raises(ErrorImportacion, match="horas ambiguas"):
        _leer_tabla(_tabla_pdf(fin_primera="09:55"))
