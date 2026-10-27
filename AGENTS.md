# Horarios FSTF 26-27 — entrada para herramientas de IA

Contexto común para cualquier modelo o herramienta que trabaje sobre este
repositorio. Léelo antes de tocar nada; el detalle está en los documentos
enlazados.

## Qué es

Web estática con el horario de Fundamentos de Sistemas y Tecnologías de
Fabricación (FSTF), curso 2026-27, servida por GitHub Pages:
`https://guillermolareo-art.github.io/Horarios-FSTF2627/artifact.html`.
La rama `main` es la que se publica. El repositorio es **público** a propósito
(Pages), así que todo lo que entra aquí es visible para cualquiera.

Hay dos caminos para actualizar `data/fstf-2627.json`:

1. **Automático.** `.github/workflows/update-fabric.yml` corre a diario, lee la
   sábana del correo (solo lectura), la importa con `scripts/import_fabric.py`
   y publica directamente en `main` sin revisión humana si pasa todas las
   comprobaciones.
2. **Manual, con cualquier modelo.** Ver [FLUJO-ACTUALIZACION.md](FLUJO-ACTUALIZACION.md):
   el contrato es `data/schedule.schema.json` y el modelo devuelve el JSON entero.

## Regla de privacidad — no negociable

Algunas columnas de la sábana no son un grupo sino **una persona** (un cadete
sin grupo asignado o un alumno de intercambio), y su etiqueta es un nombre
propio. Unido a día, hora y aula, eso dice dónde está una persona concreta a
cada hora. **Nunca** se publica un nombre: se sustituye por `Cadete 1`,
`Cadete 2`… (orden alfabético del nombre original, coherente en todo el archivo).

La regla se aplica en tres sitios, y los tres deben seguir de acuerdo:

- `scripts/import_fabric.py` → `agrupar()` seudonimiza antes de escribir
  (lista blanca: lo que no tiene forma de grupo se trata como persona).
- `scripts/validate-schedules.mjs` → rechaza cualquier etiqueta que no sea
  grupo colectivo o `Cadete N`. Corre en el job diario y en los PR. Su mensaje
  no repite la etiqueta, porque los logs de Actions son públicos.
- El prompt de `FLUJO-ACTUALIZACION.md`, para el camino manual.

Tampoco van aquí nombres reales en código, comentarios, tests ni mensajes de
commit, ni direcciones o textos de correo de otras personas. Los tests usan
nombres inventados. La correspondencia entre `Cadete N` y la persona no se
guarda en el repositorio: se mira en la sábana, que vive en el correo.

## Secretos

`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET` y `GMAIL_REFRESH_TOKEN` están en los
GitHub Secrets del repositorio. GitHub no permite leerlos y **no consta que haya
copia en otro sitio**. Por tanto: **no borrar ni recrear este repositorio**, ni
proponerlo como solución a nada. Se perderían los secretos, la configuración de
Pages y la URL publicada.

## Pendiente (27/10/2026)

Desde el commit `b6f6898` el contenido actual está limpio, pero **los commits
anteriores conservan datos personales**, igual que las ramas ya mergeadas
`auto/update-fabric` y `codex/modular-schedule` y las vistas de los PR #1–#4.
Plan acordado con el autor, **pendiente de su visto bueno explícito**:

1. Reescribir el historial con `git filter-repo --replace-text`, aplicando los
   mismos seudónimos que ya hay en `main` (la lista de sustituciones se escribe
   solo en local, nunca se versiona).
2. `push --force` sobre `main`; borrar las dos ramas mergeadas.
3. El autor borra las ejecuciones antiguas en la pestaña Actions.
4. El autor solicita a GitHub Support la purga de vistas en caché y referencias
   de los PR (procedimiento oficial de eliminación de datos sensibles).

Es irreversible: los identificadores de commit cambian y cualquier clon previo
debe volver a clonarse, no hacer `pull`. No ejecutarlo sin confirmación.

## Cómo trabajar y verificar

- Cambios mínimos. El autor ha invertido trabajo en que esto sea independiente
  del modelo: no reconstruir ni reorganizar lo que ya funciona.
- Antes de proponer cambios: `python -m pytest tests/` y `npm run validate-schedules`.
- Una actualización ordinaria de datos solo modifica el JSON del horario.
