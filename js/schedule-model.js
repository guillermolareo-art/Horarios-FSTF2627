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

// Una etiqueta de "grupos" es o un grupo colectivo (G1, G3B, IM2, con o sin el paréntesis de
// curso) o un alumno individual seudonimizado ("Cadete N"). Mismo criterio que el de
// scripts/validate-schedules.mjs: si los dos se separan, estos avisos dejan de ser fiables.
const COLLECTIVE_GROUP = /^(?:G\d+[AB]?|IM\d+)(?:\s*\(.*\))?$/i;

export function splitGroups(groups = "") {
  return String(groups).split(",").map((label) => label.trim()).filter(Boolean);
}

export function isCollectiveGroup(label = "") {
  return COLLECTIVE_GROUP.test(String(label).trim());
}

// Sesiones de una misma semana que se pisan en el tiempo dentro del mismo día.
// Diferencia importante con detectar_solapamientos() de scripts/merge_schedule.py: aquel solo
// avisa si las dos sesiones comparten aula o algún grupo, porque asume que dos clases a la vez
// en aulas distintas son desdobles legítimos ENTRE profesores. Aquí todas las sesiones del
// horario son de la misma persona, así que dos a la vez son imposibles de atender compartan
// aula o no — que es justo el caso que se escapaba. Por eso esto es un aviso de la vista y no
// un bloqueo del pipeline: el horario se sigue publicando, pero el problema se ve.
export function overlappingSessions(classes = [], daysOrder = DEFAULT_DAYS) {
  const conflicts = [];
  for (const [day, items] of scheduleDays(classes, daysOrder)) {
    for (let i = 0; i < items.length; i += 1) {
      for (let j = i + 1; j < items.length; j += 1) {
        const [a, b] = [items[i], items[j]];
        if (minutes(a.inicio) < minutes(b.fin) && minutes(b.inicio) < minutes(a.fin)) {
          conflicts.push({ day, a, b });
        }
      }
    }
  }
  return conflicts;
}

// Sesiones cuyo alumnado es SOLO individual: ningún grupo colectivo, únicamente alumnos
// sueltos. Son horas montadas para una o varias personas concretas; conviene verlas pronto
// porque suelen ser el origen de las coincidencias y de horas de clase individuales que no
// estaban previstas.
export function individualOnlySessions(classes = []) {
  return (classes || []).filter((item) => {
    const labels = splitGroups(item.grupos);
    return labels.length > 0 && !labels.some(isCollectiveGroup);
  });
}

// Cubo del recuento semanal al que va una sesión, o null si sus horas no deben sumarse.
// Regla confirmada por el autor (19/11/2026): los exámenes PARCIALES cuentan como teoría
// (ocupan horas de teoría de la asignatura); el examen FINAL no, porque tiene horas propias
// dedicadas en el control de horas de firma. Cualquier otro tipo desconocido cae en "teoria":
// mejor que una hora rara se vea en el recuento a que desaparezca en silencio.
// typeKey() se mantiene aparte porque la vista lo usa para las clases CSS de los badges.
export function countingKey(type = "") {
  const normalized = String(type).toUpperCase();
  if (normalized.startsWith("SEM")) return "seminario";
  if (normalized.startsWith("LAB")) return "laboratorio";
  if (normalized.includes("FINAL")) return null;
  return "teoria";
}

