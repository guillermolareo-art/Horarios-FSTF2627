import test from "node:test";
import assert from "node:assert/strict";

import { findFirstClass, findNextClass, scheduleDays } from "../js/schedule-model.js";

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
