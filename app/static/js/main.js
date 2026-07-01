import { createApiClient, errorMessage, isUnauthorized } from "./api.js?v=v2.0-drawers-20260702";
import { dispatchAction, registerActions } from "./actions.js?v=v2.0-drawers-20260702";
import { createAppShell, exitToLogin } from "./app-shell.js?v=v2.0-drawers-20260702";
import { onDomReady } from "./bootstrap.js?v=v2.0-drawers-20260702";
import {
  $,
  $$,
  checked,
  clone,
  numberValue,
  setValue,
  text,
  value,
} from "./dom.js?v=v2.0-drawers-20260702";
import { createAssistHubFeature } from "./assist-hub.js?v=v2.0-drawers-20260702";
import { createCharacterFeature } from "./characters.js?v=v2.0-drawers-20260702";
import { createGenerationActionsFeature } from "./generation-actions.js?v=v2.0-drawers-20260702";
import { createGenerationFormFeature } from "./generation-form.js?v=v2.0-drawers-20260702";
import { createHistoryFeature } from "./history.js?v=v2.0-drawers-20260702";
import { createHistoryReuseFeature } from "./history-reuse.js?v=v2.0-drawers-20260702";
import { createI2iFeature } from "./i2i.js?v=v2.0-drawers-20260702";
import { createLoraFeature } from "./loras.js?v=v2.0-drawers-20260702";
import { createPromptRandomUi } from "./prompt-random.js?v=v2.0-drawers-20260702";
import { createPromptLibraryFeature } from "./prompt-library.js?v=v2.0-drawers-20260702";
import { createPromptPresetsFeature } from "./prompt-presets.js?v=v2.0-drawers-20260702";
import { createQueueFeature } from "./queue.js?v=v2.0-drawers-20260702";
import { createReferenceFeature } from "./reference.js?v=v2.0-drawers-20260702";
import { createSettingsFeature } from "./settings.js?v=v2.0-drawers-20260702";
import { createInitialState } from "./state.js?v=v2.0-drawers-20260702";
import { createDetailerFeature } from "./detailers.js?v=v2.0-drawers-20260702";
import { addMetaRow, characterSummary, fillSelect } from "./render-helpers.js?v=v2.0-drawers-20260702";
import { createTuningControlsFeature } from "./tuning-controls.js?v=v2.0-drawers-20260702";

