import { authExpiredMessage as defaultAuthExpiredMessage } from "./api.js?v=v1.65-comfy-cache-stabilization-20260630";
import { $, $$, text, value } from "./dom.js?v=v1.65-comfy-cache-stabilization-20260630";

export function exitToLogin(message = "", { UI = window.UI } = {}) {
  UI.closeSheets();
  $("#loginView")?.classList.add("is-active");
  $$(".view[data-view]").forEach((view) => view.classList.remove("is-active"));
  $("#tabs")?.classList.add("hidden");
  $("#exposeBar")?.classList.add("hidden");
  UI.safelight("idle");
  if (message) text("#loginStatus", message);
}

export function createAppShell({
  api,
  state,
  UI = window.UI,
  errorMessage,
  isUnauthorized = () => false,
  authExpiredMessage = defaultAuthExpiredMessage,
  applySettingsToForm,
  characters,
  fillSelect,
  history,
  loadModels,
  loras,
  updateSummaries,
} = {}) {
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
      exitToLogin(message, { UI });
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
      exitToLogin(message, { UI });
    }
  }

  return {
    bootstrap,
    exitToLogin: (message = "") => exitToLogin(message, { UI }),
    login,
    reportBootstrapFailures,
    tryBootstrapSession,
  };
}
