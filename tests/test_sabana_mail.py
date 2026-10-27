"""
Tests contra correos REALES del buzon institucional de coordinacion de
horarios (recogidos con mcp__Gmail__search_threads / get_message en la
auditoria de una sesion anterior, semanas 2B/3A/4B de septiembre 2026). No
son datos sinteticos inventados: son el asunto, fecha y nombre de adjunto
reales de cada mensaje, tal como los devolvio Gmail.

Lo que SI esta sustituido, a proposito, son los datos de personas concretas.
Este repositorio es publico: la direccion de un companero y el texto de su
correo no son del autor para publicarlos. Donde hace falta un remitente que
no sea el esperado, se usa una direccion ficticia del mismo dominio.
"""
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


# --- clasificacion real: los 9 correos de la auditoria de septiembre 2026 ---

def test_correo_4b_provisional_es_candidato_valido_y_provisional():
    c = correo(
        message_id="1a0a0f75858c52db",
        fecha_envio=datetime(2026, 9, 14, 17, 29, 2, tzinfo=UTC),
        asunto="[pdi] Sábana semana 4B",
        cuerpo_texto="Adjunto sábana de la semana que viene en versión provisional con las aulas sin asignar.",
        adjuntos=("SABANA_20260914_4B_PROVISIONAL.xlsm",),
    )
    assert tiene_adjunto_real(c)
    sc = clasificar(c)
    assert sc.es_definitiva is False
    assert sc.semana_envio_lunes == date(2026, 9, 14)
    assert sc.semana_destino_lunes == date(2026, 9, 21)


def test_correo_3a_definitiva():
    c = correo(
        message_id="1a090940bc2f676e",
        fecha_envio=datetime(2026, 9, 11, 13, 6, 39, tzinfo=UTC),
        asunto="[pdi] Sábana definitiva",
        cuerpo_texto="Adjunto la versión que se va a publicar en la orden del lunes.",
        adjuntos=("SABANA_20260911_3A_FINAL.xlsm",),
    )
    sc = clasificar(c)
    assert sc.es_definitiva is True
    assert sc.semana_destino_lunes == date(2026, 9, 14)


def test_correo_3a_provisional_con_aulas():
    c = correo(
        message_id="1a087510d75a7436",
        fecha_envio=datetime(2026, 9, 9, 17, 56, 56, tzinfo=UTC),
        asunto="[pdi] Sábana provisional 3A con aulas",
        cuerpo_texto="Adjunto sábana provisional con los cambios remitidos desde el lunes, y con aulas ya asignadas.",
        adjuntos=("SABANA_20260909_3A_PROVISIONAL_AULAS.xlsm",),
    )
    sc = clasificar(c)
    assert sc.es_definitiva is False
    assert sc.semana_destino_lunes == date(2026, 9, 14)


def test_respuesta_de_otro_profesor_se_descarta_aunque_tenga_remitente_similar():
    # Otro profesor respondiendo al hilo: no es el remitente esperado.
    # Direccion y cuerpo ficticios; lo que se prueba es la forma, no el texto.
    c = correo(
        message_id="1a08a1c3f1d1e7f5",
        remitente="otro.profesor@cud.uvigo.es",
        fecha_envio=datetime(2026, 9, 10, 6, 57, 0, tzinfo=UTC),
        asunto="Re: [pdi] Sábana provisional 3A con aulas",
        cuerpo_texto="¿la clase de refuerzo sería el jueves de 9 a 11?",
        adjuntos=(),
    )
    assert es_respuesta_de_hilo(c) is True
    assert candidatos_validos([c]) == []


def test_aviso_de_error_sin_adjunto_se_descarta():
    c = correo(
        message_id="1a06742630296a8c",
        fecha_envio=datetime(2026, 9, 3, 12, 32, 42, tzinfo=UTC),
        asunto="[pdi] Re: Sábana provisonal semana 2B (actualización)",
        cuerpo_texto="Creo qué hay un error en el archivo, no es la última versión con los últimos cambios, en cuanto lo consiga lo envío.",
        adjuntos=(),
    )
    assert candidatos_validos([c]) == []


def test_reenvio_tras_error_si_cuenta_una_vez_tiene_adjunto_real():
    c = correo(
        message_id="1a0677309ac2c19d",
        fecha_envio=datetime(2026, 9, 3, 13, 26, 10, tzinfo=UTC),
        asunto="[pdi] Re: Sábana provisonal semana 2B (actualización)",
        cuerpo_texto="Ahora si adjunto la sábana con todas las actualizaciones, ya que faltaba un cambio.",
        adjuntos=("SABANA_20260903_2B_ACTUALIZACION2.xlsm",),
    )
    assert candidatos_validos([c]) == [c]
    sc = clasificar(c)
    assert sc.es_definitiva is False  # no dice "definitiva"/"final": no se asciende por defecto


def test_definitiva_y_provisional_a_la_vez_detiene_el_proceso():
    with pytest.raises(SabanaAmbigua):
        clasificar_definitiva_o_provisional(
            "Sábana definitiva (aún provisional en aulas)",
            "Es la versión definitiva de horas, aunque las aulas siguen siendo provisionales.",
        )


def test_dos_adjuntos_en_el_mismo_correo_es_ambiguo_y_detiene_el_proceso():
    c = correo(
        message_id="x1",
        fecha_envio=datetime(2026, 9, 14, 17, 29, 2, tzinfo=UTC),
        asunto="[pdi] Sábana semana 4B",
        cuerpo_texto="provisional",
        adjuntos=("SABANA_A.xlsm", "SABANA_B.xlsx"),
    )
    with pytest.raises(SabanaAmbigua):
        clasificar(c)


def test_misma_semana_destino_se_queda_con_el_envio_mas_reciente():
    # Secuencia real de la semana 3A (target_monday 2026-09-14): 07/09, 09/09, 11/09.
    c1 = clasificar(correo(
        message_id="m1", fecha_envio=datetime(2026, 9, 7, 15, 19, 50, tzinfo=UTC),
        asunto="[pdi] Sábana semana 3A", cuerpo_texto="primera versión provisional",
        adjuntos=("SABANA_20260907_3A_PROVISIONAL.xlsm",),
    ))
    c2 = clasificar(correo(
        message_id="m2", fecha_envio=datetime(2026, 9, 9, 17, 56, 56, tzinfo=UTC),
        asunto="[pdi] Sábana provisional 3A con aulas", cuerpo_texto="provisional con aulas",
        adjuntos=("SABANA_20260909_3A_PROVISIONAL_AULAS.xlsm",),
    ))
    c3 = clasificar(correo(
        message_id="m3", fecha_envio=datetime(2026, 9, 11, 13, 6, 39, tzinfo=UTC),
        asunto="[pdi] Sábana definitiva", cuerpo_texto="se va a publicar",
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
