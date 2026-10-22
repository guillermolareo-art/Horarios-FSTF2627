"""
Tests de merge_schedule.py contra el JSON REAL publicado en el repo
(data/fstf-2627.json, clonado de github.com/guillermolareo-art/Horarios-FSTF2627
en la auditoria de esta misma conversacion) -- no es un objeto de prueba
inventado, es el documento que de verdad sirve GitHub Pages ahora mismo.
"""
import json
import os
from datetime import date

import pytest

from scripts.merge_schedule import detectar_solapamientos, detectar_sesiones_perdidas, fusionar, validar_horas

RUTA_JSON_REAL = os.path.join(
    os.path.dirname(__file__), "..", "..", "repo_audit", "Horarios-FSTF2627", "data", "fstf-2627.json"
)

pytestmark = pytest.mark.skipif(not os.path.exists(RUTA_JSON_REAL), reason="Clon del repo no presente en esta maquina")


@pytest.fixture
def datos_reales():
    with open(RUTA_JSON_REAL, encoding="utf-8") as f:
        return json.load(f)


def test_el_json_real_del_repo_no_tiene_solapamientos_ni_horas_invalidas(datos_reales):
    # Primero una comprobacion de cordura sobre el dato real tal cual esta
    # publicado: si esto fallara, seria un hallazgo en si mismo.
    assert validar_horas(datos_reales["clases"]) == []
    assert detectar_solapamientos(datos_reales["clases"]) == []


def test_cambio_de_semana_archiva_la_saliente_en_historial(datos_reales):
    # datos_reales: semanaInicio 2026-10-12 (semana 7A), proximaSemana 8B.
    # Simulamos que llega la definitiva de la semana 8B (siguiente lunes).
    clases_8b = [
        {"dia": "Lunes", "inicio": "08:15", "fin": "09:05", "tipo": "TEORIA", "aula": "40", "grupos": "G1 (4 CGA-ST)"},
    ]
    resultado = fusionar(
        datos_reales,
        archivo_nuevo="SABANA_20261019_8B_FINAL.xlsm",
        actualizado_nuevo="2026-10-19",
        clases_nuevas=clases_8b,
        es_definitiva_nueva=True,
        semana_destino=date(2026, 10, 19),
        today_monday=date(2026, 10, 19),
        es_para_proxima_semana=False,
    )
    assert resultado.datos is not None
    # 7A (la saliente) debe quedar archivada; no estaba antes en el historial.
    semanas_historial = [h["semana"] for h in resultado.datos["historial"]]
    assert "7A" in semanas_historial
    assert resultado.datos["archivo"] == "SABANA_20261019_8B_FINAL.xlsm"
    assert resultado.datos["semanaInicio"] == "2026-10-19"
    assert resultado.datos["clases"] == clases_8b


def test_no_se_sustituye_una_definitiva_por_una_provisional_de_la_misma_semana(datos_reales):
    # proximaSemana real ya esta marcada provisional=True (8B), asi que
    # aqui forzamos el caso contrario: supongamos que ya fuera definitiva.
    datos = dict(datos_reales)
    datos["proximaSemana"] = dict(datos_reales["proximaSemana"])
    datos["proximaSemana"]["provisional"] = False
    resultado = fusionar(
        datos,
        archivo_nuevo="SABANA_20261013_8B_OTRA_PROVISIONAL.xlsm",
        actualizado_nuevo="2026-10-20",
        clases_nuevas=[{"dia": "Lunes", "inicio": "08:15", "fin": "09:05", "tipo": "TEORIA", "aula": "40", "grupos": "G1 (4 CGA-ST)"}],
        es_definitiva_nueva=False,
        semana_destino=date(2026, 10, 19),
        today_monday=date(2026, 10, 12),
        es_para_proxima_semana=True,
    )
    assert resultado.datos is None
    assert any("provisional" in p.lower() and "definitiv" in p.lower() for p in resultado.problemas)


def test_detecta_solapamiento_real_mismo_grupo_misma_aula_dos_veces():
    clases = [
        {"dia": "Lunes", "inicio": "09:00", "fin": "10:00", "tipo": "TEORIA", "aula": "40", "grupos": "G1 (4 CGA-ST)"},
        {"dia": "Lunes", "inicio": "09:30", "fin": "10:30", "tipo": "SEMINARIO", "aula": "40", "grupos": "G2 (4 CGA-ST)"},
    ]
    problemas = detectar_solapamientos(clases)
    assert len(problemas) == 1
    assert "Lunes" in problemas[0]


def test_desdoble_legitimo_mismo_horario_distinta_aula_sin_grupos_comunes_no_es_solapamiento():
    clases = [
        {"dia": "Lunes", "inicio": "09:00", "fin": "10:00", "tipo": "SEMINARIO", "aula": "40", "grupos": "G1 (4 CGA-ST)"},
        {"dia": "Lunes", "inicio": "09:00", "fin": "10:00", "tipo": "SEMINARIO", "aula": "45", "grupos": "G2 (4 CGA-ST)"},
    ]
    assert detectar_solapamientos(clases) == []


def test_sesion_perdida_se_detecta_entre_dos_versiones_de_la_misma_semana():
    previas = [{"dia": "Lunes", "inicio": "08:15", "fin": "09:05", "tipo": "TEORIA", "aula": "40", "grupos": "G1"}]
    nuevas = []  # desaparece sin dejar rastro
    avisos = detectar_sesiones_perdidas(previas, nuevas)
    assert len(avisos) == 1
    assert "08:15" in avisos[0]
