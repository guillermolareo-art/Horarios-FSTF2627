import { readScheduleFile } from "./adapters/json-schedule.js";
import { validateSchedule } from "./schedule-model.js";
import { createScheduleView } from "./schedule-view.js";

const selector = document.getElementById("schedule-select");
const fileInput = document.getElementById("schedule-files");
const errorBox = document.getElementById("input-error");
const reloadButton = document.getElementById("reload-button");
const title = document.getElementById("app-title");
const subtitle = document.getElementById("subtitle");

let config;
let schedules = new Map();
let selectedScheduleId;
let weekView = "actual";
let view;
let publishedSnapshot = new Map();

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function render() {
  const schedule = schedules.get(selectedScheduleId);
  if (schedule) view.render(schedule, weekView);
}

function refreshScheduleOptions() {
  selector.replaceChildren();
  for (const [id, schedule] of schedules) {
    const option = document.createElement("option");
    option.value = id;
    option.textContent = schedule.label || schedule.title || id;
    selector.append(option);
  }
  if (schedules.has(selectedScheduleId)) selector.value = selectedScheduleId;
}

async function importFiles(files) {
  errorBox.hidden = true;
  const loaded = [];
  try {
    for (const file of files) loaded.push(await readScheduleFile(file, config));
  } catch (error) {
    showError(`${files[loaded.length]?.name || "Archivo JSON"}: ${error.message}`);
    fileInput.value = "";
    return;
  }
  loaded.forEach((schedule) => schedules.set(schedule.id, schedule));
  if (loaded.length) {
    selectedScheduleId = loaded.at(-1).id;
    weekView = "actual";
    refreshScheduleOptions();
    render();
  }
  fileInput.value = "";
}

async function start() {
  const [configText, catalogText] = await Promise.all([
    fetch("config/config.json", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`No se pudo leer config/config.json (${response.status}).`);
      return response.text();
    }),
    fetch("data/catalog.json", { cache: "no-store" }).then((response) => {
      if (!response.ok) throw new Error(`No se pudo leer data/catalog.json (${response.status}).`);
      return response.text();
    })
  ]);
  const loadedConfig = JSON.parse(configText);
  const catalog = JSON.parse(catalogText);
  publishedSnapshot.set("config/config.json", configText);
  publishedSnapshot.set("data/catalog.json", catalogText);
  config = loadedConfig;
  title.textContent = config.title || "Horario";
  subtitle.textContent = config.subtitle || "";
  view = createScheduleView(config, (nextView) => { weekView = nextView; render(); });
  const entries = await Promise.all(catalog.schedules.map(async (entry) => {
    const response = await fetch(entry.path, { cache: "no-store" });
    if (!response.ok) throw new Error(`No se pudo leer ${entry.path} (${response.status}).`);
    const scheduleText = await response.text();
    publishedSnapshot.set(entry.path, scheduleText);
    const schedule = JSON.parse(scheduleText);
    const issue = validateSchedule(schedule, config);
    if (issue) throw new Error(`${entry.path}: ${issue}`);
    schedule.label ||= entry.label;
    return [entry.id, schedule];
  }));
  schedules = new Map(entries);
  selectedScheduleId = schedules.has(config.defaultScheduleId) ? config.defaultScheduleId : entries[0]?.[0];
  refreshScheduleOptions();
  selector.addEventListener("change", () => { selectedScheduleId = selector.value; weekView = "actual"; render(); });
  fileInput.addEventListener("change", (event) => importFiles([...event.target.files]));
  reloadButton.addEventListener("click", () => window.location.reload());
  render();
  startUpdateMonitor(catalog);
}

function startUpdateMonitor(catalog) {
  let checking = false;
  const checkForPublishedUpdate = async () => {
    if (checking || document.visibilityState === "hidden") return;
    checking = true;
    try {
      for (const [path, url] of [["config/config.json", "config/config.json"], ["data/catalog.json", "data/catalog.json"]]) {
        const response = await fetch(url, { cache: "no-store" });
        if (response.ok && await response.text() !== publishedSnapshot.get(path)) {
          window.location.reload();
          return;
        }
      }
      for (const entry of catalog.schedules) {
        const response = await fetch(entry.path, { cache: "no-store" });
        if (response.ok && await response.text() !== publishedSnapshot.get(entry.path)) {
          window.location.reload();
          return;
        }
      }
    } catch {
      // Una interrupción breve de red se vuelve a comprobar en el siguiente ciclo.
    } finally {
      checking = false;
    }
  };
  window.setInterval(checkForPublishedUpdate, 120000);
  document.addEventListener("visibilitychange", checkForPublishedUpdate);
}

start().catch((error) => {
  showError(`No se pudo cargar el horario: ${error.message} Abre la carpeta mediante un servidor web local y revisa su configuración y catálogo.`);
});
