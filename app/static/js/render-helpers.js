import { $, displayValue, unique } from "./dom.js?v=v1.69-detailer-sampling-20260702";

export function fillSelect(selector, options, selected) {
  const select = typeof selector === "string" ? $(selector) : selector;
  if (!select) return;
  const current = String(selected ?? select.value ?? "").trim();
  const values = unique([current, ...(options || [])]);
  select.replaceChildren();
  for (const optionValue of values.length ? values : [current || ""]) {
    const option = document.createElement("option");
    option.value = optionValue;
    option.textContent = optionValue || "-";
    select.appendChild(option);
  }
  if (current) select.value = current;
}

export function addMetaRow(table, label, value, selectable = false) {
  const tr = document.createElement("tr");
  const th = document.createElement("td");
  th.textContent = label;
  const td = document.createElement("td");
  td.textContent = displayValue(value);
  if (selectable) {
    td.style.userSelect = "text";
    td.style.webkitUserSelect = "text";
  }
  tr.append(th, td);
  table.appendChild(tr);
}

export function characterSummary(item = {}) {
  const chars = Array.isArray(item.characters) ? item.characters : [];
  if (!chars.length) return item.original_character || "-";
  return chars.map((char) => {
    if (typeof char === "string") return char;
    const role = char.role || char.position || "";
    const name = char.display_name || char.name || char.id || "";
    return role && name ? `${role}: ${name}` : name;
  }).filter(Boolean).join(", ") || "-";
}
