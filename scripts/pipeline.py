"""
Orquestador: ata sabana_mail.py + gmail_fetch.py + import_fabric.py +
merge_schedule.py para producir (o no) una nueva version de
data/fstf-2627.json a partir de Gmail. Pensado para correr en GitHub
Actions via update-fabric.yml.

Filosofia de errores: un problema REAL (correo ambiguo, credenciales
rotas, solapamiento, horas mal formadas) hace que el script termine con
codigo de salida distinto de 0 y SIN escribir nada en data/fstf-2627.json
-- el horario publicado anterior se conserva intacto y el detalle va a la
salida estandar para que aparezca en el log de Actions. Un bloqueo
ESPERADO y correcto (p.ej. una provisional mas vieja que la definitiva ya
publicada, o una sabana que no es ni de esta semana ni de la siguiente)
NO es un error: se registra como aviso informativo y el script termina
con exit code 0, para no generar notificaciones de fallo quando no ha
pasado nada malo.

Este script NO llama a ningun modelo de IA. Toda la logica es la de los
otros cuatro modulos, deterministas y ya probados con pytest.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from scripts.gmail_fetch import descargar_adjunto, id_de_adjunto, listar_candidatos, obtener_servicio
from scripts.import_fabric import agrupar, parse_fabric
from scripts.merge_schedule import fusionar
from scripts.sabana_mail import (
    EstadoProcesados,
    SabanaAmbigua,
    candidatos_validos,
    clasificar,
    pendientes_de_procesar,
    semana_lunes,
    ultima_por_semana_destino,
)

RUTA_DATOS = Path("data/fstf-2627.json")
RUTA_ESTADO = Path("data/.sabanas_procesadas.json")


class FalloPipeline(Exception):
    """Se usa para parar el pipeline con un mensaje explicativo completo;
    ``main()`` la captura, la imprime entera y termina con exit code 1 sin
    tocar RUTA_DATOS."""


def cargar_estado() -> EstadoProcesados:
    if RUTA_ESTADO.exists():
        return EstadoProcesados.from_json(json.loads(RUTA_ESTADO.read_text(encoding="utf-8")))
    return EstadoProcesados()


def guardar_estado(estado: EstadoProcesados) -> None:
    RUTA_ESTADO.write_text(json.dumps(estado.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ejecutar(hoy: date | None = None) -> bool:
    """Devuelve True si se escribio una nueva version de RUTA_DATOS."""
    hoy = hoy or datetime.now(timezone.utc).date()
    today_monday = semana_lunes(hoy)

    if not RUTA_DATOS.exists():
        raise FalloPipeline(f"No existe {RUTA_DATOS}; este pipeline solo actualiza un horario que ya existe.")
    datos_actuales = json.loads(RUTA_DATOS.read_text(encoding="utf-8"))

    estado = cargar_estado()
    servicio = obtener_servicio()
    candidatos_crudos = listar_candidatos(servicio)
    validos = candidatos_validos([c for c, _m in candidatos_crudos])
    mensajes_por_id = {c.message_id: m for c, m in candidatos_crudos}

    try:
        clasificados = [clasificar(c) for c in validos]
    except SabanaAmbigua as exc:
        raise FalloPipeline(f"Correo ambiguo, revision manual necesaria: {exc}") from exc

    pendientes = pendientes_de_procesar(clasificados, estado)
    if not pendientes:
        return False  # nada nuevo que procesar

    ganadoras = ultima_por_semana_destino(pendientes)
    cambios_aplicados = False
    estado_modificado = False
    avisos_totales: list[str] = []

    for semana_destino, sc in sorted(ganadoras.items()):
        es_actual = semana_destino == today_monday
        es_proxima = (semana_destino - today_monday).days == 7
        if not es_actual and not es_proxima:
            # Ni es la semana de hoy ni la siguiente: no se aplica sola
            # (podria ser una sabana tardia de una semana ya cerrada); se
            # deja constancia y se sigue con el resto de ganadoras.
            avisos_totales.append(
                f"Se ignora {sc.archivo} (mensaje {sc.message_id}): su semana destino "
                f"{semana_destino.isoformat()} no es ni la actual ({today_monday.isoformat()}) "
                "ni la siguiente; revisar a mano si hace falta incorporarla."
            )
            continue

        mensaje = mensajes_por_id[sc.message_id]
        attachment_id = id_de_adjunto(mensaje, sc.archivo)
        contenido = descargar_adjunto(servicio, sc.message_id, attachment_id)
        with tempfile.NamedTemporaryFile(suffix=".xlsm", delete=False) as tmp:
            tmp.write(contenido)
            ruta_tmp = tmp.name
        try:
            clases_crudas = parse_fabric(ruta_tmp)
        finally:
            Path(ruta_tmp).unlink(missing_ok=True)
        clases_agrupadas, avisos_import = agrupar(clases_crudas)

        resultado = fusionar(
            datos_actuales,
            archivo_nuevo=sc.archivo,
            actualizado_nuevo=sc.fecha_envio.date().isoformat(),
            clases_nuevas=clases_agrupadas,
            es_definitiva_nueva=sc.es_definitiva,
            semana_destino=semana_destino,
            today_monday=today_monday,
            es_para_proxima_semana=es_proxima,
        )
        if resultado.datos is None:
            if resultado.bloqueo_es_error:
                # Fallo real (datos invalidos: solapamientos, horas mal
                # formadas...): se para todo el pipeline y se marca el job
                # como fallido para que llegue la notificacion.
                raise FalloPipeline(
                    f"No se aplica {sc.archivo} (mensaje {sc.message_id}):\n- "
                    + "\n- ".join(resultado.problemas)
                )
            # Bloqueo esperado y correcto (p.ej. una provisional mas vieja
            # que la definitiva ya publicada): no es un error, no se marca
            # el job como fallido ni se envia notificacion por esto. Se
            # deja constancia en el log y se marca como procesada para no
            # volver a intentarlo cada dia con el mismo correo ya superado.
            avisos_totales.append(
                f"Se ignora {sc.archivo} (mensaje {sc.message_id}, sin marcar error): "
                + "; ".join(resultado.problemas)
            )
            estado.marcar_procesado(sc.message_id)
            estado_modificado = True
            continue
        avisos_totales.extend(avisos_import)
        avisos_totales.extend(resultado.problemas)  # avisos no bloqueantes que si se publicaron
        datos_actuales = resultado.datos
        cambios_aplicados = True
        estado_modificado = True
        estado.marcar_procesado(sc.message_id)

    if cambios_aplicados:
        RUTA_DATOS.write_text(json.dumps(datos_actuales, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if estado_modificado:
        guardar_estado(estado)
    if avisos_totales:
        print(
            "AVISOS (revisar el log; algunos pueden ya estar publicados y otros solo informativos):",
            file=sys.stderr,
        )
        for a in avisos_totales:
            print(f"- {a}", file=sys.stderr)
    return cambios_aplicados


def main() -> int:
    try:
        hubo_cambios = ejecutar()
    except FalloPipeline as exc:
        print(f"PIPELINE DETENIDO -- no se ha escrito nada: {exc}", file=sys.stderr)
        return 1
    print("Sin cambios nuevos." if not hubo_cambios else "Horario actualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