(() => {
  "use strict";

  const UI = window.UI;

  const state = createInitialState();
  let tuningControls = null;

  const { api, fetchWithAuthHandling } = createApiClient({
    onUnauthorized: (message) => exitToLogin(message, { UI }),
  });
  const assistHub = createAssistHubFeature();
  const promptPresets = createPromptPresetsFeature({
    api,
    state,
    UI,
    updateSummaries: () => updateSummaries(),
  });
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
    confirmDanger: (options) => confirmDanger(options),
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
    historyPositiveText: () => "",
    historyNegativeText: () => "",
    collectWatermark: () => settingsFeature.collectWatermark(),
    collectPublicSaveFinish: () => settingsFeature.collectPublicSaveFinish(),
    collectPublicSaveRequestSettings: () => settingsFeature.collectPublicSaveRequestSettings(),
  });
  const queue = createQueueFeature({
    api,
    state,
    UI,
    confirmDanger: (options) => confirmDanger(options),
    errorMessage,
    refreshHistory: () => history.loadContact(true, { preserveLoadedWindow: true, reason: "queue-refresh" }),
  });
  const detailers = createDetailerFeature({
    api,
    state,
    UI,
    history,
    updateSummaries: () => updateSummaries(),
  });
  const generationForm = createGenerationFormFeature({
    state,
    UI,
    fillSelect: (selector, options, selected) => fillSelect(selector, options, selected),
    slotRequestValue: (slotName) => characters.slotRequestValue(slotName),
    collectRatingPromptOverrides: () => promptPresets.collectRatingPromptOverrides(),
    collectQualityPromptOverrides: () => promptPresets.collectQualityPromptOverrides(),
    collectFaceDetailerSettings: (enabled, mode) => detailers.collectFaceSettings(enabled, mode),
    collectHandDetailerSettings: (enabled, mode) => detailers.collectHandSettings(enabled, mode),
    promptRandom,
    loras,
    i2i,
    reference,
  });
  const historyReuse = createHistoryReuseFeature({
    state,
    UI,
    characters,
    generationForm,
    promptPresets,
    promptRandom,
    loras,
    i2i,
    reference,
    detailers,
    updateSummaries: () => updateSummaries(),
  });
  history.setTextProviders({
    historyPositiveText: (item) => historyReuse.historyPositiveText(item),
    historyNegativeText: (item) => historyReuse.historyNegativeText(item),
  });
  const generationActions = createGenerationActionsFeature({
    api,
    state,
    UI,
    errorMessage,
    collectRequest: () => collectRequest(),
    generationForm,
    history,
    historyReuse,
    promptRandom,
  });
  tuningControls = createTuningControlsFeature({
    UI,
    loras,
    reference,
    detailers,
    promptRandom,
    i2i,
    generationForm,
    collectRequest: () => collectRequest(),
    updateSummaries: () => updateSummaries(),
  });
  const promptLibrary = createPromptLibraryFeature({
    api,
    state,
    UI,
    errorMessage,
    confirmDanger: (options) => confirmDanger(options),
    updateSummaries: () => updateSummaries(),
    collectRequest: () => collectRequest(),
    applyHistoryReuseData: (data) => historyReuse.applyHistoryReuseData(data),
    reuseDataFromRequest: (request) => historyReuse.reuseDataFromRequest(request),
  });
  const appShell = createAppShell({
    api,
    state,
    UI,
    errorMessage,
    isUnauthorized,
    applySettingsToForm: (nextSettings, defaults) => applySettingsToForm(nextSettings, defaults),
    characters,
    fillSelect,
    history,
    loadModels: (refresh) => loadModels(refresh),
    loras,
    updateSummaries: () => updateSummaries(),
  });

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

  function applySettingsToForm(settings = {}, defaults = state.defaults) {
    generationForm.applySettingsBasicsToForm(settings, defaults);
    promptPresets.applySettings(settings);

    loras.applyOfficialToForm(settings.official_loras || {}, settings.official_lora_preset || "custom", {
      turboRestoreSettings: settings.turbo_restore_settings,
    });
    promptRandom.applyToForm(settings.prompt_random_collect || {});
    promptRandom.renderInstructionFavorites(settings);
    detailers.applyToForm(settings);
    settingsFeature.applyWatermark(settings.watermark || {});
    settingsFeature.applyPublicSaveSettings(settings.public_save || {});
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
    detailers.refreshSamplingOptions?.();
    return data;
  }

  function officialLoraSummaryParts(official = {}) {
    const parts = [];
    if (official.highres?.enabled) parts.push(`Highres ${Number(official.highres.strength || 0).toFixed(2)}`);
    if (official.turbo?.enabled) parts.push(`Turbo ${Number(official.turbo.strength || 0).toFixed(2)}`);
    if (official.colorfix?.enabled) parts.push(`ColorFix ${Number(official.colorfix.strength || 0).toFixed(2)}`);
    return parts;
  }

  function updateSummaries() {
    const req = collectRequest();
    const officialParts = officialLoraSummaryParts(req.official_loras);
    const techLabel = `${req.width}×${req.height} · ${req.steps} · ${req.cfg} · shift${req.shift}`;
    text("#techSummary", techLabel);
    text("#secDevelopValue", techLabel);
    text("#officialLoraSummary", officialParts.length ? officialParts.join(" · ") : "OFF");
    const subjectCount = [
      req.character1,
      req.character2,
      req.character3,
      req.original_character,
    ].filter((item) => item && item !== "None").length;
    text("#secSubjectValue", subjectCount ? `${subjectCount}件選択` : "未選択");
    UI.railMark?.("sec-subject", subjectCount > 0);
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
    const modules = req.reference_modules || {};
    const background = modules.background || {};
    const refParts = [
      modules.outfit?.enabled ? "OUTFIT ON" : "OUTFIT OFF",
      modules.pose?.enabled ? "POSE ON" : "POSE OFF",
      background.enabled ? `BG ${background.mode || "depth"} ${Number(background.strength || 0).toFixed(2)}` : "BG OFF",
    ];
    text("#refModSummary", refParts.join(" / "));
    const promptLength = String(req.positive_prompt || "").trim().length;
    const promptLabel = [
      `Prompt ${promptLength}`,
      `Neg ${negMode}`,
      req.prompt_random_collect.enabled ? "Random ON" : "Random OFF",
      value("#promptConverterSummary", "LOCAL"),
    ].join(" · ");
    text("#promptWorkbenchSummary", promptLabel);
    text("#secPromptValue", promptLabel);
    UI.railMark?.("sec-prompt", Boolean(promptLength || req.negative_prompt || req.prompt_ban));
    const toolsLabel = [
      `Convert ${value("#promptConverterSummary", "LOCAL")}`,
      req.prompt_random_collect.enabled ? "Random ON" : "Random OFF",
      checked("#resetComfyCache") ? "Cache reset ON" : "",
    ].filter(Boolean).join(" · ");
    text("#secToolsValue", toolsLabel);
    UI.railMark?.("sec-tools", Boolean(req.prompt_random_collect.enabled || checked("#resetComfyCache")));
    const loraRows = Array.isArray(req.loras) ? req.loras : [];
    const loraOn = loraRows.filter((row) => row?.enabled !== false && row?.name).length + officialParts.length;
    const loraOff = loraRows.filter((row) => row?.enabled === false && row?.name).length;
    const slotOn = loraRows.filter((row) => row?.enabled !== false && row?.name).length;
    const slotOff = loraRows.filter((row) => row?.enabled === false && row?.name).length;
    text("#loraSlotSummary", slotOn || slotOff ? `${slotOn} ON${slotOff ? ` / ${slotOff} OFF` : ""}` : "0 ON");
    const bulkAssist = [
      loraRows.length ? `LoRA ${slotOn}/${loraRows.length}` : "LoRA 0",
      (modules.outfit?.enabled || modules.pose?.enabled || background.enabled) ? "Ref ON" : "Ref OFF",
      (checked("#fdEnabled") || checked("#hdEnabled")) ? "Det ON" : "Det OFF",
    ];
    text("#quickControlsSummary", bulkAssist.join(" · "));
    const presetId = req.official_lora_preset || value("#officialLoraPresetSelect", "");
    const presetNames = {
      color_stable: "Color Stable",
      quality: "Quality",
      fast_preview: "Fast Preview",
      fast_color: "Fast Color",
      final_quality: "Final Quality",
      custom: "Custom",
    };
    const presetLabel = presetId && presetId !== "off" ? (presetNames[presetId] || String(presetId).replaceAll("_", " ")) : "";
    const officialLabel = presetLabel
      ? `Official ${presetLabel}`
      : (officialParts.length ? `Official ${officialParts.length} ON` : "Official OFF");
    const slotsLabel = loraRows.length ? `Slots ${slotOn}/${loraRows.length}${slotOff ? ` (${slotOff} OFF)` : ""}` : "Slots 0";
    const hiresLabel = req.hires_fix.enabled ? `Hires ${req.hires_fix.mode || "latent"} ×${Number(req.hires_fix.upscale_factor || 1.5)}` : "Hires OFF";
    const boostLabel = `${officialLabel} · ${slotsLabel} · ${hiresLabel}`;
    text("#assistHubSummary", boostLabel);
    text("#secBoostValue", boostLabel);
    UI.railMark?.("sec-boost", Boolean(officialParts.length || slotOn || req.hires_fix.enabled));
    const advancedLabel = [
      checked("#i2iEnabled") ? `i2i ${req.image_to_image.denoise}` : "i2i OFF",
      background.enabled ? `BG ${background.mode || "depth"}` : ((modules.outfit?.enabled || modules.pose?.enabled) ? "Ref ON" : "Ref OFF"),
      (checked("#fdEnabled") || checked("#hdEnabled")) ? [
        checked("#fdEnabled") ? "Face" : "",
        checked("#hdEnabled") ? "Hand" : "",
      ].filter(Boolean).join("+") : "Detailer OFF",
      req.dynamic_prompt.enabled ? "Dyn ON" : "Dyn OFF",
    ];
    const retouchLabel = advancedLabel.join(" · ");
    text("#advancedAssistSummary", retouchLabel);
    text("#secRetouchValue", retouchLabel);
    UI.railMark?.("sec-retouch", Boolean(
      checked("#i2iEnabled")
      || modules.outfit?.enabled
      || modules.pose?.enabled
      || background.enabled
      || checked("#fdEnabled")
      || checked("#hdEnabled")
      || req.dynamic_prompt.enabled,
    ));
    const detailerSampling = (settings = {}) => settings.sampler_mode === "source" ? "source sampler" : `${settings.sampler || "euler"}/${settings.scheduler || "normal"}`;
    text(
      "#fdSummary",
      checked("#fdEnabled")
        ? `ON · ${req.face_detailer.preset || "custom"} · ${detailerSampling(req.face_detailer)} · max ${req.face_detailer.max_detections} · bbox ${Number(req.face_detailer.bbox_threshold).toFixed(2)}`
        : "OFF",
    );
    text(
      "#hdSummary",
      checked("#hdEnabled")
        ? `ON · ${req.hand_detailer.preset || "custom"} · ${detailerSampling(req.hand_detailer)} · max ${req.hand_detailer.max_detections} · L${Number(req.hand_detailer.lllite_strength).toFixed(2)}`
        : "OFF",
    );
    tuningControls?.renderStatus(req);
    updateSizeChips();
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
      rating: promptPresets.selectedRatingPreset(),
      rating_prompt_overrides: promptPresets.collectRatingPromptOverrides(),
      quality_preset: promptPresets.selectedQualityPreset(),
      quality_prompt_overrides: promptPresets.collectQualityPromptOverrides(),
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
      official_lora_preset: loras.collectOfficialPreset(),
      turbo_restore_settings: loras.collectTurboRestoreSettings(),
      loras: loras.collect(),
      prompt_random_collect: promptRandom.collect(),
      hires_fix: hiresFix,
      face_detailer: detailers.collectFaceSettings(checked("#fdEnabled"), "generation"),
      hand_detailer: detailers.collectHandSettings(checked("#hdEnabled"), "generation"),
      watermark: settingsFeature.collectWatermark(),
      public_save: {
        ...(next.public_save || {}),
        apply_watermark: checked("#watermarkEnabled"),
        ...settingsFeature.collectPublicSaveFinish(),
      },
    });
    return next;
  }

  function registerMainActions() {
    registerActions({
      login: () => appShell.login(),
      "frame-reuse": () => {
        if (state.detailItem) historyReuse.applyHistoryToForm(state.detailItem);
      },
      "frame-to-i2i": () => i2i.setFromHistoryItem(state.detailItem),
    });
    registerActions(promptPresets.actions);
    registerActions(characters.actions);
    registerActions(history.actions);
    registerActions(i2i.actions);
    registerActions(reference.actions);
    registerActions(loras.actions);
    registerActions(promptRandom.actions);
    registerActions(queue.actions);
    registerActions(settingsFeature.actions);
    registerActions(promptLibrary.actions);
    registerActions(detailers.actions);
    registerActions(generationActions.actions);
    registerActions(tuningControls.actions);
  }

  function bindEvents() {
    $("#pinInput")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") appShell.login();
    });

    promptPresets.bindEvents();
    characters.bindEvents();
    history.bindEvents();
    loras.bindEvents();
    i2i.bindEvents();
    reference.bindEvents();
    promptRandom.bindEvents();
    queue.bindEvents();
    settingsFeature.bindEvents();
    promptLibrary.bindEvents();
    assistHub.bindEvents();
    detailers.bindEvents();

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
        if (action?.startsWith("outfit-") || action?.startsWith("pose-") || action?.startsWith("background-")) text("#refModStatus", errorMessage(error));
        if (action?.startsWith("official-lora-preset")) text("#officialLoraPresetStatus", errorMessage(error));
        if (action?.startsWith("tuning-") || action?.startsWith("assist-") || action?.startsWith("lora-") || action?.startsWith("reference-") || action?.startsWith("detailers-")) text("#tuningQuickStatus", errorMessage(error));
        if (action?.startsWith("prompt-convert")) text("#promptConverterStatus", errorMessage(error));
        if (action?.startsWith("prompt-random")) text("#promptRandomStatus", errorMessage(error));
        if (action?.startsWith("comfy-restart")) text("#comfyRestartStatus", errorMessage(error));
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
    appShell.tryBootstrapSession();
  }

  onDomReady(init);
})();
