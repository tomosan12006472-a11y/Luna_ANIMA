import {
  $,
  checked,
  clone,
  setChecked,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.41-turbo-presets-20260622";

const PROMPT_RANDOM_MODES = new Set(["random", "positive_completion"]);
const PROMPT_RANDOM_DEFAULT_INSTRUCTIONS = {
  random: "衣装、表情、背景、小物をランダムに足す",
  positive_completion: "既存Positiveの意図を保ったまま、不足している描写を英語タグで補う",
};
const PROMPT_RANDOM_STRENGTHS = new Set(["subtle", "standard", "reference_568", "legacy_568", "rich"]);
const PROMPT_RANDOM_STRENGTH_LABELS = {
  subtle: "控えめ",
  standard: "標準",
  reference_568: "#568基準",
  legacy_568: "#568再現",
  rich: "大胆",
};
const PROMPT_RANDOM_FAVORITES_LIMIT = 80;

export function normalizePromptRandomMode(mode) {
  const normalized = String(mode || "random").trim().toLowerCase();
  return PROMPT_RANDOM_MODES.has(normalized) ? normalized : "random";
}

export function promptRandomDefaultInstruction(mode = "random") {
  return PROMPT_RANDOM_DEFAULT_INSTRUCTIONS[normalizePromptRandomMode(mode)] || PROMPT_RANDOM_DEFAULT_INSTRUCTIONS.random;
}

export function normalizePromptRandomStrength(strength) {
  const normalized = String(strength || "standard").trim().toLowerCase();
  return PROMPT_RANDOM_STRENGTHS.has(normalized) ? normalized : "standard";
}

export function defaultPromptRandomCollect(mode = "random") {
  const normalizedMode = normalizePromptRandomMode(mode);
  return {
    enabled: false,
    mode: normalizedMode,
    instruction: promptRandomDefaultInstruction(normalizedMode),
    strength: "standard",
    include_characters: true,
    use_character_motifs: true,
  };
}

function fallbackErrorMessage(error) {
  return error?.data?.message || error?.data?.detail || error?.message || String(error);
}

export function createPromptRandomUi({
  api,
  state,
  UI = window.UI,
  updateSummaries = () => {},
  confirmDanger = async () => false,
  errorMessage = fallbackErrorMessage,
} = {}) {
  function appSettings() {
    return state?.appSettings || {};
  }

  function collectPromptRandomCollect() {
    const mode = normalizePromptRandomMode(value("#promptRandomMode", "random"));
    const includeCharacters = checked("#promptRandomIncludeCharacters");
    return {
      enabled: checked("#promptRandomEnabled"),
      mode,
      instruction: value("#promptRandomInstruction", promptRandomDefaultInstruction(mode)),
      strength: normalizePromptRandomStrength(value("#promptRandomStrength", "standard")),
      include_characters: includeCharacters,
      use_character_motifs: includeCharacters && checked("#promptRandomUseCharacterMotifs"),
    };
  }

  function promptRandomOnSummary() {
    const mode = normalizePromptRandomMode(value("#promptRandomMode", "random"));
    const modeLabel = mode === "positive_completion" ? "補完" : "RANDOM";
    const strength = normalizePromptRandomStrength(value("#promptRandomStrength", "standard"));
    const strengthLabel = PROMPT_RANDOM_STRENGTH_LABELS[strength] || "標準";
    const charLabel = checked("#promptRandomIncludeCharacters") ? "CHAR" : "NO CHAR";
    const motifLabel = checked("#promptRandomIncludeCharacters") && checked("#promptRandomUseCharacterMotifs") ? "MOTIF" : "NO MOTIF";
    return `ON / ${modeLabel} / ${strengthLabel} / ${charLabel} / ${motifLabel}`;
  }

  function renderPromptRandomSummary(enabled = collectPromptRandomCollect().enabled) {
    text("#promptRandomSummary", enabled ? promptRandomOnSummary() : "OFF");
  }

  function applyPromptRandomCollectToForm(config = {}) {
    const mode = normalizePromptRandomMode(config.mode);
    const defaults = defaultPromptRandomCollect(mode);
    setChecked("#promptRandomEnabled", Boolean(config.enabled));
    setValue("#promptRandomMode", mode);
    setValue("#promptRandomInstruction", config.instruction || defaults.instruction);
    setValue("#promptRandomStrength", normalizePromptRandomStrength(config.strength || defaults.strength));
    setChecked("#promptRandomIncludeCharacters", config.include_characters !== false);
    setChecked("#promptRandomUseCharacterMotifs", Boolean(config.include_characters !== false && config.use_character_motifs !== false));
  }

  function updatePromptRandomMode() {
    const mode = normalizePromptRandomMode(value("#promptRandomMode", "random"));
    const current = value("#promptRandomInstruction", "").trim();
    const knownDefaults = Object.values(PROMPT_RANDOM_DEFAULT_INSTRUCTIONS);
    if (!current || knownDefaults.includes(current)) {
      setValue("#promptRandomInstruction", promptRandomDefaultInstruction(mode));
    }
    updateSummaries();
  }

  function promptRandomModeLabel(mode) {
    return normalizePromptRandomMode(mode) === "positive_completion" ? "Positive補完" : "ランダム追加";
  }

  function normalizePromptRandomInstructionFavorite(raw, index = 0) {
    if (!raw || typeof raw !== "object") return null;
    const instruction = String(raw.instruction || "").trim();
    if (!instruction) return null;
    const mode = normalizePromptRandomMode(raw.mode);
    const strength = normalizePromptRandomStrength(raw.strength);
    const includeCharacters = raw.include_characters !== false;
    const label = String(raw.label || raw.title || instruction.slice(0, 32)).trim().slice(0, 80);
    return {
      id: String(raw.id || `favorite_${index + 1}`).trim().slice(0, 80),
      label: label || instruction.slice(0, 32),
      instruction: instruction.slice(0, 500),
      mode,
      strength,
      include_characters: includeCharacters,
      use_character_motifs: Boolean(includeCharacters && raw.use_character_motifs !== false),
    };
  }

  function promptRandomInstructionFavorites(settings = appSettings()) {
    const raw = Array.isArray(settings?.prompt_random_instruction_favorites)
      ? settings.prompt_random_instruction_favorites
      : [];
    return raw
      .map((item, index) => normalizePromptRandomInstructionFavorite(item, index))
      .filter(Boolean)
      .slice(0, PROMPT_RANDOM_FAVORITES_LIMIT);
  }

  function promptRandomFavoriteTitle(favorite) {
    const strength = PROMPT_RANDOM_STRENGTH_LABELS[favorite.strength] || "標準";
    const char = favorite.include_characters ? "CHAR" : "NO CHAR";
    const motif = favorite.include_characters && favorite.use_character_motifs ? "MOTIF" : "NO MOTIF";
    return `${favorite.label} / ${promptRandomModeLabel(favorite.mode)} / ${strength} / ${char} / ${motif}`;
  }

  function updatePromptRandomFavoriteControls() {
    const hasSelection = Boolean(value("#promptRandomFavoriteSelect", ""));
    $("[data-action='prompt-random-favorite-apply']")?.toggleAttribute("disabled", !hasSelection);
    $("[data-action='prompt-random-favorite-delete']")?.toggleAttribute("disabled", !hasSelection);
  }

  function renderPromptRandomInstructionFavorites(settings = appSettings()) {
    const favorites = promptRandomInstructionFavorites(settings);
    const select = $("#promptRandomFavoriteSelect");
    if (select) {
      const current = select.value;
      select.replaceChildren();
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = favorites.length ? "お気に入りを選択" : "お気に入りなし";
      select.appendChild(empty);
      for (const favorite of favorites) {
        const option = document.createElement("option");
        option.value = favorite.id;
        option.textContent = promptRandomFavoriteTitle(favorite);
        option.title = favorite.instruction;
        select.appendChild(option);
      }
      if (favorites.some((favorite) => favorite.id === current)) select.value = current;
    }
    text("#promptRandomFavoriteCount", `${favorites.length}件`);
    updatePromptRandomFavoriteControls();
  }

  function selectedPromptRandomInstructionFavorite() {
    const selectedId = value("#promptRandomFavoriteSelect", "");
    if (!selectedId) return null;
    return promptRandomInstructionFavorites().find((favorite) => favorite.id === selectedId) || null;
  }

  async function savePromptRandomInstructionFavorites(favorites, { status = "保存しました", selectedId = "" } = {}) {
    const settings = {
      ...clone(appSettings()),
      prompt_random_instruction_favorites: favorites.slice(0, PROMPT_RANDOM_FAVORITES_LIMIT),
    };
    const data = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        settings,
        mode: "current",
        reason: "prompt_random_instruction_favorites",
      }),
    });
    state.appSettings = data.settings;
    renderPromptRandomInstructionFavorites(state.appSettings);
    if (selectedId) {
      setValue("#promptRandomFavoriteSelect", selectedId);
      updatePromptRandomFavoriteControls();
    }
    text("#promptRandomStatus", status);
    return data.settings;
  }

  async function saveCurrentPromptRandomInstructionFavorite() {
    const config = collectPromptRandomCollect();
    const instruction = String(config.instruction || "").trim();
    if (!instruction) {
      UI.toast("AI指示が空です", "error");
      return;
    }
    const defaultLabel = instruction.replace(/\s+/g, " ").slice(0, 32);
    const input = window.prompt("お気に入り名", defaultLabel);
    if (input === null) return;
    const label = String(input || defaultLabel).trim().slice(0, 80) || defaultLabel;
    const id = `prc_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
    const favorite = {
      id,
      label,
      instruction,
      mode: config.mode,
      strength: config.strength,
      include_characters: config.include_characters,
      use_character_motifs: config.use_character_motifs,
    };
    const favorites = [favorite, ...promptRandomInstructionFavorites().filter((item) => item.id !== id)]
      .slice(0, PROMPT_RANDOM_FAVORITES_LIMIT);
    await savePromptRandomInstructionFavorites(favorites, { status: "AI指示お気に入りを保存しました", selectedId: id });
    UI.toast("AI指示お気に入りを保存しました");
  }

  function applyPromptRandomInstructionFavorite() {
    const favorite = selectedPromptRandomInstructionFavorite();
    if (!favorite) {
      UI.toast("AI指示お気に入りを選択してください", "error");
      return;
    }
    setValue("#promptRandomMode", favorite.mode);
    setValue("#promptRandomInstruction", favorite.instruction);
    setValue("#promptRandomStrength", favorite.strength);
    setChecked("#promptRandomIncludeCharacters", favorite.include_characters);
    setChecked("#promptRandomUseCharacterMotifs", Boolean(favorite.include_characters && favorite.use_character_motifs));
    updateSummaries();
    text("#promptRandomStatus", `${favorite.label} を適用しました`);
    UI.toast("AI指示お気に入りを適用しました");
  }

  async function deletePromptRandomInstructionFavorite() {
    const favorite = selectedPromptRandomInstructionFavorite();
    if (!favorite) {
      UI.toast("AI指示お気に入りを選択してください", "error");
      return;
    }
    const ok = await confirmDanger({
      title: "削除しますか?",
      message: `${favorite.label}\n${favorite.instruction.slice(0, 120)}`,
      label: "削除する",
    });
    if (!ok) return;
    const favorites = promptRandomInstructionFavorites().filter((item) => item.id !== favorite.id);
    await savePromptRandomInstructionFavorites(favorites, { status: "AI指示お気に入りを削除しました" });
    UI.toast("AI指示お気に入りを削除しました");
  }

  function setPromptRandomStatus(data = {}) {
    if (data.enabled === false) {
      text("#promptRandomSummary", "DISABLED");
      text("#promptRandomStatus", "Random Collect APIは設定で無効です。");
      return;
    }
    if (data.reachable) {
      const model = data.active_model || data.model || "auto";
      text("#promptRandomSummary", checked("#promptRandomEnabled") ? promptRandomOnSummary() : "READY");
      text("#promptRandomStatus", `${data.provider || "provider"} / ${model}`);
      return;
    }
    text("#promptRandomSummary", checked("#promptRandomEnabled") ? "OFFLINE" : "OFF");
    text("#promptRandomStatus", data.message || "ローカルRandom Collect APIに接続できません。LM StudioなどのLocal Serverを起動してください。");
  }

  async function loadPromptRandomStatus(force = false) {
    if (state.promptRandomStatusLoaded && !force) return null;
    state.promptRandomStatusLoaded = true;
    try {
      const data = await api("/api/prompt-random-collect/status");
      setPromptRandomStatus(data);
      return data;
    } catch (error) {
      state.promptRandomStatusLoaded = false;
      text("#promptRandomStatus", errorMessage(error));
      throw error;
    }
  }

  function historyPromptRandomCollect(raw = {}) {
    const data = raw && typeof raw === "object" ? raw : {};
    const mode = normalizePromptRandomMode(data.mode);
    const defaults = defaultPromptRandomCollect(mode);
    return {
      enabled: Boolean(data.enabled),
      mode,
      instruction: data.instruction || defaults.instruction,
      strength: data.strength || defaults.strength,
      include_characters: data.include_characters !== false,
      use_character_motifs: Boolean(data.include_characters !== false && data.use_character_motifs !== false),
    };
  }

  function setStatus(message) {
    text("#promptRandomStatus", message);
  }

  function bindEvents() {
    $("details[data-fold='prompt-random']")?.addEventListener("toggle", (event) => {
      if (event.target.open) {
        loadPromptRandomStatus().catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    $("#promptRandomEnabled")?.addEventListener("change", updateSummaries);
    $("#promptRandomIncludeCharacters")?.addEventListener("change", updateSummaries);
    $("#promptRandomUseCharacterMotifs")?.addEventListener("change", updateSummaries);
    $("#promptRandomMode")?.addEventListener("change", updatePromptRandomMode);
    $("#promptRandomInstruction")?.addEventListener("input", updateSummaries);
    $("#promptRandomStrength")?.addEventListener("change", updateSummaries);
    $("#promptRandomFavoriteSelect")?.addEventListener("change", updatePromptRandomFavoriteControls);
  }

  return {
    actions: {
      "prompt-random-status": () => loadPromptRandomStatus(true),
      "prompt-random-favorite-apply": () => applyPromptRandomInstructionFavorite(),
      "prompt-random-favorite-save": () => saveCurrentPromptRandomInstructionFavorite(),
      "prompt-random-favorite-delete": () => deletePromptRandomInstructionFavorite(),
    },
    applyToForm: applyPromptRandomCollectToForm,
    bindEvents,
    collect: collectPromptRandomCollect,
    historyCollect: historyPromptRandomCollect,
    loadStatus: loadPromptRandomStatus,
    onSummary: promptRandomOnSummary,
    renderInstructionFavorites: renderPromptRandomInstructionFavorites,
    renderSummary: renderPromptRandomSummary,
    setStatus,
    updateFavoriteControls: updatePromptRandomFavoriteControls,
    updateMode: updatePromptRandomMode,
  };
}
