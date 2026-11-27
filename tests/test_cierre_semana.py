"""
Tests del cierre de semana y de la ventana de ejecucion del pipeline.

Fijan los dos fallos que dejaron de publicar actualizaciones en noviembre de
2026, para que no vuelvan:

  - La semana se cerraba en cuanto acababa la ULTIMA CLASE DE FSTF, no al
    acabar la semana lectiva. El miercoles 25 a las 12:05 acabo la ultima
    sesion de la 13B y esa misma tarde la 14A -- que empezaba el 30 -- paso a
    ser la semana actual.
  - La ventana de ejecucion cerraba el viernes a las 12:00 y no abria hasta el
    lunes a las 12:00, justo cuando llegan las sabanas definitivas de la
    semana siguiente.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.pipeline import dentro_ventana_de_ejecucion
from scripts.week_rollover import cerrar_semana_si_corresponde

TZ = ZoneInfo("Europe/Madrid")


def _datos():
    """Semana 13B (lunes 23/11) con la 14A (lunes 30/11) ya en proximaSemana.
    La ultima sesion de la 13B termina el miercoles a las 12:05."""
    return {
        "archivo": "SABANA_20261119_13B_PROVISIONAL.xlsm",
        "actualizado": "2026-11-19",
        "semanaInicio": "2026-11-23",
        "historial": [],
        "clases": [
            {"dia": "Lunes", "inicio": "14:35", "fin": "15:25", "tipo": "LABORATORIO",
             "aula": 50, "grupos": "G3 (4 CGA-ST)"},
            {"dia": "Miércoles", "inicio": "11:15", "fin": "12:05", "tipo": "TEORIA",
             "aula": 45, "grupos": "G5 (4 CGA-ST)"},
        ],
        "proximaSemana": {
            "archivo": "SABANA_20261124_14A_PROVISIONAL.xlsm",
            "actualizado": "2026-11-24",
            "provisional": True,
            "semanaInicio": "2026-11-30",
            "clases": [
                {"dia": "Martes", "inicio": "10:20", "fin": "11:10", "tipo": "TEORIA",
                 "aula": 40, "grupos": "G1 (4 CGA-ST)"},
            ],
        },
    }


def test_no_cierra_la_semana_al_acabar_la_ultima_clase_de_la_asignatura():
    # Miercoles por la tarde, con la ultima sesion de FSTF ya dada: la semana
    # lectiva sigue, asi que la 13B tiene que seguir siendo la actual.
    datos, promovida = cerrar_semana_si_corresponde(
        _datos(), datetime(2026, 11, 25, 17, 25, tzinfo=TZ)
    )
    assert promovida is False
    assert datos["semanaInicio"] == "2026-11-23"
    assert datos["proximaSemana"] is not None


def test_el_viernes_ya_cerrado_el_horario_si_promueve():
    # El viernes, con la docencia de la semana ya terminada, adelantar la vista
    # a la semana siguiente si es util: es el comportamiento que se quiso
    # originalmente y que se conserva. Lo que no vale es hacerlo antes del
    # viernes solo porque la ultima clase de FSTF caiga en miercoles.
    _, promovida = cerrar_semana_si_corresponde(
        _datos(), datetime(2026, 11, 27, 20, 0, tzinfo=TZ)
    )
    assert promovida is True


def test_cierra_al_llegar_el_sabado():
    # Sabado 28: empieza la semana academica siguiente (regla sabado->viernes).
    datos, promovida = cerrar_semana_si_corresponde(
        _datos(), datetime(2026, 11, 28, 9, 0, tzinfo=TZ)
    )
    assert promovida is True
    assert datos["semanaInicio"] == "2026-11-30"
    assert datos["archivo"] == "SABANA_20261124_14A_PROVISIONAL.xlsm"
    assert datos["proximaSemana"] is None
    assert [h["semana"] for h in datos["historial"]] == ["13B"]


def test_la_ventana_cubre_el_viernes_por_la_tarde():
    # La definitiva de la 14A llego un viernes a las 11:14; con la ventana
    # anterior (que cerraba a las 12:00) solo quedaba una ejecucion para
    # cogerla antes del lunes.
    assert dentro_ventana_de_ejecucion(datetime(2026, 11, 27, 11, 20, tzinfo=TZ)) is True
    assert dentro_ventana_de_ejecucion(datetime(2026, 11, 27, 16, 20, tzinfo=TZ)) is True
    assert dentro_ventana_de_ejecucion(datetime(2026, 11, 27, 20, 20, tzinfo=TZ)) is True


def test_la_ventana_abre_el_lunes_por_la_mañana():
    # Una sabana que llegue el fin de semana tiene que entrar el lunes antes
    # de las clases, no a mediodia.
    assert dentro_ventana_de_ejecucion(datetime(2026, 11, 30, 8, 20, tzinfo=TZ)) is True
    assert dentro_ventana_de_ejecucion(datetime(2026, 11, 30, 9, 20, tzinfo=TZ)) is True


def test_la_ventana_sigue_cerrada_de_madrugada_y_en_fin_de_semana():
    assert dentro_ventana_de_ejecucion(datetime(2026, 11, 30, 6, 20, tzinfo=TZ)) is False
    assert dentro_ventana_de_ejecucion(datetime(2026, 11, 28, 10, 20, tzinfo=TZ)) is False
    assert dentro_ventana_de_ejecucion(datetime(2026, 11, 29, 10, 20, tzinfo=TZ)) is False
