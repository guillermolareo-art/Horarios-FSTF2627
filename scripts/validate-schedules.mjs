import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { validateSchedule } from "../js/schedule-model.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const readJson = async (relativePath) => JSON.parse(await readFile(path.join(root, relativePath), "utf8"));
const config = await readJson("config/config.json");
const catalog = await readJson("data/catalog.json");
if (!Array.isArray(catalog.schedules) || catalog.schedules.length === 0) throw new Error("El catálogo no contiene horarios.");

for (const entry of catalog.schedules) {
  if (!entry.id || !entry.path) throw new Error("Cada entrada del catálogo necesita id y path.");
  const absolutePath = path.resolve(root, entry.path);
  if (!absolutePath.startsWith(`${root}${path.sep}`)) throw new Error(`Ruta fuera del proyecto en catálogo: ${entry.path}`);
  const schedule = JSON.parse(await readFile(absolutePath, "utf8"));
  const issue = validateSchedule(schedule, config);
  if (issue) throw new Error(`${entry.path}: ${issue}`);
  console.log(`OK ${entry.id}: ${schedule.clases.length} sesiones actuales${schedule.proximaSemana?.clases?.length ? ` y ${schedule.proximaSemana.clases.length} próximas` : ""}`);
}
