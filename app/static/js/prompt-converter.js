import { $, text, value } from "./dom.js?v=v1.41-turbo-presets-20260622";
import { promptExcerpt } from "./prompt-library-utils.js?v=v1.41-turbo-presets-20260622";

const SCORE_TAG_RE = /^[([{]*score_\d+(?:_up)?(?::[0-9.]+)?[\])}]*$/i;

export function createPromptConverterFeature({
  api,
  state,
  UI = window.UI,
  errorMessage = (error) => error?.message || String(error),
  helpers,
} = {}) {
  const { applyPositivePromptInsert } = helpers || {};

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

  function bindEvents() {
    $("details[data-fold='prompt-converter']")?.addEventListener("toggle", (event) => {
      if (event.target.open) {
        loadPromptConverterStatus().catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    $("#promptConvertSource")?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || (!event.ctrlKey && !event.metaKey)) return;
      event.preventDefault();
      convertPromptFromJapanese().catch((error) => {
        text("#promptConverterStatus", errorMessage(error));
        UI.toast(errorMessage(error), "error");
      });
    });
  }

  return {
    choosePromptConverterInsert,
    convertPromptFromJapanese,
    dedupePromptConverterTags,
    insertPromptConverterText,
    loadPromptConverterStatus,
    renderPromptConverterResult,
    setPromptConverterStatus,
    bindEvents,
    actions: {
      "prompt-convert": () => convertPromptFromJapanese(),
      "prompt-converter-status": () => loadPromptConverterStatus(true),
    },
  };
}
