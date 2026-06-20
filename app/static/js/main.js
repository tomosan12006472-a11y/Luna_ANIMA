import { createApiClient, authExpiredMessage, errorMessage, isUnauthorized } from "./api.js?v=v1.32-generation-form-module-20260620";
import { dispatchAction, registerActions } from "./actions.js?v=v1.32-generation-form-module-20260620";
import { onDomReady } from "./bootstrap.js?v=v1.32-generation-form-module-20260620";
import {
  $,
  $$,
  checked,
  clone,
  displayValue,
  escapePathSegment,
  intFrom,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
  text,
  unique,
  value,
} from "./dom.js?v=v1.32-generation-form-module-20260620";
import { createGenerationFormFeature } from "./generation-form.js?v=v1.32-generation-form-module-20260620";
import { createHistoryFeature } from "./history.js?v=v1.32-generation-form-module-20260620";
import { createI2iFeature } from "./i2i.js?v=v1.32-generation-form-module-20260620";
import { createLoraFeature } from "./loras.js?v=v1.32-generation-form-module-20260620";
import { createPromptRandomUi } from "./prompt-random.js?v=v1.32-generation-form-module-20260620";
import { createQueueFeature } from "./queue.js?v=v1.32-generation-form-module-20260620";
import { createReferenceFeature } from "./reference.js?v=v1.32-generation-form-module-20260620";
import { CHARACTER_FAVORITES_COLLAPSED_KEY, createInitialState, storeBoolean } from "./state.js?v=v1.32-generation-form-module-20260620";

