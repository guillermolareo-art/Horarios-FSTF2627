import { classKey, countTypes, filterPrintClasses, findFirstClass, findNextClass, minutes, scheduleDays, shortGroups, typeKey, weekCode } from "./schedule-model.js?v=2026-11-21-print-1";

function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined && text !== null) el.textContent = String(text);
  return el;
}

export function createScheduleView(config, onWeekChange) {
  const excludedPrintKeys = new Set();
  let printSchedule = null;
  let printPreview = false;
  const ui = {
    title: document.getElementById("app-title"), subtitle: document.getElementById("subtitle"),
    weekLabel: document.getElementById("week-label"), source: document.getElementById("source-label"),
    updated: document.getElementById("updated-label"), checked: document.getElementById("checked-label"),
    tabs: document.getElementById("week-tabs"), banner: document.getElementById("provisional-banner"),
    history: document.getElementById("week-history-body"), nav: document.getElementById("day-nav"),
    days: document.getElementById("days"), print: document.getElementById("print-sheet"),
    selectAllPrint: document.getElementById("select-all-print"),
    selectNonePrint: document.getElementById("select-none-print"),
    printSelected: document.getElementById("print-selected")
  };
  const daysOrder = config.daysOrder || ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];

  function activeClassesForPrint() {
    if (!printSchedule) return [];
    return (printPreview ? printSchedule.proximaSemana : printSchedule)?.clases || [];
  }

  ui.selectAllPrint?.addEventListener("click", () => {
    activeClassesForPrint().forEach((item) => excludedPrintKeys.delete(classKey(item)));
    document.querySelectorAll(".print-select input").forEach((checkbox) => { checkbox.checked = true; });
    if (printSchedule) renderPrintSheet(printSchedule, printPreview);
  });
  ui.selectNonePrint?.addEventListener("click", () => {
    activeClassesForPrint().forEach((item) => excludedPrintKeys.add(classKey(item)));
    document.querySelectorAll(".print-select input").forEach((checkbox) => { checkbox.checked = false; });
    if (printSchedule) renderPrintSheet(printSchedule, printPreview);
  });
  ui.printSelected?.addEventListener("click", () => {
    if (typeof window.print === "function") window.print();
  });

  function renderTabs(schedule, view) {
    ui.tabs.replaceChildren();
    const next = schedule.proximaSemana;
    if (!next?.clases?.length) { ui.tabs.hidden = true; return; }
    ui.tabs.hidden = false;
    const current = node("button", view === "actual" ? "active" : "", `Semana actual · ${weekCode(schedule.archivo)}`);
    current.type = "button";
    if (schedule.provisional) current.append(node("span", "tag", "Provisional"));
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
    appendRow(`${currentCode} (${schedule.provisional ? "actual provisional" : "actual"})`, countTypes(schedule.clases), "current");
    if (schedule.proximaSemana?.clases?.length) {
      const next = schedule.proximaSemana;
      appendRow(`${weekCode(next.archivo)} (${next.provisional ? "provisional" : "próxima"})`, countTypes(next.clases), "upcoming");
    }
  }

  function addClassCard(container, item, flags = {}, onSelectionChange) {
    const card = node("article", ["slot", flags.isNow && "is-now", flags.isPast && "is-past", flags.isNext && "is-next"].filter(Boolean).join(" "));
    if (flags.isNext) card.append(node("div", "next-tag", "PRÓXIMA CLASE"));
    const selection = node("label", "print-select");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.checked = !excludedPrintKeys.has(classKey(item));
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) excludedPrintKeys.delete(classKey(item));
      else excludedPrintKeys.add(classKey(item));
      onSelectionChange?.();
    });
    selection.append(checkbox, document.createTextNode(" Incluir al imprimir"));
    card.append(selection);
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
    let upcoming = preview ? null : findNextClass(days, now, daysOrder);
    let upcomingNextWeek = null;
    if (!preview && !upcoming.item && schedule.proximaSemana?.clases?.length) {
      const nextDays = scheduleDays(schedule.proximaSemana.clases, daysOrder);
      const first = findFirstClass(nextDays);
      if (first.item) upcomingNextWeek = first;
    }
    ui.source.textContent = active.archivo || "—";
    ui.updated.textContent = active.actualizado || "—";
    ui.checked.textContent = schedule.comprobado || schedule.actualizado || "—";
    ui.weekLabel.replaceChildren(document.createTextNode(`${days.length} días con clase${preview ? " — vista previa" : " esta semana"}`));
    if (!preview && upcomingNextWeek?.item) {
      const next = upcomingNextWeek;
      ui.weekLabel.append(node(
        "p",
        "no-upcoming",
        `Próxima clase: ${next.day} ${next.item.inicio}–${next.item.fin} · Aula ${next.item.aula ?? "—"} · ${weekCode(schedule.proximaSemana.archivo)}`
      ));
    } else if (!preview && days.length && !upcoming.item) {
      ui.weekLabel.append(node("p", "no-upcoming", "Ya no quedan clases programadas esta semana."));
    }
    if (!days.length) ui.weekLabel.textContent = "Sin clases programadas esta semana.";
    ui.banner.hidden = !active.provisional;
    ui.banner.textContent = active.provisional
      ? preview
        ? "Sábana provisional: puede sufrir cambios antes de que llegue esta semana."
        : "Horario actual basado en una sábana provisional; puede sufrir cambios."
      : "";
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
        }, () => renderPrintSheet(schedule, preview));
      });
      ui.days.append(section);
    }
  }

  function renderPrintSheet(schedule, preview = false) {
    printSchedule = schedule;
    printPreview = preview;
    const active = preview ? schedule.proximaSemana : schedule;
    const selectedClasses = filterPrintClasses(active?.clases || [], excludedPrintKeys);
    const days = scheduleDays(selectedClasses, daysOrder);
    const table = node("table");
    const etiquetaProvisional = active?.provisional ? " · PROVISIONAL" : "";
    table.append(node("caption", "", `Resumen días y horas · ${schedule.title || config.title}${etiquetaProvisional}`));
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
    const totalMinutes = selectedClasses.reduce((sum, item) => sum + minutes(item.fin) - minutes(item.inicio), 0);
    const meta = node("div", "meta", selectedClasses.length
      ? `Actualizado: ${active.actualizado} · ${selectedClasses.length} sesiones seleccionadas · ${Math.floor(totalMinutes / 60)}h ${totalMinutes % 60 ? `${totalMinutes % 60}min` : ""} lectivas${etiquetaProvisional}`
      : "No hay sesiones seleccionadas para imprimir.");
    const summary = node("div", "summary");
    summary.append(table, meta);
    ui.print.replaceChildren(summary);
  }

  return {
    render(schedule, view) {
      ui.title.textContent = schedule.title || config.title;
      ui.subtitle.textContent = schedule.subtitle || config.subtitle || "";
      const preview = view === "proxima" && Boolean(schedule.proximaSemana?.clases?.length);
      renderTabs(schedule, view);
      renderHistory(schedule);
      renderSchedule(schedule, preview);
      renderPrintSheet(schedule, preview);
    }
  };
}
