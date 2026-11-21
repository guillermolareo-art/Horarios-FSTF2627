"""Pruebas deterministas con identificadores y datos de correo sintéticos."""
from datetime import datetime, timezone, date

import pytest

from scripts.sabana_mail import (
    CorreoCandidato,
    SabanaAmbigua,
    candidatos_validos,
    clasificar,
    clasificar_definitiva_o_provisional,
    es_respuesta_de_hilo,
    semana_lunes,
    tiene_adjunto_real,
    ultima_por_semana_destino,
    EstadoProcesados,
    pendientes_de_procesar,
)

UTC = timezone.utc


def correo(**kw):
    base = dict(
        thread_id="t1",
        remitente="coordinacion.horarios.espacios@cud.uvigo.es",
        cuerpo_texto="",
        adjuntos=(),
    )
    base.update(kw)
    return CorreoCandidato(**base)


# --- semana_lunes: sabado->viernes, incluyendo el caso de "hoy es sabado/domingo" ---

@pytest.mark.parametrize(
    "d,esperado",
    [
        (date(2026, 9, 15), date(2026, 9, 14)),   # martes -> lunes de su propia semana
        (date(2026, 9, 14), date(2026, 9, 14)),   # lunes -> el mismo lunes
        (date(2026, 9, 19), date(2026, 9, 21)),   # sabado -> YA es la semana siguiente (empieza ese sabado)
        (date(2026, 9, 12), date(2026, 9, 14)),   # sabado 12/9 -> empieza la semana que arranca ese sabado
        (date(2026, 9, 13), date(2026, 9, 14)),   # domingo 13/9 -> misma semana que el sabado anterior
    ],
)
def test_semana_lunes_sabado_viernes(d, esperado):
    assert semana_lunes(d) == esperado


# --- clasificación de mensajes sintéticos ---

def test_correo_4b_provisional_es_candidato_valido_y_provisional():
    c = correo(
        message_id="synthetic-provisional",
        fecha_envio=datetime(2026, 9, 14, 17, 29, 2, tzinfo=UTC),
        asunto="Schedule notice 4B provisional",
        cuerpo_texto="Synthetic provisional schedule update.",
        adjuntos=("SABANA_20260914_4B_PROVISIONAL.xlsm",),
    )
    assert tiene_adjunto_real(c)
    sc = clasificar(c)
    assert sc.es_definitiva is False
    assert sc.semana_envio_lunes == date(2026, 9, 14)
    assert sc.semana_destino_lunes == date(2026, 9, 21)


def test_correo_3a_definitiva():
    c = correo(
        message_id="synthetic-definitive",
        fecha_envio=datetime(2026, 9, 11, 13, 6, 39, tzinfo=UTC),
        asunto="Schedule notice 3A definitive",
        cuerpo_texto="This version is marked final.",
        adjuntos=("SABANA_20260911_3A_FINAL.xlsm",),
    )
    sc = clasificar(c)
    assert sc.es_definitiva is True
    assert sc.semana_destino_lunes == date(2026, 9, 14)


def test_correo_3a_provisional_con_aulas():
    c = correo(
        message_id="synthetic-provisional-rooms",
        fecha_envio=datetime(2026, 9, 9, 17, 56, 56, tzinfo=UTC),
        asunto="Schedule notice 3A provisional with rooms",
        cuerpo_texto="Synthetic provisional schedule update with room data.",
        adjuntos=("SABANA_20260909_3A_PROVISIONAL_AULAS.xlsm",),
    )
    sc = clasificar(c)
    assert sc.es_definitiva is False
    assert sc.semana_destino_lunes == date(2026, 9, 14)


def test_adjunto_pdf_es_un_formato_admitido_y_se_clasifica():
    c = correo(
        message_id="pdf-candidate",
        fecha_envio=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
        asunto="Sábana provisional",
        adjuntos=("SABANA_20261120_13B_PROVISIONAL.pdf",),
    )
    assert tiene_adjunto_real(c)
    assert clasificar(c).formato == "pdf"


def test_respuesta_de_otro_profesor_se_descarta_aunque_tenga_remitente_similar():
    # Un remitente diferente respondiendo al hilo no cuenta como sábana nueva.
    c = correo(
        message_id="synthetic-reply",
        remitente="other.sender@example.test",
        fecha_envio=datetime(2026, 9, 10, 6, 57, 0, tzinfo=UTC),
        asunto="Re: Schedule notice 3A provisional",
        cuerpo_texto="Synthetic reply without a schedule attachment.",
        adjuntos=(),
    )
    assert es_respuesta_de_hilo(c) is True
    assert candidatos_validos([c]) == []