(() => {
  "use strict";

  const UI = window.UI;

  const EMPTY_SLOT_LABELS = {
    character1: "未選択",
    character2: "未選択",
    character3: "未選択",
    original: "未選択",
  };
  const SCORE_TAG_RE = /^[([{]*score_\d+(?:_up)?(?::[0-9.]+)?[\])}]*$/i;
  const QUALITY_PROMPTS = Object.freeze({
    standard: "masterpiece, best quality, score_7",
    high: "masterpiece, best quality, high quality, highly detailed, score_8, score_7",
    character_check: "best quality, clean character design, clear face, full body",
  });
  const RATING_PROMPTS = Object.freeze({
    safe: "safe",
    sensitive: "sensitive",
    nsfw: "nsfw",
    explicit: "explicit",
  });

  const state = createInitialState();

  function exitToLogin(message = "") {
    UI.closeSheets();
    $("#loginView")?.classList.add("is-active");
    $$(".view[data-view]").forEach((view) => view.classList.remove("is-active"));
    $("#tabs")?.classList.add("hidden");
    $("#exposeBar")?.classList.add("hidden");
    UI.safelight("idle");
    if (message) text("#loginStatus", message);
  }

  const { api, fetchWithAuthHandling } = createApiClient({ onUnauthorized: exitToLogin });
  const promptRandom = createPromptRandomUi({
    api,
    state,
    UI,
    updateSummaries: () => updateSummaries(),
    confirmDanger: (options) => confirmDanger(options),
    errorMessage,
  });
  const loras = createLoraFeature({
    api,
    state,
    updateSummaries: () => updateSummaries(),
  });
  const i2i = createI2iFeature({
    api,
    state,
    UI,
    updateSummaries: () => updateSummaries(),
  });
  const reference = createReferenceFeature({
    api,
    state,
    UI,
    updateSummaries: () => updateSummaries(),
  });
  const history = createHistoryFeature({
    api,
    fetchWithAuthHandling,
    state,
    UI,
    errorMessage,
    isUnauthorized,
    loras,
    addMetaRow: (table, label, nextValue, selectable) => addMetaRow(table, label, nextValue, selectable),
    characterSummary: (item) => characterSummary(item),
    historyPositiveText: (item) => historyPositiveText(item),
    historyNegativeText: (item) => historyNegativeText(item),
    collectWatermark: () => collectWatermark(),
  });
  const queue = createQueueFeature({
    api,
    state,
    UI,
    confirmDanger: (options) => confirmDanger(options),
    errorMessage,
    refreshHistory: () => history.loadContact(true),
  });
  const generationForm = createGenerationFormFeature({
    state,
    UI,
    fillSelect: (selector, options, selected) => fillSelect(selector, options, selected),
    slotRequestValue: (slotName) => slotRequestValue(slotName),
    collectRatingPromptOverrides: () => collectRatingPromptOverrides(),
    collectQualityPromptOverrides: () => collectQualityPromptOverrides(),
    collectFaceDetailerSettings: (enabled, mode) => collectFaceDetailerSettings(enabled, mode),
    collectHandDetailerSettings: (enabled, mode) => collectHandDetailerSettings(enabled, mode),
    promptRandom,
    loras,
    i2i,
    reference,
  });

  function fillSelect(selector, options, selected) {
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

  function slotRequestValue(slotName) {
    const item = state.slots[slotName];
    if (item?.value) return item.value;
    return "None";
  }

  function selectedQualityPreset() {
    return UI.segValue("#qualitySeg", "quality") || "standard";
  }

  function selectedRatingPreset() {
    return UI.segValue("#ratingSeg", "rating") || "safe";
  }

  function ratingPromptOverrides(settings = state.appSettings) {
    const raw = settings?.rating_prompt_overrides;
    const out = {};
    if (!raw || typeof raw !== "object") return out;
    for (const key of Object.keys(RATING_PROMPTS)) {
      if (Object.prototype.hasOwnProperty.call(raw, key)) out[key] = String(raw[key] ?? "");
    }
    return out;
  }

  function ratingPromptForPreset(preset, overrides = ratingPromptOverrides()) {
    if (Object.prototype.hasOwnProperty.call(overrides, preset)) return String(overrides[preset] ?? "");
    return RATING_PROMPTS[preset] || String(preset || "");
  }

  function mergedRatingPromptDrafts() {
    return { ...ratingPromptOverrides(state.appSettings), ...state.ratingPromptDrafts };
  }

  function isCustomRatingPrompt(preset, overrides = mergedRatingPromptDrafts()) {
    return (
      Object.prototype.hasOwnProperty.call(overrides, preset) &&
      String(overrides[preset] ?? "") !== (RATING_PROMPTS[preset] || "")
    );
  }

  function normalizeRatingPromptOverrides(overrides = {}) {
    const out = {};
    for (const key of Object.keys(RATING_PROMPTS)) {
      if (!Object.prototype.hasOwnProperty.call(overrides, key)) continue;
      const prompt = String(overrides[key] ?? "");
      if (prompt !== RATING_PROMPTS[key]) out[key] = prompt;
    }
    return out;
  }

  function qualityPromptOverrides(settings = state.appSettings) {
    const raw = settings?.quality_prompt_overrides;
    const out = {};
    if (!raw || typeof raw !== "object") return out;
    for (const key of Object.keys(QUALITY_PROMPTS)) {
      if (Object.prototype.hasOwnProperty.call(raw, key)) out[key] = String(raw[key] ?? "");
    }
    return out;
  }

  function qualityPromptForPreset(preset, overrides = qualityPromptOverrides()) {
    if (Object.prototype.hasOwnProperty.call(overrides, preset)) return String(overrides[preset] ?? "");
    return QUALITY_PROMPTS[preset] || "";
  }

  function isCustomQualityPrompt(preset, overrides = mergedQualityPromptDrafts()) {
    return (
      Object.prototype.hasOwnProperty.call(overrides, preset) &&
      String(overrides[preset] ?? "") !== (QUALITY_PROMPTS[preset] || "")
    );
  }

  function normalizeQualityPromptOverrides(overrides = {}) {
    const out = {};
    for (const key of Object.keys(QUALITY_PROMPTS)) {
      if (!Object.prototype.hasOwnProperty.call(overrides, key)) continue;
      const prompt = String(overrides[key] ?? "");
      if (prompt !== QUALITY_PROMPTS[key]) out[key] = prompt;
    }
    return out;
  }

  function mergedQualityPromptDrafts() {
    return { ...qualityPromptOverrides(state.appSettings), ...state.qualityPromptDrafts };
  }

  function renderQualityPrompt() {
    const preset = selectedQualityPreset();
    const overrides = mergedQualityPromptDrafts();
    setValue("#qualityPrompt", qualityPromptForPreset(preset, overrides));
    text(
      "#qualityPromptSummary",
      isCustomQualityPrompt(preset, overrides) ? "CUSTOM" : "DEFAULT"
    );
  }

  function renderRatingPrompt() {
    const preset = selectedRatingPreset();
    const overrides = mergedRatingPromptDrafts();
    setValue("#ratingPrompt", ratingPromptForPreset(preset, overrides));
    text(
      "#ratingPromptSummary",
      isCustomRatingPrompt(preset, overrides) ? "CUSTOM" : "DEFAULT"
    );
  }

  function updateQualityPromptDraft() {
    const preset = selectedQualityPreset();
    const prompt = value("#qualityPrompt", "");
    state.qualityPromptDrafts[preset] = prompt;
    text("#autoPromptStatus", "");
    text("#qualityPromptSummary", prompt === (QUALITY_PROMPTS[preset] || "") ? "DEFAULT" : "CUSTOM");
    updateSummaries();
  }

  function updateRatingPromptDraft() {
    const preset = selectedRatingPreset();
    const prompt = value("#ratingPrompt", "");
    state.ratingPromptDrafts[preset] = prompt;
    text("#autoPromptStatus", "");
    text("#ratingPromptSummary", prompt === (RATING_PROMPTS[preset] || "") ? "DEFAULT" : "CUSTOM");
    updateSummaries();
  }

  function collectQualityPromptOverrides() {
    const preset = selectedQualityPreset();
    return normalizeQualityPromptOverrides({
      ...mergedQualityPromptDrafts(),
      [preset]: value("#qualityPrompt", ""),
    });
  }

  function collectRatingPromptOverrides() {
    const preset = selectedRatingPreset();
    return normalizeRatingPromptOverrides({
      ...mergedRatingPromptDrafts(),
      [preset]: value("#ratingPrompt", ""),
    });
  }

  function collectRequest() {
    return generationForm.collectRequest();
  }

  function sourceForCharacter(item) {
    const source = String(item?.source || "");
    if (source === "original_character" || item?.kind === "original") return "original_character";
    return "wai_characters";
  }

  function containsCjkText(textValue) {
    return /[\u3400-\u9fff\uf900-\ufaff]/.test(String(textValue || ""));
  }

  function containsKanaText(textValue) {
    return /[\u3040-\u30ff]/.test(String(textValue || ""));
  }

  function isRandomSlotItem(item) {
    return String(item?.kind || "").toLowerCase() === "random" || String(item?.value || "").toLowerCase() === "random";
  }

  function randomSlotItem(slotName = state.armedSlot) {
    const original = slotName === "original";
    const displayName = original ? "Original Random" : "Random";
    return {
      source: original ? "original_character" : "wai_characters",
      id: "Random",
      displayName,
      originalDisplayName: displayName,
      promptTag: "",
      promptSafeName: "",
      kind: "random",
      value: "Random",
    };
  }

  function normalizeCharacterItem(raw = {}) {
    const source = sourceForCharacter(raw);
    const originalDisplayName = String(raw.display_name_original || raw.display_name || raw.name || raw.id || "").trim();
    const localizedDisplayName = String(raw.display_name_ja || raw.localized_display_name || raw.displayNameJa || "").trim();
    const promptTag = String(raw.prompt_tag || raw.promptTag || "").trim();
    const promptSafeName = String(raw.prompt_safe_name || raw.promptSafeName || "").trim();
    const fallbackDisplayName = String(raw.displayName || originalDisplayName).trim();
    const legacyCjkDisplay = source !== "original_character" && promptSafeName && containsCjkText(fallbackDisplayName) && !containsKanaText(fallbackDisplayName);
    const displayName = localizedDisplayName || (legacyCjkDisplay ? promptSafeName : fallbackDisplayName) || promptSafeName || promptTag;
    const id = String(raw.id || originalDisplayName || displayName).trim();
    const kind = raw.kind || (source === "original_character" ? "original" : "wai");
    return { source, id, displayName, originalDisplayName, promptTag, promptSafeName, kind };
  }

  function valueForSlot(slotName, item) {
    if (isRandomSlotItem(item)) return "Random";
    if (slotName === "original") return item.id || item.displayName || "None";
    if (item.source === "original_character" || item.kind === "original") {
      return `original:${item.id || item.displayName}`;
    }
    return item.promptTag || item.originalDisplayName || item.id || item.displayName || "None";
  }

  function applyCharacterToSlot(raw, slotName = state.armedSlot) {
    const item = normalizeCharacterItem(raw);
    if (!item.displayName && !item.id) return;
    state.slots[slotName] = {
      ...item,
      value: valueForSlot(slotName, item),
    };
    renderSlots();
    updateSummaries();
  }

  function clearSlot(slotName = state.armedSlot) {
    state.slots[slotName] = null;
    renderSlots();
    updateSummaries();
  }

  function slotShortLabel(slotName) {
    return { character1: "C1", character2: "C2", character3: "C3", original: "ORIGINAL" }[slotName] || slotName;
  }

  function setRandomSlot(slotName = state.armedSlot) {
    state.slots[slotName] = randomSlotItem(slotName);
    renderSlots();
    updateSummaries();
    UI.toast(`${slotShortLabel(slotName)} をRandomにしました`);
  }

  function compactSlotName(textValue) {
    const text = String(textValue || "").replace(/\s+/g, " ").trim();
    const limit = 18;
    if (text.length <= limit) return text;
    return `${text.slice(0, limit)}...`;
  }

  function renderSlots() {
    $$(".slot", $("#charSlots")).forEach((slot) => {
      const slotName = slot.dataset.slot;
      const item = state.slots[slotName];
      const fullName = item?.displayName || EMPTY_SLOT_LABELS[slotName] || "未選択";
      slot.classList.toggle("is-armed", slotName === state.armedSlot);
      slot.classList.toggle("is-empty", !item);
      slot.classList.toggle("is-random", isRandomSlotItem(item));
      const name = slot.querySelector(".name");
      if (name) {
        name.textContent = compactSlotName(fullName);
        name.title = fullName;
      }
    });
  }

  function allFavorites() {
    return [
      ...(state.favorites.characters || []),
      ...(state.favorites.original_characters || []),
    ];
  }

  function favoriteMatchesSlot(favorite, slotItem) {
    if (!favorite || !slotItem) return false;
    if (isRandomSlotItem(slotItem)) return false;
    const fav = normalizeCharacterItem(favorite);
    if (fav.source !== slotItem.source) return false;
    if (fav.source === "original_character") {
      return fav.id === slotItem.id || fav.originalDisplayName === slotItem.originalDisplayName || fav.displayName === slotItem.displayName;
    }
    return (
      (fav.promptTag && fav.promptTag === slotItem.promptTag) ||
      fav.originalDisplayName === slotItem.originalDisplayName ||
      fav.displayName === slotItem.displayName
    );
  }

  function favoriteForSlot(slotName = state.armedSlot) {
    const slotItem = state.slots[slotName];
    return allFavorites().find((favorite) => favoriteMatchesSlot(favorite, slotItem));
  }

  function renderFavorites() {
    const root = $("#favRow");
    if (!root) return;
    root.replaceChildren();
    const favorites = allFavorites();
    text("#favCount", `${favorites.length}件`);
    const toggle = $("#favToggle");
    if (toggle) {
      toggle.textContent = `★ お気に入り ${state.characterFavoritesCollapsed ? "▸" : "▾"}`;
      toggle.setAttribute("aria-expanded", String(!state.characterFavoritesCollapsed));
    }
    root.hidden = Boolean(state.characterFavoritesCollapsed);
    if (state.characterFavoritesCollapsed) return;
    if (!favorites.length) {
      const empty = document.createElement("span");
      empty.className = "lbl";
      empty.textContent = "お気に入りなし";
      root.appendChild(empty);
      return;
    }
    for (const favorite of favorites) {
      const item = normalizeCharacterItem(favorite);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.dataset.favoriteId = favorite.id || "";
      button.dataset.favoriteSource = item.source || "";
      button.dataset.favoriteName = item.originalDisplayName || item.displayName || "";
      button.dataset.favoriteDisplayName = item.displayName || "";
      button.dataset.favoritePromptTag = item.promptTag || "";
      button.dataset.favoritePromptSafeName = item.promptSafeName || "";
      button.textContent = `★ ${item.displayName || item.originalDisplayName || item.id}`;
      root.appendChild(button);
    }
  }

  function setFavorites(data) {
    state.favorites = {
      characters: Array.isArray(data?.characters) ? data.characters : [],
      original_characters: Array.isArray(data?.original_characters) ? data.original_characters : [],
    };
    renderFavorites();
  }

  async function loadFavorites() {
    const data = await api("/api/favorites");
    setFavorites(data);
  }

  async function markFavoriteUsedWithRetry(source, favoriteId) {
    if (!source || !favoriteId) return;
    const path = `/api/favorites/${escapePathSegment(source)}/${escapePathSegment(favoriteId)}/use`;
    const options = { method: "POST", body: "{}" };
    try {
      setFavorites(await api(path, options));
    } catch (error) {
      console.debug("favorite use update failed; retrying", error);
      try {
        setFavorites(await api(path, options));
      } catch (retryError) {
        console.debug("favorite use update failed", retryError);
      }
    }
  }

  async function toggleFavoriteForArmedSlot() {
    const slotItem = state.slots[state.armedSlot];
    if (!slotItem) {
      UI.toast("選択中スロットが空です", "error");
      return;
    }
    if (isRandomSlotItem(slotItem)) {
      UI.toast("Randomはお気に入り登録できません", "error");
      return;
    }
    const existing = favoriteForSlot();
    if (existing) {
      const data = await api(`/api/favorites/${escapePathSegment(existing.source)}/${escapePathSegment(existing.id)}`, {
        method: "DELETE",
      });
      setFavorites(data);
      UI.toast(data.removed ? "お気に入りを解除しました" : "登録が見つかりませんでした");
      return;
    }
    const data = await api("/api/favorites", {
      method: "POST",
      body: JSON.stringify({
        source: slotItem.source,
        id: slotItem.id || "",
        name: slotItem.displayName,
        display_name: slotItem.displayName,
        prompt_tag: slotItem.promptTag || "",
      }),
    });
    setFavorites(data);
    UI.toast(data.action === "already_exists" ? "追加済みです" : "お気に入りに追加しました");
  }

  function toggleCharacterFavorites() {
    state.characterFavoritesCollapsed = !state.characterFavoritesCollapsed;
    storeBoolean(CHARACTER_FAVORITES_COLLAPSED_KEY, state.characterFavoritesCollapsed);
    renderFavorites();
  }

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

  function appendPositivePrompt(prompt) {
    const nextPrompt = String(prompt || "").trim();
    if (!nextPrompt) return;
    const current = value("#positivePrompt", "").trim();
    setValue("#positivePrompt", current ? `${current}, ${nextPrompt}` : nextPrompt);
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

  function promptItemPrompt(item = {}) {
    return String(item.prompt || item.positive_prompt || item.text || "").trim();
  }

  function promptItemTitle(item = {}) {
    const prompt = promptItemPrompt(item);
    return String(item.title || item.name || prompt.slice(0, 40) || "Untitled").trim();
  }

  function promptExcerpt(prompt, limit = 60) {
    const compact = String(prompt || "").replace(/\s+/g, " ").trim();
    return compact.length > limit ? `${compact.slice(0, limit)}...` : compact;
  }

  function promptItemTagsText(item = {}) {
    if (Array.isArray(item.tags)) return item.tags.join(", ");
    return String(item.tags || "");
  }

  function parsePromptTags(valueText) {
    return String(valueText || "")
      .replace(/;/g, ",")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
  }

  function promptSheetQueryField() {
    return $("#promptSheetQuery")?.closest(".field") || null;
  }

  function showPromptSheetList() {
    state.promptSheetEditingId = "";
    $("#promptSheetEditor")?.classList.add("hidden");
    $("#promptSheetEditor")?.replaceChildren();
    $("#promptSheetList")?.classList.remove("hidden");
    promptSheetQueryField()?.classList.remove("hidden");
  }

  function showPromptSheetEditor() {
    $("#promptSheetEditor")?.classList.remove("hidden");
    $("#promptSheetList")?.classList.add("hidden");
    promptSheetQueryField()?.classList.add("hidden");
  }

  function promptEditorField(labelText, control) {
    const label = document.createElement("label");
    label.className = "field";
    const labelSpan = document.createElement("span");
    labelSpan.className = "lbl";
    labelSpan.textContent = labelText;
    label.append(labelSpan, control);
    return label;
  }

  function renderPositiveFavoriteEditor(item) {
    if (state.promptSheetMode !== "favorites" || !item?.id) return;
    const root = $("#promptSheetEditor");
    if (!root) return;
    state.promptSheetEditingId = String(item.id || "");
    root.replaceChildren();

    const title = document.createElement("input");
    title.name = "title";
    title.type = "text";
    title.value = promptItemTitle(item);

    const prompt = document.createElement("textarea");
    prompt.name = "prompt";
    prompt.rows = 7;
    prompt.value = promptItemPrompt(item);

    const tags = document.createElement("input");
    tags.name = "tags";
    tags.type = "text";
    tags.value = promptItemTagsText(item);

    const note = document.createElement("textarea");
    note.name = "note";
    note.rows = 3;
    note.value = String(item.note || "");

    const actions = document.createElement("div");
    actions.className = "row";
    const save = document.createElement("button");
    save.type = "submit";
    save.className = "ghost";
    save.textContent = "保存";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ghost";
    cancel.textContent = "キャンセル";
    cancel.addEventListener("click", () => {
      showPromptSheetList();
      renderPromptSheet();
    });
    actions.append(save, cancel);

    const form = document.createElement("form");
    form.append(
      promptEditorField("TITLE", title),
      promptEditorField("POSITIVE", prompt),
      promptEditorField("TAGS", tags),
      promptEditorField("NOTE", note),
      actions,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      savePositiveFavoriteEdit(item.id, form).catch((error) => UI.toast(errorMessage(error), "error"));
    });
    root.appendChild(form);
    showPromptSheetEditor();
    text("#promptSheetCount", "編集中");
    text("#promptSheetStatus", "");
    prompt.focus();
  }

  async function confirmDanger({ title = "確認しますか?", message = "", label = "実行する" } = {}) {
    const choice = await UI.ask({
      title,
      message,
      choices: [{ label, value: "yes", kind: "danger" }],
    });
    return choice === "yes";
  }

  function renderPromptSheet(items = state.promptSheetItems) {
    const root = $("#promptSheetList");
    if (!root) return;
    const query = value("#promptSheetQuery", "").trim().toLowerCase();
    const sourceItems = Array.isArray(items) ? items : [];
    const visibleItems = state.promptSheetMode === "favorites" && query
      ? sourceItems.filter((item) => {
        const haystack = [
          promptItemTitle(item),
          promptItemPrompt(item),
          ...(Array.isArray(item.tags) ? item.tags : []),
          item.note || "",
        ].join("\n").toLowerCase();
        return haystack.includes(query);
      })
      : sourceItems;

    root.replaceChildren();
    if (!visibleItems.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = query ? "一致する項目がありません" : "項目がありません";
      root.appendChild(empty);
    } else {
      for (const item of visibleItems) {
        const row = document.createElement("button");
        row.type = "button";
        row.dataset.promptItemId = item.id || "";
        row.dataset.promptKind = state.promptSheetMode;

        const label = document.createElement("span");
        label.textContent = promptItemTitle(item);

        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = promptExcerpt(promptItemPrompt(item));

        if (state.promptSheetMode === "favorites") {
          const remove = document.createElement("span");
          remove.className = "tag";
          remove.dataset.promptDeleteId = item.id || "";
          remove.setAttribute("role", "button");
          remove.setAttribute("tabindex", "0");
          remove.textContent = "削除";
          row.append(label, tag, remove);
        } else {
          row.append(label, tag);
        }
        root.appendChild(row);
      }
    }

    if (state.promptSheetMode === "templates") {
      const page = state.promptSheetPage || {};
      const total = Number(page.total ?? visibleItems.length);
      text("#promptSheetCount", total > visibleItems.length ? `${visibleItems.length} / ${total}` : String(total));
      if (page.hasMore) {
        const more = document.createElement("button");
        more.type = "button";
        more.className = "ghost";
        more.dataset.action = "load-more-prompts";
        more.textContent = `もっと見る (${Math.max(0, total - visibleItems.length)}件)`;
        root.appendChild(more);
      }
    } else {
      text("#promptSheetCount", String(visibleItems.length));
    }
    text("#promptSheetStatus", "");
  }

  function setPromptSheetLoading(message) {
    showPromptSheetList();
    $("#promptSheetList")?.replaceChildren();
    text("#promptSheetCount", "-");
    text("#promptSheetStatus", message);
  }

  async function loadPositiveFavorites() {
    const data = await api("/api/prompts/positive-favorites");
    state.promptSheetItems = Array.isArray(data.items) ? data.items : [];
    state.promptSheetPage = { query: "", total: state.promptSheetItems.length, limit: 50, hasMore: false };
    renderPromptSheet();
    return data;
  }

  async function loadPositiveTemplates(query = value("#promptSheetQuery", ""), { append = false } = {}) {
    const normalizedQuery = String(query || "").trim();
    const limit = Number(state.promptSheetPage?.limit || 50);
    const offset = append && state.promptSheetPage?.query === normalizedQuery ? state.promptSheetItems.length : 0;
    const params = new URLSearchParams({
      query: normalizedQuery,
      limit: String(limit),
      offset: String(offset),
    });
    const data = await api(`/api/prompts/positive-templates?${params.toString()}`);
    if (value("#promptSheetQuery", "").trim() !== normalizedQuery) return data;
    const pageItems = Array.isArray(data.items) ? data.items : [];
    state.promptSheetItems = append && state.promptSheetPage?.query === normalizedQuery
      ? [...state.promptSheetItems, ...pageItems]
      : pageItems;
    state.promptSheetPage = {
      query: normalizedQuery,
      total: Number(data.total ?? state.promptSheetItems.length),
      limit: Number(data.limit ?? limit),
      hasMore: Boolean(data.has_more),
    };
    renderPromptSheet();
    return data;
  }

  async function savePositiveFavorite() {
    const prompt = value("#positivePrompt", "").trim();
    if (!prompt) {
      UI.toast("Positiveが空です", "error");
      return;
    }
    await api("/api/prompts/positive-favorites", {
      method: "POST",
      body: JSON.stringify({
        title: prompt.slice(0, 40),
        prompt,
        tags: [],
        note: "",
      }),
    });
    UI.toast("保存しました");
    if (state.promptSheetMode === "favorites" && $("#promptSheet")?.classList.contains("is-open")) {
      await loadPositiveFavorites();
    }
  }

  async function savePositiveFavoriteEdit(favoriteId, form) {
    const fields = form.elements;
    const prompt = String(fields.prompt?.value || "").trim();
    if (!prompt) {
      UI.toast("Positiveが空です", "error");
      return;
    }
    const data = await api(`/api/prompts/positive-favorites/${escapePathSegment(favoriteId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: String(fields.title?.value || "").trim(),
        prompt,
        tags: parsePromptTags(fields.tags?.value),
        note: String(fields.note?.value || "").trim(),
      }),
    });
    state.promptSheetItems = Array.isArray(data.items) ? data.items : [];
    showPromptSheetList();
    renderPromptSheet();
    UI.toast("更新しました");
  }

  async function openPositiveFavorites() {
    state.promptSheetMode = "favorites";
    state.promptSheetItems = [];
    text("#promptSheetTitle", "Positiveお気に入り");
    setValue("#promptSheetQuery", "");
    setPromptSheetLoading("読み込み中...");
    UI.openSheet("#promptSheet");
    await loadPositiveFavorites();
  }

  async function openPositiveTemplates() {
    state.promptSheetMode = "templates";
    state.promptSheetItems = [];
    state.promptSheetPage = { query: "", total: 0, limit: 50, hasMore: false };
    text("#promptSheetTitle", "テンプレート");
    setValue("#promptSheetQuery", "");
    setPromptSheetLoading("読み込み中...");
    UI.openSheet("#promptSheet");
    await loadPositiveTemplates("");
  }

  async function usePromptSheetItem(itemId) {
    const item = state.promptSheetItems.find((candidate) => String(candidate.id || "") === String(itemId || ""));
    const prompt = promptItemPrompt(item);
    if (!prompt) return;
    const choices = [
      { label: "先頭に挿入", value: "prepend" },
      { label: "末尾に追記", value: "append", kind: "primary" },
    ];
    if (state.promptSheetMode === "favorites" && item?.id) {
      choices.push({ label: "編集", value: "edit" });
    }
    choices.push({ label: "置換", value: "replace", kind: "danger" });
    const mode = await UI.ask({
      title: "どこに入れますか?",
      message: `${promptItemTitle(item)}\n${promptExcerpt(prompt, 120)}`,
      choices,
    });
    if (!mode) return;
    if (mode === "edit") {
      renderPositiveFavoriteEditor(item);
      return;
    }
    applyPositivePromptInsert(prompt, mode);
    if (state.promptSheetMode === "favorites" && item?.id) {
      await api(`/api/prompts/positive-favorites/${escapePathSegment(item.id)}/used`, {
        method: "POST",
        body: "{}",
      });
    }
    UI.closeSheets();
    UI.toast("Positiveに反映しました");
  }

  async function deletePositiveFavorite(favoriteId) {
    if (!favoriteId) return;
    const item = state.promptSheetItems.find((candidate) => String(candidate.id || "") === String(favoriteId || ""));
    const ok = await confirmDanger({
      title: "削除しますか?",
      message: `${promptItemTitle(item)}\n${promptExcerpt(promptItemPrompt(item), 120)}`,
      label: "削除する",
    });
    if (!ok) return;
    const data = await api(`/api/prompts/positive-favorites/${escapePathSegment(favoriteId)}`, {
      method: "DELETE",
    });
    state.promptSheetItems = Array.isArray(data.items) ? data.items : [];
    renderPromptSheet();
    UI.toast(data.removed ? "削除しました" : "見つかりませんでした");
  }

  function recipeAutoName(request) {
    const selectedCharacter = state.slots.character1;
    const character = selectedCharacter?.displayName || (request.character1 === "None" ? "未選択" : request.character1) || "未選択";
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    return `${character || "Random"} / ${request.quality_preset || "standard"} / ${request.width}x${request.height} / ${hh}:${mm}`.slice(0, 60);
  }

  function recipeSummary(request) {
    return [
      request.rating || "safe",
      request.quality_preset || "standard",
      `${request.width || 0}x${request.height || 0}`,
      `${request.steps || 0}steps`,
    ].join(" · ").slice(0, 120);
  }

  function setRecipeListLoading(message) {
    $("#recipeList")?.replaceChildren();
    text("#recipeCountLbl", "-");
    text("#recipeStatus", message);
  }

  function renderRecipes(items = state.recipes) {
    const root = $("#recipeList");
    if (!root) return;
    const recipes = Array.isArray(items) ? items : [];
    root.replaceChildren();
    if (!recipes.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "レシピはまだありません";
      root.appendChild(empty);
    } else {
      for (const item of recipes) {
        const row = document.createElement("div");
        row.style.display = "grid";
        row.style.gridTemplateColumns = "minmax(0, 1fr) auto";
        row.style.alignItems = "stretch";
        row.style.gap = "8px";

        const apply = document.createElement("button");
        apply.type = "button";
        apply.dataset.recipeId = item.id || "";
        apply.style.textAlign = "left";

        const label = document.createElement("span");
        label.textContent = item.name || "Untitled Recipe";

        const summary = document.createElement("span");
        summary.className = "tag";
        summary.textContent = item.summary || "";
        apply.append(label, summary);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "ghost";
        remove.dataset.recipeDeleteId = item.id || "";
        remove.textContent = "削除";

        row.append(apply, remove);
        root.appendChild(row);
      }
    }
    text("#recipeCountLbl", String(recipes.length));
    text("#recipeStatus", "");
  }

  async function saveRecipe() {
    const request = collectRequest();
    const data = await api("/api/recipes", {
      method: "POST",
      body: JSON.stringify({
        name: recipeAutoName(request),
        summary: recipeSummary(request),
        request,
      }),
    });
    state.recipes = Array.isArray(data.items) ? data.items : state.recipes;
    text("#recipeStatus", "保存しました");
    text("#recipeCountLbl", String(data.count ?? state.recipes.length));
    UI.toast("レシピを保存しました");
    if ($("#recipeSheet")?.classList.contains("is-open")) renderRecipes();
  }

  async function openRecipes() {
    state.recipes = [];
    setRecipeListLoading("読み込み中...");
    UI.openSheet("#recipeSheet");
    const data = await api("/api/recipes");
    state.recipes = Array.isArray(data.items) ? data.items : [];
    renderRecipes();
  }

  async function applyRecipe(recipeId) {
    const item = state.recipes.find((recipe) => String(recipe.id || "") === String(recipeId || ""));
    if (!item || !item.request || typeof item.request !== "object") {
      UI.toast("レシピを適用できませんでした", "error");
      return;
    }
    applyHistoryReuseData(reuseDataFromRequest(item.request));
    UI.closeSheets();
    UI.switchTab("expose");
    UI.toast("レシピを適用しました");
    try {
      const data = await api(`/api/recipes/${escapePathSegment(item.id)}/used`, {
        method: "POST",
        body: "{}",
      });
      if (data.item) {
        state.recipes = state.recipes.map((recipe) => recipe.id === data.item.id ? data.item : recipe);
      }
    } catch (error) {
      console.debug("recipe used update failed", error);
    }
  }

  async function deleteRecipeItem(recipeId) {
    if (!recipeId) return;
    const item = state.recipes.find((recipe) => String(recipe.id || "") === String(recipeId || ""));
    const ok = await confirmDanger({
      title: "削除しますか?",
      message: `${item?.name || "Untitled Recipe"}\n${item?.summary || ""}`,
      label: "削除する",
    });
    if (!ok) return;
    const data = await api(`/api/recipes/${escapePathSegment(recipeId)}`, {
      method: "DELETE",
    });
    if (data.removed) state.recipes = state.recipes.filter((item) => item.id !== recipeId);
    renderRecipes();
    UI.toast(data.removed ? "削除しました" : "見つかりませんでした");
  }

  async function loadDynamicWildcards() {
    const data = await api("/api/dynamic-prompts/wildcards");
    const root = $("#wildcardChips");
    if (!root) return data;
    root.replaceChildren();
    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) {
      const empty = document.createElement("span");
      empty.className = "lbl";
      empty.textContent = "ワイルドカードなし";
      root.appendChild(empty);
    } else {
      for (const item of items) {
        const name = String(item.name || "").trim();
        if (!name) continue;
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "chip";
        chip.dataset.wildcardName = name;
        chip.textContent = `__${name}__`;
        root.appendChild(chip);
      }
    }
    if (Array.isArray(data.warnings) && data.warnings.length) {
      UI.toast(data.warnings.map((warning) => warning.message || String(warning)).slice(0, 2).join(" / "));
    }
    return data;
  }

  async function previewDynamicPrompt() {
    const data = await api("/api/dynamic-prompts/preview", {
      method: "POST",
      body: JSON.stringify({
        positive_prompt: value("#positivePrompt", ""),
        negative_prompt: "",
        seed: Math.trunc(numberValue("#seedInput", -1)),
        enabled: true,
      }),
    });
    const preview = $("#dynamicPreview");
    if (preview) {
      preview.textContent = data.expanded_positive_prompt || "";
      preview.classList.remove("hidden");
    }
    if (Array.isArray(data.warnings) && data.warnings.length) {
      UI.toast(data.warnings.map((warning) => warning.message || String(warning)).slice(0, 2).join(" / "));
    }
  }

  function dictInsertText(item = {}) {
    return String(item.insert_text || item.display_tag || item.tag || "").trim();
  }

  function dictDisplayText(item = {}) {
    return String(item.ja || item.display_tag || item.tag || item.description || "").trim();
  }

  function dictTagText(item = {}) {
    return String(item.display_tag || item.tag || item.insert_text || "").trim();
  }

  function setDictStatus(data = {}) {
    if (!data || data.ok === false || data.available === false || data.warning) {
      text("#dictStatus", data?.warning || "Prompt辞書データが未配置です。データ配置後に検索できます。");
      return;
    }
    text("#dictStatus", "");
  }

  async function loadPromptDictionaryStatus() {
    if (state.dictStatusLoaded) return null;
    state.dictStatusLoaded = true;
    try {
      const data = await api("/api/prompt-dictionary/status");
      setDictStatus(data);
      return data;
    } catch (error) {
      state.dictStatusLoaded = false;
      text("#dictStatus", errorMessage(error));
      throw error;
    }
  }

  function renderPromptDictionaryResults(items) {
    const root = $("#dictResults");
    if (!root) return;
    root.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "見つかりません";
      root.appendChild(empty);
      return;
    }
    for (const item of items) {
      const insertText = dictInsertText(item);
      if (!insertText) continue;
      const row = document.createElement("button");
      row.type = "button";
      row.dataset.dictInsert = insertText;

      const label = document.createElement("span");
      label.textContent = dictDisplayText(item) || insertText;

      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = dictTagText(item) || insertText;

      row.append(label, tag);
      root.appendChild(row);
    }
  }

  async function searchPromptDictionary() {
    const query = value("#dictQuery", "").trim();
    if (!query) {
      $("#dictResults")?.replaceChildren();
      return;
    }
    await loadPromptDictionaryStatus();
    const params = new URLSearchParams({ q: query, limit: "50" });
    const data = await api(`/api/prompt-dictionary/search?${params.toString()}`);
    if (value("#dictQuery", "").trim() !== query) return;
    setDictStatus(data);
    renderPromptDictionaryResults(Array.isArray(data.items) ? data.items : []);
  }

  function schedulePromptDictionarySearch() {
    window.clearTimeout(state.dictQueryTimer);
    state.dictQueryTimer = window.setTimeout(() => {
      searchPromptDictionary().catch((error) => {
        text("#dictStatus", errorMessage(error));
        UI.toast(errorMessage(error), "error");
      });
    }, 250);
  }

  function appendNegativePromptText(insertText) {
    const tag = String(insertText || "").trim();
    if (!tag) return;
    const current = value("#negativePrompt", "").trimEnd();
    setValue("#negativePrompt", current ? `${current}, ${tag}` : tag);
    updateSummaries();
  }

  function insertPromptDictionaryTag(insertText) {
    const tag = String(insertText || "").trim();
    if (!tag) return;
    if (value("#dictTarget", "positive") === "negative") {
      appendNegativePromptText(tag);
    } else {
      insertPositivePromptText(`${tag}, `);
    }
    UI.toast(`追加: ${tag}`);
  }

  function splitPromptConverterTags(textValue) {
    return String(textValue || "")
      .replace(/[\n;]/g, ",")
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }

  function normalizePromptConverterTag(tag) {
    let textValue = String(tag || "")
      .replace(/<\s*lora:[^>]+>/ig, "")
      .replace(/__[^_\n]+__/g, "")
      .trim();
    if (!textValue) return "";
    if (!SCORE_TAG_RE.test(textValue)) textValue = textValue.replaceAll("_", " ");
    return textValue.replace(/\s+/g, " ").replace(/^[\s,;.]+|[\s,;.]+$/g, "");
  }

  function promptConverterDedupeKey(tag) {
    return normalizePromptConverterTag(tag)
      .toLowerCase()
      .replace(/^[([{]+/, "")
      .replace(/[\])}]+$/, "")
      .replace(/:[0-9.]+$/, "")
      .replace(/\s+/g, " ")
      .replace(/^[\s,;.]+|[\s,;.]+$/g, "");
  }

  function dedupePromptConverterTags(insertText, existingText) {
    const seen = new Set(splitPromptConverterTags(existingText).map(promptConverterDedupeKey).filter(Boolean));
    const out = [];
    for (const raw of splitPromptConverterTags(insertText)) {
      const tag = normalizePromptConverterTag(raw);
      const key = promptConverterDedupeKey(tag);
      if (!tag || !key || seen.has(key)) continue;
      seen.add(key);
      out.push(tag);
    }
    return out.join(", ");
  }

  function setPromptConverterStatus(data = {}) {
    if (data.enabled === false) {
      text("#promptConverterSummary", "DISABLED");
      text("#promptConverterStatus", "Prompt変換は設定で無効です。");
      return;
    }
    if (data.reachable) {
      const model = data.active_model || data.model || "auto";
      text("#promptConverterSummary", "READY");
      text("#promptConverterStatus", `${data.provider || "provider"} / ${model}`);
      return;
    }
    text("#promptConverterSummary", "OFFLINE");
    text("#promptConverterStatus", data.message || "ローカル変換APIに接続できません。LM StudioなどのLocal Serverを起動してください。");
  }

  async function loadPromptConverterStatus(force = false) {
    if (state.promptConverterStatusLoaded && !force) return null;
    state.promptConverterStatusLoaded = true;
    try {
      const data = await api("/api/prompt-converter/status");
      setPromptConverterStatus(data);
      return data;
    } catch (error) {
      state.promptConverterStatusLoaded = false;
      text("#promptConverterStatus", errorMessage(error));
      throw error;
    }
  }

  function renderPromptConverterResult(data = {}) {
    const root = $("#promptConvertResult");
    if (!root) return;
    const lines = [];
    if (data.natural_en) lines.push(`Natural\n${data.natural_en}`);
    if (data.tags_en) lines.push(`Tags\n${data.tags_en}`);
    const warnings = Array.isArray(data.warnings) ? data.warnings : [];
    if (warnings.length) lines.push(`Warnings\n${warnings.map((warning) => warning.message || String(warning)).join("\n")}`);
    root.textContent = lines.join("\n\n") || "変換結果が空でした。";
    root.classList.remove("hidden");
  }

  async function choosePromptConverterInsert(data = {}) {
    const mode = String(data.mode || value("#promptConvertMode", "tags"));
    if (mode === "both" && data.tags_en && data.natural_en) {
      const choice = await UI.ask({
        title: "どちらを入れますか?",
        message: "変換結果をPositiveに入れます。",
        choices: [
          { label: "タグ", value: "tags", kind: "primary" },
          { label: "自然文", value: "natural" },
          { label: "キャンセル", value: "cancel" },
        ],
      });
      if (!choice || choice === "cancel") return null;
      return { kind: choice, text: choice === "natural" ? data.natural_en : data.tags_en };
    }
    const kind = mode === "natural" ? "natural" : "tags";
    return { kind, text: kind === "natural" ? data.natural_en : data.tags_en || data.insert_text };
  }

  async function insertPromptConverterText(result) {
    const rawText = String(result?.text || "").trim();
    if (!rawText) {
      UI.toast("挿入できる変換結果がありません", "error");
      return false;
    }
    const mode = await UI.ask({
      title: "どこに入れますか?",
      message: promptExcerpt(rawText, 140),
      choices: [
        { label: "先頭に挿入", value: "prepend" },
        { label: "末尾に追記", value: "append", kind: "primary" },
        { label: "置換", value: "replace", kind: "danger" },
        { label: "キャンセル", value: "cancel" },
      ],
    });
    if (!mode || mode === "cancel") return false;
    const insertText = result.kind === "tags" ? dedupePromptConverterTags(rawText, value("#positivePrompt", "")) : rawText;
    if (!insertText) {
      UI.toast("既存Positiveと重複しているため追加するタグがありません");
      return false;
    }
    applyPositivePromptInsert(insertText, mode);
    return true;
  }

  async function convertPromptFromJapanese() {
    const sourceText = value("#promptConvertSource", "").trim();
    if (!sourceText) {
      UI.toast("変換する日本語自然文が空です", "error");
      return;
    }
    text("#promptConverterStatus", "変換中...");
    const data = await api("/api/prompt-converter/convert", {
      method: "POST",
      body: JSON.stringify({
        source_text: sourceText,
        mode: value("#promptConvertMode", "tags"),
        existing_positive: value("#positivePrompt", ""),
      }),
    });
    state.promptConverterLast = data;
    renderPromptConverterResult(data);
    if (data.provider) setPromptConverterStatus({ enabled: true, reachable: true, ...data.provider });
    const warnings = Array.isArray(data.warnings) ? data.warnings : [];
    if (warnings.length) UI.toast(warnings.map((warning) => warning.message || String(warning)).join(" / "));
    const chosen = await choosePromptConverterInsert(data);
    if (!chosen) {
      text("#promptConverterStatus", "変換しました");
      return;
    }
    const inserted = await insertPromptConverterText(chosen);
    text("#promptConverterStatus", inserted ? "Positiveに反映しました" : "変換しました");
    if (inserted) UI.toast("Positiveに反映しました");
  }

  function collectFaceDetailerSettings(enabled = checked("#fdEnabled"), mode = "generation") {
    return {
      enabled: Boolean(enabled),
      mode,
      detector: "bbox/face_yolov8m.pt",
      steps: Math.trunc(numberValue("#fdSteps", 12)),
      cfg: numberValue("#fdCfg", 4.0),
      denoise: numberValue("#fdDenoise", 0.3),
      guide_size: 512,
      max_size: 1024,
      bbox_threshold: numberValue("#fdBbox", 0.5),
      bbox_dilation: 10,
      bbox_crop_factor: 3.0,
      sam_enabled: false,
      seed_policy: "image_seed_plus_offset",
      seed_offset: 100000,
    };
  }

  function collectHandDetailerSettings(enabled = checked("#hdEnabled"), mode = "generation") {
    return {
      enabled: Boolean(enabled),
      mode,
      detector: "bbox/hand_yolov8s.pt",
      steps: Math.trunc(numberValue("#hdSteps", 14)),
      cfg: numberValue("#hdCfg", 4.0),
      denoise: numberValue("#hdDenoise", 0.45),
      guide_size: 512,
      max_size: 1024,
      bbox_threshold: numberValue("#hdBbox", 0.35),
      bbox_dilation: 16,
      bbox_crop_factor: 2.5,
      drop_size: 24,
      sam_enabled: false,
      seed_policy: "image_seed_plus_offset",
      seed_offset: 200000,
      lllite_enabled: true,
      lllite_model: "anima-lllite-inpainting-v2.safetensors",
      lllite_strength: numberValue("#hdLlliteStrength", 0.85),
      lllite_start: 0,
      lllite_end: 1,
    };
  }

  async function queueFrameFaceDetailer() {
    if (!state.detailItem?.id) return;
    text("#frameActionStatus", "顔補正をキュー投入中...");
    const data = await api("/api/face-detailer/postprocess", {
      method: "POST",
      body: JSON.stringify({
        history_id: state.detailItem.id,
        settings: collectFaceDetailerSettings(true, "postprocess"),
      }),
    });
    UI.closeSheets();
    text("#fdStatus", "顔補正をキューに入れました");
    UI.toast("顔補正をキューに入れました");
    UI.safelight("developing", "FACE DETAILING");
    state.pollHadActive = true;
    await history.loadContact(true);
    if (Array.isArray(data.warnings) && data.warnings.length) {
      UI.toast(data.warnings.slice(0, 2).join(" / "));
    }
  }

  async function queueFrameHandDetailer() {
    if (!state.detailItem?.id) return;
    text("#frameActionStatus", "手補正をキュー投入中...");
    const data = await api("/api/hand-detailer/postprocess", {
      method: "POST",
      body: JSON.stringify({
        history_id: state.detailItem.id,
        settings: collectHandDetailerSettings(true, "postprocess"),
      }),
    });
    UI.closeSheets();
    text("#hdStatus", "手補正をキューに入れました");
    UI.toast("手補正をキューに入れました");
    UI.safelight("developing", "HAND DETAILING");
    state.pollHadActive = true;
    await history.loadContact(true);
    if (Array.isArray(data.warnings) && data.warnings.length) {
      UI.toast(data.warnings.slice(0, 2).join(" / "));
    }
  }

  function canSubmitGenerateRequest() {
    if (checked("#i2iEnabled") && !state.i2i.imageId) {
      text("#i2iStatus", "下絵が未選択です");
      UI.toast("下絵が未選択です", "error");
      return false;
    }
    if (checked("#outfitEnabled") && !state.refmod.outfit.imageId) {
      text("#refModStatus", "Outfit参照が未選択です");
      UI.toast("Outfit参照が未選択です", "error");
      return false;
    }
    if (checked("#poseEnabled") && !state.refmod.pose.imageId) {
      text("#refModStatus", "Pose参照が未選択です");
      UI.toast("Pose参照が未選択です", "error");
      return false;
    }
    return true;
  }

  function renderCharacterResults(items, meta = {}) {
    const root = $("#charResults");
    if (!root) return;
    root.replaceChildren();
    const total = Number(meta.total ?? items.length);
    const shown = Number(meta.shown ?? items.length);
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "見つかりません";
      root.appendChild(empty);
      return;
    }
    const summary = document.createElement("p");
    summary.className = "hint";
    summary.textContent = total > shown ? `${shown} / ${total} 件を表示` : `${total} 件`;
    root.appendChild(summary);
    for (const raw of items) {
      const item = normalizeCharacterItem(raw);
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.characterId = item.id || "";
      button.dataset.characterName = item.displayName || "";
      button.dataset.characterOriginalName = item.originalDisplayName || "";
      button.dataset.characterKind = item.kind || "";
      button.dataset.characterSource = item.source || "";
      button.dataset.characterPromptTag = item.promptTag || "";
      button.dataset.characterPromptSafeName = item.promptSafeName || "";
      const name = document.createElement("span");
      name.textContent = item.displayName || item.id || "-";
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = item.promptTag || item.kind || "";
      button.append(name, tag);
      root.appendChild(button);
    }
    if (meta.hasMore) {
      const more = document.createElement("button");
      more.type = "button";
      more.dataset.action = "load-more-characters";
      more.textContent = `もっと見る (${Math.max(0, total - shown)}件)`;
      root.appendChild(more);
    }
  }

  function clearCharacterSearch() {
    setValue("#charSearch", "");
    state.characterSearch = { query: "", items: [], total: 0, offset: 0, limit: 60, hasMore: false };
    $("#charResults")?.replaceChildren();
  }

  async function searchCharacters({ append = false } = {}) {
    const query = value("#charSearch", "").trim();
    if (!query) {
      state.characterSearch = { query: "", items: [], total: 0, offset: 0, limit: 60, hasMore: false };
      $("#charResults")?.replaceChildren();
      return;
    }
    const limit = state.characterSearch.limit || 60;
    const offset = append && state.characterSearch.query === query ? state.characterSearch.items.length : 0;
    const data = await api(`/api/catalog?q=${encodeURIComponent(query)}&kind=all&limit=${limit}&offset=${offset}`);
    if (value("#charSearch", "").trim() !== query) return;
    const newItems = Array.isArray(data.items) ? data.items : [];
    const items = append && state.characterSearch.query === query ? [...state.characterSearch.items, ...newItems] : newItems;
    state.characterSearch = {
      query,
      items,
      total: Number(data.total ?? items.length),
      offset: Number(data.offset ?? offset),
      limit: Number(data.limit ?? limit),
      hasMore: Boolean(data.has_more),
    };
    renderCharacterResults(items, {
      total: state.characterSearch.total,
      shown: items.length,
      hasMore: state.characterSearch.hasMore,
    });
  }

  async function loadMoreCharacters() {
    if (!state.characterSearch.hasMore) return;
    await searchCharacters({ append: true });
  }

  function scheduleCharacterSearch() {
    window.clearTimeout(state.characterSearchTimer);
    state.characterSearchTimer = window.setTimeout(() => {
      searchCharacters().catch((error) => UI.toast(errorMessage(error), "error"));
    }, 250);
  }

  function collectWatermark() {
    const previous = state.appSettings?.watermark || {};
    return {
      ...previous,
      enabled: checked("#watermarkEnabled"),
      text: value("#watermarkText", "@Luna_AIart_"),
      position: value("#watermarkPosition", "bottom_right"),
      opacity: numberValue("#watermarkOpacity", 0.72),
      size: numberValue("#watermarkSize", 36),
    };
  }

  function applyWatermark(watermark = {}) {
    setChecked("#watermarkEnabled", watermark.enabled !== false);
    setValue("#watermarkText", watermark.text || "@Luna_AIart_");
    setValue("#watermarkPosition", watermark.position || "bottom_right");
    setValue("#watermarkOpacity", watermark.opacity ?? 0.72);
    setValue("#watermarkSize", watermark.size ?? 36);
  }

  function applySettingsToForm(settings = {}, defaults = state.defaults) {
    generationForm.applySettingsBasicsToForm(settings, defaults);
    UI.setSegValue("#ratingSeg", "rating", settings.rating || "safe");
    UI.setSegValue("#qualitySeg", "quality", settings.quality_preset || "standard");
    state.ratingPromptDrafts = ratingPromptOverrides(settings);
    state.qualityPromptDrafts = qualityPromptOverrides(settings);
    renderRatingPrompt();
    renderQualityPrompt();

    loras.applyOfficialToForm(settings.official_loras || {});
    promptRandom.applyToForm(settings.prompt_random_collect || {});
    promptRandom.renderInstructionFavorites(settings);
    applyWatermark(settings.watermark || {});
    updateSizeChips();
    updateSummaries();
  }

  function updateSizeChips() {
    const size = `${numberValue("#widthInput", 0)}x${numberValue("#heightInput", 0)}`;
    $$("#sizeChips .chip").forEach((chip) => chip.classList.toggle("is-active", chip.dataset.size === size));
  }

  async function loadModels(refresh = false) {
    const data = await api(`/api/models${refresh ? "?refresh=true" : ""}`);
    state.models = data;
    fillSelect("#modelSelect", data.models || [], value("#modelSelect", state.defaults.model || state.appSettings.model || ""));
    fillSelect("#samplerSelect", data.samplers || [], value("#samplerSelect", state.defaults.sampler || state.appSettings.sampler || ""));
    fillSelect("#schedulerSelect", data.schedulers || [], value("#schedulerSelect", state.defaults.scheduler || state.appSettings.scheduler || ""));
    fillSelect("#hiresMethod", data.upscale_methods || [], value("#hiresMethod", state.appSettings.hires_fix?.latent_upscale_method || state.appSettings.hires_fix?.upscale_method || "nearest-exact"));
    fillSelect("#hiresModel", data.upscale_models || [], value("#hiresModel", state.appSettings.hires_fix?.upscale_model || ""));
    return data;
  }

  function updateSummaries() {
    const req = collectRequest();
    text("#techSummary", `${req.width}×${req.height} · ${req.steps} · ${req.cfg} · shift${req.shift}`);
    const sceneParts = [
      req.outfit_prompt,
      req.expression_prompt,
      req.pose_prompt,
      req.background_prompt,
      req.camera_prompt,
      req.lighting_prompt,
      req.year_prompt,
    ].filter(Boolean);
    text("#autoInsertSummary", [
      req.quality_preset || "standard",
      req.rating || "safe",
      ...sceneParts.slice(0, 2),
    ].filter(Boolean).join(" / ") || "—");
    const negMode = req.negative_prompt_mode || "append";
    const custom = req.negative_prompt ? "+custom" : "no custom";
    text("#negativeSummary", `${req.negative_preset} · ${negMode} · ${custom}`);
    text("#dynamicSummary", req.dynamic_prompt.enabled ? "ON" : "OFF");
    promptRandom.renderSummary(req.prompt_random_collect.enabled);
    text("#hiresSummary", req.hires_fix.enabled ? `ON · ×${Number(req.hires_fix.upscale_factor || 1.5)} · ${req.hires_fix.mode || "latent"}` : "OFF");
    text("#i2iSummary", checked("#i2iEnabled") ? `ON · ${req.image_to_image.denoise}` : "OFF");
    const refParts = [];
    if (checked("#outfitEnabled")) refParts.push("OUTFIT");
    if (checked("#poseEnabled")) refParts.push("POSE");
    text("#refModSummary", refParts.length ? refParts.join("+") : "OFF");
    text("#fdSummary", checked("#fdEnabled") ? `ON · ${Number(req.face_detailer.denoise).toFixed(2)}` : "OFF");
    text("#hdSummary", checked("#hdEnabled") ? `ON · ${Number(req.hand_detailer.denoise).toFixed(2)} · L${Number(req.hand_detailer.lllite_strength).toFixed(2)}` : "OFF");
    updateSizeChips();
  }

  async function previewPayload() {
    const request = collectRequest();
    if (request.prompt_random_collect?.enabled) promptRandom.setStatus("AIタグ生成中...");
    const data = await api("/api/payload/preview", {
      method: "POST",
      body: JSON.stringify(request),
    });
    if (request.prompt_random_collect?.enabled) promptRandom.setStatus("AIタグをPreviewに反映しました");
    const preview = $("#payloadPreview");
    if (preview) {
      preview.textContent = JSON.stringify(data, null, 2);
      preview.classList.remove("hidden");
    }
  }

  function assertGenerateQueued(data) {
    if (data.status !== "queued" && data.status !== "partial") {
      throw Object.assign(new Error(data.message || "露光できませんでした"), { data });
    }
  }

  function generateQueuedCount(data, request) {
    return Number(data.queued_count || data.items?.length || request.count || 1);
  }

  async function finishGenerateQueued(data, request, options = {}) {
    const queued = generateQueuedCount(data, request);
    const toastMessage = typeof options.toast === "function"
      ? options.toast(queued)
      : options.toast || `${queued}枚 露光しました`;
    const safelightMessage = typeof options.safelight === "function"
      ? options.safelight(queued)
      : options.safelight || `${queued} FRAMES DEVELOPING`;
    UI.toast(toastMessage);
    UI.safelight("developing", safelightMessage);
    state.pollHadActive = true;
    await history.loadContact(true);
    return queued;
  }

  async function generate() {
    if (!canSubmitGenerateRequest()) return;
    const button = $("#exposeBtn");
    button?.setAttribute("disabled", "disabled");
    try {
      const request = collectRequest();
      if (request.prompt_random_collect?.enabled) {
        promptRandom.setStatus("AIタグ生成中...");
        UI.safelight("developing", "RANDOM COLLECT");
      }
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(request),
      });
      if (request.prompt_random_collect?.enabled) promptRandom.setStatus("AIタグを反映して投入しました");
      assertGenerateQueued(data);
      await finishGenerateQueued(data, request);
    } catch (error) {
      UI.toast(errorMessage(error), "error");
      UI.safelight("error");
    } finally {
      button?.removeAttribute("disabled");
    }
  }

  function characterSummary(item = {}) {
    const chars = Array.isArray(item.characters) ? item.characters : [];
    if (!chars.length) return item.original_character || "-";
    return chars.map((char) => {
      if (typeof char === "string") return char;
      const role = char.role || char.position || "";
      const name = char.display_name || char.name || char.id || "";
      return role && name ? `${role}: ${name}` : name;
    }).filter(Boolean).join(", ") || "-";
  }

  function firstHistoryText(item, keys) {
    for (const key of keys) {
      const parts = key.split(".");
      let valueRef = item;
      for (const part of parts) valueRef = valueRef && typeof valueRef === "object" ? valueRef[part] : undefined;
      if (typeof valueRef === "string" && valueRef.trim()) return valueRef.trim();
    }
    return "";
  }

  function historyPositiveText(item = {}) {
    return firstHistoryText(item, [
      "dynamic_prompt.expanded_positive_prompt",
      "positive",
      "positive_prompt",
      "dynamic_prompt.raw_positive_prompt",
    ]);
  }

  function historyRawPositiveText(item = {}) {
    return firstHistoryText(item, [
      "request.positive_prompt",
      "request_data.positive_prompt",
      "positive_prompt",
    ]);
  }

  function historyNegativeText(item = {}) {
    return firstHistoryText(item, [
      "dynamic_prompt.expanded_negative_prompt",
      "negative",
      "negative_prompt",
      "dynamic_prompt.raw_negative_prompt",
    ]);
  }

  function addMetaRow(table, label, value, selectable = false) {
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

  function historyCharacterValue(char, targetSlot) {
    if (!char || typeof char !== "object") return "";
    const source = sourceForCharacter(char);
    const displayName = char.display_name || char.name || char.id || "";
    if (targetSlot === "original") return char.id || displayName;
    if (source === "original_character") return `original:${char.id || displayName}`;
    return char.prompt_tag || displayName;
  }

  function historyFaceDetailerRequest(item = {}) {
    const face = item.face_detailer && typeof item.face_detailer === "object" ? item.face_detailer : {};
    return {
      enabled: Boolean(face.enabled),
      mode: String(face.mode || "generation"),
      detector: String(face.detector || "bbox/face_yolov8m.pt"),
      steps: intFrom(face.steps, 12),
      cfg: numberFrom(face.cfg, 4.0),
      denoise: numberFrom(face.denoise, 0.3),
      guide_size: intFrom(face.guide_size, 512),
      max_size: intFrom(face.max_size, 1024),
      bbox_threshold: numberFrom(face.bbox_threshold, 0.5),
      bbox_dilation: intFrom(face.bbox_dilation, 10),
      bbox_crop_factor: numberFrom(face.bbox_crop_factor, 3.0),
      sam_enabled: Boolean(face.sam_enabled),
      seed_policy: String(face.seed_policy || "image_seed_plus_offset"),
      seed_offset: intFrom(face.seed_offset, 100000),
    };
  }

  function historyHandDetailerRequest(item = {}) {
    const hand = item.hand_detailer && typeof item.hand_detailer === "object" ? item.hand_detailer : {};
    const lllite = hand.lllite && typeof hand.lllite === "object" ? hand.lllite : {};
    return {
      enabled: Boolean(hand.enabled),
      mode: String(hand.mode || "generation"),
      detector: String(hand.detector || "bbox/hand_yolov8s.pt"),
      steps: intFrom(hand.steps, 14),
      cfg: numberFrom(hand.cfg, 4.0),
      denoise: numberFrom(hand.denoise, 0.45),
      guide_size: intFrom(hand.guide_size, 512),
      max_size: intFrom(hand.max_size, 1024),
      bbox_threshold: numberFrom(hand.bbox_threshold, 0.35),
      bbox_dilation: intFrom(hand.bbox_dilation, 16),
      bbox_crop_factor: numberFrom(hand.bbox_crop_factor, 2.5),
      drop_size: intFrom(hand.drop_size, 24),
      sam_enabled: Boolean(hand.sam_enabled),
      seed_policy: String(hand.seed_policy || "image_seed_plus_offset"),
      seed_offset: intFrom(hand.seed_offset, 200000),
      lllite_enabled: hand.lllite_enabled !== false && lllite.enabled !== false,
      lllite_model: String(hand.lllite_model || lllite.model || "anima-lllite-inpainting-v2.safetensors"),
      lllite_strength: numberFrom(hand.lllite_strength ?? lllite.strength, 0.85),
      lllite_start: numberFrom(hand.lllite_start ?? lllite.start_percent, 0),
      lllite_end: numberFrom(hand.lllite_end ?? lllite.end_percent, 1),
    };
  }

  const HISTORY_QUALITY_PROMPTS = QUALITY_PROMPTS;
  const HISTORY_RATING_TAGS = RATING_PROMPTS;
  function promptTerms(textValue) {
    return String(textValue || "").split(/,|\n/).map((term) => term.trim()).filter(Boolean);
  }

  function normalizePromptTerm(term) {
    return String(term || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function historyPromptRandomGeneratedParts(item = {}) {
    const candidates = [
      item.prompt_random_collect,
      item.request_data?.prompt_random_collect,
      item.request?.prompt_random_collect,
    ];
    const parts = [];
    for (const candidate of candidates) {
      const data = candidate && typeof candidate === "object" ? candidate : {};
      const generatedItem = data.generated_item && typeof data.generated_item === "object" ? data.generated_item : {};
      if (typeof data.generated_tags === "string" && data.generated_tags.trim()) parts.push(data.generated_tags);
      if (typeof generatedItem.tags === "string" && generatedItem.tags.trim()) parts.push(generatedItem.tags);
    }
    return parts;
  }

  function appendUniquePromptTerms(baseText, extraParts = []) {
    const terms = promptTerms(baseText);
    const seen = new Set(terms.map(normalizePromptTerm).filter(Boolean));
    for (const part of extraParts || []) {
      for (const term of promptTerms(part)) {
        const normalized = normalizePromptTerm(term);
        if (!normalized || seen.has(normalized)) continue;
        seen.add(normalized);
        terms.push(term);
      }
    }
    return terms.join(", ");
  }

  const HISTORY_GENERIC_AUTO_TERMS = new Set(
    [
      ...Object.values(HISTORY_QUALITY_PROMPTS).flatMap(promptTerms),
      ...Object.values(HISTORY_RATING_TAGS),
      "anime illustration",
    ].map(normalizePromptTerm).filter(Boolean),
  );
  const HISTORY_AUTO_BLOCK_START_TERMS = new Set([
    "masterpiece",
    "best quality",
    "anime illustration",
    "score_7",
    "score_8",
    "score_9",
  ]);

  function isHistoryPeopleTag(term) {
    return /^\d+\s*(?:girl|girls|boy|boys)$/i.test(normalizePromptTerm(term));
  }

  function isGeneratedNaturalDescriptionTerm(term) {
    return /^an anime illustration of .+ in a clean, expressive composition\.?$/i.test(normalizePromptTerm(term));
  }

  function isGeneratedNaturalDescriptionStart(term) {
    return /^an anime illustration of .+ in a clean$/i.test(normalizePromptTerm(term));
  }

  function isGeneratedNaturalDescriptionEnd(term) {
    return /^expressive composition\.?$/i.test(normalizePromptTerm(term));
  }

  function generatedNaturalEndIndex(terms, index) {
    if (isGeneratedNaturalDescriptionTerm(terms[index])) return index;
    if (isGeneratedNaturalDescriptionStart(terms[index]) && isGeneratedNaturalDescriptionEnd(terms[index + 1])) return index + 1;
    return -1;
  }

  function stripHistoryGeneratedBlocks(terms = []) {
    const kept = [];
    for (let index = 0; index < terms.length; index += 1) {
      const term = terms[index];
      const normalized = normalizePromptTerm(term);
      if (HISTORY_AUTO_BLOCK_START_TERMS.has(normalized)) {
        const limit = Math.min(terms.length, index + 64);
        let endIndex = -1;
        for (let cursor = index; cursor < limit; cursor += 1) {
          const naturalEnd = generatedNaturalEndIndex(terms, cursor);
          if (naturalEnd >= 0) {
            endIndex = naturalEnd;
            break;
          }
        }
        if (endIndex >= 0) {
          index = endIndex;
          continue;
        }
      }
      kept.push(term);
    }
    return kept;
  }

  function stripGeneratedNaturalFragments(terms = []) {
    const kept = [];
    for (let index = 0; index < terms.length; index += 1) {
      const term = terms[index];
      const naturalEnd = generatedNaturalEndIndex(terms, index);
      if (naturalEnd >= 0) {
        if (kept.length) kept.pop();
        index = naturalEnd;
        continue;
      }
      if (isGeneratedNaturalDescriptionEnd(term)) continue;
      kept.push(term);
    }
    return kept;
  }

  function escapeHistoryCharacterTag(tag) {
    return String(tag || "").replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
  }

  function inferHistoryQualityPreset(item = {}) {
    if (item.quality_preset) return item.quality_preset;
    const terms = new Set(promptTerms(historyPositiveText(item)).map(normalizePromptTerm));
    if (terms.has("clean character design") || terms.has("clear face") || terms.has("full body")) return "character_check";
    if (terms.has("score_8") || terms.has("high quality") || terms.has("highly detailed")) return "high";
    return "standard";
  }

  function historyGeneratedPositiveParts(item = {}, qualityPreset = "standard") {
    const parts = [
      qualityPromptForPreset(qualityPreset, qualityPromptOverrides(item)),
      item.meta_prompt || "anime illustration",
      item.year_prompt || "",
      ratingPromptForPreset(item.rating || "safe", ratingPromptOverrides(item)),
      item.common || "",
      item.outfit_prompt || "",
      item.expression_prompt || "",
      item.pose_prompt || "",
      item.background_prompt || "",
      item.camera_prompt || "",
      item.lighting_prompt || "",
      item.natural_description || "",
    ];
    const characters = Array.isArray(item.characters) ? item.characters : [];
    const characterCount = characters.length;
    if (characterCount === 1) parts.push("1girl");
    if (characterCount > 1) parts.push(`${characterCount}girls`);
    for (const char of characters) {
      if (!char || typeof char !== "object") continue;
      parts.push(char.prompt_tag || "");
      parts.push(escapeHistoryCharacterTag(char.prompt_tag || ""));
      parts.push(char.identity_prompt || "");
      parts.push(char.prompt_safe_name || "");
    }
    parts.push(item.natural_description || "");
    return parts;
  }

  function stripGeneratedHistoryPositive(item = {}, qualityPreset = "standard") {
    const positive = historyPositiveText(item);
    if (!positive) return "";
    const rawPositive = historyRawPositiveText(item);
    if (rawPositive) return appendUniquePromptTerms(rawPositive, historyPromptRandomGeneratedParts(item));
    const generated = new Set(
      historyGeneratedPositiveParts(item, qualityPreset)
        .flatMap(promptTerms)
        .map(normalizePromptTerm)
        .filter(Boolean),
    );
    const terms = stripGeneratedNaturalFragments(
      stripHistoryGeneratedBlocks(promptTerms(positive))
        .filter((term) => {
          const normalized = normalizePromptTerm(term);
          return !generated.has(normalized) && !HISTORY_GENERIC_AUTO_TERMS.has(normalized) && !isHistoryPeopleTag(term);
        }),
    );
    return terms.join(", ");
  }

  function historyReuseData(item = {}) {
    const slots = { character1: null, character2: null, character3: null, original: null };
    for (const char of item.characters || []) {
      const slotNumber = Number(char.slot || 0);
      const slotName = slotNumber === 1 ? "character1" : slotNumber === 2 ? "character2" : slotNumber === 3 ? "character3" : slotNumber === 4 ? "original" : "";
      if (!slotName) continue;
      const normalized = normalizeCharacterItem({
        ...char,
        source: sourceForCharacter(char),
        kind: sourceForCharacter(char) === "original_character" ? "original" : "wai",
      });
      slots[slotName] = { ...normalized, value: historyCharacterValue(char, slotName) };
    }
    const qualityPreset = inferHistoryQualityPreset(item);
    return {
      slots,
      rating: item.rating || "safe",
      rating_prompt_overrides: ratingPromptOverrides(item),
      quality_preset: qualityPreset,
      quality_prompt_overrides: qualityPromptOverrides(item),
      meta_prompt: item.meta_prompt || "anime illustration",
      year_prompt: item.year_prompt || "",
      outfit_prompt: item.outfit_prompt || "",
      expression_prompt: item.expression_prompt || "",
      pose_prompt: item.pose_prompt || "",
      background_prompt: item.background_prompt || "",
      lighting_prompt: item.lighting_prompt || "",
      camera_prompt: item.camera_prompt || "",
      positive_prompt: stripGeneratedHistoryPositive(item, qualityPreset),
      negative_prompt: historyNegativeText(item),
      negative_prompt_mode: "custom",
      negative_preset: item.negative_preset || "anima_recommended",
      prompt_ban: item.prompt_ban || "",
      natural_description: item.natural_description || "",
      model: item.model || state.defaults.model || "",
      width: numberFrom(item.width, 1024),
      height: numberFrom(item.height, 1536),
      steps: intFrom(item.steps, 32),
      cfg: numberFrom(item.cfg, 4.5),
      shift: numberFrom(item.shift ?? item.model_sampling?.shift, numberFrom(state.defaults.shift, 4)),
      sampler: item.sampler || state.defaults.sampler || "er_sde",
      scheduler: item.scheduler || state.defaults.scheduler || "simple",
      seed: intFrom(item.seed, -1),
      seed_mode: "fixed",
      official_loras: loras.historyOfficial(item.official_loras || {}),
      loras: loras.history(item.loras || []),
      dynamic_prompt: { enabled: false },
      prompt_random_collect: { ...promptRandom.historyCollect(item.prompt_random_collect), enabled: false },
      hires_fix: generationForm.historyHiresFix(item),
      image_to_image: i2i.history(item),
      reference_modules: reference.historyModules(item),
      face_detailer: historyFaceDetailerRequest(item),
      hand_detailer: historyHandDetailerRequest(item),
      source_item: item,
    };
  }

  function applyHistoryReuseData(data) {
    state.slots = {
      character1: data.slots.character1,
      character2: data.slots.character2,
      character3: data.slots.character3,
      original: data.slots.original,
    };
    renderSlots();
    UI.setSegValue("#ratingSeg", "rating", data.rating);
    UI.setSegValue("#qualitySeg", "quality", data.quality_preset);
    state.ratingPromptDrafts = ratingPromptOverrides(data);
    state.qualityPromptDrafts = qualityPromptOverrides(data);
    renderRatingPrompt();
    renderQualityPrompt();
    generationForm.applyHistoryBasicsToForm(data);
    loras.applyOfficialToForm(data.official_loras);
    loras.renderRows(data.loras || []);
    setChecked("#dynamicEnabled", Boolean(data.dynamic_prompt?.enabled));
    promptRandom.applyToForm(data.prompt_random_collect || {});

    i2i.applyToForm(data.image_to_image || {}, { update: false });
    reference.applyModulesToForm(data.reference_modules || {}, { update: false });

    const face = data.face_detailer || {};
    setChecked("#fdEnabled", Boolean(face.enabled));
    setValue("#fdSteps", face.steps ?? 12);
    setValue("#fdCfg", face.cfg ?? 4.0);
    setValue("#fdDenoise", face.denoise ?? 0.3);
    setValue("#fdBbox", face.bbox_threshold ?? 0.5);
    const hand = data.hand_detailer || {};
    setChecked("#hdEnabled", Boolean(hand.enabled));
    setValue("#hdSteps", hand.steps ?? 14);
    setValue("#hdCfg", hand.cfg ?? 4.0);
    setValue("#hdDenoise", hand.denoise ?? 0.45);
    setValue("#hdBbox", hand.bbox_threshold ?? 0.35);
    setValue("#hdLlliteStrength", hand.lllite_strength ?? hand.lllite?.strength ?? 0.85);
    updateSummaries();
  }

  function slotRequestValueFromData(data, slotName) {
    const item = data.slots[slotName];
    if (item?.value) return item.value;
    return "None";
  }

  function slotItemFromRequest(slotName, rawValue) {
    const raw = String(rawValue || "").trim();
    if (!raw || raw === "None") return null;
    if (raw.toLowerCase() === "random") return randomSlotItem(slotName);
    const original = slotName === "original";
    const display = raw.startsWith("original:") ? raw.slice("original:".length) : raw;
    const displayName = !original && containsCjkText(display) && !containsKanaText(display) ? "Legacy character" : display;
    return {
      source: original ? "original_character" : "wai_characters",
      id: display,
      displayName,
      originalDisplayName: display,
      promptTag: "",
      kind: original ? "original" : "wai",
      value: raw,
    };
  }

  function reuseDataFromRequest(request = {}) {
    const req = request && typeof request === "object" ? request : {};
    const defaultPositive = state.appSettings.default_positive_prompt ?? state.defaults.positive_prompt ?? "";
    const defaultNegative = state.appSettings.default_negative_prompt ?? state.defaults.negative_prompt ?? "";
    return {
      slots: {
        character1: slotItemFromRequest("character1", req.character1 ?? "None"),
        character2: slotItemFromRequest("character2", req.character2 ?? "None"),
        character3: slotItemFromRequest("character3", req.character3 ?? "None"),
        original: slotItemFromRequest("original", req.original_character ?? "None"),
      },
      rating: req.rating || state.appSettings.rating || "safe",
      rating_prompt_overrides: ratingPromptOverrides(req),
      quality_preset: req.quality_preset || state.appSettings.quality_preset || "standard",
      quality_prompt_overrides: qualityPromptOverrides(req),
      meta_prompt: req.meta_prompt ?? state.appSettings.meta_prompt ?? "anime illustration",
      year_prompt: req.year_prompt ?? state.appSettings.year_prompt ?? "",
      outfit_prompt: req.outfit_prompt ?? state.appSettings.outfit_prompt ?? "",
      expression_prompt: req.expression_prompt ?? state.appSettings.expression_prompt ?? "",
      pose_prompt: req.pose_prompt ?? state.appSettings.pose_prompt ?? "",
      background_prompt: req.background_prompt ?? state.appSettings.background_prompt ?? "",
      lighting_prompt: req.lighting_prompt ?? state.appSettings.lighting_prompt ?? "",
      camera_prompt: req.camera_prompt ?? state.appSettings.camera_prompt ?? "",
      positive_prompt: req.positive_prompt ?? defaultPositive,
      negative_prompt: req.negative_prompt_raw ?? req.negative_prompt ?? defaultNegative,
      negative_prompt_mode: req.negative_prompt_mode || state.appSettings.negative_prompt_mode || "append",
      negative_preset: req.negative_preset || state.appSettings.negative_preset || "anima_recommended",
      prompt_ban: req.prompt_ban ?? "",
      natural_description: req.natural_description ?? state.appSettings.natural_description ?? "",
      model: req.model || state.appSettings.model || state.defaults.model || "",
      width: numberFrom(req.width, numberFrom(state.appSettings.width ?? state.defaults.width, 1024)),
      height: numberFrom(req.height, numberFrom(state.appSettings.height ?? state.defaults.height, 1536)),
      steps: intFrom(req.steps, intFrom(state.appSettings.steps ?? state.defaults.steps, 32)),
      cfg: numberFrom(req.cfg, numberFrom(state.appSettings.cfg ?? state.defaults.cfg, 4.5)),
      shift: numberFrom(req.shift, numberFrom(state.appSettings.shift ?? state.defaults.shift, 4)),
      sampler: req.sampler || state.appSettings.sampler || state.defaults.sampler || "er_sde",
      scheduler: req.scheduler || state.appSettings.scheduler || state.defaults.scheduler || "simple",
      seed: intFrom(req.seed, intFrom(state.appSettings.seed ?? state.defaults.seed, -1)),
      seed_mode: req.seed_mode || state.appSettings.seed_mode || "fixed",
      official_loras: loras.historyOfficial(req.official_loras || {}),
      loras: loras.history(req.loras || []),
      dynamic_prompt: req.dynamic_prompt && typeof req.dynamic_prompt === "object" ? req.dynamic_prompt : { enabled: false },
      prompt_random_collect: promptRandom.historyCollect(req.prompt_random_collect),
      hires_fix: generationForm.historyHiresFix({ hires_fix: req.hires_fix }),
      image_to_image: i2i.history({ image_to_image: req.image_to_image }),
      reference_modules: reference.historyModules({ reference_modules: req.reference_modules }),
      face_detailer: historyFaceDetailerRequest({ face_detailer: req.face_detailer }),
      hand_detailer: historyHandDetailerRequest({ hand_detailer: req.hand_detailer }),
      source_item: req,
    };
  }

  function historyRequestFromItem(item = {}) {
    const data = historyReuseData(item);
    return {
      workflow_mode: data.hires_fix.enabled ? "anima_mobile_extended" : "anima",
      character1: slotRequestValueFromData(data, "character1"),
      character2: slotRequestValueFromData(data, "character2"),
      character3: slotRequestValueFromData(data, "character3"),
      original_character: slotRequestValueFromData(data, "original"),
      character1_weight: 1.0,
      character2_weight: 1.0,
      character3_weight: 1.0,
      original_weight: 1.0,
      character1_role: "main",
      character2_role: "left",
      character3_role: "right",
      rating: data.rating,
      rating_prompt_overrides: data.rating_prompt_overrides,
      quality_preset: data.quality_preset,
      quality_prompt_overrides: data.quality_prompt_overrides,
      meta_prompt: item.meta_prompt || "anime illustration",
      year_prompt: item.year_prompt || "",
      outfit_prompt: item.outfit_prompt || "",
      expression_prompt: item.expression_prompt || "",
      pose_prompt: item.pose_prompt || "",
      background_prompt: item.background_prompt || "",
      lighting_prompt: item.lighting_prompt || "",
      camera_prompt: item.camera_prompt || "",
      natural_description: data.natural_description,
      positive_prompt: data.positive_prompt,
      negative_prompt: data.negative_prompt,
      negative_prompt_raw: data.negative_prompt,
      negative_prompt_mode: data.negative_prompt_mode,
      negative_preset: data.negative_preset,
      prompt_ban: item.prompt_ban || "",
      common_prompt: item.common || "",
      model: data.model,
      text_encoder: state.appSettings.text_encoder || state.defaults.text_encoder || "qwen_3_06b_base.safetensors",
      vae: state.appSettings.vae || state.defaults.vae || "qwen_image_vae.safetensors",
      width: data.width,
      height: data.height,
      steps: data.steps,
      cfg: data.cfg,
      shift: data.shift,
      sampler: data.sampler,
      scheduler: data.scheduler,
      seed: data.seed,
      seed_mode: data.seed_mode,
      official_loras: data.official_loras,
      loras: data.loras,
      count: 1,
      wait: false,
      dynamic_prompt: { enabled: false },
      prompt_random_collect: promptRandom.historyCollect(data.prompt_random_collect),
      hires_fix: data.hires_fix,
      reference_assist: { enabled: false },
      image_to_image: i2i.history(item),
      face_detailer: historyFaceDetailerRequest(item),
      hand_detailer: historyHandDetailerRequest(item),
      reference_modules: reference.historyModules(item),
    };
  }

  function applyHistoryToForm(item) {
    applyHistoryReuseData(historyReuseData(item));
    UI.closeSheets();
    UI.switchTab("expose");
    UI.toast("設定を再利用しました");
  }

  async function generateFrameVariations() {
    if (!state.detailItem?.id) return;
    const count = generationForm.selectedVariationCount();
    const request = {
      ...historyRequestFromItem(state.detailItem),
      seed_mode: "random",
      seed: -1,
      count,
      wait: false,
    };
    try {
      text("#frameActionStatus", "バリエーションをキュー投入中...");
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(request),
      });
      assertGenerateQueued(data);
      UI.closeSheets();
      await finishGenerateQueued(data, request, {
        toast: (queued) => `🎲 ${queued}枚キューに入れました`,
      });
    } catch (error) {
      text("#frameActionStatus", errorMessage(error));
      UI.toast(errorMessage(error), "error");
    }
  }

  function settingsFromForm() {
    const next = clone(state.appSettings);
    const hiresFix = generationForm.collectHiresFix();
    Object.assign(next, {
      workflow_mode: hiresFix.enabled ? "anima_mobile_extended" : "anima",
      model: value("#modelSelect", state.defaults.model || next.model || ""),
      text_encoder: state.defaults.text_encoder || next.text_encoder || "qwen_3_06b_base.safetensors",
      vae: state.defaults.vae || next.vae || "qwen_image_vae.safetensors",
      width: numberValue("#widthInput", 1024),
      height: numberValue("#heightInput", 1536),
      steps: numberValue("#stepsInput", 32),
      cfg: numberValue("#cfgInput", 4.5),
      shift: numberValue("#shiftInput", 4),
      sampler: value("#samplerSelect", "er_sde"),
      scheduler: value("#schedulerSelect", "simple"),
      seed: Math.trunc(numberValue("#seedInput", -1)),
      seed_mode: value("#seedModeSelect", "fixed"),
      generation_count: generationForm.selectedQueueCount(),
      default_positive_prompt: value("#positivePrompt", ""),
      default_negative_prompt: value("#negativePrompt", ""),
      negative_prompt_mode: value("#negativeMode", "append"),
      negative_preset: value("#negativePreset", "anima_recommended"),
      rating: UI.segValue("#ratingSeg", "rating") || "safe",
      rating_prompt_overrides: collectRatingPromptOverrides(),
      quality_preset: UI.segValue("#qualitySeg", "quality") || "standard",
      quality_prompt_overrides: collectQualityPromptOverrides(),
      meta_prompt: value("#metaPrompt", "anime illustration"),
      year_prompt: value("#yearPrompt", ""),
      outfit_prompt: value("#outfitPrompt", ""),
      expression_prompt: value("#expressionPrompt", ""),
      pose_prompt: value("#posePrompt", ""),
      background_prompt: value("#backgroundPrompt", ""),
      camera_prompt: value("#cameraPrompt", ""),
      lighting_prompt: value("#lightingPrompt", ""),
      natural_description: value("#naturalDescription", ""),
      official_loras: loras.collectOfficial(),
      loras: loras.collect(),
      prompt_random_collect: promptRandom.collect(),
      hires_fix: hiresFix,
      face_detailer: collectFaceDetailerSettings(checked("#fdEnabled"), "generation"),
      hand_detailer: collectHandDetailerSettings(checked("#hdEnabled"), "generation"),
      watermark: collectWatermark(),
      public_save: {
        ...(next.public_save || {}),
        apply_watermark: checked("#watermarkEnabled"),
      },
    });
    return next;
  }

  async function saveAutoPrompts() {
    const settings = clone(state.appSettings);
    Object.assign(settings, {
      rating: selectedRatingPreset(),
      rating_prompt_overrides: collectRatingPromptOverrides(),
      quality_preset: selectedQualityPreset(),
      quality_prompt_overrides: collectQualityPromptOverrides(),
      meta_prompt: value("#metaPrompt", "anime illustration"),
      year_prompt: value("#yearPrompt", ""),
      outfit_prompt: value("#outfitPrompt", ""),
      expression_prompt: value("#expressionPrompt", ""),
      pose_prompt: value("#posePrompt", ""),
      background_prompt: value("#backgroundPrompt", ""),
      camera_prompt: value("#cameraPrompt", ""),
      lighting_prompt: value("#lightingPrompt", ""),
      natural_description: value("#naturalDescription", ""),
    });
    const data = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        settings,
        mode: "current",
        reason: "darkroom_frontend_save_auto_prompts",
      }),
    });
    state.appSettings = data.settings;
    state.ratingPromptDrafts = ratingPromptOverrides(state.appSettings);
    state.qualityPromptDrafts = qualityPromptOverrides(state.appSettings);
    renderRatingPrompt();
    renderQualityPrompt();
    text("#autoPromptStatus", "保存しました");
    UI.toast("自動挿入プロンプトを保存しました");
  }

  async function saveDefaults() {
    const settings = settingsFromForm();
    const data = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        settings,
        mode: "current",
        reason: "darkroom_frontend_save_defaults",
      }),
    });
    state.appSettings = data.settings;
    applySettingsToForm(state.appSettings, state.defaults);
    loras.renderConfigured(state.appSettings);
    text("#settingsStatus", "保存しました");
    UI.toast("既定値を保存しました");
  }

  async function resetDefaults() {
    const data = await api("/api/settings/reset", { method: "POST", body: "{}" });
    state.appSettings = data.settings;
    applySettingsToForm(state.appSettings, state.defaults);
    loras.renderConfigured(state.appSettings);
    text("#settingsStatus", "リセットしました");
    UI.toast("既定値をリセットしました");
  }

  function renderDiagnostics(data) {
    const table = $("#connMeta");
    if (table) {
      table.replaceChildren();
      addMetaRow(table, "API_ADDR", data.api_addr || "-");
      addMetaRow(table, "CHARACTER_CATALOG", data.character_catalog_root_exists ? "built-in/fallback found" : "missing");
      addMetaRow(table, "WORKFLOW", data.anima_workflow_found ? "found" : "missing");
      addMetaRow(table, "MAPPING", data.anima_mapping_found ? "found" : "missing");
      addMetaRow(table, "MODELS_CACHE", data.models_cache || {});
      addMetaRow(table, "CATALOG", `${data.catalog_count ?? "-"} + custom ${data.custom_count ?? 0} / original ${data.original_count ?? "-"}`);
      addMetaRow(table, "HISTORY", data.history_count ?? "-");
      addMetaRow(table, "SHIFT", data.anima_shift || {});
    }
    text("#diagBadge", data.api_addr || "-");
  }

  async function loadDiagnostics() {
    text("#settingsStatus", "");
    try {
      const data = await api("/api/diagnostics");
      renderDiagnostics(data);
    } catch (error) {
      text("#settingsStatus", errorMessage(error));
    }
  }

  async function reloadModels() {
    text("#settingsStatus", "モデル一覧を取得中...");
    await loadModels(true);
    text("#settingsStatus", "モデル一覧を更新しました");
    UI.toast("モデル一覧を更新しました");
  }

  async function reloadUi() {
    text("#settingsStatus", "UIを再読み込みします...");
    try {
      if ("caches" in window) {
        const keys = await window.caches.keys();
        await Promise.all(keys.map((key) => window.caches.delete(key)));
      }
    } catch (error) {
      console.warn("Failed to clear browser caches", error);
    }
    UI.toast("UIを再読み込みします");
    const url = new URL(window.location.href);
    url.searchParams.set("reload", String(Date.now()));
    window.location.replace(url.toString());
  }

  async function login() {
    text("#loginStatus", "");
    try {
      await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ pin: value("#pinInput", "") }),
      });
      UI.enterDarkroom();
      await bootstrap();
    } catch (error) {
      text("#loginStatus", errorMessage(error));
    }
  }

  function reportBootstrapFailures(results, tasks) {
    const failures = results
      .map((result, index) => ({ result, task: tasks[index] || {} }))
      .filter((entry) => entry.result.status === "rejected");
    if (!failures.length) return;
    for (const failure of failures) {
      console.warn(`bootstrap optional failed: ${failure.task.label || "optional"}`, failure.result.reason);
    }
    const authFailure = failures.find((failure) => isUnauthorized(failure.result.reason));
    if (authFailure) {
      const message = errorMessage(authFailure.result.reason) || authExpiredMessage();
      text("#loginStatus", message);
      exitToLogin(message);
      throw authFailure.result.reason;
    }
    const labels = failures.map((failure) => failure.task.label || "optional").join(" / ");
    UI.toast(`起動時の一部読み込みに失敗: ${labels}`, "error");
    for (const failure of failures) {
      if (failure.task.status) text(failure.task.status, `${failure.task.label}: ${errorMessage(failure.result.reason)}`);
    }
  }

  async function bootstrap(initialData = null) {
    const data = initialData || await api("/api/bootstrap");
    state.bootstrap = data;
    state.appSettings = data.settings || {};
    state.defaults = data.defaults || {};
    text("#catalogCount", `${data.catalog_count || 0} chars + ${data.custom_count || 0} custom / original ${data.original_count || 0}`);
    applySettingsToForm(state.appSettings, state.defaults);

    const modelResult = await Promise.allSettled([loadModels(false), loras.loadCatalog()]);
    if (modelResult[0].status === "rejected") {
      console.warn(modelResult[0].reason);
      fillSelect("#modelSelect", [], state.defaults.model || state.appSettings.model || "Anima\\anima-preview3-base.safetensors");
      fillSelect("#samplerSelect", [], state.defaults.sampler || state.appSettings.sampler || "er_sde");
      fillSelect("#schedulerSelect", [], state.defaults.scheduler || state.appSettings.scheduler || "simple");
    }
    reportBootstrapFailures(modelResult, [
      { label: "モデル一覧", status: "#settingsStatus" },
      { label: "LoRA一覧", status: "#settingsStatus" },
    ]);
    loras.renderConfigured(state.appSettings);
    const optionalResults = await Promise.allSettled([
      loadFavorites(),
      searchCharacters(),
      history.loadContact(true),
    ]);
    reportBootstrapFailures(optionalResults, [
      { label: "お気に入り", status: "#catalogCount" },
      { label: "キャラ検索", status: "#catalogCount" },
      { label: "履歴", status: "#contactCount" },
    ]);
    updateSummaries();
  }

  async function tryBootstrapSession() {
    try {
      const data = await api("/api/bootstrap");
      UI.enterDarkroom();
      await bootstrap(data);
    } catch (error) {
      const message = errorMessage(error) || authExpiredMessage();
      text("#loginStatus", message);
      exitToLogin(message);
    }
  }

  function registerMainActions() {
    registerActions({
      login: () => login(),
      "random-slot": () => setRandomSlot(),
      "clear-slot": () => clearSlot(),
      "toggle-character-favorites": () => toggleCharacterFavorites(),
      "load-more-characters": () => loadMoreCharacters(),
      "toggle-favorite-slot": () => toggleFavoriteForArmedSlot(),
      preview: () => previewPayload(),
      generate: () => generate(),
      "dynamic-wildcards": () => loadDynamicWildcards(),
      "dynamic-preview": () => previewDynamicPrompt(),
      "prompt-convert": () => convertPromptFromJapanese(),
      "prompt-converter-status": () => loadPromptConverterStatus(true),
      "save-positive-fav": () => savePositiveFavorite(),
      "open-positive-favs": () => openPositiveFavorites(),
      "open-templates": () => openPositiveTemplates(),
      "save-recipe": () => saveRecipe(),
      "open-recipes": () => openRecipes(),
      "frame-variations": () => generateFrameVariations(),
      "frame-reuse": () => {
        if (state.detailItem) applyHistoryToForm(state.detailItem);
      },
      "frame-to-i2i": () => i2i.setFromHistoryItem(state.detailItem),
      "frame-face-detail": () => queueFrameFaceDetailer(),
      "frame-hand-detail": () => queueFrameHandDetailer(),
      "save-auto-prompts": () => saveAutoPrompts(),
      "save-defaults": () => saveDefaults(),
      "reset-defaults": () => resetDefaults(),
      "reload-models": () => reloadModels(),
      "reload-ui": () => reloadUi(),
    });
    registerActions(history.actions);
    registerActions(i2i.actions);
    registerActions(reference.actions);
    registerActions(loras.actions);
    registerActions(promptRandom.actions);
    registerActions(queue.actions);
  }

  function bindEvents() {
    UI.bindSeg("#ratingSeg", "rating", () => {
      renderRatingPrompt();
      updateSummaries();
    });
    UI.bindSeg("#qualitySeg", "quality", () => {
      renderQualityPrompt();
      updateSummaries();
    });
    $("#pinInput")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") login();
    });

    $("#charSearch")?.addEventListener("input", scheduleCharacterSearch);

    $("details[data-fold='dictionary']")?.addEventListener("toggle", (event) => {
      if (event.target.open) {
        loadPromptDictionaryStatus().catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    $("details[data-fold='prompt-converter']")?.addEventListener("toggle", (event) => {
      if (event.target.open) {
        loadPromptConverterStatus().catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    history.bindEvents();
    i2i.bindEvents();
    reference.bindEvents();
    promptRandom.bindEvents();
    queue.bindEvents();
    $("#ratingPrompt")?.addEventListener("input", updateRatingPromptDraft);
    $("#qualityPrompt")?.addEventListener("input", updateQualityPromptDraft);

    $("#dictQuery")?.addEventListener("input", schedulePromptDictionarySearch);

    $("#promptConvertSource")?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || (!event.ctrlKey && !event.metaKey)) return;
      event.preventDefault();
      convertPromptFromJapanese().catch((error) => {
        text("#promptConverterStatus", errorMessage(error));
        UI.toast(errorMessage(error), "error");
      });
    });

    $("#dictResults")?.addEventListener("click", (event) => {
      const row = event.target.closest("[data-dict-insert]");
      if (!row) return;
      insertPromptDictionaryTag(row.dataset.dictInsert);
    });

    $("#wildcardChips")?.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip[data-wildcard-name]");
      if (!chip) return;
      insertPositivePromptText(`__${chip.dataset.wildcardName}__, `);
    });

    $("#promptSheetList")?.addEventListener("click", (event) => {
      const moreTarget = event.target.closest("[data-action='load-more-prompts']");
      if (moreTarget) {
        event.preventDefault();
        text("#promptSheetStatus", "読み込み中...");
        loadPositiveTemplates(value("#promptSheetQuery", ""), { append: true }).catch((error) => {
          text("#promptSheetStatus", errorMessage(error));
          UI.toast(errorMessage(error), "error");
        });
        return;
      }
      const deleteTarget = event.target.closest("[data-prompt-delete-id]");
      if (deleteTarget) {
        event.preventDefault();
        deletePositiveFavorite(deleteTarget.dataset.promptDeleteId).catch((error) => UI.toast(errorMessage(error), "error"));
        return;
      }
      const row = event.target.closest("[data-prompt-item-id]");
      if (!row) return;
      usePromptSheetItem(row.dataset.promptItemId).catch((error) => UI.toast(errorMessage(error), "error"));
    });

    $("#promptSheetQuery")?.addEventListener("input", () => {
      window.clearTimeout(state.promptSheetQueryTimer);
      if (state.promptSheetMode === "favorites") {
        renderPromptSheet();
        return;
      }
      state.promptSheetQueryTimer = window.setTimeout(() => {
        text("#promptSheetStatus", "読み込み中...");
        loadPositiveTemplates(value("#promptSheetQuery", ""), { append: false }).catch((error) => {
          text("#promptSheetStatus", errorMessage(error));
          UI.toast(errorMessage(error), "error");
        });
      }, 250);
    });

    $("#recipeList")?.addEventListener("click", (event) => {
      const deleteTarget = event.target.closest("[data-recipe-delete-id]");
      if (deleteTarget) {
        event.preventDefault();
        deleteRecipeItem(deleteTarget.dataset.recipeDeleteId).catch((error) => {
          text("#recipeStatus", errorMessage(error));
          UI.toast(errorMessage(error), "error");
        });
        return;
      }
      const row = event.target.closest("[data-recipe-id]");
      if (!row) return;
      applyRecipe(row.dataset.recipeId).catch((error) => {
        text("#recipeStatus", errorMessage(error));
        UI.toast(errorMessage(error), "error");
      });
    });

    $("#charSlots")?.addEventListener("click", (event) => {
      const slot = event.target.closest(".slot[data-slot]");
      if (!slot) return;
      state.armedSlot = slot.dataset.slot;
      renderSlots();
    });

    $("#sizeChips")?.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip[data-size]");
      if (!chip) return;
      const [width, height] = chip.dataset.size.split("x").map(Number);
      setValue("#widthInput", width);
      setValue("#heightInput", height);
      updateSummaries();
    });

    document.addEventListener("click", (event) => {
      const favorite = event.target.closest("[data-favorite-id]");
      if (favorite) {
        applyCharacterToSlot({
          source: favorite.dataset.favoriteSource,
          id: favorite.dataset.favoriteId,
          display_name: favorite.dataset.favoriteName,
          display_name_ja: favorite.dataset.favoriteDisplayName,
          prompt_tag: favorite.dataset.favoritePromptTag,
          prompt_safe_name: favorite.dataset.favoritePromptSafeName,
        });
        markFavoriteUsedWithRetry(favorite.dataset.favoriteSource, favorite.dataset.favoriteId);
        clearCharacterSearch();
        UI.toast(`${favorite.dataset.favoriteDisplayName || favorite.dataset.favoriteName} を反映しました`);
        return;
      }

      const result = event.target.closest("[data-character-id]");
      if (result) {
        applyCharacterToSlot({
          source: result.dataset.characterSource,
          id: result.dataset.characterId,
          display_name: result.dataset.characterOriginalName || result.dataset.characterName,
          display_name_ja: result.dataset.characterName,
          kind: result.dataset.characterKind,
          prompt_tag: result.dataset.characterPromptTag,
          prompt_safe_name: result.dataset.characterPromptSafeName,
        });
        clearCharacterSearch();
        UI.toast(`${result.dataset.characterName} を反映しました`);
        return;
      }

      const settingsTab = event.target.closest("#tabs button[data-tab='settings']");
      if (settingsTab) window.setTimeout(loadDiagnostics, 0);

      const actionTarget = event.target.closest("[data-action]");
      if (!actionTarget) return;
      const action = actionTarget.dataset.action;
      if (action === "close-sheet") {
        queue.stopPolling();
        return;
      }
      dispatchAction(action, actionTarget).catch((error) => {
        UI.toast(errorMessage(error), "error");
        if (action?.startsWith("frame-")) text("#frameActionStatus", errorMessage(error));
        if (action?.startsWith("i2i-")) text("#i2iStatus", errorMessage(error));
        if (action?.startsWith("outfit-") || action?.startsWith("pose-")) text("#refModStatus", errorMessage(error));
        if (action?.startsWith("prompt-convert")) text("#promptConverterStatus", errorMessage(error));
        if (action?.startsWith("prompt-random")) text("#promptRandomStatus", errorMessage(error));
        if (action === "save-auto-prompts") text("#autoPromptStatus", errorMessage(error));
        if (["save-defaults", "reset-defaults", "reload-models", "reload-ui"].includes(action)) text("#settingsStatus", errorMessage(error));
        if (["save-recipe", "open-recipes"].includes(action)) text("#recipeStatus", errorMessage(error));
        if (["open-queue", "queue-refresh", "queue-interrupt"].includes(action)) text("#queueStatus", errorMessage(error));
        if (action === "history-refresh") text("#contactCount", "更新失敗");
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") queue.stopPolling();
    });

    document.addEventListener("input", (event) => {
      if (event.target.closest("#settingsSheet")) {
        state.appSettings = { ...state.appSettings, watermark: collectWatermark() };
      }
      if (event.target.closest("#exposeView") || event.target.closest("#exposeBar")) updateSummaries();
    });

    document.addEventListener("change", (event) => {
      if (event.target.closest("#settingsSheet")) {
        state.appSettings = { ...state.appSettings, watermark: collectWatermark() };
      }
      if (event.target.closest("#exposeView") || event.target.closest("#exposeBar")) updateSummaries();
    });
  }

  function init() {
    registerMainActions();
    bindEvents();
    clearCharacterSearch();
    i2i.renderPreview();
    reference.renderPreviews();
    renderSlots();
    updateSummaries();
    tryBootstrapSession();
  }

  onDomReady(init);
})();
