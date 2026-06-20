import { createApiClient, authExpiredMessage, errorMessage, isUnauthorized } from "./api.js?v=v1.34-character-module-20260620";
import { dispatchAction, registerActions } from "./actions.js?v=v1.34-character-module-20260620";
import { onDomReady } from "./bootstrap.js?v=v1.34-character-module-20260620";
import {
  $,
  $$,
  checked,
  clone,
  displayValue,
  intFrom,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
  text,
  unique,
  value,
} from "./dom.js?v=v1.34-character-module-20260620";
import { createCharacterFeature } from "./characters.js?v=v1.34-character-module-20260620";
import { createGenerationFormFeature } from "./generation-form.js?v=v1.34-character-module-20260620";
import { createHistoryFeature } from "./history.js?v=v1.34-character-module-20260620";
import { createI2iFeature } from "./i2i.js?v=v1.34-character-module-20260620";
import { createLoraFeature } from "./loras.js?v=v1.34-character-module-20260620";
import { createPromptRandomUi } from "./prompt-random.js?v=v1.34-character-module-20260620";
import { createPromptLibraryFeature } from "./prompt-library.js?v=v1.34-character-module-20260620";
import { createQueueFeature } from "./queue.js?v=v1.34-character-module-20260620";
import { createReferenceFeature } from "./reference.js?v=v1.34-character-module-20260620";
import { createSettingsFeature } from "./settings.js?v=v1.34-character-module-20260620";
import { createInitialState } from "./state.js?v=v1.34-character-module-20260620";

(() => {
  "use strict";

  const UI = window.UI;

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
  const characters = createCharacterFeature({
    api,
    state,
    UI,
    errorMessage,
    updateSummaries: () => updateSummaries(),
  });
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
  const settingsFeature = createSettingsFeature({
    api,
    state,
    UI,
    errorMessage,
    addMetaRow: (table, label, nextValue, selectable) => addMetaRow(table, label, nextValue, selectable),
    loadModels: (refresh) => loadModels(refresh),
    collectSettings: () => settingsFromForm(),
    applySettingsToForm: (nextSettings, defaults) => applySettingsToForm(nextSettings, defaults),
    renderConfiguredLoras: (nextSettings) => loras.renderConfigured(nextSettings),
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
    collectWatermark: () => settingsFeature.collectWatermark(),
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
    slotRequestValue: (slotName) => characters.slotRequestValue(slotName),
    collectRatingPromptOverrides: () => collectRatingPromptOverrides(),
    collectQualityPromptOverrides: () => collectQualityPromptOverrides(),
    collectFaceDetailerSettings: (enabled, mode) => collectFaceDetailerSettings(enabled, mode),
    collectHandDetailerSettings: (enabled, mode) => collectHandDetailerSettings(enabled, mode),
    promptRandom,
    loras,
    i2i,
    reference,
  });
  const promptLibrary = createPromptLibraryFeature({
    api,
    state,
    UI,
    errorMessage,
    confirmDanger: (options) => confirmDanger(options),
    updateSummaries: () => updateSummaries(),
    collectRequest: () => collectRequest(),
    applyHistoryReuseData: (data) => applyHistoryReuseData(data),
    reuseDataFromRequest: (request) => reuseDataFromRequest(request),
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

  async function confirmDanger({ title = "確認しますか?", message = "", label = "実行する" } = {}) {
    const choice = await UI.ask({
      title,
      message,
      choices: [{ label, value: "yes", kind: "danger" }],
    });
    return choice === "yes";
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
    settingsFeature.applyWatermark(settings.watermark || {});
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
      const normalized = characters.normalizeCharacterItem({
        ...char,
        source: characters.sourceForCharacter(char),
        kind: characters.sourceForCharacter(char) === "original_character" ? "original" : "wai",
      });
      slots[slotName] = { ...normalized, value: characters.historyCharacterValue(char, slotName) };
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
    characters.applySlots(data.slots);
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

  function reuseDataFromRequest(request = {}) {
    const req = request && typeof request === "object" ? request : {};
    const defaultPositive = state.appSettings.default_positive_prompt ?? state.defaults.positive_prompt ?? "";
    const defaultNegative = state.appSettings.default_negative_prompt ?? state.defaults.negative_prompt ?? "";
    return {
      slots: {
        character1: characters.slotItemFromRequest("character1", req.character1 ?? "None"),
        character2: characters.slotItemFromRequest("character2", req.character2 ?? "None"),
        character3: characters.slotItemFromRequest("character3", req.character3 ?? "None"),
        original: characters.slotItemFromRequest("original", req.original_character ?? "None"),
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
      character1: characters.slotRequestValueFromData(data, "character1"),
      character2: characters.slotRequestValueFromData(data, "character2"),
      character3: characters.slotRequestValueFromData(data, "character3"),
      original_character: characters.slotRequestValueFromData(data, "original"),
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
      watermark: settingsFeature.collectWatermark(),
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
      characters.loadFavorites(),
      characters.searchCharacters(),
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
      preview: () => previewPayload(),
      generate: () => generate(),
      "frame-variations": () => generateFrameVariations(),
      "frame-reuse": () => {
        if (state.detailItem) applyHistoryToForm(state.detailItem);
      },
      "frame-to-i2i": () => i2i.setFromHistoryItem(state.detailItem),
      "frame-face-detail": () => queueFrameFaceDetailer(),
      "frame-hand-detail": () => queueFrameHandDetailer(),
      "save-auto-prompts": () => saveAutoPrompts(),
    });
    registerActions(characters.actions);
    registerActions(history.actions);
    registerActions(i2i.actions);
    registerActions(reference.actions);
    registerActions(loras.actions);
    registerActions(promptRandom.actions);
    registerActions(queue.actions);
    registerActions(settingsFeature.actions);
    registerActions(promptLibrary.actions);
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

    characters.bindEvents();
    history.bindEvents();
    i2i.bindEvents();
    reference.bindEvents();
    promptRandom.bindEvents();
    queue.bindEvents();
    settingsFeature.bindEvents();
    promptLibrary.bindEvents();
    $("#ratingPrompt")?.addEventListener("input", updateRatingPromptDraft);
    $("#qualityPrompt")?.addEventListener("input", updateQualityPromptDraft);

    $("#sizeChips")?.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip[data-size]");
      if (!chip) return;
      const [width, height] = chip.dataset.size.split("x").map(Number);
      setValue("#widthInput", width);
      setValue("#heightInput", height);
      updateSummaries();
    });

    document.addEventListener("click", (event) => {
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
      if (event.target.closest("#exposeView") || event.target.closest("#exposeBar")) updateSummaries();
    });

    document.addEventListener("change", (event) => {
      if (event.target.closest("#exposeView") || event.target.closest("#exposeBar")) updateSummaries();
    });
  }

  function init() {
    registerMainActions();
    bindEvents();
    characters.clearCharacterSearch();
    i2i.renderPreview();
    reference.renderPreviews();
    characters.renderSlots();
    updateSummaries();
    tryBootstrapSession();
  }

  onDomReady(init);
})();
