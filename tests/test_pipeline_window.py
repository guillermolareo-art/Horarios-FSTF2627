import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import scripts.pipeline as pipeline
from scripts.pipeline import dentro_ventana_de_ejecucion
from scripts.merge_schedule import fusionar

MADRID = ZoneInfo("Europe/Madrid")


@pytest.mark.parametrize(
    "ahora,esperado",
    [
        # Ventana ampliada el 27/11/2026: el lunes ya abre a las 08:00, para
        # recoger antes de las clases lo que haya llegado el fin de semana.
        (datetime(2026, 11, 23, 7, 59, tzinfo=MADRID), False),
        (datetime(2026, 11, 23, 8, 0, tzinfo=MADRID), True),
        (datetime(2026, 11, 23, 12, 0, tzinfo=MADRID), True),
        (datetime(2026, 11, 24, 8, 0, tzinfo=MADRID), True),
        (datetime(2026, 11, 24, 21, 0, tzinfo=MADRID), True),
        (datetime(2026, 11, 24, 21, 1, tzinfo=MADRID), False),
        # El viernes ya no cierra a las 12:00: las definitivas de la semana
        # siguiente llegan a menudo el viernes por la mañana o mas tarde.
        (datetime(2026, 11, 27, 12, 0, tzinfo=MADRID), True),
        (datetime(2026, 11, 27, 12, 1, tzinfo=MADRID), True),
        (datetime(2026, 11, 27, 21, 0, tzinfo=MADRID), True),
        (datetime(2026, 11, 27, 21, 1, tzinfo=MADRID), False),
        (datetime(2026, 11, 28, 10, 0, tzinfo=MADRID), False),
    ],
)
def test_ventana_lectiva_y_cambio_horario(ahora, esperado):
    assert dentro_ventana_de_ejecucion(ahora) is esperado


@pytest.mark.parametrize("semana_promovida", [False, True])
def test_sin_sabana_nueva_no_emite_salida_de_notificacion(
    tmp_path, monkeypatch, semana_promovida
):
    ruta_datos = tmp_path / "schedule.json"
    datos = {"semanaInicio": "2026-11-16", "clases": []}
    ruta_datos.write_text(json.dumps(datos), encoding="utf-8")
    salida = tmp_path / "github-output.txt"
    monkeypatch.setattr(pipeline, "RUTA_DATOS", ruta_datos)
    monkeypatch.setattr(pipeline, "RUTA_ESTADO", tmp_path / "state.json")
    monkeypatch.setattr(
        pipeline,
        "cerrar_semana_si_corresponde",
        lambda actual, ahora: (actual, semana_promovida),
    )
    monkeypatch.setattr(pipeline, "obtener_servicio", lambda: object())
    monkeypatch.setattr(pipeline, "listar_candidatos", lambda servicio: [])
    monkeypatch.setattr(pipeline, "candidatos_validos", lambda candidatos: [])
    monkeypatch.setattr(pipeline, "pendientes_de_procesar", lambda correos, estado: [])
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_OUTPUT", str(salida))

    resultado = pipeline.ejecutar(hoy=date(2026, 11, 20))

    assert resultado is semana_promovida
    assert "sabana_aplicada=false" in salida.read_text(encoding="utf-8")


def test_sabana_aceptada_emite_salida_para_notificacion(tmp_path, monkeypatch):
    ruta_datos = tmp_path / "schedule.json"
    datos = {"semanaInicio": "2026-11-16", "clases": []}
    ruta_datos.write_text(json.dumps(datos), encoding="utf-8")
    salida = tmp_path / "github-output.txt"
    fecha_semana = date(2026, 11, 16)
    candidato = SimpleNamespace(message_id="synthetic-message")
    sabana = SimpleNamespace(
        message_id="synthetic-message",
        archivo="SABANA_20261119_10A_FINAL.xlsx",
        formato="xlsx",
        fecha_envio=datetime(2026, 11, 19, tzinfo=timezone.utc),
        es_definitiva=True,
        semana_destino_lunes=fecha_semana,
    )
    monkeypatch.setattr(pipeline, "RUTA_DATOS", ruta_datos)
    monkeypatch.setattr(pipeline, "RUTA_ESTADO", tmp_path / "state.json")
    monkeypatch.setattr(pipeline, "cerrar_semana_si_corresponde", lambda actual, ahora: (actual, False))
    monkeypatch.setattr(pipeline, "semana_lunes", lambda hoy: fecha_semana)
    monkeypatch.setattr(pipeline, "obtener_servicio", lambda: object())
    monkeypatch.setattr(pipeline, "listar_candidatos", lambda servicio: [(candidato, "message")])
    monkeypatch.setattr(pipeline, "candidatos_validos", lambda candidatos: [candidato])
    monkeypatch.setattr(pipeline, "clasificar", lambda candidato: sabana)
    monkeypatch.setattr(pipeline, "pendientes_de_procesar", lambda correos, estado: [sabana])
    monkeypatch.setattr(
        pipeline,
        "ultima_por_semana_destino",
        lambda pendientes: {fecha_semana: sabana},
    )
    monkeypatch.setattr(pipeline, "id_de_adjunto", lambda mensaje, archivo: "synthetic-attachment")
    monkeypatch.setattr(pipeline, "descargar_adjunto", lambda *args: b"synthetic")
    monkeypatch.setattr(pipeline, "parse_fabric", lambda ruta: [])
    monkeypatch.setattr(pipeline, "agrupar", lambda clases, **kwargs: ([{"tipo": "TEORIA"}], []))
    monkeypatch.setattr(
        pipeline,
        "fusionar",
        lambda *args, **kwargs: SimpleNamespace(
            datos={"semanaInicio": fecha_semana.isoformat(), "clases": [{"tipo": "TEORIA"}]},
            problemas=[],
            bloqueo_es_error=False,
        ),
    )
    monkeypatch.setattr(pipeline, "guardar_estado", lambda estado: None)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_OUTPUT", str(salida))

    assert pipeline.ejecutar(hoy=date(2026, 11, 20)) is True
    assert "sabana_aplicada=true" in salida.read_text(encoding="utf-8")


def test_fusiona_semana_actual_si_proxima_semana_es_null():
    datos = {
        "historial": [],
        "archivo": "SABANA_20261116_12A_PROVISIONAL.xlsm",
        "actualizado": "2026-11-16",
        "provisional": True,
        "semanaInicio": "2026-11-16",
        "clases": [],
        "proximaSemana": None,
    }
    clases = [{
        "dia": "Viernes",
        "inicio": "08:15",
        "fin": "09:05",
        "tipo": "TEORIA",
        "aula": 40,
        "grupos": "G1",
    }]
    resultado = fusionar(
        datos,
        archivo_nuevo="SABANA_20261120_13B_FINAL.xlsm",
        actualizado_nuevo="2026-11-20",
        clases_nuevas=clases,
        es_definitiva_nueva=True,
        semana_destino=date(2026, 11, 20),
        today_monday=date(2026, 11, 16),
        es_para_proxima_semana=False,
    )
    assert resultado.datos is not None
    assert resultado.datos["proximaSemana"] is None
