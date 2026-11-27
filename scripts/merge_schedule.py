"""
Fusiona una nueva sabana ya importada (import_fabric.agrupar) en el JSON
vigente (mismo contrato que data/schedule.schema.json del repo:
schemaVersion, archivo, actualizado, semanaInicio,
historial, clases, proximaSemana).

Esto es la pieza que cierra los requisitos que ni el validador del repo ni
el importador cubren por si solos:
  - detectar solapamientos de horario (requisito 9: el validador de
    data/schedule.schema.json no lo comprueba, se confirmo en la auditoria);
  - impedir que una sabana PROVISIONAL sustituya a una ya marcada
    DEFINITIVA para la misma semana (requisito 13);
  - mantener el historico cuando cambia la semana (requisito 10/11);
  - preservar el ultimo horario valido si algo de esto falla (requisito 12):
    todas las funciones de aqui devuelven un resultado con una lista de
    problemas en vez de levantar una excepcion a la primera, y quien llama
    decide no escribir nada si la lista no esta vacia.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from scripts.sabana_mail import semana_lunes
from datetime import date, datetime

ZONA_HORARIA = ZoneInfo("Europe/Madrid")
_DIAS_ORDEN = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


@dataclass
class ResultadoFusion:
    datos: dict | None
    problemas: list[str] = field(default_factory=list)
    # True (por defecto) = "problemas" describe un fallo real que merece
    # parar el pipeline y avisar (datos invalidos: solapamientos, horas
    # mal formadas...). False = "problemas" solo explica por que, de forma
    # CORRECTA y esperada, no se ha sustituido nada (p.ej. una provisional
    # mas vieja que la definitiva ya publicada) -- no es un error, el
    # llamador debe seguir sin esta sabana y SIN marcar el job como fallido.
    bloqueo_es_error: bool = True

    @property
    def ok(self) -> bool:
        return self.datos is not None and not self.problemas


def detectar_solapamientos(clases: list[dict]) -> list[str]:
    """Dos clases del mismo dia se solapan si comparten tiempo Y (misma
    aula, o algun grupo en comun) -- clases simultaneas en aulas distintas
    y sin grupos en comun son desdobles legitimos, no un solapamiento."""
    problemas = []
    por_dia: dict[str, list[dict]] = {}
    for c in clases:
        por_dia.setdefault(c["dia"], []).append(c)
    for dia, lista in por_dia.items():
        for i in range(len(lista)):
            for j in range(i + 1, len(lista)):
                a, b = lista[i], lista[j]
                se_solapan_en_tiempo = _minutos(a["inicio"]) < _minutos(b["fin"]) and _minutos(b["inicio"]) < _minutos(a["fin"])
                if not se_solapan_en_tiempo:
                    continue
                misma_aula = a.get("aula") is not None and a.get("aula") == b.get("aula")
                grupos_a = {g.strip() for g in a["grupos"].split(",")}
                grupos_b = {g.strip() for g in b["grupos"].split(",")}
                grupos_comunes = grupos_a & grupos_b
                if misma_aula or grupos_comunes:
                    motivo = f"aula {a.get('aula')!r} compartida" if misma_aula else f"grupo(s) {sorted(grupos_comunes)} en ambas"
                    problemas.append(
                        f"Solapamiento en {dia}: {a['inicio']}-{a['fin']} ({a['tipo']}, {a['grupos']}) "
                        f"con {b['inicio']}-{b['fin']} ({b['tipo']}, {b['grupos']}) -- {motivo}."
                    )
    return problemas


def validar_horas(clases: list[dict]) -> list[str]:
    problemas = []
    for c in clases:
        try:
            if _minutos(c["fin"]) <= _minutos(c["inicio"]):
                problemas.append(f"{c['dia']} {c['inicio']}-{c['fin']}: la hora de fin no es posterior a la de inicio.")
        except Exception:
            problemas.append(f"{c['dia']}: hora con formato invalido (inicio={c.get('inicio')!r}, fin={c.get('fin')!r}).")
    return problemas


def detectar_sesiones_perdidas(clases_previas: list[dict], clases_nuevas: list[dict]) -> list[str]:
    """Avisa (no bloquea) si una franja dia+hora+aula que existia en la
    version anterior de ESTA MISMA semana ha desaparecido sin mas en la
    nueva, por si es una perdida de datos y no un cambio real de horario."""
    avisos = []
    claves_nuevas = {(c["dia"], c["inicio"], c["fin"]) for c in clases_nuevas}
    for c in clases_previas:
        clave = (c["dia"], c["inicio"], c["fin"])
        if clave not in claves_nuevas:
            avisos.append(
                f"La franja {c['dia']} {c['inicio']}-{c['fin']} ({c['tipo']}, {c['grupos']}) estaba en la "
                "version anterior de esta semana y no aparece en la nueva -- confirmar que es un cambio real."
            )
    return avisos


def _codigo_semana(archivo: str) -> str:
    import re

    m = re.search(r"_(\d{1,2}[A-Za-z])_", archivo or "")
    return m.group(1) if m else (archivo or "?")


def _clave_recuento(tipo: str | None) -> str | None:
    """Cubo del recuento semanal al que va una sesion, o None si sus horas no
    deben sumarse aqui. Regla confirmada por el autor (19/11/2026): los
    EXAMENES PARCIALES cuentan como TEORIA, porque ocupan horas de teoria de
    la asignatura; el EXAMEN FINAL no, porque tiene horas propias dedicadas en
    el control de horas de firma. Cualquier otro tipo desconocido cae en
    "teoria": es preferible que una hora rara aparezca en el recuento y se vea
    a que desaparezca en silencio.

    La deteccion del examen final es por la palabra "FINAL" en el tipo; cuando
    llegue la primera sabana con examen final conviene comprobar como lo
    escribe Coordinacion y ajustar aqui si usaran otra formula."""
    t = (tipo or "").upper()
    if t.startswith("SEM"):
        return "seminario"
    if t.startswith("LAB"):
        return "laboratorio"
    if "FINAL" in t:
        return None
    return "teoria"


def _contar_por_tipo(clases: list[dict]) -> dict:
    """Recuento semanal "de verdad" para el historial -- misma logica,
    deliberadamente identica, que countTypes() de js/schedule-model.js, para
    que lo que se archiva y lo que se ve en pantalla no se separen. Ademas de
    saltarse las sesiones marcadas como de otro profesor ("propia": false),
    hace dos ajustes y solo dos:

      1) Franjas simultaneas: dos filas a la misma hora del mismo dia (el
         mismo laboratorio partido en dos aulas, o dos grupos en paralelo) son
         una sola hora para una persona, asi que esa franja cuenta una vez.
      2) Repeticion en otro dia: si un mismo grupo tiene SEMINARIO o
         LABORATORIO en mas de un DIA (duplicidad tipica de la sabana, no dos
         horas reales), solo cuenta la primera aparicion cronologica.

    Lo que NO se descuenta es la repeticion del mismo grupo en el MISMO dia:
    los laboratorios se imparten en bloques de dos o mas horas seguidas con
    los mismos grupos y cada una de esas horas es real. Una version anterior
    (commit a8c7918) descontaba tambien esas, y por eso la semana 10B quedo
    archivada con 4 horas de laboratorio cuando eran 8."""
    cuentas = {"teoria": 0, "seminario": 0, "laboratorio": 0}
    vistos: dict[str, dict[str, str]] = {"seminario": {}, "laboratorio": {}}
    franjas_contadas: set[tuple] = set()
    propias = [c for c in clases if c.get("propia") is not False]
    ordenadas = sorted(propias, key=lambda c: (_DIAS_ORDEN.index(c["dia"]), _minutos(c["inicio"])))
    for c in ordenadas:
        clave = _clave_recuento(c.get("tipo"))
        if clave is None:
            continue
        franja = (clave, c["dia"], c["inicio"], c["fin"])
        if franja in franjas_contadas:
            continue
        if clave == "teoria":
            cuentas["teoria"] += 1
            franjas_contadas.add(franja)
            continue
        grupos = [
            re.sub(r"\s*\([^)]*\)\s*", "", g).strip().upper()
            for g in (c.get("grupos") or "").split(",")
        ]
        grupos = [g for g in grupos if g]
        vistos_tipo = vistos[clave]
        # Cuenta si aporta algun grupo nuevo, o si los grupos ya vistos lo
        # fueron ESE MISMO dia (bloque de horas seguidas, no duplicidad).
        cuenta = not grupos or any(
            g not in vistos_tipo or vistos_tipo[g] == c["dia"] for g in grupos
        )
        if cuenta:
            cuentas[clave] += 1
            franjas_contadas.add(franja)
        for g in grupos:
            vistos_tipo.setdefault(g, c["dia"])
    return cuentas


def fusionar(
    datos_actuales: dict,
    *,
    archivo_nuevo: str,
    actualizado_nuevo: str,
    clases_nuevas: list[dict],
    es_definitiva_nueva: bool,
    semana_destino: date,
    today_monday: date,
    es_para_proxima_semana: bool,
) -> ResultadoFusion:
    """Aplica una sabana ya clasificada y ya importada sobre el JSON
    vigente. No escribe nada por si mismo: construye y devuelve el nuevo
    documento (o, si hay problemas, los problemas) para que el pipeline
    decida si lo publica."""
    problemas = validar_horas(clases_nuevas) + detectar_solapamientos(clases_nuevas)
    if problemas:
        return ResultadoFusion(datos=None, problemas=problemas)

    nuevo = dict(datos_actuales)
    nuevo["historial"] = list(datos_actuales.get("historial", []))

    if es_para_proxima_semana:
        anterior_proxima = datos_actuales.get("proximaSemana")
        if (
            anterior_proxima
            and anterior_proxima.get("semanaInicio") == semana_destino.isoformat()
            and not anterior_proxima.get("provisional", True)
            and not es_definitiva_nueva
        ):
            return ResultadoFusion(
                datos=None,
                problemas=[
                    "La semana siguiente ya estaba marcada DEFINITIVA "
                    "y la nueva sabana es "
                    "PROVISIONAL: no se sustituye un horario definitivo por uno provisional."
                ],
                bloqueo_es_error=False,
            )
        avisos_perdidas = detectar_sesiones_perdidas(
            (anterior_proxima or {}).get("clases", []), clases_nuevas
        )
        nuevo["proximaSemana"] = {
            "archivo": archivo_nuevo,
            "actualizado": actualizado_nuevo,
            "provisional": not es_definitiva_nueva,
            "semanaInicio": semana_destino.isoformat(),
            "clases": clases_nuevas,
        }
        return ResultadoFusion(datos=nuevo, problemas=avisos_perdidas)

    # Es para la semana ACTUAL.
    semana_actual_vigente = datos_actuales.get("semanaInicio")
    if semana_actual_vigente == semana_destino.isoformat():
        definitiva_vigente = _codigo_semana(datos_actuales.get("archivo", "")) and "FINAL" in (datos_actuales.get("archivo") or "").upper() or "DEFINITIV" in (datos_actuales.get("archivo") or "").upper()
        if definitiva_vigente and not es_definitiva_nueva:
            return ResultadoFusion(
                datos=None,
                problemas=[
                    "La semana actual ya estaba en una version definitiva y la nueva sabana "
                    "es provisional: no se sustituye."
                ],
                bloqueo_es_error=False,
            )
        avisos_perdidas = detectar_sesiones_perdidas(datos_actuales.get("clases", []), clases_nuevas)
    else:
        # Cambio de semana: archivar la saliente en el historial si procede.
        codigo_saliente = _codigo_semana(datos_actuales.get("archivo", ""))
        if codigo_saliente and not any(h.get("semana") == codigo_saliente for h in nuevo["historial"]):
            nuevo["historial"].append({"semana": codigo_saliente, **_contar_por_tipo(datos_actuales.get("clases", []))})
        avisos_perdidas = []

    nuevo["archivo"] = archivo_nuevo
    nuevo["actualizado"] = actualizado_nuevo
    nuevo["provisional"] = not es_definitiva_nueva
    nuevo["semanaInicio"] = semana_destino.isoformat()
    nuevo["clases"] = clases_nuevas
    nuevo["comprobado"] = datetime.now(ZONA_HORARIA).strftime("%Y-%m-%d %H:%M")
    # Si la proximaSemana que ya teniamos resulta ser justo esta semana que
    # acaba de llegar, se limpia -- ya no es "la que viene", es la actual.
    proxima = nuevo.get("proximaSemana")
    if proxima and proxima.get("semanaInicio") == semana_destino.isoformat():
        nuevo["proximaSemana"] = None
    return ResultadoFusion(datos=nuevo, problemas=avisos_perdidas)
