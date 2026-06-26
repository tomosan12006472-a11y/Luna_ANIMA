import { $, setValue, value } from "./dom.js?v=v1.52-payload-preview-close-20260626";

export function createPositivePromptHelpers({ updateSummaries = () => {} } = {}) {
  function insertPositivePromptText(insertText) {
    const el = $("#positivePrompt");
    if (!el) return;
    const textValue = String(insertText || "");
    const start = Number.isFinite(el.selectionStart) ? el.selectionStart : el.value.length;
    const end = Number.isFinite(el.selectionEnd) ? el.selectionEnd : start;
    el.value = `${el.value.slice(0, start)}${textValue}${el.value.slice(end)}`;
    const cursor = start + textValue.length;
    el.focus();
    el.setSelectionRange(cursor, cursor);
    updateSummaries();
  }

  function joinPositivePromptParts(parts = []) {
    return parts.map((part) => String(part || "").trim()).filter(Boolean).join(", ");
  }

  function applyPositivePromptInsert(prompt, mode) {
    const nextPrompt = String(prompt || "").trim();
    if (!nextPrompt) return;
    const current = value("#positivePrompt", "").trim();
    if (mode === "replace") {
      setValue("#positivePrompt", nextPrompt);
    } else if (mode === "prepend") {
      setValue("#positivePrompt", joinPositivePromptParts([nextPrompt, current]));
    } else {
      setValue("#positivePrompt", joinPositivePromptParts([current, nextPrompt]));
    }
    updateSummaries();
  }

  return {
    applyPositivePromptInsert,
    insertPositivePromptText,
    joinPositivePromptParts,
  };
}

export function promptItemPrompt(item = {}) {
  return String(item.prompt || item.positive_prompt || item.text || "").trim();
}

export function promptItemTitle(item = {}) {
  const prompt = promptItemPrompt(item);
  return String(item.title || item.name || prompt.slice(0, 40) || "Untitled").trim();
}

export function promptExcerpt(prompt, limit = 60) {
  const compact = String(prompt || "").replace(/\s+/g, " ").trim();
  return compact.length > limit ? `${compact.slice(0, limit)}...` : compact;
}

export function promptItemTagsText(item = {}) {
  if (Array.isArray(item.tags)) return item.tags.join(", ");
  return String(item.tags || "");
}

export function parsePromptTags(valueText) {
  return String(valueText || "")
    .replace(/;/g, ",")
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}
