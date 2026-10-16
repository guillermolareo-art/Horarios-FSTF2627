import { countTypes, findNextClass, minutes, scheduleDays, shortGroups, typeKey, weekCode } from "./schedule-model.js";

function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = String(text);
  return el;
}

export function createScheduleView(config, onWeekChange) {
  const ui = {
    title: document.getElementById("app-title"), subtitle: document.getElementById("subtitle"),
    weekLabel: document.getElementById("week-label"), source: document.getElementById("source-label"),
    updated: document.getElementById("updated-label"), checked: document.getElementById("checked-label"),
    tabs: document.getElementById("week-tabs"), banner: document.getElementById("provisional-banner"),
    history: document.getElementById("week-history-body"), nav: document.getElementById("day-nav"),
    days: document.getElementById("days"), print: document.getElementById("print-sheet")
  };
  const daysOrder = config.daysOrder || ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

  function renderTabs(schedule, view) {
    ui.tabs.replaceChildren();
    const next = schedule.proximaSemana;
    if (!next?.clases?.length) { ui.tabs.hidden = true; return; }
    ui.tabs.hidden = false;
    const current = node("button", view === "actual" ? "active" : "", `Semana actual · ${weekCode(schedule.archivo)}`);
    current.type = "button";
    current.addEventListener("click", () => onWeekChange("actual"));
    const upcoming = node("button", view === "proxima" ? "active" : "", `Semana ${weekCode(next.archivo)}`);
    upcoming.type = "button";
    if (next.provisional) upcoming.append(node("span", "tag", "Provisional"));
    upcoming.addEventListener("click", () => onWeekChange("proxima"));
    ui.tabs.append(current, upcoming);
  }

  function renderHistory(schedule) {
    ui.history.replaceChildren();
    const currentCode = weekCode(schedule.archivo);
    const appendRow = (label, counts, className = "") => {
      const row = node("tr", className);
      row.append(node("td", "", label));
      for (const type of ["teoria", "seminario", "laboratorio"]) row.append(node("td", "num", counts[type] || 0));
      ui.history.append(row);
    };
    (Array.isArray(schedule.historial) ? schedule.historial : [])
      .filter((row) => row.semana !== currentCode)
      .forEach((row) => appendRow(row.semana, row));
    appendRow(`${currentCode} (actual)`, countTypes(schedule.clases), "current");
    if (schedule.proximaSemana?.clases?.length) {
      const next = schedule.proximaSemana;
      appendRow(`${weekCode(next.archivo)} (${next.provisional ? "provisional" : "próxima"})`, countTypes(next.clases), "upcoming");
    }
  }

  function addClassCard(container, item, flags = {}) {
    const card = node("article", ["slot", flags.isNow && "is-now", flags.isPast && "is-past", flags.isNext && "is-next"].filter(Boolean).join(" "));
    if (flags.isNext) card.append(node("div", "next-tag", "PRÓXIMA CLASE"));
    const row = node("div", "slot-row1");
    const time = node("div", "t mono");
    time.append(document.createTextNode(item.inicio), node("span", "end", item.fin));
    const room = node("div", "room", "Aula ");
    room.append(node("b", "", item.aula ?? "—"));
    row.append(time, room);
    const details = node("div", "g");
    details.append(node("span", `badge ${typeKey(item.tipo)}`, item.tipo));
    details.append(document.createTextNode(shortGroups(item.grupos)));
    card.append(row, details);
    container.append(card);
  }

  function renderSchedule(schedule, preview) {
    const active = preview ? schedule.proximaSemana : schedule;
    const days = scheduleDays(active.clases, daysOrder);
    const now = new Date();
    const upcoming = preview ? null : findNextClass(days, now, daysOrder);
    ui.source.textContent = active.archivo || "—";
    ui.updated.textContent = active.actualizado || "—";
    ui.checked.textContent = schedule.comprobado || schedule.actualizado || "—";
    ui.weekLabel.replaceChildren(document.createTextNode(`${days.length} días con clase${preview ? " — vista previa" : " esta semana"}`));
    if (!preview && days.length && !upcoming.item) ui.weekLabel.append(node("p", "no-upcoming", "Ya no quedan clases programadas esta semana."));
    if (!days.length) ui.weekLabel.textContent = "Sin clases programadas esta semana.";
    ui.banner.hidden = !(preview && active.provisional);
    ui.banner.textContent = preview && active.provisional ? "Sábana provisional: puede sufrir cambios antes de que llegue esta semana." : "";
    ui.nav.replaceChildren();
    ui.days.replaceChildren();

    for (const [day, classes] of days) {
      const anchor = node("a", "", day);
      anchor.href = `#d-${encodeURIComponent(day)}`;
      ui.nav.append(anchor);
      const section = node("section", "day");
      section.id = `d-${day}`;
      const heading = node("h2", "", day);
      heading.append(node("span", "count", `${classes.length} clase${classes.length === 1 ? "" : "s"}`));
      section.append(heading);
      const dayIndex = daysOrder.indexOf(day);
      classes.forEach((item) => {
        const start = minutes(item.inicio);
        const end = minutes(item.fin);
        addClassCard(section, item, {
          isNow: !preview && dayIndex === upcoming?.todayIndex && upcoming.nowMinute >= start && upcoming.nowMinute < end,
          isPast: !preview && (dayIndex < upcoming?.todayIndex || (dayIndex === upcoming?.todayIndex && upcoming.nowMinute >= end)),
          isNext: !preview && upcoming?.day === day && upcoming.item === item
        });
      });
      ui.days.append(section);
    }
  }

  function renderPrintSheet(schedule) {
    const days = scheduleDays(schedule.clases, daysOrder);
    const table = node("table");
    table.append(node("caption", "", `Resumen días y horas · ${schedule.title || config.title}`));
    const head = node("thead");
    const headerRow = node("tr");
    days.forEach(([day]) => headerRow.append(node("th", "", day)));
    head.append(headerRow);
    const body = node("tbody");
    const maxRows = Math.max(0, ...days.map(([, classes]) => classes.length));
    for (let rowIndex = 0; rowIndex < maxRows; rowIndex += 1) {
      const row = node("tr");
      for (const [, classes] of days) {
        const item = classes[rowIndex];
        const cell = node("td");
        if (item) {
          cell.append(rowIndex === 0 ? node("span", "hora-borde", item.inicio) : document.createTextNode(item.inicio));
          cell.append(document.createTextNode(" - "));
          cell.append(rowIndex === classes.length - 1 ? node("span", "hora-borde", item.fin) : document.createTextNode(item.fin));
        }
        row.append(cell);
      }
      body.append(row);
    }
    table.append(head, body);
    const totalMinutes = schedule.clases.reduce((sum, item) => sum + minutes(item.fin) - minutes(item.inicio), 0);
    const meta = node("div", "meta", `Actualizado: ${schedule.actualizado} · ${schedule.clases.length} sesiones · ${Math.floor(totalMinutes / 60)}h ${totalMinutes % 60 ? `${totalMinutes % 60}min` : ""} lectivas`);
    const summary = node("div", "summary");
    summary.append(table, meta);
    ui.print.replaceChildren(summary);
  }

  return {
    render(schedule, view) {
      ui.title.textContent = schedule.title || config.title;
      ui.subtitle.textContent = schedule.subtitle || config.subtitle || "";
      renderTabs(schedule, view);
      renderHistory(schedule);
      renderSchedule(schedule, view === "proxima" && Boolean(schedule.proximaSemana?.clases?.length));
      renderPrintSheet(schedule);
    }
  };
}
