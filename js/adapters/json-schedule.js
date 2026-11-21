import { validateSchedule } from "../schedule-model.js?v=2026-11-21-print-1";

export async function readScheduleFile(file, config) {
  const value = JSON.parse(await file.text());
  const issue = validateSchedule(value, config);
  if (issue) throw new Error(issue);
  value.label ||= value.title;
  return value;
}
