"""Cierre determinista de la semana publicada y promoción de la siguiente."""
from __future__ import annotations

import copy
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from scripts.merge_schedule import _contar_por_tipo

ZONA_HORARIA = ZoneInfo("Europe/Madrid")
_DIA = {
    "lunes": 0,
    "martes": 1,
    "miércoles": 2,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sábado": 5,
    "sabado": 5,
    "domingo": 6,
}


def _ultimo_fin(datos: dict, semana_inicio: date) -> datetime | None:
    finales = []
    for clase in datos.get("clases", []):
        desplazamiento = _DIA.get(str(clase.get("dia", "")).casefold())
        if desplazamiento is None:
            continue
        try:
            hora = time.fromisoformat(clase["fin"])
        except (KeyError, ValueError):
            continue
        finales.append(datetime.combine(semana_inicio + timedelta(days=desplazamiento), hora, ZONA_HORARIA))
    return max(finales) if finales else None


def cerrar_semana_si_corresponde(datos_actuales: dict, ahora: datetime | None = None) -> tuple[dict, bool]:
    """Promueve la siguiente semana al llegar el sábado, o ya el viernes en
    cuanto ha terminado la última clase de la semana."""
    ahora = ahora or datetime.now(ZONA_HORARIA)
    if ahora.tzinfo is None:
        raise ValueError("La fecha de cierre debe incluir zona horaria.")
    actual = datos_actuales.get("semanaInicio")
    proxima = datos_actuales.get("proximaSemana")
    if not actual or not proxima or not proxima.get("semanaInicio"):
        return datos_actuales, False

    inicio_actual = date.fromisoformat(actual)
    inicio_proxima = date.fromisoformat(proxima["semanaInicio"])
    if inicio_proxima.toordinal() != inicio_actual.toordinal() + 7:
        return datos_actuales, False

    # La semana academica va de sabado a viernes (misma regla que semana_lunes()
    # en sabana_mail.py). Se cierra al llegar el sabado, o ya el viernes en
    # cuanto ha pasado la ultima clase de la semana: a esas alturas no queda
    # docencia y adelantar la vista a la semana siguiente es util.
    #
    # ACOTADO el 27/11/2026 con "and ahora.date() >= viernes". Antes bastaba con
    # que hubiera pasado la hora de fin de la ultima clase, sin mirar que dia
    # era, y la ultima clase de FSTF no es el final de la semana lectiva: la
    # 13B tenia su ultima sesion el miercoles 25 a las 12:05, el pipeline corrio
    # a las 17:25 de ese mismo miercoles y promovio la 14A -- que empezaba el
    # 30 -- a semana actual. La pagina paso a enseñar la semana siguiente tres
    # dias antes, la 13B se archivo a mitad de semana y proximaSemana quedo a
    # null, con lo que tambien desaparecio la pestaña de vista previa.
    #
    # Y era irreversible: pipeline.py calcula today_monday como el maximo entre
    # el lunes real y el semanaInicio del fichero, asi que una vez adelantado el
    # fichero ya no podia volver atras por si solo.
    sabado = inicio_actual + timedelta(days=5)
    viernes = inicio_actual + timedelta(days=4)
    fin_ultimo = _ultimo_fin(datos_actuales, inicio_actual)
    cerrada = ahora.date() >= sabado or (
        fin_ultimo is not None and ahora >= fin_ultimo and ahora.date() >= viernes
    )
    if not cerrada:
        return datos_actuales, False

    nuevo = copy.deepcopy(datos_actuales)
    codigo = re.search(r"_(\d{1,2}[A-Za-z])_", datos_actuales.get("archivo", ""))
    if not codigo:
        raise ValueError("No se puede archivar la semana porque falta su codigo de semana.")
    if not any(h.get("semana") == codigo.group(1) for h in nuevo.get("historial", [])):
        nuevo.setdefault("historial", []).append({
            "semana": codigo.group(1),
            **_contar_por_tipo(datos_actuales.get("clases", [])),
        })

    nuevo["archivo"] = proxima.get("archivo", datos_actuales.get("archivo", ""))
    nuevo["actualizado"] = proxima.get("actualizado", datos_actuales.get("actualizado", ""))
    nuevo["provisional"] = bool(proxima.get("provisional", False))
    nuevo["semanaInicio"] = proxima["semanaInicio"]
    nuevo["clases"] = copy.deepcopy(proxima.get("clases", []))
    nuevo["proximaSemana"] = None
    nuevo["comprobado"] = ahora.strftime("%Y-%m-%d %H:%M")
    return nuevo, True
