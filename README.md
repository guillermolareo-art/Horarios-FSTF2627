# Horario FSTF 26-27

La página publicada sigue disponible en la misma dirección: <https://guillermolareo-art.github.io/Horarios-FSTF2627/artifact.html>. El repositorio es la única fuente de datos publicada; todos los dispositivos consultan la misma página y los mismos JSON.

## Diseño

- `artifact.html`: página que conserva la URL usada en el iPhone.
- `css/styles.css`: interfaz adaptable a móvil e impresión.
- `js/app.js`: carga del catálogo, entradas temporales y comprobación de actualizaciones publicadas.
- `js/schedule-model.js`: reglas y validación compartidas.
- `js/schedule-view.js`: presentación del horario, historial y vista de impresión.
- `js/adapters/json-schedule.js`: adaptador de entrada JSON; futuras fuentes se incorporan como adaptadores independientes.
- `config/config.json`: título, curso inicial y orden de los días.
- `data/catalog.json`: horarios disponibles.
- `data/fstf-2627.json`: única fuente de datos del horario actual y su próxima semana provisional.
- `data/schedule.schema.json`: formato común para cualquier modelo o herramienta.
- `.github/workflows/validate-schedules.yml`: comprueba los horarios en cada PR y después de cambios en `main`.

La página no contiene llamadas a Claude, ChatGPT ni a otro proveedor. Los archivos de datos se solicitan sin usar la copia local de caché; una página abierta comprueba cambios y se recarga al detectarlos. También tiene un botón para volver a cargar manualmente la versión publicada. Si se modifica la aplicación, se incrementa `appVersion` en `config/config.json` para que las páginas abiertas detecten la publicación.

## Actualizar con cualquier modelo

Sigue el procedimiento de [`FLUJO-ACTUALIZACION.md`](FLUJO-ACTUALIZACION.md). El modelo que esté disponible transforma la sábana nueva al JSON común. La actualización se revisa y se integra en GitHub; GitHub Pages la publica. Ningún modelo guarda una versión separada de la web.

## Vista local

Se necesita Node.js 22 para validar y Python para servir la vista local. Desde la raíz del repositorio:

```powershell
npm run validate-schedules
python -m http.server 8000
```

Abre `http://localhost:8000/artifact.html`. Para probar una actualización antes de proponerla, usa el selector **Previsualizar horarios JSON**. Esa vista previa solo vive en el navegador y no modifica la página pública.

## Publicación

La página usa rutas relativas, así que mantiene su funcionamiento bajo la ruta de proyecto de GitHub Pages. Integra los cambios en la rama que Pages publica después de que el control `Validate schedule data` termine correctamente. Hasta que se integre en esa rama, el iPhone y los demás dispositivos seguirán viendo la versión pública vigente.
