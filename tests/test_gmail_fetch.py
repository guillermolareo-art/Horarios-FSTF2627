"""Pruebas de interpretación de mensajes sintéticos con la forma de Gmail API."""
import base64

from scripts.gmail_fetch import construir_query, extraer_candidato, id_de_adjunto


def _b64(texto: str) -> str:
    return base64.urlsafe_b64encode(texto.encode("utf-8")).decode("ascii")


def test_construir_query_incluye_remitente_adjunto_y_ventana_de_dias():
    q = construir_query("schedules@example.test", dias=14)
    assert "from:schedules@example.test" in q
    assert "has:attachment" in q
    assert "newer_than:14d" in q


def _mensaje_ejemplo():
    return {
        "id": "synthetic-message",
        "threadId": "synthetic-thread",
        "internalDate": "1789131999000",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Sample schedule definitive"},
                {"name": "From", "value": "Schedule Sender <schedules@example.test>"},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": _b64("Synthetic schedule version marked final.")},
                        },
                        {
                            "mimeType": "text/html",
                            "body": {"data": _b64("<p>Synthetic schedule notice.</p>")},
                        },
                    ],
                },
                {
                    "filename": "SABANA_20260911_3A_FINAL.xlsm",
                    "mimeType": "application/vnd.ms-excel.sheet.macroenabled.12",
                    "body": {"attachmentId": "synthetic-attachment", "size": 473000},
                },
            ],
        },
    }


def test_extraer_candidato_de_un_mensaje_sintetico_de_gmail():
    c = extraer_candidato(_mensaje_ejemplo())
    assert c.message_id == "synthetic-message"
    assert c.remitente == "schedules@example.test"
    assert c.asunto == "Sample schedule definitive"
    assert "marked final" in c.cuerpo_texto
    assert c.adjuntos == ("SABANA_20260911_3A_FINAL.xlsm",)
    assert c.fecha_envio.year == 2026 and c.fecha_envio.month == 9 and c.fecha_envio.day == 11


def test_id_de_adjunto_encuentra_el_attachment_id_correcto():
    mensaje = _mensaje_ejemplo()
    assert id_de_adjunto(mensaje, "SABANA_20260911_3A_FINAL.xlsm") == "synthetic-attachment"


def test_id_de_adjunto_falla_si_no_existe_ese_nombre():
    mensaje = _mensaje_ejemplo()
    try:
        id_de_adjunto(mensaje, "NO_EXISTE.xlsm")
        assert False, "deberia haber lanzado ValueError"
    except ValueError:
        pass