// Recuento semanal "de verdad". Misma lógica, deliberadamente idéntica, que
// _contar_por_tipo() de scripts/merge_schedule.py, para que el recuento que se ve en pantalla
// y el que se archiva en el historial no se separen. Hace dos ajustes, y solo dos:
//   1) Franjas simultáneas: dos filas a la misma hora del mismo día (un laboratorio partido en
//      dos aulas, o dos grupos en paralelo) son una sola hora para una persona.
//   2) Repetición en otro día: si un grupo tiene seminario o laboratorio en más de un DÍA
//      (duplicidad típica de la sábana), solo cuenta la primera aparición cronológica.
// La repetición del mismo grupo en el MISMO día sí cuenta: los laboratorios se dan en bloques
// de horas seguidas y cada una es real. Descontarlas dejó la semana 10B en 4 horas en vez de 8.
export function countTypes(classes = [], daysOrder = DEFAULT_DAYS) {
  const counts = { teoria: 0, seminario: 0, laboratorio: 0 };
  const seen = { seminario: new Map(), laboratorio: new Map() };
  const countedSlots = new Set();
  const ordered = [...classes].sort((a, b) =>
    daysOrder.indexOf(a.dia) - daysOrder.indexOf(b.dia) || minutes(a.inicio) - minutes(b.inicio));
  ordered.forEach((item) => {
    if (item.propia === false) return; // sesión marcada como de otro profesor
    const key = countingKey(item.tipo);
    if (key === null) return;
    const slot = `${key}||${item.dia}||${item.inicio}||${item.fin}`;
    if (countedSlots.has(slot)) return;
    if (key === "teoria") { counts.teoria += 1; countedSlots.add(slot); return; }
    const groups = shortGroups(item.grupos).split(",").map((g) => g.trim().toUpperCase()).filter(Boolean);
    const seenType = seen[key];
    const isRealHour = groups.length === 0 || groups.some((g) => !seenType.has(g) || seenType.get(g) === item.dia);
    if (isRealHour) { counts[key] += 1; countedSlots.add(slot); }
    groups.forEach((g) => { if (!seenType.has(g)) seenType.set(g, item.dia); });
  });
  return counts;
}

export function validateSchedule(value, config) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return "La entrada debe ser un objeto JSON.";
  if (value.schemaVersion !== 1) return "“schemaVersion” debe ser 1; consulta el formato de entrada antes de actualizarlo.";
  for (const field of ["id", "title", "archivo", "actualizado"]) {
    if (typeof value[field] !== "string" || !value[field].trim()) return `Falta el campo de texto obligatorio “${field}”.`;
  }
  if (value.provisional !== undefined && typeof value.provisional !== "boolean") return "“provisional” debe ser un valor booleano.";
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
    if (item.propia !== undefined && typeof item.propia !== "boolean") return `“propia” no es válido en la clase ${index + 1}.`;
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

export function findFirstClass(days) {
  for (const [day, classes] of days) {
    if (classes.length) return { day, item: classes[0] };
  }
  return { day: null, item: null };
}

export function classKey(item) {
  return [
    item.dia,
    item.inicio,
    item.fin,
    item.tipo,
    item.aula ?? "",
    item.grupos,
  ].join("|");
}

export function filterPrintClasses(classes, excludedKeys) {
  return (classes || []).filter((item) => !excludedKeys.has(classKey(item)));
}

export function concurrentGroups(classes) {
  const groups = [];
  const lookup = new Map();
  for (const item of classes || []) {
    const key = `${item.inicio}|${item.fin}`;
    if (!lookup.has(key)) {
      const group = { inicio: item.inicio, fin: item.fin, items: [] };
      lookup.set(key, group);
      groups.push(group);
    }
    lookup.get(key).items.push(item);
  }
  return groups.sort((a, b) => minutes(a.inicio) - minutes(b.inicio));
}

export function groupConsecutiveLaboratories(classes) {
  const result = [];
  for (const item of classes || []) {
    const current = result[result.length - 1];
    if (
      current
      && String(item.tipo).toUpperCase().startsWith("LAB")
      && String(current.tipo).toUpperCase().startsWith("LAB")
      && String(item.aula ?? "") === String(current.aula ?? "")
      && String(item.grupos).trim() === String(current.grupos).trim()
      && minutes(item.inicio) >= minutes(current.fin)
      && minutes(item.inicio) - minutes(current.fin) <= 15
    ) {
      const firstKey = classKey(current);
      const secondKey = classKey(item);
      current.fin = item.fin;
      current._sourceKeys = [
        ...(current._sourceKeys || [firstKey]),
        secondKey,
      ];
    } else {
      result.push({ ...item });
    }
  }
  return result;
}
