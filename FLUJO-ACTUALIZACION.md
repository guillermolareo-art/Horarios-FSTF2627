# Flujo de actualización independiente del modelo

## Una vez por actualización

1. Reúne la sábana de horarios nueva y la versión vigente de `data/fstf-2627.json` desde la rama publicada. El JSON vigente conserva el historial y la semana provisional.
2. Usa cualquier modelo que pueda leer la sábana. Pídele que devuelva el JSON completo del contrato `data/schedule.schema.json`, preservando el historial existente y sustituyendo los horarios correspondientes. No hace falta que el modelo tenga conexión con GitHub.
3. Comprueba el resultado con `npm run validate-schedules`, o cárgalo en **Previsualizar horarios JSON** en una vista local para revisar los días, horas, aulas y grupos.
4. Propón el cambio de `data/fstf-2627.json` en una rama y un pull request. Espera a que `Validate schedule data` indique que pasó; después integra el PR en la rama que publica GitHub Pages.
5. La página conserva la URL actual. Los móviles que ya la tengan abierta detectan el JSON nuevo y recargan; también se puede tocar **Volver a la versión publicada**.

## Prompt reutilizable

> Actualiza el horario a partir de la sábana adjunta. Usa `data/fstf-2627.json` como estado vigente y `data/schedule.schema.json` como contrato. Devuelve un archivo JSON completo que cumpla el esquema, con `schemaVersion: 1`. Conserva el historial y las sesiones no afectadas; actualiza la semana actual y, si la sábana incluye la siguiente, represéntala en `proximaSemana` e indica si es provisional. No inventes horas, aulas, grupos ni fechas. Conserva las sesiones simultáneas como filas separadas. Si encuentras contradicciones o datos ambiguos, no los resuelvas por intuición: enumera las dudas para revisarlas. No modifiques la aplicación, la configuración, el catálogo ni otros cursos para una actualización normal. **Privacidad:** algunas columnas de la sábana no son un grupo sino una persona (un cadete sin grupo o un alumno de intercambio). Nunca escribas su nombre en el JSON ni en tu respuesta: sustitúyelo por `Cadete 1`, `Cadete 2`… numerados por orden alfabético del nombre original y usados de forma coherente en todo el archivo. Las únicas etiquetas de grupo válidas son G1–G6 (con desdoble A/B), IM1 e IM2, con su curso entre paréntesis.

La validación (`npm run validate-schedules` y la comprobación del PR) rechaza cualquier etiqueta de grupo que no sea un grupo colectivo o un `Cadete N`. Si salta, no la desactives: revisa qué columna de la sábana la ha producido.

## Qué queda desacoplado

- **Modelo:** el contrato JSON es la interfaz común. Si se agota el límite de un proveedor, otro modelo puede producir el mismo archivo.
- **Publicación:** GitHub Pages sirve una única versión desde el repositorio; los dispositivos no alojan copias que haya que sincronizar manualmente.
- **Datos:** una actualización ordinaria modifica solo el JSON del horario. Añadir cursos implica añadir un JSON y una entrada al catálogo.
- **Nuevas fuentes:** si se quiere convertir Excel/CSV sin pedirle esa conversión a un modelo, se añade un adaptador específico. Ese trabajo no es necesario para cambiar de modelo.

La carga temporal del selector sirve para revisar un archivo antes de proponerlo; no publica ni guarda cambios por sí sola. Una actualización normal de datos no cambia el código ni `appVersion`.
