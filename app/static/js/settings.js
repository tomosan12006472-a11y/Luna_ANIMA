import {
  $,
  checked,
  numberValue,
  setChecked,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.46-tuning-quick-controls-20260625";

export function createSettingsFeature({
  api,
  state,
  UI = window.UI,
  errorMessage = (error) => error?.message || String(error),
  addMetaRow = () => {},
  loadModels = async () => {},
  collectSettings = () => ({}),
  applySettingsToForm = () => {},
  renderConfiguredLoras = () => {},
} = {}) {
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

  function syncWatermarkSettings(event) {
    if (!event.target.closest("#settingsSheet")) return;
    state.appSettings = { ...state.appSettings, watermark: collectWatermark() };
  }

  function setupStateLabel(value) {
    const raw = String(value || "unknown");
    if (raw === "available") return "available";
    if (raw === "missing") return "missing";
    if (raw === "warning") return "warning";
    return "unknown";
  }

  function compactList(items = [], fallback = "-") {
    const values = Array.isArray(items) ? items.filter(Boolean) : [];
    return values.length ? values.slice(0, 8).join(", ") : fallback;
  }

  function backgroundModeSummary(modes = {}) {
    return Object.entries(modes || {}).map(([mode, data]) => {
      const state = data?.available ? "ok" : compactList([...(data?.missing_nodes || []), ...(data?.missing_models || [])], "missing");
      return `${mode}: ${state}`;
    }).join(" / ") || "-";
  }

  function modelList(...groups) {
    return groups.flatMap((items) => Array.isArray(items) ? items : []).filter(Boolean);
  }

  function renderReferenceSetup(setup = {}) {
    const summary = setup.summary || {};
    const table = $("#referenceSetupMeta");
    text("#referenceSetupBadge", setup.ok === false ? "CHECK" : "READY");
    text(
      "#referenceSetupSummary",
      [
        `Outfit/IPAdapter ${setupStateLabel(summary.outfit)}`,
        `Pose/ControlNet ${setupStateLabel(summary.pose)}`,
        `Background ${setupStateLabel(summary.background)}`,
        `Aux ${setupStateLabel(summary.controlnet_aux)}`,
      ].join(" / "),
    );
    if (!table) return;
    table.replaceChildren();
    addMetaRow(table, "IPAdapter nodes", compactList(setup.outfit?.ipadapter_nodes));
    addMetaRow(table, "clip_vision models", compactList(modelList(setup.outfit?.clip_vision_models?.found, setup.outfit?.clip_vision_models?.object_info_choices)));
    addMetaRow(table, "ipadapter models", compactList(modelList(setup.outfit?.ipadapter_models?.ipadapter_dir?.found, setup.outfit?.ipadapter_models?.ipadapter_flux_dir?.found, setup.outfit?.ipadapter_models?.object_info_choices)));
    addMetaRow(table, "ControlNet nodes", compactList(setup.pose?.controlnet_nodes || setup.background?.controlnet_nodes || []));
    addMetaRow(table, "ControlNet Aux", compactList(setup.background?.controlnet_aux_nodes || []));
    addMetaRow(table, "Background mapping", setup.background?.mapping?.enabled ? "enabled" : "disabled");
    addMetaRow(table, "Background modes", backgroundModeSummary(setup.background?.modes || {}));
    addMetaRow(table, "Missing nodes", compactList(setup.missing_nodes || []));
    addMetaRow(table, "Missing models", compactList(setup.missing_models || []));
    if (setup.comfyui?.error) addMetaRow(table, "object_info", setup.comfyui.error);
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
    renderReferenceSetup(data.reference_setup || {});
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

  async function saveDefaults() {
    const settings = collectSettings();
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
    renderConfiguredLoras(state.appSettings);
    text("#settingsStatus", "保存しました");
    UI.toast("既定値を保存しました");
  }

  async function resetDefaults() {
    const data = await api("/api/settings/reset", { method: "POST", body: "{}" });
    state.appSettings = data.settings;
    applySettingsToForm(state.appSettings, state.defaults);
    renderConfiguredLoras(state.appSettings);
    text("#settingsStatus", "リセットしました");
    UI.toast("既定値をリセットしました");
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const settingsTab = event.target.closest("#tabs button[data-tab='settings']");
      if (settingsTab) window.setTimeout(loadDiagnostics, 0);
    });
    document.addEventListener("input", syncWatermarkSettings);
    document.addEventListener("change", syncWatermarkSettings);
  }

  return {
    collectWatermark,
    applyWatermark,
    renderDiagnostics,
    loadDiagnostics,
    reloadModels,
    reloadUi,
    saveDefaults,
    resetDefaults,
    bindEvents,
    actions: {
      "save-defaults": () => saveDefaults(),
      "reset-defaults": () => resetDefaults(),
      "reload-models": () => reloadModels(),
      "reload-ui": () => reloadUi(),
    },
  };
}
