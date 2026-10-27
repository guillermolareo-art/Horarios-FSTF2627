import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateSchedule } from "../js/schedule-model.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const readJson = async (relativePath) => JSON.parse(await readFile(path.join(root, relativePath), "utf8"));
const config = await readJson("config/config.json");

// Privacidad: un grupo publicado solo puede ser un grupo colectivo (G1, G3B,
// IM2, "G1 (4 CGA-ST)") o un seudonimo "Cadete N". Cualquier otra etiqueta
// puede ser el nombre de una persona y bloquea la publicacion, venga el JSON
// del importador o de un modelo. Mismo criterio que scripts/import_fabric.py.
// El mensaje NO repite la etiqueta: este log es publico.
const ETIQUETA_PUBLICABLE = /^(?:(?:G\d+[AB]?|IM\d+)(?:\s*\(.*\))?|Cadete \d+)$/i;
const etiquetasNoPublicables = (clases = []) =>
  clases.flatMap((c) =>
    String(c.grupos ?? "")
      .split(",")
      .map((g) => g.trim())
      .filter((g) => g && !ETIQUETA_PUBLICABLE.test(g))
      .map(() => `${c.dia} ${c.inicio}`),
  );
const catalog = await readJson("data/catalog.json");
if (!Array.isArray(catalog.schedules) || catalog.schedules.length === 0) throw new Error("El catálogo no contiene horarios.");

for (const entry of catalog.schedules) {
  if (!entry.id || !entry.path) throw new Error("Cada entrada del catálogo necesita id y path.");
  const absolutePath = path.resolve(root, entry.path);
  if (!absolutePath.startsWith(`${root}${path.sep}`)) throw new Error(`Ruta fuera del proyecto en catálogo: ${entry.path}`);
  const schedule = JSON.parse(await readFile(absolutePath, "utf8"));
  const issue = validateSchedule(schedule, config);
  if (issue) throw new Error(`${entry.path}: ${issue}`);
  const sospechosas = [
    ...etiquetasNoPublicables(schedule.clases),
    ...etiquetasNoPublicables(schedule.proximaSemana?.clases),
  ];
  if (sospechosas.length) {
    throw new Error(
      `${entry.path}: ${sospechosas.length} etiqueta(s) de grupo no reconocidas (${sospechosas.join("; ")}). ` +
        "Si es una persona, sustituirla por 'Cadete N'; si es un grupo nuevo, ampliar el patron aqui y en import_fabric.py.",
    );
  }
  console.log(`OK ${entry.id}: ${schedule.clases.length} sesiones actuales${schedule.proximaSemana?.clases?.length ? ` y ${schedule.proximaSemana.clases.length} próximas` : ""}`);
}
