import {
  $,
  checked,
  numberValue,
  setChecked,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.38-prompt-library-split-20260620";

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
