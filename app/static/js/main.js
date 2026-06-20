import { createApiClient, authExpiredMessage, errorMessage, isUnauthorized } from "./api.js?v=v1.36-main-shell-cleanup-20260620";
import { dispatchAction, registerActions } from "./actions.js?v=v1.36-main-shell-cleanup-20260620";
import { onDomReady } from "./bootstrap.js?v=v1.36-main-shell-cleanup-20260620";
import {
  $,
  $$,
  checked,
  clone,
  displayValue,
  numberValue,
  setValue,
  text,
  unique,
  value,
} from "./dom.js?v=v1.36-main-shell-cleanup-20260620";
import { createCharacterFeature } from "./characters.js?v=v1.36-main-shell-cleanup-20260620";
import { createGenerationActionsFeature } from "./generation-actions.js?v=v1.36-main-shell-cleanup-20260620";
import { createGenerationFormFeature } from "./generation-form.js?v=v1.36-main-shell-cleanup-20260620";
import { createHistoryFeature } from "./history.js?v=v1.36-main-shell-cleanup-20260620";
import { createHistoryReuseFeature } from "./history-reuse.js?v=v1.36-main-shell-cleanup-20260620";
import { createI2iFeature } from "./i2i.js?v=v1.36-main-shell-cleanup-20260620";
import { createLoraFeature } from "./loras.js?v=v1.36-main-shell-cleanup-20260620";
import { createPromptRandomUi } from "./prompt-random.js?v=v1.36-main-shell-cleanup-20260620";
import { createPromptLibraryFeature } from "./prompt-library.js?v=v1.36-main-shell-cleanup-20260620";
import { createPromptPresetsFeature } from "./prompt-presets.js?v=v1.36-main-shell-cleanup-20260620";
import { createQueueFeature } from "./queue.js?v=v1.36-main-shell-cleanup-20260620";
import { createReferenceFeature } from "./reference.js?v=v1.36-main-shell-cleanup-20260620";
import { createSettingsFeature } from "./settings.js?v=v1.36-main-shell-cleanup-20260620";
import { createInitialState } from "./state.js?v=v1.36-main-shell-cleanup-20260620";
import { createDetailerFeature } from "./detailers.js?v=v1.36-main-shell-cleanup-20260620";

(() => {
  "use strict";

  const UI = window.UI;

  const state = createInitialState();
  let historyReuse;

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
    historyPositiveText: (item) => historyReuse.historyPositiveText(item),
    historyNegativeText: (item) => historyReuse.historyNegativeText(item),
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
  const detailers = createDetailerFeature({
    api,
    state,
    UI,
    history,
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
  historyReuse = createHistoryReuseFeature({
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
      loras: loras.collect(),
      prompt_random_collect: promptRandom.collect(),
      hires_fix: hiresFix,
      face_detailer: detailers.collectFaceSettings(checked("#fdEnabled"), "generation"),
      hand_detailer: detailers.collectHandSettings(checked("#hdEnabled"), "generation"),
      watermark: settingsFeature.collectWatermark(),
      public_save: {
        ...(next.public_save || {}),
        apply_watermark: checked("#watermarkEnabled"),
      },
    });
    return next;
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
  }

  function bindEvents() {
    $("#pinInput")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") login();
    });

    promptPresets.bindEvents();
    characters.bindEvents();
    history.bindEvents();
    i2i.bindEvents();
    reference.bindEvents();
    promptRandom.bindEvents();
    queue.bindEvents();
    settingsFeature.bindEvents();
    promptLibrary.bindEvents();

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
