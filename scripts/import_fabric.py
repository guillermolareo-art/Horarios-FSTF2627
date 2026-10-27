"""
Importador determinista (sin IA) de la hoja "SABANA 26_27" a la lista de
clases de FABRIC, en el mismo formato que usan el repo
(data/schedule.schema.json) y el Artifact de Claude.

Estructura real de la hoja, verificada celda a celda contra
SABANA_20261021_9A_PROVISIONAL.xlsm (no asumida de documentacion anterior):

  - Filas 1-5: cabecera de columnas. Cada columna de alumno/grupo tiene su
    etiqueta repartida en hasta 4 filas (1=Nombre alumno especifico si lo hay,
    2=Empleo/rango, 3=Promocion, 4=Grupo). Para un grupo colectivo (G1..G6,
    IM1, IM2) la fila 4 trae el nombre completo con curso, p.ej.
    "G1 (4 CGA-ST)". Para un cadete INDIVIDUAL sin grupo asignado (dos
    columnas en este curso) el nombre esta en la fila 1, y la fila 4 esta
    vacia o solo trae el rango ("GM2º") -- usar la fila 1 ahi es obligatorio,
    o la columna sale mal (dos alumnos distintos apareciendo ambos como
    "GM2º"). Para un alumno de intercambio sin nada en la fila 1 (cuatro
    columnas en este curso) la fila 4 SI trae su nombre de pila y es la que
    hay que usar. Por eso el orden de preferencia real (verificado, no
    copiado de documentacion previa) es: fila1 -> fila4 -> fila3 -> fila2.

    Ninguno de esos nombres se reproduce en este archivo ni llega al JSON:
    ver la seccion de seudonimizacion mas abajo. Para saber que columna es
    quien, se mira la sabana, que no esta en el repositorio.

  - A partir de la fila 6: bloques de 6 filas por franja horaria, repetidos
    por cada dia (con una fila en blanco de separacion entre dias, no todas
    las franjas duran 6 filas de distancia entre si por eso):
      offset 0: columna A = dia (solo en la primera franja del dia; se
                arrastra); columna B = indice de turno; columna C = hora
                de inicio.
      offset 1: TIPO (p.ej. TEORIA, SEMINARIO, LABORATORIO, pero tambien
                ESTUDIO/CURSO_SUSPENSOS en franjas que no son clase).
      offset 2: ASIGNATURA (codigo exacto, p.ej. "FABRIC", "F_AUTOMA").
      offset 3: AULA.
      offset 4: PROFESOR(es), separados por coma (no se usa en el JSON de
                salida; se conserva solo para los avisos de ambiguedad).
      offset 5: columna C = hora de fin.

  - "FABRIC" y "F_AUTOMA" son codigos de ASIGNATURA distintos y exactos
    (confirmados en la hoja ACRONIMOS: fila 28 "Fundamentos de Sistemas y
    Tecnologias de Fabricacion" = FABRIC = profesor GLARCAL; fila 20
    "Fundamentos de Automatica" = F_AUTOMA = profesora AOGAMAR). Por tanto
    la exclusion de F_AUTOMA es una comparacion de texto exacta, no una
    heuristica: basta con filtrar ASIGNATURA == "FABRIC" y nunca coincide
    con F_AUTOMA aunque compartan columna y franja horaria.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field

import openpyxl

HOJA = "SABANA 26_27"
ASIGNATURA_OBJETIVO = "FABRIC"
DIAS_VALIDOS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")

# Cabecera -> nombre visible del dia tal y como lo usa el JSON (la hoja trae
# "MIÉRCOLES" en mayusculas; el JSON usa "Miércoles").
_NORMALIZA_DIA = {d.upper(): d for d in DIAS_VALIDOS}


# --- Seudonimizacion de cadetes individuales -------------------------------
#
# Algunas columnas de la sabana no son un grupo sino UNA persona: un cadete
# sin grupo asignado, o un alumno de intercambio. Su etiqueta es, por tanto,
# un nombre propio. Ese nombre NO puede llegar al JSON publicado: unido al
# dia, la hora y el aula diria donde esta una persona concreta a cada hora.
#
# El filtro es una lista blanca, no una lista negra: se reconoce la FORMA de
# una etiqueta de grupo colectivo y todo lo que no encaje se considera una
# persona. Asi un nombre nuevo en una sabana futura queda cubierto sin tocar
# el codigo, que es justo lo que no puede fallar en un job automatico.
#
# A cada persona se le da un seudonimo estable dentro de la importacion
# ("Cadete 1", "Cadete 2"...) en lugar de una etiqueta comun: si dos cadetes
# distintos coincidieran en la misma franja en aulas distintas, una etiqueta
# comun los haria parecer el mismo grupo y merge_schedule.py lo denunciaria
# como solapamiento inexistente, deteniendo la publicacion.
#
# La correspondencia entre seudonimo y persona no se guarda en ninguna parte
# del repositorio, a proposito. Para saber quien es "Cadete 2" se mira la
# sabana original, que vive en el correo y no aqui.

_GRUPO_COLECTIVO = re.compile(r"^(?:G\d+[AB]?|IM\d+)(?:\s*\(.*\))?$", re.IGNORECASE)


def es_grupo_colectivo(etiqueta: str) -> bool:
    """True si la etiqueta designa a un grupo (G1, G3B, IM2, "G1 (4 CGA-ST)")
    y no a una persona. Ante la duda devuelve False: preferimos seudonimizar
    un grupo raro a publicar un nombre."""
    return bool(_GRUPO_COLECTIVO.match(etiqueta.strip()))


def construir_seudonimos(etiquetas) -> dict[str, str]:
    """{etiqueta_original: seudonimo} para las etiquetas que son personas.
    Orden alfabetico estable, para que el JSON no cambie entre ejecuciones
    si no ha cambiado la sabana."""
    personas = sorted({e for e in etiquetas if not es_grupo_colectivo(e)})
    return {e: f"Cadete {n}" for n, e in enumerate(personas, start=1)}


class ErrorImportacion(Exception):
    """Fallo detectado al importar: la fila/columna que lo causa va en el mensaje.
    Nunca se silencia ni se adivina un valor por defecto."""


@dataclass
class ClaseFabric:
    dia: str
    inicio: str
    fin: str
    tipo: str
    aula: object  # str | int | None
    grupos: tuple[str, ...]
    profesores: tuple[str, ...] = field(default_factory=tuple)
    fila_origen: int = 0
    columna_origen: int = 0
    anotacion_fila1: str | None = None


def _hhmm(t) -> str:
    if not isinstance(t, _dt.time):
        raise ErrorImportacion(f"Se esperaba una hora y se encontro: {t!r}")
    return f"{t.hour:02d}:{t.minute:02d}"


def construir_mapa_columnas(ws) -> tuple[dict[int, str], dict[int, str]]:
    """Devuelve (mapa, anotaciones).

    ``mapa``: {columna: etiqueta_de_grupo}, con el orden de preferencia
    verificado celda a celda contra la sabana real: fila4 ("Grupo") primero
    -- es la unica fila que SIEMPRE esta rellena cuando la columna es un
    grupo normal (G1..G6, IM1, IM2, G1A/G1B) o un alumno de intercambio --
    y solo si la fila 4 esta vacia se cae a fila1 (ahi es donde aparece el
    nombre propio de un cadete SIN grupo asignado), despues fila3, fila2.

    Las etiquetas que salen de aqui pueden ser nombres de persona. No se
    publican tal cual: ``agrupar`` las sustituye por un seudonimo.

    IMPORTANTE (verificado, no asumido): la fila 1 ("Nombre alumno") tambien
    se usa, en columnas que SI tienen grupo en la fila 4, para anotar que un
    cadete suelto de otro origen (una academia extranjera, p.ej.) comparte
    esa franja -- no es el nombre de la columna.
    Un primer intento de este importador uso fila1 con prioridad sobre
    fila4 y eso convirtio la columna real de G4 en "PORTUGUESES" sin
    ningun cadete de ese grupo en la franja; de ahi que la prioridad
    correcta sea fila4 primero. Esas anotaciones de la fila 1 NO se
    descartan en silencio: se devuelven en ``anotaciones`` para que el
    importador las incluya como aviso a revisar por una persona.
    """
    filas = {}
    for n_fila in (1, 2, 3, 4):
        filas[n_fila] = [c.value for c in next(ws.iter_rows(min_row=n_fila, max_row=n_fila))]
    mapa: dict[int, str] = {}
    anotaciones: dict[int, str] = {}
    max_col = len(filas[1])
    for idx in range(max_col):
        valor_fila4 = filas[4][idx]
        valor_fila1 = filas[1][idx]
        etiqueta = None
        for n_fila in (4, 1, 3, 2):
            v = filas[n_fila][idx]
            if isinstance(v, str) and v.strip():
                etiqueta = v.strip()
                break
        if etiqueta is None:
            continue
        mapa[idx + 1] = etiqueta
        if (
            isinstance(valor_fila4, str) and valor_fila4.strip()
            and isinstance(valor_fila1, str) and valor_fila1.strip()
            and valor_fila1.strip() != valor_fila4.strip()
        ):
            anotaciones[idx + 1] = valor_fila1.strip()
    return mapa, anotaciones


def parse_fabric(ruta_excel: str) -> list[ClaseFabric]:
    wb = openpyxl.load_workbook(ruta_excel, data_only=True, read_only=True)
    if HOJA not in wb.sheetnames:
        raise ErrorImportacion(f"No existe la hoja {HOJA!r}; hojas disponibles: {wb.sheetnames}")
    ws = wb[HOJA]
    mapa_columnas, anotaciones_fila1 = construir_mapa_columnas(ws)

    filas_cache: dict[int, list] = {}

    def fila(n: int) -> list:
        if n not in filas_cache:
            filas_cache[n] = [c.value for c in next(ws.iter_rows(min_row=n, max_row=n))]
        return filas_cache[n]

    def valor(n: int, idx: int):
        f = fila(n)
        return f[idx] if idx < len(f) else None

    max_row = ws.max_row

    # Fase 1: localizar el inicio de cada franja. Un inicio de franja es una
    # fila con hora en la columna C Y algo (numero o letra de turno) en la
    # columna B. Esto es mas robusto que asumir bloques de 6 filas exactos:
    # las franjas de turno de comida/deporte ("A"/"B" en este curso) no
    # siempre tienen fila de hora de fin en el mismo desplazamiento, y hay
    # una fila en blanco de separacion entre dias que rompe la periodicidad.
    inicios = [
        r for r in range(1, max_row + 1)
        if isinstance(valor(r, 2), _dt.time) and valor(r, 1) is not None
    ]
    if not inicios:
        raise ErrorImportacion("No se ha encontrado ninguna franja horaria (columna B+C) en la hoja.")

    clases: list[ClaseFabric] = []
    dia_actual = None
    for pos, r in enumerate(inicios):
        siguiente = inicios[pos + 1] if pos + 1 < len(inicios) else max_row + 1
        fila_a = valor(r, 0)
        if isinstance(fila_a, str) and fila_a.strip():
            dia_normalizado = _NORMALIZA_DIA.get(fila_a.strip().upper())
            if dia_normalizado is None:
                raise ErrorImportacion(f"Dia desconocido en fila {r}: {fila_a!r}")
            dia_actual = dia_normalizado
        if dia_actual is None:
            raise ErrorImportacion(f"Franja horaria en fila {r} sin dia conocido todavia.")

        fila_tipo, fila_asig = fila(r + 1) if r + 1 < siguiente else [], fila(r + 2) if r + 2 < siguiente else []
        hay_fabric = any(
            (fila_asig[c - 1] if c - 1 < len(fila_asig) else None) == ASIGNATURA_OBJETIVO
            for c in mapa_columnas
        )
        if not hay_fabric:
            continue  # bloques sin FABRIC (comida, deporte, otras asignaturas): no hace falta mas precision

        # Hora de fin: la primera fila con hora en columna C, DESPUES del
        # inicio y antes de la siguiente franja, que NO tenga turno en
        # columna B (si tuviera turno seria ya el inicio de la franja
        # siguiente, no el fin de esta).
        hora_fin = None
        for rf in range(r + 1, siguiente):
            vc = valor(rf, 2)
            if isinstance(vc, _dt.time) and valor(rf, 1) is None:
                hora_fin = vc
                break
        if hora_fin is None:
            raise ErrorImportacion(
                f"La franja de la fila {r} contiene FABRIC pero no se le encuentra hora de fin "
                f"antes de la fila {siguiente}; revisar manualmente esa franja en la sabana."
            )
        hora_inicio_txt = _hhmm(valor(r, 2))
        hora_fin_txt = _hhmm(hora_fin)
        fila_aula = fila(r + 3) if r + 3 < siguiente else []
        fila_prof = fila(r + 4) if r + 4 < siguiente else []
        for col, etiqueta in mapa_columnas.items():
            idx = col - 1
            asignatura = fila_asig[idx] if idx < len(fila_asig) else None
            if asignatura != ASIGNATURA_OBJETIVO:
                continue
            tipo = fila_tipo[idx] if idx < len(fila_tipo) else None
            if not isinstance(tipo, str) or not tipo.strip():
                raise ErrorImportacion(
                    f"Fila {r + 1}, columna {col}: ASIGNATURA es FABRIC pero TIPO esta vacio."
                )
            aula = fila_aula[idx] if idx < len(fila_aula) else None
            profesores_raw = fila_prof[idx] if idx < len(fila_prof) else None
            profesores = tuple(p.strip() for p in str(profesores_raw or "").split(",") if p.strip())
            clases.append(
                ClaseFabric(
                    dia=dia_actual,
                    inicio=hora_inicio_txt,
                    fin=hora_fin_txt,
                    tipo=tipo.strip(),
                    aula=aula,
                    grupos=(etiqueta,),
                    profesores=profesores,
                    fila_origen=r + 2,
                    columna_origen=col,
                    anotacion_fila1=anotaciones_fila1.get(col),
                )
            )
    return clases


def agrupar(clases: list[ClaseFabric]) -> list[dict]:
    """Une en una sola entrada las filas de ClaseFabric que comparten dia,
    hora de inicio/fin, tipo y aula -- igual que ya hace la pagina/el repo
    para desdobles. Avisa (no fusiona en silencio) si el mismo grupo aparece
    dos veces en la misma franja/aula: eso es o un desdoble legitimo mal
    marcado o un error de la sabana, y no se decide por intuicion aqui."""
    agrupadas: dict[tuple, dict] = {}
    avisos: list[str] = []

    # Las etiquetas que son nombres de persona se sustituyen por un seudonimo
    # antes de construir nada. A partir de aqui el nombre real no vuelve a
    # aparecer: ni en el JSON, ni en los avisos, ni en el log del pipeline.
    seudonimos = construir_seudonimos(g for c in clases for g in c.grupos)

    def publicable(etiqueta: str) -> str:
        return seudonimos.get(etiqueta, etiqueta)

    for c in clases:
        clave = (c.dia, c.inicio, c.fin, c.tipo, c.aula)
        entrada = agrupadas.setdefault(clave, {"dia": c.dia, "inicio": c.inicio, "fin": c.fin,
                                                 "tipo": c.tipo, "aula": c.aula, "_grupos": [],
                                                 "_profesores": set()})
        for g in c.grupos:
            etiqueta = publicable(g)
            if etiqueta in entrada["_grupos"]:
                avisos.append(
                    f"{c.dia} {c.inicio}-{c.fin} ({c.tipo}, aula {c.aula}): el grupo {etiqueta!r} "
                    f"aparece repetido en la misma franja (fila {c.fila_origen}, columna {c.columna_origen})."
                )
            else:
                entrada["_grupos"].append(etiqueta)
        entrada["_profesores"].update(c.profesores)
        if c.anotacion_fila1:
            # El texto de la fila 1 puede ser un origen ("PORTUGUESES") o un
            # nombre propio. No se reproduce: el aviso da la columna, que es
            # lo que hace falta para ir a mirarlo a la sabana.
            avisos.append(
                f"{c.dia} {c.inicio}-{c.fin} ({c.tipo}, aula {c.aula}), columna {c.columna_origen} "
                f"(grupo {publicable(c.grupos[0])!r}): la fila 1 de la sabana trae una anotacion en esta "
                "columna -- puede haber un cadete adicional en la franja; mirar esa columna en la "
                "sabana, no se ha asumido ninguna interpretacion."
            )
    resultado = []
    for entrada in agrupadas.values():
        resultado.append({
            "dia": entrada["dia"], "inicio": entrada["inicio"], "fin": entrada["fin"],
            "tipo": entrada["tipo"], "aula": entrada["aula"],
            "grupos": ", ".join(entrada["_grupos"]),
        })
    return resultado, avisos


if __name__ == "__main__":
    import json
    import sys

    ruta = sys.argv[1] if len(sys.argv) > 1 else None
    if not ruta:
        print("Uso: python import_fabric.py <ruta_al_excel.xlsm>", file=sys.stderr)
        raise SystemExit(2)
    clases = parse_fabric(ruta)
    agrupadas, avisos = agrupar(clases)
    agrupadas.sort(key=lambda c: (DIAS_VALIDOS.index(c["dia"]), c["inicio"]))
    print(json.dumps({"clases": agrupadas, "avisos": avisos}, ensure_ascii=False, indent=2))
