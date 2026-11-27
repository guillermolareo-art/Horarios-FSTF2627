"""
Tests del recuento semanal de horas (_contar_por_tipo de scripts/merge_schedule.py).

Autocontenidos a proposito: no dependen de ningun clon externo del repo, para que
no se salten en silencio como los de test_merge_schedule.py cuando esa ruta no
existe. Fijan la regla acordada con el autor el 19/11/2026, despues de detectar
que la semana 10B se habia archivado con 4 horas de laboratorio en vez de 8.

El equivalente en JavaScript esta en tests/schedule-model.test.mjs: las dos
implementaciones tienen que dar siempre lo mismo.
"""
from scripts.merge_schedule import _clave_recuento, _contar_por_tipo


def _lab(dia, inicio, fin, grupos, aula=50):
    return {"dia": dia, "inicio": inicio, "fin": fin, "tipo": "LABORATORIO", "aula": aula, "grupos": grupos}


def test_bloque_de_horas_seguidas_el_mismo_dia_cuenta_todas_las_horas():
    # Un laboratorio de dos horas seguidas con los mismos grupos son dos horas
    # reales. Es el caso que se contaba mal: la version anterior descartaba la
    # segunda fila por "grupos ya vistos".
    clases = [
        _lab("Lunes", "14:35", "15:25", "G3 (4 CGA-ST), G4 (4 CGA-ST)"),
        _lab("Lunes", "15:30", "16:20", "G3 (4 CGA-ST), G4 (4 CGA-ST)"),
    ]
    assert _contar_por_tipo(clases)["laboratorio"] == 2


def test_el_mismo_grupo_repetido_en_otro_dia_solo_cuenta_una_vez():
    clases = [
        {"dia": "Martes", "inicio": "16:25", "fin": "17:15", "tipo": "SEMINARIO", "grupos": "IM1 (4 CIM-ST)"},
        {"dia": "Jueves", "inicio": "08:15", "fin": "09:05", "tipo": "SEMINARIO", "grupos": "IM1 (4 CIM-ST)"},
    ]
    assert _contar_por_tipo(clases)["seminario"] == 1


def test_dos_aulas_a_la_misma_hora_son_una_sola_hora():
    # Una persona no puede estar en dos aulas a la vez: la franja cuenta una vez.
    clases = [
        _lab("Martes", "14:35", "15:25", "IM1 (4 CIM-ST), IM2 (4 CIM-ST)", aula=50),
        _lab("Martes", "14:35", "15:25", "Cadete 1", aula=45),
    ]
    assert _contar_por_tipo(clases)["laboratorio"] == 1


def test_no_cuenta_las_sesiones_marcadas_como_de_otro_profesor():
    clases = [
        _lab("Lunes", "14:35", "15:25", "G1 (4 CGA-ST)"),
        dict(_lab("Lunes", "15:30", "16:20", "G1 (4 CGA-ST)"), propia=False),
    ]
    assert _contar_por_tipo(clases)["laboratorio"] == 1


def test_examen_parcial_cuenta_como_teoria_y_el_final_no():
    assert _clave_recuento("EX. PARCIAL") == "teoria"
    assert _clave_recuento("EXAMEN PARCIAL") == "teoria"
    assert _clave_recuento("EX. FINAL") is None
    assert _clave_recuento("EXAMEN FINAL") is None
    clases = [
        {"dia": "Jueves", "inicio": "08:15", "fin": "09:05", "tipo": "EX. PARCIAL", "grupos": "G1 (4 CGA-ST)"},
        {"dia": "Jueves", "inicio": "09:10", "fin": "10:00", "tipo": "EX. FINAL", "grupos": "G1 (4 CGA-ST)"},
    ]
    assert _contar_por_tipo(clases) == {"teoria": 1, "seminario": 0, "laboratorio": 0}


def test_semana_10B_real_da_ocho_horas_de_laboratorio():
    # Las ocho filas de laboratorio que tenia la semana 10B tal y como las
    # importo el pipeline. Quedo archivada con 4; son 8.
    clases = [
        _lab("Lunes", "14:35", "15:25", "IM1 (4 CIM-ST), IM2 (4 CIM-ST), Cadete 1"),
        _lab("Lunes", "15:30", "16:20", "IM1 (4 CIM-ST), IM2 (4 CIM-ST), Cadete 1"),
        _lab("Lunes", "16:25", "17:15", "G1 (4 CGA-ST), G2 (4 CGA-ST), Cadete 3"),
        _lab("Lunes", "17:20", "18:10", "G1 (4 CGA-ST), G2 (4 CGA-ST), Cadete 3"),
        _lab("Miércoles", "11:15", "12:05", "G3 (4 CGA-ST), G4 (4 CGA-ST)", aula=18),
        _lab("Miércoles", "12:10", "13:00", "G3 (4 CGA-ST), G4 (4 CGA-ST)", aula=18),
        _lab("Miércoles", "16:25", "17:15", "G5 (4 CGA-ST), G6 (4 CGA-ST), Cadete 2", aula=43),
        _lab("Miércoles", "17:20", "18:10", "G5 (4 CGA-ST), G6 (4 CGA-ST), Cadete 2", aula=43),
    ]
    assert _contar_por_tipo(clases)["laboratorio"] == 8


def test_la_teoria_repetida_en_la_semana_cuenta_cada_hora():
    clases = [
        {"dia": "Lunes", "inicio": "08:15", "fin": "09:05", "tipo": "TEORIA", "grupos": "G1 (4 CGA-ST)"},
        {"dia": "Miércoles", "inicio": "10:20", "fin": "11:10", "tipo": "TEORIA", "grupos": "G1 (4 CGA-ST)"},
        {"dia": "Viernes", "inicio": "08:15", "fin": "09:05", "tipo": "TEORIA", "grupos": "G1 (4 CGA-ST)"},
    ]
    assert _contar_por_tipo(clases)["teoria"] == 3
