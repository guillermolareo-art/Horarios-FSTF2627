// Tests de la lógica de js/schedule-model.js con el runner propio de Node (sin dependencias).
// Ejecutar: npm run test-model
import test from "node:test";
import assert from "node:assert/strict";
import {
  countTypes, countingKey, individualOnlySessions, isCollectiveGroup, overlappingSessions,
} from "../js/schedule-model.js";

const lab = (dia, inicio, fin, grupos, aula = 50) =>
  ({ dia, inicio, fin, tipo: "LABORATORIO", aula, grupos });

test("detecta dos sesiones a la vez aunque estén en aulas distintas y sin grupos comunes", () => {
  // Es el caso que el detector del pipeline deja pasar (lo toma por un desdoble entre
  // profesores), pero aquí las dos sesiones son de la misma persona.
  const conflictos = overlappingSessions([
    lab("Martes", "14:35", "15:25", "IM1 (4 CIM-ST), IM2 (4 CIM-ST)", 50),
    lab("Martes", "14:35", "15:25", "Cadete 2", 45),
  ]);
  assert.equal(conflictos.length, 1);
  assert.equal(conflictos[0].day, "Martes");
});

test("detecta también solapamientos parciales, no solo franjas idénticas", () => {
  const conflictos = overlappingSessions([
    { dia: "Lunes", inicio: "08:15", fin: "10:00", tipo: "TEORIA", aula: 40, grupos: "G1 (4 CGA-ST)" },
    { dia: "Lunes", inicio: "09:10", fin: "10:00", tipo: "SEMINARIO", aula: 45, grupos: "G2 (4 CGA-ST)" },
  ]);
  assert.equal(conflictos.length, 1);
});

test("no marca como coincidencia dos sesiones consecutivas que solo se tocan", () => {
  assert.equal(overlappingSessions([
    lab("Lunes", "14:35", "15:25", "G1 (4 CGA-ST)"),
    lab("Lunes", "15:25", "16:15", "G1 (4 CGA-ST)"),
  ]).length, 0);
});

test("distingue grupo colectivo de alumno individual igual que el validador", () => {
  for (const etiqueta of ["G1", "G3B", "IM2", "G1 (4 CGA-ST)"]) {
    assert.equal(isCollectiveGroup(etiqueta), true, etiqueta);
  }
  for (const etiqueta of ["Cadete 1", "Cadete 12"]) {
    assert.equal(isCollectiveGroup(etiqueta), false, etiqueta);
  }
});

test("avisa de las horas montadas solo para alumnado individual", () => {
  const sesiones = [
    { dia: "Martes", inicio: "09:10", fin: "10:00", tipo: "TEORIA", aula: 45, grupos: "Cadete 3" },
    { dia: "Martes", inicio: "11:15", fin: "12:05", tipo: "TEORIA", aula: 45, grupos: "G5 (4 CGA-ST), Cadete 3" },
  ];
  const sueltas = individualOnlySessions(sesiones);
  assert.equal(sueltas.length, 1, "la que va acompañada de un grupo no debe avisar");
  assert.equal(sueltas[0].inicio, "09:10");
});

test("un bloque de laboratorio de dos horas seguidas cuenta como dos horas", () => {
  // Regresión: descontarlas dejó la semana 10B archivada con 4 horas en vez de 8.
  assert.equal(countTypes([
    lab("Lunes", "14:35", "15:25", "G3 (4 CGA-ST), G4 (4 CGA-ST)"),
    lab("Lunes", "15:30", "16:20", "G3 (4 CGA-ST), G4 (4 CGA-ST)"),
  ]).laboratorio, 2);
});

test("dos aulas a la misma hora son una sola hora, y la repetición en otro día no suma", () => {
  assert.equal(countTypes([
    lab("Martes", "14:35", "15:25", "IM1 (4 CIM-ST)", 50),
    lab("Martes", "14:35", "15:25", "Cadete 2", 45),
  ]).laboratorio, 1);
  assert.equal(countTypes([
    { dia: "Martes", inicio: "16:25", fin: "17:15", tipo: "SEMINARIO", grupos: "IM1 (4 CIM-ST)" },
    { dia: "Jueves", inicio: "08:15", fin: "09:05", tipo: "SEMINARIO", grupos: "IM1 (4 CIM-ST)" },
  ]).seminario, 1);
});

test("el examen parcial cuenta como teoría y el final no", () => {
  assert.equal(countingKey("EX. PARCIAL"), "teoria");
  assert.equal(countingKey("EX. FINAL"), null);
  assert.deepEqual(
    countTypes([
      { dia: "Jueves", inicio: "08:15", fin: "09:05", tipo: "EX. PARCIAL", grupos: "G1 (4 CGA-ST)" },
      { dia: "Jueves", inicio: "09:10", fin: "10:00", tipo: "EX. FINAL", grupos: "G1 (4 CGA-ST)" },
    ]),
    { teoria: 1, seminario: 0, laboratorio: 0 },
  );
});
