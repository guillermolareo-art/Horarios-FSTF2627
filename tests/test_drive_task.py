import pytest

from scripts.drive_task import (
    _hash_horario,
    _necesita_pdf,
    _pendientes_excel,
    _semana_numero,
    _validar_excel_existente,
)


def test_identifica_semanas_pendientes_tras_la_ultima_version_excel():
    datos = {
        "historial": [
            {"semana": "10B", "teoria": 4, "laboratorio": 0, "seminario": 2},
            {"semana": "11A", "teoria": 6, "laboratorio": 1, "seminario": 0},
            {"semana": "12B", "teoria": 2, "laboratorio": 4, "seminario": 1},
        ]
    }
    archivos = [{
        "name": "Plantilla Control firma FSTF 1 cuat 2026-2027 s11.xlsx",
        "id": "test-id",
    }]
    assert _pendientes_excel(datos, archivos) == [(12, datos["historial"][2])]
    assert _semana_numero("12B") == 12
    assert _semana_numero("sin-codigo") is None


def test_pdf_se_actualiza_solo_si_cambia_el_hash_del_horario():
    datos = {"archivo": "SABANA_20261120_13B_FINAL.xlsm", "clases": []}
    nombre = "Horario_FABRIC_Semana13B.pdf"
    assert _necesita_pdf(datos, [])[0]
    assert not _necesita_pdf(
        datos,
        [{"name": nombre, "id": "pdf-id", "appProperties": {"scheduleHash": _hash_horario(datos)}}],
    )[0]
    with pytest.raises(ValueError, match="varias copias"):
        _necesita_pdf(datos, [{"name": nombre}, {"name": nombre}])


def test_hay_que_configurar_excel_base_antes_de_actualizar_historial():
    with pytest.raises(ValueError, match="version numerada"):
        _pendientes_excel({"historial": [{"semana": "1A"}]}, [])


def test_rechaza_versiones_excel_duplicadas():
    datos = {"historial": [{"semana": "1A"}]}
    archivos = [
        {"name": "Plantilla Control firma FSTF 1 cuat 2026-2027 s1.xlsx"},
        {"name": "Plantilla Control firma FSTF 1 cuat 2026-2027 s01.xlsx"},
    ]
    with pytest.raises(ValueError, match="varias versiones"):
        _pendientes_excel(datos, archivos)


def test_solo_valida_en_excel_las_semanas_hasta_la_version_base(monkeypatch):
    semanas_validadas = []

    def actualizar(*_args, numero_semana, **_kwargs):
        semanas_validadas.append(numero_semana)
        return None if numero_semana == 11 else b"actualizacion pendiente"

    monkeypatch.setattr("scripts.drive_task.actualizar_excel_control", actualizar)
    _validar_excel_existente(
        b"excel-base",
        [
            {"semana": "11B", "teoria": 1, "laboratorio": 2, "seminario": 3},
            {"semana": "12A", "teoria": 4, "laboratorio": 5, "seminario": 6},
        ],
        "Responsable",
        numero_maximo=11,
    )
    assert semanas_validadas == [11]
