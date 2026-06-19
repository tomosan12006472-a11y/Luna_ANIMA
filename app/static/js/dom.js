const UI = window.UI;

export const $ = UI.$;
export const $$ = UI.$$;

export function text(selector, nextValue) {
  const el = typeof selector === "string" ? $(selector) : selector;
  if (el) el.textContent = String(nextValue ?? "");
}

export function value(selector, fallback = "") {
  const el = $(selector);
  if (!el) return fallback;
  const raw = "value" in el ? el.value : "";
  return raw === "" || raw === undefined || raw === null ? fallback : raw;
}

export function setValue(selector, next) {
  const el = $(selector);
  if (el && "value" in el) el.value = next ?? "";
}

export function numberValue(selector, fallback = 0) {
  const raw = Number(value(selector, fallback));
  return Number.isFinite(raw) ? raw : fallback;
}

export function numberFrom(raw, fallback = 0) {
  const next = Number(raw);
  return Number.isFinite(next) ? next : fallback;
}

export function intFrom(raw, fallback = 0) {
  return Math.trunc(numberFrom(raw, fallback));
}

export function setChecked(selector, next) {
  const el = $(selector);
  if (el && "checked" in el) el.checked = Boolean(next);
}

export function checked(selector) {
  const el = $(selector);
  return Boolean(el && "checked" in el && el.checked);
}

export function clone(nextValue) {
  try {
    return JSON.parse(JSON.stringify(nextValue ?? {}));
  } catch {
    return {};
  }
}

export function escapePathSegment(nextValue) {
  return encodeURIComponent(String(nextValue || ""));
}

export function formatDate(nextValue) {
  if (!nextValue) return "-";
  const date = new Date(nextValue);
  if (Number.isNaN(date.getTime())) return String(nextValue);
  return date.toLocaleString("ja-JP", { hour12: false });
}

export function modelFileName(nextValue) {
  const textValue = String(nextValue || "").replaceAll("\\", "/");
  return textValue.split("/").filter(Boolean).pop() || textValue || "-";
}

export function displayValue(nextValue) {
  if (nextValue === null || nextValue === undefined || nextValue === "") return "-";
  if (Array.isArray(nextValue)) return nextValue.length ? nextValue.join(", ") : "-";
  if (typeof nextValue === "object") {
    try {
      return JSON.stringify(nextValue);
    } catch {
      return String(nextValue);
    }
  }
  return String(nextValue);
}

export function unique(values) {
  const seen = new Set();
  const out = [];
  for (const item of values || []) {
    const textValue = String(item ?? "").trim();
    if (!textValue || seen.has(textValue)) continue;
    seen.add(textValue);
    out.push(textValue);
  }
  return out;
}
