"""
Tests de la parte de gmail_fetch.py que SI se puede probar sin red: la
interpretacion del JSON que devuelve la API de Gmail (formato "full" del
recurso Message -- https://developers.google.com/gmail/api/reference/rest/v1/users.messages).
Los mensajes de ejemplo de aqui reproducen esa forma con el mismo asunto,
remitente y nombre de adjunto que el correo real "Sábana definitiva" del
11/09/2026 ya usado en test_sabana_mail.py, para que ambos modulos se
validen con el mismo caso real.
"""
import base64

from scripts.gmail_fetch import construir_query, extraer_candidato, id_de_adjunto


def _b64(texto: str) -> str:
    return base64.urlsafe_b64encode(texto.encode("utf-8")).decode("ascii")


def test_construir_query_incluye_remitente_adjunto_y_ventana_de_dias():
    q = construir_query("coordinacion.horarios.espacios@cud.uvigo.es", dias=14)
    assert "from:coordinacion.horarios.espacios@cud.uvigo.es" in q
    assert "has:attachment" in q
    assert "newer_than:14d" in q


def _mensaje_ejemplo():
    return {
        "id": "1a090940bc2f676e",
        "threadId": "1a090940bc2f676e",
        "internalDate": "1789131999000",  # 2026-09-11T13:06:39Z, igual que el correo real
        "payload": {
            "headers": [
                {"name": "Subject", "value": "[pdi] Sábana definitiva"},
                {"name": "From", "value": "Coordinación de Horarios y Espacios Docentes CUD <coordinacion.horarios.espacios@cud.uvigo.es>"},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": _b64("Adjunto la versión que se va a publicar en la orden del lunes.")},
                        },
                        {
                            "mimeType": "text/html",
                            "body": {"data": _b64("<p>Adjunto la versión...</p>")},
                        },
                    ],
                },
                {
                    "filename": "SABANA_20260911_3A_FINAL.xlsm",
                    "mimeType": "application/vnd.ms-excel.sheet.macroenabled.12",
                    "body": {"attachmentId": "ANGjdJ-abc123", "size": 473000},
                },
            ],
        },
    }


def test_extraer_candidato_de_un_mensaje_real_de_gmail():
    c = extraer_candidato(_mensaje_ejemplo())
    assert c.message_id == "1a090940bc2f676e"
    assert c.remitente == "coordinacion.horarios.espacios@cud.uvigo.es"
    assert c.asunto == "[pdi] Sábana definitiva"
    assert "se va a publicar" in c.cuerpo_texto
    assert c.adjuntos == ("SABANA_20260911_3A_FINAL.xlsm",)
    assert c.fecha_envio.year == 2026 and c.fecha_envio.month == 9 and c.fecha_envio.day == 11


def test_id_de_adjunto_encuentra_el_attachment_id_correcto():
    mensaje = _mensaje_ejemplo()
    assert id_de_adjunto(mensaje, "SABANA_20260911_3A_FINAL.xlsm") == "ANGjdJ-abc123"


def test_id_de_adjunto_falla_si_no_existe_ese_nombre():
    mensaje = _mensaje_ejemplo()
    try:
        id_de_adjunto(mensaje, "NO_EXISTE.xlsm")
        assert False, "deberia haber lanzado ValueError"
    except ValueError:
        pass
