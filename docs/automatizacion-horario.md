# Automatización autónoma del horario

La actualización programada se ejecuta en GitHub Actions con código
determinista. No llama a Claude ni a ningún otro modelo o agente.

## Flujo automático

`.github/workflows/update-fabric.yml` consulta Gmail en días lectivos. El
workflow está programado cada hora en UTC y `scripts/pipeline.py` aplica la
ventana configurada en `Europe/Madrid`: lunes desde las 12:00, martes-jueves
de 08:00 a 21:00 y viernes de 08:00 a 12:00. El disparo manual desde Actions
no tiene esa restricción.

El pipeline:

1. Busca sábanas con adjuntos Excel o PDF y clasifica la semana, la fecha y el
   carácter provisional/definitivo a partir del correo.
2. Importa las hojas Excel con `scripts/import_fabric.py` y los PDF con
   `scripts/import_fabric_pdf.py`. Una extracción PDF incompleta o dudosa se
   detiene; no publica datos aproximados.
3. Seudonimiza etiquetas individuales como `Cadete N`, valida horas y
   solapamientos, evita degradar una versión definitiva y conserva el
   historial.
4. Cuando termina la última clase de la semana (o llega el sábado), promueve
   la semana siguiente si está disponible.
5. Valida el JSON y lo publica en `main`. GitHub Pages sirve esa versión.
6. Si una sábana nueva se ha aplicado y el horario cambió, envía una única
   notificación a ntfy después de que el `push` haya terminado correctamente.
   Las ejecuciones sin novedades, el cierre automático de semana y las sábanas
   ignoradas no envían notificaciones.

Los cambios comunicados solo en texto libre no se detectan ni se convierten en
sesiones automáticamente. Deben revisarse manualmente y reflejarse en una
sábana Excel o PDF. El flujo no interpreta instrucciones de correo mediante
heurísticas.

Después de publicar, la tarea de Drive genera un PDF A4 de una página desde la
web y actualiza el Excel de control al cerrar semanas. El Excel se edita de
forma conservadora: verifica la fila esperada, no sobrescribe celdas ocupadas
con valores diferentes, guarda una versión nueva por semana y fuerza el
recalculo de fórmulas.

## Configuración necesaria

El acceso a Gmail ya usa los secretos `GMAIL_CLIENT_ID`,
`GMAIL_CLIENT_SECRET` y `GMAIL_REFRESH_TOKEN`. Para Drive:

1. Habilita Google Drive API y crea una cuenta de servicio dedicada a esta
   automatización.
2. Comparte únicamente la carpeta de entrega con el correo de esa cuenta y
   dale permiso de editor. No compartas toda la unidad ni otras carpetas. El
   cliente usa el ámbito de Drive API; limita el acceso efectivo compartiendo
   solo esta carpeta con la cuenta dedicada.
3. Guarda el JSON de credenciales de la cuenta como secreto
   `DRIVE_SERVICE_ACCOUNT_JSON`, y el identificador de esa carpeta como
   `DRIVE_FOLDER_ID`.
4. Configura `CONTROL_OWNER_LABEL` con el texto de la celda de responsable del
   Excel y `SCHEDULE_OWNER_ID` con el identificador del profesor tal como
   aparece en la sábana. Ambos valores van en GitHub Secrets, nunca en el
   repositorio. Se usan para verificar la fila y excluir del cómputo las
   sesiones asignadas a otro profesor cuando la sábana lo indica.
5. Deja `ENABLE_DRIVE_SYNC` sin configurar (o distinto de `true`), ejecuta
   manualmente **Update FABRIC schedule from Gmail** y comprueba la publicación
   en Actions y la web.
6. Desactiva la tarea antigua de Claude y crea la variable de Actions
   `ENABLE_DRIVE_SYNC=true`. Ejecuta el workflow manualmente y comprueba el PDF
   y el Excel en la carpeta compartida antes de dar por terminada la transición.
7. Para las notificaciones, configura un tópico aleatorio y poco predecible
   como secreto `NTFY_TOPIC`. Si el servidor exige autenticación, añade también
   el secreto opcional `NTFY_TOKEN`. Suscríbete al tópico desde la app ntfy.
   El workflow publica en `https://ntfy.sh`; no incluye nombres, aulas ni datos
   del horario en el mensaje.

Si `ENABLE_DRIVE_SYNC` no vale `true`, la actualización de la web sigue
funcionando y Drive no se consulta. Si faltan secretos de Drive después de
habilitar la variable, la sincronización se omite con un aviso. Los errores de
autenticación, los conflictos de celdas o un PDF que no cabe en una página
detienen esa sincronización sin modificar el Excel existente.

El envío a ntfy no se reintenta: si falla, la publicación web ya realizada
permanece y Actions marca el paso como fallido. No se volverá a notificar en
ejecuciones posteriores sin una nueva sábana publicada. La tarea antigua de
Claude es externa; desactiva allí sus notificaciones para evitar duplicados.

## Transición desde la tarea anterior

La tarea programada antigua de Claude es externa al repositorio y este
workflow no puede desactivarla. Primero valida la publicación web con
`ENABLE_DRIVE_SYNC` desactivado; luego desactiva la tarea antigua y solo después
activa Drive para evitar escrituras duplicadas. La publicación web de este
repositorio se hace mediante GitHub Pages, no mediante un Artifact de Claude.
