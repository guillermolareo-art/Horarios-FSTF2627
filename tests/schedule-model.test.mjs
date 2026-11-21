import test from "node:test";
import assert from "node:assert/strict";

import { classKey, concurrentGroups, filterPrintClasses, findFirstClass, findNextClass, scheduleDays } from "../js/schedule-model.js";

const daysOrder = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

test("elige la primera clase a partir del momento actual", () => {
  const days = scheduleDays([
    { dia: "Viernes", inicio: "08:15", fin: "09:05", tipo: "TEORIA", grupos: "G1", aula: 40 },
    { dia: "Viernes", inicio: "10:20", fin: "11:10", tipo: "SEMINARIO", grupos: "G2", aula: 56 },
  ], daysOrder);
  const result = findNextClass(days, new Date(2026, 10, 20, 9, 30), daysOrder);
  assert.equal(result.day, "Viernes");
  assert.equal(result.item.inicio, "10:20");
});

test("cuando ha terminado la semana actual toma la primera clase de la siguiente", () => {
  const finished = scheduleDays([
    { dia: "Viernes", inicio: "08:15", fin: "09:05", tipo: "TEORIA", grupos: "G1", aula: 40 },
  ], daysOrder);
  const noUpcoming = findNextClass(
    finished,
    new Date(2026, 10, 20, 12, 0),
    daysOrder,
  );
  assert.equal(noUpcoming.item, null);

  const nextWeek = scheduleDays([
    { dia: "Lunes", inicio: "14:35", fin: "15:25", tipo: "LABORATORIO", grupos: "G3", aula: 50 },
  ], daysOrder);
  assert.deepEqual(findFirstClass(nextWeek), {
    day: "Lunes",
    item: nextWeek[0][1][0],
  });
});

test("filtra sesiones excluidas sin mezclar franjas simultaneas", () => {
  const clases = [
    { dia: "Martes", inicio: "14:35", fin: "15:25", tipo: "LABORATORIO", grupos: "IM1", aula: 50 },
    { dia: "Martes", inicio: "14:35", fin: "15:25", tipo: "LABORATORIO", grupos: "Cadete 2", aula: 45 },
  ];
  const excluded = new Set([classKey(clases[1])]);
  assert.deepEqual(filterPrintClasses(clases, excluded), [clases[0]]);
});

test("agrupa sesiones simultaneas y mantiene distintas aulas y grupos", () => {
  const clases = [
    { dia: "Martes", inicio: "14:35", fin: "15:25", tipo: "LABORATORIO", grupos: "IM1, IM2", aula: 50 },
    { dia: "Martes", inicio: "14:35", fin: "15:25", tipo: "LABORATORIO", grupos: "Cadete 2", aula: 45 },
  ];
  const groups = concurrentGroups(clases);
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].items, clases);
});
