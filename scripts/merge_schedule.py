"""
Fusiona una nueva sabana ya importada (import_fabric.agrupar) en el JSON
vigente (mismo contrato que data/schedule.schema.json del repo y que el
Artifact de Claude: schemaVersion, archivo, actualizado, semanaInicio,
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

from dataclasses import dataclass, field

from scripts.sabana_mail import semana_lunes
from datetime import date, datetime


def _minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


@dataclass
class ResultadoFusion:
    datos: dict | None
    problemas: list[str] = field(default_factory=list)

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


def _contar_por_tipo(clases: list[dict]) -> dict:
    cuentas = {"teoria": 0, "seminario": 0, "laboratorio": 0}
    for c in clases:
        tipo = c["tipo"].upper()
        clave = "seminario" if tipo.startswith("SEM") else "laboratorio" if tipo.startswith("LAB") else "teoria"
        cuentas[clave] += 1
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
                    f"({anterior_proxima.get('archivo')}) y la nueva sabana ({archivo_nuevo}) es "
                    "PROVISIONAL: no se sustituye un horario definitivo por uno provisional."
                ],
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
                    f"La semana actual ya estaba en una version definitiva ({datos_actuales.get('archivo')}) "
                    f"y la nueva sabana ({archivo_nuevo}) es provisional: no se sustituye."
                ],
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
    nuevo["semanaInicio"] = semana_destino.isoformat()
    nuevo["clases"] = clases_nuevas
    nuevo["comprobado"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Si la proximaSemana que ya teniamos resulta ser justo esta semana que
    # acaba de llegar, se limpia -- ya no es "la que viene", es la actual.
    if nuevo.get("proximaSemana", {}).get("semanaInicio") == semana_destino.isoformat():
        nuevo["proximaSemana"] = None
    return ResultadoFusion(datos=nuevo, problemas=avisos_perdidas)
