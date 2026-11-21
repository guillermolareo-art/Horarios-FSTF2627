from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.week_rollover import cerrar_semana_si_corresponde

MADRID = ZoneInfo("Europe/Madrid")


def _datos():
    return {
        "archivo": "SABANA_20261113_12A_FINAL.xlsm",
        "actualizado": "2026-11-13",
        "semanaInicio": "2026-11-16",
        "historial": [],
        "clases": [
            {"dia": "Viernes", "inicio": "10:20", "fin": "11:10", "tipo": "SEMINARIO", "aula": 56, "grupos": "G2"},
            {"dia": "Viernes", "inicio": "12:10", "fin": "13:00", "tipo": "TEORIA", "aula": 45, "grupos": "G3", "propia": False},
        ],
        "proximaSemana": {
            "archivo": "SABANA_20261118_13B_PROVISIONAL.xlsm",
            "actualizado": "2026-11-18",
            "semanaInicio": "2026-11-23",
            "provisional": True,
            "clases": [
                {"dia": "Lunes", "inicio": "08:15", "fin": "09:05", "tipo": "TEORIA", "aula": 40, "grupos": "G1"},
            ],
        },
    }


def test_no_promueve_antes_de_terminar_la_ultima_clase():
    original = _datos()
    salida, promovida = cerrar_semana_si_corresponde(
        original, datetime(2026, 11, 20, 10, 30, tzinfo=MADRID)
    )
    assert not promovida
    assert salida is original


def test_promueve_al_terminar_clases_y_archiva_la_semana_saliente():
    original = _datos()
    salida, promovida = cerrar_semana_si_corresponde(
        original, datetime(2026, 11, 20, 13, 0, tzinfo=MADRID)
    )
    assert promovida
    assert salida["semanaInicio"] == "2026-11-23"
    assert salida["provisional"] is True
    assert salida["proximaSemana"] is None
    assert salida["historial"] == [
        {"semana": "12A", "teoria": 0, "seminario": 1, "laboratorio": 0}
    ]
    assert original["semanaInicio"] == "2026-11-16"


def test_el_fin_de_semana_promueve_aunque_no_haya_clases_programadas():
    datos = _datos()
    datos["clases"] = []
    salida, promovida = cerrar_semana_si_corresponde(
        datos, datetime(2026, 11, 21, 8, 0, tzinfo=MADRID)
    )
    assert promovida
    assert salida["semanaInicio"] == "2026-11-23"


def test_no_promueve_si_no_puede_archivar_el_codigo_de_la_semana():
    datos = _datos()
    datos["archivo"] = "horario.xlsm"
    with pytest.raises(ValueError, match="falta su codigo"):
        cerrar_semana_si_corresponde(datos, datetime(2026, 11, 21, 8, 0, tzinfo=MADRID))
