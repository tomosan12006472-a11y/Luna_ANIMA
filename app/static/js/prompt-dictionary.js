import { $, setValue, text, value } from "./dom.js?v=v1.41-background-reference-20260623";

export function createPromptDictionaryFeature({
  api,
  state,
  UI = window.UI,
  errorMessage = (error) => error?.message || String(error),
  helpers,
  updateSummaries = () => {},
} = {}) {
  const { insertPositivePromptText } = helpers || {};

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

  function bindEvents() {
    $("details[data-fold='dictionary']")?.addEventListener("toggle", (event) => {
      if (event.target.open) {
        loadPromptDictionaryStatus().catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    $("#dictQuery")?.addEventListener("input", schedulePromptDictionarySearch);

    $("#dictResults")?.addEventListener("click", (event) => {
      const row = event.target.closest("[data-dict-insert]");
      if (!row) return;
      insertPromptDictionaryTag(row.dataset.dictInsert);
    });
  }

  return {
    insertPromptDictionaryTag,
    loadPromptDictionaryStatus,
    renderPromptDictionaryResults,
    schedulePromptDictionarySearch,
    searchPromptDictionary,
    bindEvents,
    actions: {},
  };
}
