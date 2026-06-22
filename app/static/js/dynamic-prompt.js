import { $, numberValue, value } from "./dom.js?v=v1.41-turbo-presets-20260622";

export function createDynamicPromptFeature({
  api,
  UI = window.UI,
  helpers,
} = {}) {
  const { insertPositivePromptText } = helpers || {};

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

  function bindEvents() {
    $("#wildcardChips")?.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip[data-wildcard-name]");
      if (!chip) return;
      insertPositivePromptText(`__${chip.dataset.wildcardName}__, `);
    });
  }

  return {
    loadDynamicWildcards,
    previewDynamicPrompt,
    bindEvents,
    actions: {
      "dynamic-wildcards": () => loadDynamicWildcards(),
      "dynamic-preview": () => previewDynamicPrompt(),
    },
  };
}
