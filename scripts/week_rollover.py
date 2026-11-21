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
    """Promueve la siguiente semana al terminar las clases o al llegar el sábado."""
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

    sabado = inicio_actual + timedelta(days=5)
    fin_ultimo = _ultimo_fin(datos_actuales, inicio_actual)
    cerrada = ahora.date() >= sabado or (fin_ultimo is not None and ahora >= fin_ultimo)
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
