import {
  clone,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.46-tuning-quick-controls-20260625";

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

export function createPromptPresetsFeature({
  api,
  state,
  UI = window.UI,
  updateSummaries = () => {},
} = {}) {
  function selectedQualityPreset() {
    return UI.segValue("#qualitySeg", "quality") || "standard";
  }

  function selectedRatingPreset() {
    return UI.segValue("#ratingSeg", "rating") || "safe";
  }

  function ratingPromptOverrides(settings = state?.appSettings) {
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
    return { ...ratingPromptOverrides(state?.appSettings), ...state.ratingPromptDrafts };
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

  function qualityPromptOverrides(settings = state?.appSettings) {
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
    return { ...qualityPromptOverrides(state?.appSettings), ...state.qualityPromptDrafts };
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

  function applySettings(settings = {}) {
    UI.setSegValue("#ratingSeg", "rating", settings.rating || "safe");
    UI.setSegValue("#qualitySeg", "quality", settings.quality_preset || "standard");
    state.ratingPromptDrafts = ratingPromptOverrides(settings);
    state.qualityPromptDrafts = qualityPromptOverrides(settings);
    renderRatingPrompt();
    renderQualityPrompt();
  }

  function applyReuseData(data = {}) {
    UI.setSegValue("#ratingSeg", "rating", data.rating);
    UI.setSegValue("#qualitySeg", "quality", data.quality_preset);
    state.ratingPromptDrafts = ratingPromptOverrides(data);
    state.qualityPromptDrafts = qualityPromptOverrides(data);
    renderRatingPrompt();
    renderQualityPrompt();
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

  function bindEvents() {
    UI.bindSeg("#ratingSeg", "rating", () => {
      renderRatingPrompt();
      updateSummaries();
    });
    UI.bindSeg("#qualitySeg", "quality", () => {
      renderQualityPrompt();
      updateSummaries();
    });
    document.querySelector("#ratingPrompt")?.addEventListener("input", updateRatingPromptDraft);
    document.querySelector("#qualityPrompt")?.addEventListener("input", updateQualityPromptDraft);
  }

  return {
    QUALITY_PROMPTS,
    RATING_PROMPTS,
    selectedQualityPreset,
    selectedRatingPreset,
    ratingPromptOverrides,
    qualityPromptOverrides,
    collectRatingPromptOverrides,
    collectQualityPromptOverrides,
    ratingPromptForPreset,
    qualityPromptForPreset,
    renderRatingPrompt,
    renderQualityPrompt,
    updateRatingPromptDraft,
    updateQualityPromptDraft,
    applySettings,
    applyReuseData,
    saveAutoPrompts,
    bindEvents,
    actions: {
      "save-auto-prompts": () => saveAutoPrompts(),
    },
  };
}
