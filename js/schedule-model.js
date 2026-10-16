export const DEFAULT_DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

export function minutes(time) {
  if (typeof time !== "string" || !/^\d{1,2}:\d{2}$/.test(time)) return NaN;
  const [hour, minute] = time.split(":").map(Number);
  return hour * 60 + minute;
}

export function weekCode(filename = "") {
  return filename.match(/_(\d{1,2}[A-Za-z])_/)?.[1] || filename || "?";
}

export function shortGroups(groups = "") {
  return String(groups).split(",").map((group) => group.replace(/\s*\([^)]*\)\s*/g, "").trim()).join(", ");
}

export function typeKey(type = "") {
  const normalized = String(type).toUpperCase();
  return normalized.startsWith("SEM") ? "seminario" : normalized.startsWith("LAB") ? "laboratorio" : "teoria";
}

export function countTypes(classes = []) {
  const counts = { teoria: 0, seminario: 0, laboratorio: 0 };
  classes.forEach((item) => { counts[typeKey(item.tipo)] += 1; });
  return counts;
}

export function validateSchedule(value, config) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "La entrada debe ser un objeto JSON.";
  if (value.schemaVersion !== 1) return "“schemaVersion” debe ser 1; consulta el formato de entrada antes de actualizarlo.";
  for (const field of ["id", "title", "archivo", "actualizado"]) {
    if (typeof value[field] !== "string" || !value[field].trim()) return `Falta el campo de texto obligatorio “${field}”.`;
  }
  if (value.historial !== undefined && !Array.isArray(value.historial)) return "“historial” debe ser una lista.";
  for (const [index, row] of (value.historial || []).entries()) {
    if (!row || typeof row.semana !== "string" || [row.teoria, row.seminario, row.laboratorio].some((hours) => !Number.isFinite(hours) || hours < 0)) {
      return `El registro ${index + 1} del historial no tiene semana y horas válidas.`;
    }
  }
  if (!Array.isArray(value.clases)) return "“clases” debe ser una lista.";
  const validDays = new Set(config.daysOrder || DEFAULT_DAYS);
  const nextClasses = value.proximaSemana?.clases || [];
  if (value.proximaSemana && !Array.isArray(nextClasses)) return "“proximaSemana.clases” debe ser una lista.";
  for (const [index, item] of [...value.clases, ...nextClasses].entries()) {
    if (!item || typeof item !== "object") return `La clase ${index + 1} no es un objeto.`;
    if (!validDays.has(item.dia)) return `La clase ${index + 1} tiene un día desconocido: ${item.dia || "(vacío)"}.`;
    if (!Number.isFinite(minutes(item.inicio)) || !Number.isFinite(minutes(item.fin)) || minutes(item.fin) <= minutes(item.inicio)) {
      return `La clase ${index + 1} tiene un intervalo horario no válido.`;
    }
    for (const field of ["tipo", "grupos"]) {
      if (typeof item[field] !== "string") return `Falta “${field}” en la clase ${index + 1}.`;
    }
  }
  return null;
}

export function scheduleDays(classes, daysOrder = DEFAULT_DAYS) {
  const grouped = new Map();
  classes.forEach((item) => {
    if (!grouped.has(item.dia)) grouped.set(item.dia, []);
    grouped.get(item.dia).push(item);
  });
  for (const items of grouped.values()) items.sort((a, b) => minutes(a.inicio) - minutes(b.inicio));
  return daysOrder.filter((day) => grouped.has(day)).map((day) => [day, grouped.get(day)]);
}

// Devuelve solo una sesión futura dentro de la semana que se está mostrando.
// No envuelve de vuelta al principio: así no marca como próxima una clase pasada.
export function findNextClass(days, now, daysOrder = DEFAULT_DAYS) {
  const today = daysOrder[(now.getDay() + 6) % 7];
  const todayIndex = daysOrder.indexOf(today);
  const nowMinute = now.getHours() * 60 + now.getMinutes();
  for (const [day, classes] of days) {
    const dayIndex = daysOrder.indexOf(day);
    const item = classes.find((candidate) => (dayIndex === todayIndex && minutes(candidate.inicio) >= nowMinute) || dayIndex > todayIndex);
    if (item) return { day, item, today, todayIndex, nowMinute };
  }
  return { day: null, item: null, today, todayIndex, nowMinute };
}