def test_aviso_de_error_sin_adjunto_se_descarta():
    c = correo(
        message_id="synthetic-notice",
        fecha_envio=datetime(2026, 9, 3, 12, 32, 42, tzinfo=UTC),
        asunto="Re: Schedule notice 2B",
        cuerpo_texto="Synthetic notice without an updated attachment.",
        adjuntos=(),
    )
    assert candidatos_validos([c]) == []


def test_reenvio_tras_error_si_cuenta_una_vez_tiene_adjunto_real():
    c = correo(
        message_id="synthetic-retry",
        fecha_envio=datetime(2026, 9, 3, 13, 26, 10, tzinfo=UTC),
        asunto="Re: Schedule notice 2B updated",
        cuerpo_texto="Synthetic updated schedule attachment.",
        adjuntos=("SABANA_20260903_2B_ACTUALIZACION2.xlsm",),
    )
    assert candidatos_validos([c]) == [c]
    sc = clasificar(c)
    assert sc.es_definitiva is False  # no dice "definitiva"/"final": no se asciende por defecto


def test_definitiva_y_provisional_a_la_vez_detiene_el_proceso():
    with pytest.raises(SabanaAmbigua):
        clasificar_definitiva_o_provisional(
            "Schedule final and provisional",
            "The schedule is marked final and provisional.",
        )


def test_una_respuesta_citada_no_vuelve_ambiguo_el_estado_del_adjunto_actual():
    c = correo(
        message_id="quoted-status",
        fecha_envio=datetime(2026, 11, 20, 14, 0, tzinfo=UTC),
        asunto="Schedule provisional updated",
        cuerpo_texto=(
            "Synthetic current update.\n\n"
            "-----Mensaje original-----\n"
            "The previous version was final."
        ),
        adjuntos=("SABANA_20261118_13B_PROVISIONAL.xlsm",),
    )
    assert clasificar(c).es_definitiva is False


def test_contradiccion_en_el_mensaje_actual_sigue_requiriendo_revision():
    with pytest.raises(SabanaAmbigua):
        clasificar_definitiva_o_provisional(
            "Schedule definitive",
            "Synthetic provisional update.",
        )


def test_dos_adjuntos_en_el_mismo_correo_es_ambiguo_y_detiene_el_proceso():
    c = correo(
        message_id="x1",
        fecha_envio=datetime(2026, 9, 14, 17, 29, 2, tzinfo=UTC),
        asunto="Schedule week 4B",
        cuerpo_texto="provisional",
        adjuntos=("SABANA_A.xlsm", "SABANA_B.xlsx"),
    )
    with pytest.raises(SabanaAmbigua):
        clasificar(c)


def test_misma_semana_destino_se_queda_con_el_envio_mas_reciente():
    # Varias revisiones para una misma semana de destino.
    c1 = clasificar(correo(
        message_id="m1", fecha_envio=datetime(2026, 9, 7, 15, 19, 50, tzinfo=UTC),
        asunto="Schedule week 3A", cuerpo_texto="First provisional version.",
        adjuntos=("SABANA_20260907_3A_PROVISIONAL.xlsm",),
    ))
    c2 = clasificar(correo(
        message_id="m2", fecha_envio=datetime(2026, 9, 9, 17, 56, 56, tzinfo=UTC),
        asunto="Schedule provisional 3A with rooms", cuerpo_texto="Provisional update with rooms.",
        adjuntos=("SABANA_20260909_3A_PROVISIONAL_AULAS.xlsm",),
    ))
    c3 = clasificar(correo(
        message_id="m3", fecha_envio=datetime(2026, 9, 11, 13, 6, 39, tzinfo=UTC),
        asunto="Schedule definitive", cuerpo_texto="Final schedule version.",
        adjuntos=("SABANA_20260911_3A_FINAL.xlsm",),
    ))
    resultado = ultima_por_semana_destino([c1, c2, c3])
    assert len(resultado) == 1
    ganadora = resultado[date(2026, 9, 14)]
    assert ganadora.message_id == "m3"
    assert ganadora.es_definitiva is True


def test_deduplicacion_no_reprocesa_el_mismo_mensaje():
    estado = EstadoProcesados()
    sc = clasificar(correo(
        message_id="dup1", fecha_envio=datetime(2026, 9, 11, 13, 6, 39, tzinfo=UTC),
        asunto="[pdi] Sábana definitiva", cuerpo_texto="se va a publicar",
        adjuntos=("SABANA_20260911_3A_FINAL.xlsm",),
    ))
    pendientes = pendientes_de_procesar([sc], estado)
    assert pendientes == [sc]
    estado.marcar_procesado(sc.message_id)
    assert pendientes_de_procesar([sc], estado) == []
    # Y el estado sobrevive un ciclo de guardar/cargar como JSON (igual que se
    # guardaria como artefacto o fichero en el repo entre ejecuciones de Actions).
    estado2 = EstadoProcesados.from_json(estado.to_json())
    assert pendientes_de_procesar([sc], estado2) == []
