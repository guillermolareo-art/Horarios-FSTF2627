import { validateSchedule } from "../schedule-model.js";

export async function readScheduleFile(file, config) {
  const value = JSON.parse(await file.text());
  const issue = validateSchedule(value, config);
  if (issue) throw new Error(issue);
  value.label ||= value.title;
  return value;
}
