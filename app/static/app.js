(() => {
  "use strict";

  const UI = window.UI;
  const { $, $$ } = UI;

  const CONTACT_LIMIT = 24;
  const ACTIVE_STATUSES = new Set(["queued", "running"]);
  const EMPTY_SLOT_LABELS = {
    character1: "Random",
    character2: "未選択",
    character3: "未選択",
    original: "未選択",
  };
  const I2I_EMPTY_TEXT = "下絵は未選択です。履歴の「下絵にする」からも選べます。";
  const REFMOD_EMPTY_TEXT = {
    outfit: "Outfit参照は未選択です。",
    pose: "Pose参照は未選択です。",
  };

  const state = {
    bootstrap: null,
    appSettings: {},
    defaults: {},
    models: {},
    loraSelectable: [],
    slots: {
      character1: null,
      character2: null,
      character3: null,
      original: null,
    },
    armedSlot: "character1",
    favorites: { characters: [], original_characters: [] },
    contactFilter: "all",
    contactItems: [],
    contactOffset: 0,
    contactTotal: 0,
    contactRevision: "",
    contactLoaded: false,
    contactStatusById: new Map(),
    contactPollTimer: 0,
    pollHadActive: false,
    detailItem: null,
    characterSearchTimer: 0,
    promptSheetMode: "favorites",
    promptSheetItems: [],
    promptSheetQueryTimer: 0,
    dictQueryTimer: 0,
    dictStatusLoaded: false,
    i2i: { imageId: "", thumb: "", name: "" },
    refmod: {
      outfit: { imageId: "", thumb: "", name: "" },
      pose: { imageId: "", thumb: "", name: "" },
    },
  };

  function text(selector, value) {
    const el = typeof selector === "string" ? $(selector) : selector;
    if (el) el.textContent = String(value ?? "");
  }

  function value(selector, fallback = "") {
    const el = $(selector);
    if (!el) return fallback;
    const raw = "value" in el ? el.value : "";
    return raw === "" || raw === undefined || raw === null ? fallback : raw;
  }

  function setValue(selector, next) {
    const el = $(selector);
    if (el && "value" in el) el.value = next ?? "";
  }

  function numberValue(selector, fallback = 0) {
    const raw = Number(value(selector, fallback));
    return Number.isFinite(raw) ? raw : fallback;
  }

  function setChecked(selector, checked) {
    const el = $(selector);
    if (el && "checked" in el) el.checked = Boolean(checked);
  }

  function checked(selector) {
    const el = $(selector);
    return Boolean(el && "checked" in el && el.checked);
  }

  function clone(value) {
    try {
      return JSON.parse(JSON.stringify(value ?? {}));
    } catch {
      return {};
    }
  }

  function escapePathSegment(value) {
    return encodeURIComponent(String(value || ""));
  }

  function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("ja-JP", { hour12: false });
  }

  function modelFileName(value) {
    const textValue = String(value || "").replaceAll("\\", "/");
    return textValue.split("/").filter(Boolean).pop() || textValue || "-";
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === "") return "-";
    if (Array.isArray(value)) return value.length ? value.join(", ") : "-";
    if (typeof value === "object") {
      try {
        return JSON.stringify(value);
      } catch {
        return String(value);
      }
    }
    return String(value);
  }

  function errorMessage(error) {
    return error?.data?.message || error?.data?.detail || error?.message || String(error);
  }

  function exitToLogin(message = "") {
    UI.closeSheets();
    $("#loginView")?.classList.add("is-active");
    $$(".view[data-view]").forEach((view) => view.classList.remove("is-active"));
    $("#tabs")?.classList.add("hidden");
    $("#exposeBar")?.classList.add("hidden");
    UI.safelight("idle");
    if (message) text("#loginStatus", message);
  }

  async function api(path, options = {}) {
    const fetchOptions = { ...options };
    const headers = new Headers(fetchOptions.headers || {});
    delete fetchOptions.headers;
    if (fetchOptions.body !== undefined && !(fetchOptions.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(path, {
      credentials: "same-origin",
      ...fetchOptions,
      headers,
    });
    const raw = await response.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { ok: false, message: "Response was not JSON" };
    }
    if (response.status === 401) {
      exitToLogin("ログインが切れました。PINで入り直してください。");
    }
    if (!response.ok || data?.ok === false) {
      const error = new Error(data?.message || data?.detail || response.statusText || "Request failed");
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  function unique(values) {
    const seen = new Set();
    const out = [];
    for (const value of values || []) {
      const textValue = String(value ?? "").trim();
      if (!textValue || seen.has(textValue)) continue;
      seen.add(textValue);
      out.push(textValue);
    }
    return out;
  }

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

  function selectedQueueCount() {
    const count = Number(value("#queueCount", 1));
    return Number.isFinite(count) && count > 0 ? count : 1;
  }

  function collectOfficialLoras() {
    return {
      highres: {
        enabled: checked("#officialHighresEnabled"),
        strength: numberValue("#officialHighresStrength", 0.6),
      },
      turbo: {
        enabled: checked("#officialTurboEnabled"),
        version: "auto",
        strength: numberValue("#officialTurboStrength", 0.6),
      },
    };
  }

  function collectLoras() {
    return $$("[data-lora-row]", $("#loraSlots")).map((row) => {
      const name = row.querySelector("[data-lora-field='name']")?.value || "";
      const application = row.querySelector("[data-lora-field='application']")?.value || "model_clip";
      const strengthModel = Number(row.querySelector("[data-lora-field='strength_model']")?.value || 1);
      const strengthClip = Number(row.querySelector("[data-lora-field='strength_clip']")?.value || 1);
      return {
        enabled: true,
        name,
        application,
        strength_model: Number.isFinite(strengthModel) ? strengthModel : 1,
        strength_clip: Number.isFinite(strengthClip) ? strengthClip : 1,
      };
    }).filter((item) => item.name);
  }

  function slotRequestValue(slotName) {
    const item = state.slots[slotName];
    if (item?.value) return item.value;
    if (slotName === "character1") return "Random";
    return "None";
  }

  function collectRequest() {
    const negative = value("#negativePrompt", "");
    const seedMode = value("#seedModeSelect", "fixed");
    const i2iEnabled = checked("#i2iEnabled") && Boolean(state.i2i.imageId);
    const outfitEnabled = checked("#outfitEnabled");
    const poseEnabled = checked("#poseEnabled");
    return {
      workflow_mode: "anima",
      character1: slotRequestValue("character1"),
      character2: slotRequestValue("character2"),
      character3: slotRequestValue("character3"),
      original_character: slotRequestValue("original"),
      character1_weight: 1.0,
      character2_weight: 1.0,
      character3_weight: 1.0,
      original_weight: 1.0,
      character1_role: "main",
      character2_role: "left",
      character3_role: "right",
      rating: UI.segValue("#ratingSeg", "rating") || "safe",
      quality_preset: UI.segValue("#qualitySeg", "quality") || "standard",
      meta_prompt: value("#metaPrompt", "anime illustration"),
      year_prompt: value("#yearPrompt", ""),
      outfit_prompt: value("#outfitPrompt", ""),
      expression_prompt: value("#expressionPrompt", ""),
      pose_prompt: value("#posePrompt", ""),
      background_prompt: value("#backgroundPrompt", ""),
      lighting_prompt: value("#lightingPrompt", ""),
      camera_prompt: value("#cameraPrompt", ""),
      natural_description: value("#naturalDescription", ""),
      positive_prompt: value("#positivePrompt", ""),
      negative_prompt: negative,
      negative_prompt_raw: negative,
      negative_prompt_mode: value("#negativeMode", "append"),
      negative_preset: value("#negativePreset", "anima_recommended"),
      prompt_ban: value("#promptBan", ""),
      common_prompt: "",
      model: value("#modelSelect", state.appSettings.model || state.defaults.model || "Anima\\anima-preview3-base.safetensors"),
      text_encoder: state.appSettings.text_encoder || state.defaults.text_encoder || "qwen_3_06b_base.safetensors",
      vae: state.appSettings.vae || state.defaults.vae || "qwen_image_vae.safetensors",
      width: numberValue("#widthInput", 1024),
      height: numberValue("#heightInput", 1536),
      steps: numberValue("#stepsInput", 32),
      cfg: numberValue("#cfgInput", 4.5),
      shift: numberValue("#shiftInput", 4),
      sampler: value("#samplerSelect", "er_sde"),
      scheduler: value("#schedulerSelect", "simple"),
      seed: seedMode === "random" ? -1 : Math.trunc(numberValue("#seedInput", -1)),
      seed_mode: seedMode,
      official_loras: collectOfficialLoras(),
      loras: collectLoras(),
      count: selectedQueueCount(),
      wait: false,
      dynamic_prompt: { enabled: checked("#dynamicEnabled") },
      hires_fix: { enabled: false },
      reference_assist: { enabled: false },
      image_to_image: {
        enabled: i2iEnabled,
        image_id: state.i2i.imageId,
        denoise: numberValue("#i2iDenoise", 0.45),
        resize_mode: value("#i2iResize", "fit"),
        use_source_size: checked("#i2iUseSource"),
        allow_with_hires_fix: false,
        allow_with_reference_assist: false,
      },
      face_detailer: { enabled: false },
      reference_modules: {
        enabled: true,
        preset: outfitEnabled && poseEnabled ? "outfit_pose" : outfitEnabled ? "outfit_only" : poseEnabled ? "pose_only" : "off",
        outfit: {
          enabled: outfitEnabled,
          image_id: state.refmod.outfit.imageId,
          image_name: state.refmod.outfit.name,
          strength: numberValue("#outfitStrength", 0.45),
          mode: "image_prompt",
          strategy: "ip_adapter",
          crop_mode: "user_prepared",
          start_at: numberValue("#outfitStart", 0),
          end_at: numberValue("#outfitEnd", 0.75),
        },
        pose: {
          enabled: poseEnabled,
          image_id: state.refmod.pose.imageId,
          image_name: state.refmod.pose.name,
          mode: value("#poseMode", "pose_image"),
          strength: numberValue("#poseStrength", 0.75),
          strategy: "controlnet_openpose",
          start_at: numberValue("#poseStart", 0),
          end_at: numberValue("#poseEnd", 0.85),
        },
      },
    };
  }

  function sourceForCharacter(item) {
    const source = String(item?.source || "");
    if (source === "original_character" || item?.kind === "original") return "original_character";
    return "wai_characters";
  }

  function normalizeCharacterItem(raw = {}) {
    const source = sourceForCharacter(raw);
    const displayName = String(raw.display_name || raw.displayName || raw.name || raw.id || "").trim();
    const id = String(raw.id || displayName).trim();
    const promptTag = String(raw.prompt_tag || raw.promptTag || "").trim();
    const kind = raw.kind || (source === "original_character" ? "original" : "wai");
    return { source, id, displayName, promptTag, kind };
  }

  function valueForSlot(slotName, item) {
    if (slotName === "original") return item.id || item.displayName || "None";
    if (item.source === "original_character" || item.kind === "original") {
      return `original:${item.id || item.displayName}`;
    }
    return item.displayName || "None";
  }

  function applyCharacterToSlot(raw, slotName = state.armedSlot) {
    const item = normalizeCharacterItem(raw);
    if (!item.displayName && !item.id) return;
    state.slots[slotName] = {
      ...item,
      value: valueForSlot(slotName, item),
    };
    renderSlots();
    updateSummaries();
  }

  function clearSlot(slotName = state.armedSlot) {
    state.slots[slotName] = null;
    renderSlots();
    updateSummaries();
  }

  function renderSlots() {
    $$(".slot", $("#charSlots")).forEach((slot) => {
      const slotName = slot.dataset.slot;
      const item = state.slots[slotName];
      slot.classList.toggle("is-armed", slotName === state.armedSlot);
      slot.classList.toggle("is-empty", !item);
      const name = slot.querySelector(".name");
      if (name) name.textContent = item?.displayName || EMPTY_SLOT_LABELS[slotName] || "未選択";
    });
  }

  function allFavorites() {
    return [
      ...(state.favorites.characters || []),
      ...(state.favorites.original_characters || []),
    ];
  }

  function favoriteMatchesSlot(favorite, slotItem) {
    if (!favorite || !slotItem) return false;
    if (favorite.source !== slotItem.source) return false;
    if (favorite.source === "original_character") {
      return favorite.id === slotItem.id || favorite.display_name === slotItem.displayName;
    }
    return (
      favorite.display_name === slotItem.displayName ||
      (favorite.prompt_tag && favorite.prompt_tag === slotItem.promptTag)
    );
  }

  function favoriteForSlot(slotName = state.armedSlot) {
    const slotItem = state.slots[slotName];
    return allFavorites().find((favorite) => favoriteMatchesSlot(favorite, slotItem));
  }

  function renderFavorites() {
    const root = $("#favRow");
    if (!root) return;
    root.replaceChildren();
    const favorites = allFavorites();
    if (!favorites.length) {
      const empty = document.createElement("span");
      empty.className = "lbl";
      empty.textContent = "お気に入りなし";
      root.appendChild(empty);
      return;
    }
    for (const favorite of favorites) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.dataset.favoriteId = favorite.id || "";
      button.dataset.favoriteSource = favorite.source || "";
      button.dataset.favoriteName = favorite.display_name || favorite.name || "";
      button.dataset.favoritePromptTag = favorite.prompt_tag || "";
      button.textContent = `★ ${favorite.display_name || favorite.name || favorite.id}`;
      root.appendChild(button);
    }
  }

  function setFavorites(data) {
    state.favorites = {
      characters: Array.isArray(data?.characters) ? data.characters : [],
      original_characters: Array.isArray(data?.original_characters) ? data.original_characters : [],
    };
    renderFavorites();
  }

  async function loadFavorites() {
    const data = await api("/api/favorites");
    setFavorites(data);
  }

  async function toggleFavoriteForArmedSlot() {
    const slotItem = state.slots[state.armedSlot];
    if (!slotItem) {
      UI.toast("選択中スロットが空です", "error");
      return;
    }
    const existing = favoriteForSlot();
    if (existing) {
      const data = await api(`/api/favorites/${escapePathSegment(existing.source)}/${escapePathSegment(existing.id)}`, {
        method: "DELETE",
      });
      setFavorites(data);
      UI.toast(data.removed ? "お気に入りを解除しました" : "登録が見つかりませんでした");
      return;
    }
    const data = await api("/api/favorites", {
      method: "POST",
      body: JSON.stringify({
        source: slotItem.source,
        id: slotItem.id || "",
        name: slotItem.displayName,
        display_name: slotItem.displayName,
        prompt_tag: slotItem.promptTag || "",
      }),
    });
    setFavorites(data);
    UI.toast(data.action === "already_exists" ? "追加済みです" : "お気に入りに追加しました");
  }

  function insertPositivePromptText(insertText) {
    const el = $("#positivePrompt");
    if (!el) return;
    const textValue = String(insertText || "");
    const start = Number.isFinite(el.selectionStart) ? el.selectionStart : el.value.length;
    const end = Number.isFinite(el.selectionEnd) ? el.selectionEnd : start;
    el.value = `${el.value.slice(0, start)}${textValue}${el.value.slice(end)}`;
    const cursor = start + textValue.length;
    el.focus();
    el.setSelectionRange(cursor, cursor);
    updateSummaries();
  }

  function appendPositivePrompt(prompt) {
    const nextPrompt = String(prompt || "").trim();
    if (!nextPrompt) return;
    const current = value("#positivePrompt", "").trim();
    setValue("#positivePrompt", current ? `${current}, ${nextPrompt}` : nextPrompt);
    updateSummaries();
  }

  function promptItemPrompt(item = {}) {
    return String(item.prompt || item.positive_prompt || item.text || "").trim();
  }

  function promptItemTitle(item = {}) {
    const prompt = promptItemPrompt(item);
    return String(item.title || item.name || prompt.slice(0, 40) || "Untitled").trim();
  }

  function promptExcerpt(prompt, limit = 60) {
    const compact = String(prompt || "").replace(/\s+/g, " ").trim();
    return compact.length > limit ? `${compact.slice(0, limit)}...` : compact;
  }

  function renderPromptSheet(items = state.promptSheetItems) {
    const root = $("#promptSheetList");
    if (!root) return;
    const query = value("#promptSheetQuery", "").trim().toLowerCase();
    const sourceItems = Array.isArray(items) ? items : [];
    const visibleItems = state.promptSheetMode === "favorites" && query
      ? sourceItems.filter((item) => {
        const haystack = [
          promptItemTitle(item),
          promptItemPrompt(item),
          ...(Array.isArray(item.tags) ? item.tags : []),
          item.note || "",
        ].join("\n").toLowerCase();
        return haystack.includes(query);
      })
      : sourceItems;

    root.replaceChildren();
    if (!visibleItems.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = query ? "一致する項目がありません" : "項目がありません";
      root.appendChild(empty);
    } else {
      for (const item of visibleItems) {
        const row = document.createElement("button");
        row.type = "button";
        row.dataset.promptItemId = item.id || "";
        row.dataset.promptKind = state.promptSheetMode;

        const label = document.createElement("span");
        label.textContent = promptItemTitle(item);

        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = promptExcerpt(promptItemPrompt(item));

        if (state.promptSheetMode === "favorites") {
          const remove = document.createElement("span");
          remove.className = "tag";
          remove.dataset.promptDeleteId = item.id || "";
          remove.setAttribute("role", "button");
          remove.setAttribute("tabindex", "0");
          remove.textContent = "削除";
          row.append(label, tag, remove);
        } else {
          row.append(label, tag);
        }
        root.appendChild(row);
      }
    }

    text("#promptSheetCount", String(visibleItems.length));
    text("#promptSheetStatus", "");
  }

  function setPromptSheetLoading(message) {
    $("#promptSheetList")?.replaceChildren();
    text("#promptSheetCount", "-");
    text("#promptSheetStatus", message);
  }

  async function loadPositiveFavorites() {
    const data = await api("/api/prompts/positive-favorites");
    state.promptSheetItems = Array.isArray(data.items) ? data.items : [];
    renderPromptSheet();
    return data;
  }

  async function loadPositiveTemplates(query = value("#promptSheetQuery", "")) {
    const params = new URLSearchParams({
      query: String(query || "").trim(),
      limit: "50",
    });
    const data = await api(`/api/prompts/positive-templates?${params.toString()}`);
    state.promptSheetItems = Array.isArray(data.items) ? data.items : [];
    renderPromptSheet();
    return data;
  }

  async function savePositiveFavorite() {
    const prompt = value("#positivePrompt", "").trim();
    if (!prompt) {
      UI.toast("Positiveが空です", "error");
      return;
    }
    await api("/api/prompts/positive-favorites", {
      method: "POST",
      body: JSON.stringify({
        title: prompt.slice(0, 40),
        prompt,
        tags: [],
        note: "",
      }),
    });
    UI.toast("保存しました");
    if (state.promptSheetMode === "favorites" && $("#promptSheet")?.classList.contains("is-open")) {
      await loadPositiveFavorites();
    }
  }

  async function openPositiveFavorites() {
    state.promptSheetMode = "favorites";
    state.promptSheetItems = [];
    text("#promptSheetTitle", "Positiveお気に入り");
    setValue("#promptSheetQuery", "");
    setPromptSheetLoading("読み込み中...");
    UI.openSheet("#promptSheet");
    await loadPositiveFavorites();
  }

  async function openPositiveTemplates() {
    state.promptSheetMode = "templates";
    state.promptSheetItems = [];
    text("#promptSheetTitle", "テンプレート");
    setValue("#promptSheetQuery", "");
    setPromptSheetLoading("読み込み中...");
    UI.openSheet("#promptSheet");
    await loadPositiveTemplates("");
  }

  async function usePromptSheetItem(itemId) {
    const item = state.promptSheetItems.find((candidate) => String(candidate.id || "") === String(itemId || ""));
    const prompt = promptItemPrompt(item);
    if (!prompt) return;
    appendPositivePrompt(prompt);
    if (state.promptSheetMode === "favorites" && item?.id) {
      await api(`/api/prompts/positive-favorites/${escapePathSegment(item.id)}/used`, {
        method: "POST",
        body: "{}",
      });
    }
    UI.closeSheets();
    UI.toast("Positiveに追加しました");
  }

  async function deletePositiveFavorite(favoriteId) {
    if (!favoriteId) return;
    const data = await api(`/api/prompts/positive-favorites/${escapePathSegment(favoriteId)}`, {
      method: "DELETE",
    });
    state.promptSheetItems = Array.isArray(data.items) ? data.items : [];
    renderPromptSheet();
    UI.toast(data.removed ? "削除しました" : "見つかりませんでした");
  }

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

  function i2iItemState(item = {}) {
    const imageId = String(item.image_id || "").trim();
    return {
      imageId,
      thumb: String(item.thumbnail_url || item.thumb || "").trim(),
      name: String(item.original_filename || item.filename || item.name || imageId || "").trim(),
    };
  }

  function renderI2iPreview() {
    const root = $("#i2iPreview");
    if (!root) return;
    root.replaceChildren();
    if (!state.i2i.imageId) {
      root.classList.add("is-empty");
      root.textContent = I2I_EMPTY_TEXT;
      return;
    }
    root.classList.remove("is-empty");
    if (state.i2i.thumb) {
      const img = document.createElement("img");
      img.src = state.i2i.thumb;
      img.alt = state.i2i.name || "i2i source";
      img.loading = "lazy";
      img.decoding = "async";
      root.appendChild(img);
    }
    const label = document.createElement("span");
    label.textContent = state.i2i.name || state.i2i.imageId;
    root.appendChild(label);
  }

  function applyI2iItem(item = {}) {
    state.i2i = i2iItemState(item);
    setChecked("#i2iEnabled", Boolean(state.i2i.imageId));
    renderI2iPreview();
    updateSummaries();
  }

  function clearI2iImage() {
    state.i2i = { imageId: "", thumb: "", name: "" };
    setChecked("#i2iEnabled", false);
    setValue("#i2iFile", "");
    text("#i2iStatus", "");
    renderI2iPreview();
    updateSummaries();
  }

  async function uploadI2iImage() {
    const input = $("#i2iFile");
    const file = input?.files?.[0];
    if (!file) {
      text("#i2iStatus", "下絵ファイルを選択してください");
      UI.toast("下絵ファイルを選択してください", "error");
      return;
    }
    text("#i2iStatus", "アップロード中...");
    const form = new FormData();
    form.append("file", file);
    const data = await api("/api/i2i/upload", {
      method: "POST",
      body: form,
    });
    applyI2iItem(data.item);
    text("#i2iStatus", "下絵を設定しました");
    UI.toast("下絵を設定しました");
  }

  async function setFrameAsI2iSource() {
    if (!state.detailItem?.id) return;
    text("#frameActionStatus", "下絵を準備中...");
    const data = await api("/api/i2i/from-history", {
      method: "POST",
      body: JSON.stringify({ history_id: state.detailItem.id }),
    });
    applyI2iItem(data.item);
    UI.closeSheets();
    UI.switchTab("expose");
    const fold = $("details[data-fold='i2i']");
    if (fold) fold.open = true;
    text("#i2iStatus", "下絵を設定しました");
    UI.toast("下絵に設定しました");
  }

  function refmodLabel(module) {
    return module === "pose" ? "Pose" : "Outfit";
  }

  function refmodItemState(item = {}) {
    const imageId = String(item.image_id || "").trim();
    return {
      imageId,
      thumb: String(item.thumbnail_url || item.image_url || item.thumb || "").trim(),
      name: String(item.original_filename || item.filename || item.name || imageId || "").trim(),
    };
  }

  function renderRefmodPreview(module) {
    const root = $(`#${module}Preview`);
    if (!root) return;
    const item = state.refmod[module] || { imageId: "", thumb: "", name: "" };
    root.replaceChildren();
    if (!item.imageId) {
      root.classList.add("is-empty");
      root.textContent = REFMOD_EMPTY_TEXT[module] || "参照は未選択です。";
      return;
    }
    root.classList.remove("is-empty");
    if (item.thumb) {
      const img = document.createElement("img");
      img.src = item.thumb;
      img.alt = item.name || `${module} reference`;
      img.loading = "lazy";
      img.decoding = "async";
      root.appendChild(img);
    }
    const label = document.createElement("span");
    label.textContent = item.name || item.imageId;
    root.appendChild(label);
  }

  function renderRefmodPreviews() {
    renderRefmodPreview("outfit");
    renderRefmodPreview("pose");
  }

  function applyRefmodItem(module, item = {}) {
    if (!state.refmod[module]) return;
    state.refmod[module] = refmodItemState(item);
    setChecked(`#${module}Enabled`, Boolean(state.refmod[module].imageId));
    renderRefmodPreview(module);
    updateSummaries();
  }

  function clearRefmodImage(module) {
    if (!state.refmod[module]) return;
    state.refmod[module] = { imageId: "", thumb: "", name: "" };
    setChecked(`#${module}Enabled`, false);
    setValue(`#${module}File`, "");
    text("#refModStatus", "");
    renderRefmodPreview(module);
    updateSummaries();
  }

  async function uploadRefmodImage(module) {
    if (!state.refmod[module]) return;
    const label = refmodLabel(module);
    const input = $(`#${module}File`);
    const file = input?.files?.[0];
    if (!file) {
      text("#refModStatus", `${label}参照画像を選択してください`);
      UI.toast(`${label}参照画像を選択してください`, "error");
      return;
    }
    text("#refModStatus", `${label}参照をアップロード中...`);
    const form = new FormData();
    form.append("file", file);
    const data = await api(`/api/reference-modules/upload?module=${encodeURIComponent(module)}`, {
      method: "POST",
      body: form,
    });
    applyRefmodItem(module, data.item);
    text("#refModStatus", `${label}参照を設定しました`);
    UI.toast(`${label}参照を設定しました`);
  }

  function canSubmitGenerateRequest() {
    if (checked("#i2iEnabled") && !state.i2i.imageId) {
      text("#i2iStatus", "下絵が未選択です");
      UI.toast("下絵が未選択です", "error");
      return false;
    }
    if (checked("#outfitEnabled") && !state.refmod.outfit.imageId) {
      text("#refModStatus", "Outfit参照が未選択です");
      UI.toast("Outfit参照が未選択です", "error");
      return false;
    }
    if (checked("#poseEnabled") && !state.refmod.pose.imageId) {
      text("#refModStatus", "Pose参照が未選択です");
      UI.toast("Pose参照が未選択です", "error");
      return false;
    }
    return true;
  }

  function renderCharacterResults(items) {
    const root = $("#charResults");
    if (!root) return;
    root.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "見つかりません";
      root.appendChild(empty);
      return;
    }
    for (const raw of items) {
      const item = normalizeCharacterItem(raw);
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.characterId = item.id || "";
      button.dataset.characterName = item.displayName || "";
      button.dataset.characterKind = item.kind || "";
      button.dataset.characterSource = item.source || "";
      button.dataset.characterPromptTag = item.promptTag || "";
      const name = document.createElement("span");
      name.textContent = item.displayName || item.id || "-";
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = item.promptTag || item.kind || "";
      button.append(name, tag);
      root.appendChild(button);
    }
  }

  function clearCharacterSearch() {
    setValue("#charSearch", "");
    $("#charResults")?.replaceChildren();
  }

  async function searchCharacters() {
    const query = value("#charSearch", "").trim();
    if (!query) {
      $("#charResults")?.replaceChildren();
      return;
    }
    const data = await api(`/api/catalog?q=${encodeURIComponent(query)}&kind=all&limit=60`);
    if (value("#charSearch", "").trim() !== query) return;
    renderCharacterResults(Array.isArray(data.items) ? data.items : []);
  }

  function scheduleCharacterSearch() {
    window.clearTimeout(state.characterSearchTimer);
    state.characterSearchTimer = window.setTimeout(() => {
      searchCharacters().catch((error) => UI.toast(errorMessage(error), "error"));
    }, 250);
  }

  function normalizeLoraApplication(value) {
    const raw = String(value || "model_clip").toLowerCase();
    if (raw === "model_only" || raw === "model") return "model_only";
    return "model_clip";
  }

  function loraNameFromItem(item = {}) {
    return String(item.name || item.relative_path || item.file_name || item.lora_id || "").trim();
  }

  function addLoraOption(select, value, label) {
    if (!value) return;
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label || value;
    select.appendChild(option);
  }

  function fillLoraSelect(select, selectedValue) {
    const selected = String(selectedValue || "").trim();
    select.replaceChildren();
    addLoraOption(select, "", "LoRAを選択");
    const seen = new Set([""]);
    for (const item of state.loraSelectable) {
      const optionValue = String(item.relative_path || item.file_name || item.name || item.lora_id || "").trim();
      if (!optionValue || seen.has(optionValue)) continue;
      seen.add(optionValue);
      addLoraOption(select, optionValue, item.display_name || item.file_name || optionValue);
    }
    if (selected && !seen.has(selected)) addLoraOption(select, selected, selected);
    select.value = selected;
  }

  function addLoraRow(initial = {}) {
    const root = $("#loraSlots");
    if (!root) return;
    const row = document.createElement("div");
    row.className = "tray";
    row.dataset.loraRow = "1";

    const grid = document.createElement("div");
    grid.className = "grid2";

    const nameLabel = document.createElement("label");
    nameLabel.className = "field";
    nameLabel.innerHTML = "<span class=\"lbl\">LORA</span>";
    const select = document.createElement("select");
    select.dataset.loraField = "name";
    fillLoraSelect(select, loraNameFromItem(initial));
    nameLabel.appendChild(select);

    const modelLabel = document.createElement("label");
    modelLabel.className = "field";
    modelLabel.innerHTML = "<span class=\"lbl\">MODEL</span>";
    const model = document.createElement("input");
    model.type = "number";
    model.min = "0";
    model.max = "1";
    model.step = "0.05";
    model.value = initial.strength_model ?? initial.model_strength ?? initial.weight ?? "1";
    model.dataset.loraField = "strength_model";
    modelLabel.appendChild(model);

    const clipLabel = document.createElement("label");
    clipLabel.className = "field";
    clipLabel.innerHTML = "<span class=\"lbl\">CLIP</span>";
    const clip = document.createElement("input");
    clip.type = "number";
    clip.min = "0";
    clip.max = "1";
    clip.step = "0.05";
    clip.value = initial.strength_clip ?? initial.clip_strength ?? initial.weight ?? "1";
    clip.dataset.loraField = "strength_clip";
    clipLabel.appendChild(clip);

    const appLabel = document.createElement("label");
    appLabel.className = "field";
    appLabel.innerHTML = "<span class=\"lbl\">APPLY</span>";
    const application = document.createElement("select");
    application.dataset.loraField = "application";
    addLoraOption(application, "model_clip", "model + clip");
    addLoraOption(application, "model_only", "model only");
    application.value = normalizeLoraApplication(initial.application || initial.mode);
    appLabel.appendChild(application);

    grid.append(nameLabel, modelLabel, clipLabel, appLabel);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost";
    remove.dataset.action = "remove-lora";
    remove.textContent = "削除";

    row.append(grid, remove);
    root.appendChild(row);
    updateSummaries();
  }

  function renderConfiguredLoras(settings = state.appSettings) {
    $("#loraSlots")?.replaceChildren();
    const configured = Array.isArray(settings?.loras) && settings.loras.length
      ? settings.loras
      : (settings?.lora_settings?.slots || []).filter((item) => item?.enabled && item?.lora_id !== "none");
    for (const lora of configured) addLoraRow(lora);
  }

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

  function applySettingsToForm(settings = {}, defaults = state.defaults) {
    setValue("#positivePrompt", settings.default_positive_prompt ?? defaults.positive_prompt ?? "");
    setValue("#negativePrompt", settings.default_negative_prompt ?? defaults.negative_prompt ?? "");
    setValue("#negativeMode", settings.negative_prompt_mode ?? defaults.negative_prompt_mode ?? "append");
    setValue("#negativePreset", settings.negative_preset || "anima_recommended");
    setValue("#metaPrompt", settings.meta_prompt || "anime illustration");
    setValue("#yearPrompt", settings.year_prompt || "");
    setValue("#outfitPrompt", settings.outfit_prompt || "");
    setValue("#expressionPrompt", settings.expression_prompt || "");
    setValue("#posePrompt", settings.pose_prompt || "");
    setValue("#backgroundPrompt", settings.background_prompt || "");
    setValue("#cameraPrompt", settings.camera_prompt || "");
    setValue("#lightingPrompt", settings.lighting_prompt || "");
    setValue("#naturalDescription", settings.natural_description || "");
    setValue("#widthInput", settings.width ?? defaults.width ?? 1024);
    setValue("#heightInput", settings.height ?? defaults.height ?? 1536);
    setValue("#stepsInput", settings.steps ?? defaults.steps ?? 32);
    setValue("#cfgInput", settings.cfg ?? defaults.cfg ?? 4.5);
    setValue("#shiftInput", settings.shift ?? defaults.shift ?? 4);
    setValue("#seedInput", settings.seed ?? defaults.seed ?? -1);
    setValue("#seedModeSelect", settings.seed_mode || "fixed");
    setValue("#queueCount", settings.generation_count || 1);
    UI.setSegValue("#ratingSeg", "rating", settings.rating || "safe");
    UI.setSegValue("#qualitySeg", "quality", settings.quality_preset || "standard");

    const official = settings.official_loras || {};
    setChecked("#officialHighresEnabled", official.highres?.enabled);
    setValue("#officialHighresStrength", official.highres?.strength ?? 0.6);
    setChecked("#officialTurboEnabled", official.turbo?.enabled);
    setValue("#officialTurboStrength", official.turbo?.strength ?? 0.6);
    applyWatermark(settings.watermark || {});

    fillSelect("#modelSelect", state.models.models || [], settings.model ?? defaults.model ?? "Anima\\anima-preview3-base.safetensors");
    fillSelect("#samplerSelect", state.models.samplers || [], settings.sampler ?? defaults.sampler ?? "er_sde");
    fillSelect("#schedulerSelect", state.models.schedulers || [], settings.scheduler ?? defaults.scheduler ?? "simple");
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
    return data;
  }

  async function loadLoraCatalog() {
    const data = await api("/api/loras/catalog");
    state.loraSelectable = Array.isArray(data.selectable) ? data.selectable : [];
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
    text("#sceneSummary", sceneParts.length ? sceneParts.slice(0, 3).join(" / ") : "—");
    const negMode = req.negative_prompt_mode || "append";
    const custom = req.negative_prompt ? "+custom" : "no custom";
    text("#negativeSummary", `${req.negative_preset} · ${negMode} · ${custom}`);
    text("#dynamicSummary", req.dynamic_prompt.enabled ? "ON" : "OFF");
    text("#i2iSummary", checked("#i2iEnabled") ? `ON · ${req.image_to_image.denoise}` : "OFF");
    const refParts = [];
    if (checked("#outfitEnabled")) refParts.push("OUTFIT");
    if (checked("#poseEnabled")) refParts.push("POSE");
    text("#refModSummary", refParts.length ? refParts.join("+") : "OFF");
    updateSizeChips();
  }

  async function previewPayload() {
    const data = await api("/api/payload/preview", {
      method: "POST",
      body: JSON.stringify(collectRequest()),
    });
    const preview = $("#payloadPreview");
    if (preview) {
      preview.textContent = JSON.stringify(data, null, 2);
      preview.classList.remove("hidden");
    }
  }

  function isActiveItem(item) {
    return ACTIVE_STATUSES.has(String(item?.status || ""));
  }

  function isCompletedItem(item) {
    const status = String(item?.status || "completed");
    return status === "completed" || Boolean(item?.thumbnail_url || item?.thumbnail_small_url);
  }

  function contactServerFilter() {
    return state.contactFilter === "favorite" ? "favorite" : "all";
  }

  function visibleContactItems(items) {
    if (state.contactFilter !== "active") return items;
    return items.filter(isActiveItem);
  }

  function frameNumber(item, fallbackIndex) {
    const absoluteIndex = Number.isFinite(item?._absoluteIndex) ? item._absoluteIndex : fallbackIndex;
    const no = Math.max(1, Number(state.contactTotal || 0) - absoluteIndex);
    return `#${String(no).padStart(4, "0")}`;
  }

  function renderContact() {
    const root = $("#contactGrid");
    if (!root) return;
    root.replaceChildren();
    if (!state.contactItems.length) {
      const frame = document.createElement("div");
      frame.className = "frame is-pending";
      const label = document.createElement("span");
      label.className = "no";
      label.textContent = "EMPTY";
      frame.appendChild(label);
      root.appendChild(frame);
    }

    state.contactItems.forEach((item, index) => {
      const previousStatus = state.contactStatusById.get(item.id);
      const status = String(item.status || (item.thumbnail_url ? "completed" : "queued"));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "frame";
      button.dataset.historyId = item.id || "";

      if (isCompletedItem(item)) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.decoding = "async";
        img.alt = item.filename || item.id || "";
        img.src = item.thumbnail_small_url || item.thumbnail_url || `/api/history/${escapePathSegment(item.id)}/thumbnail-small`;
        button.appendChild(img);
        if (previousStatus && ACTIVE_STATUSES.has(previousStatus) && status === "completed") {
          window.setTimeout(() => UI.markDeveloping(img), 0);
        }
      } else {
        button.classList.add(status === "failed" || status === "stale" || status === "missing" ? "is-failed" : "is-pending");
        const dot = document.createElement("span");
        dot.className = "dev-dot";
        button.appendChild(dot);
      }

      const no = document.createElement("span");
      no.className = "no";
      no.textContent = `${frameNumber(item, index)} · ${status || "completed"}`;
      button.appendChild(no);
      root.appendChild(button);
      if (item.id) state.contactStatusById.set(item.id, status);
    });
    text("#contactCount", `${state.contactItems.length} / ${state.contactTotal || 0}`);
  }

  function updateContactPolling(activeCount) {
    if (activeCount > 0) {
      state.pollHadActive = true;
      if (!state.contactPollTimer) {
        state.contactPollTimer = window.setInterval(() => {
          loadContact(false, { polling: true, knownRevision: true }).catch((error) => {
            console.warn(error);
          });
        }, 3000);
      }
      return;
    }
    if (state.contactPollTimer) {
      window.clearInterval(state.contactPollTimer);
      state.contactPollTimer = 0;
    }
    if (state.pollHadActive) {
      state.pollHadActive = false;
      UI.safelight("idle");
      UI.toast("現像完了");
    }
  }

  async function loadContact(reset = false, options = {}) {
    const replaceItems = reset || options.polling;
    const offset = replaceItems ? 0 : state.contactOffset;
    const limit = options.polling
      ? Math.max(state.contactOffset || CONTACT_LIMIT, CONTACT_LIMIT)
      : state.contactFilter === "active" ? 100 : CONTACT_LIMIT;
    const params = new URLSearchParams({
      view: "list",
      limit: String(limit),
      offset: String(offset),
      filter: contactServerFilter(),
    });
    if (options.knownRevision && state.contactRevision) params.set("known_revision", state.contactRevision);
    const data = await api(`/api/history?${params.toString()}`);
    if (data.unchanged) {
      updateContactPolling((state.contactItems || []).filter(isActiveItem).length);
      return data;
    }

    const pageItems = (Array.isArray(data.items) ? data.items : []).map((item, index) => ({
      ...item,
      _absoluteIndex: Number(data.offset || 0) + index,
    }));
    const visibleItems = visibleContactItems(pageItems);
    state.contactItems = replaceItems ? visibleItems : [...state.contactItems, ...visibleItems];
    state.contactOffset = Number(data.offset || 0) + pageItems.length;
    state.contactRevision = data.revision || state.contactRevision;
    state.contactLoaded = true;
    state.contactTotal = state.contactFilter === "active"
      ? Number(data.summary?.active ?? visibleItems.length)
      : Number(data.filtered_total ?? data.total ?? visibleItems.length);

    $("#loadMoreBtn")?.classList.toggle("hidden", !data.has_more || state.contactFilter === "active");
    renderContact();
    const activeCount = Number(data.summary?.active ?? state.contactItems.filter(isActiveItem).length);
    updateContactPolling(activeCount);
    return data;
  }

  async function generate() {
    if (!canSubmitGenerateRequest()) return;
    const button = $("#exposeBtn");
    button?.setAttribute("disabled", "disabled");
    try {
      const request = collectRequest();
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(request),
      });
      if (data.status !== "queued" && data.status !== "partial") {
        throw Object.assign(new Error(data.message || "露光できませんでした"), { data });
      }
      const queued = Number(data.queued_count || data.items?.length || request.count || 1);
      UI.toast(`${queued}枚 露光しました`);
      UI.safelight("developing", `${queued} FRAMES DEVELOPING`);
      state.pollHadActive = true;
      await loadContact(true);
    } catch (error) {
      UI.toast(errorMessage(error), "error");
      UI.safelight("error");
    } finally {
      button?.removeAttribute("disabled");
    }
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

  function loraSummary(loras = []) {
    if (!Array.isArray(loras) || !loras.length) return "-";
    return loras.map((lora) => {
      const name = lora.name || lora.display_name || lora.relative_path || lora.file_name || "LoRA";
      const model = lora.strength_model ?? lora.model_strength ?? lora.weight ?? "-";
      const clip = lora.strength_clip ?? lora.clip_strength ?? lora.weight ?? "-";
      return `${name} (M ${model} / C ${clip})`;
    }).join(", ");
  }

  function firstHistoryText(item, keys) {
    for (const key of keys) {
      const parts = key.split(".");
      let valueRef = item;
      for (const part of parts) valueRef = valueRef && typeof valueRef === "object" ? valueRef[part] : undefined;
      if (typeof valueRef === "string" && valueRef.trim()) return valueRef.trim();
    }
    return "";
  }

  function historyPositiveText(item = {}) {
    return firstHistoryText(item, [
      "dynamic_prompt.expanded_positive_prompt",
      "positive",
      "positive_prompt",
      "dynamic_prompt.raw_positive_prompt",
    ]);
  }

  function historyNegativeText(item = {}) {
    return firstHistoryText(item, [
      "dynamic_prompt.expanded_negative_prompt",
      "negative",
      "negative_prompt",
      "dynamic_prompt.raw_negative_prompt",
    ]);
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

  function updateFrameFavoriteButton(item = state.detailItem) {
    const button = $("[data-action='frame-favorite']");
    const favorite = Boolean(item?.flags?.favorite);
    if (button) button.textContent = `${favorite ? "★" : "☆"} お気に入り`;
  }

  function renderFrameDetail(item) {
    state.detailItem = item;
    text("#frameActionStatus", "");
    const image = $("#frameImage");
    const imageUrl = item.image_url || item.thumbnail_url || item.thumbnail_small_url || "";
    if (image && imageUrl) {
      image.src = imageUrl;
      image.alt = item.filename || item.id || "生成画像";
    } else if (image) {
      image.removeAttribute("src");
      image.alt = "画像なし";
    }
    updateFrameFavoriteButton(item);
    const table = $("#frameMeta");
    if (table) {
      table.replaceChildren();
      addMetaRow(table, "FRAME", item.id);
      addMetaRow(table, "TIME", formatDate(item.created_at));
      addMetaRow(table, "SEED", item.seed);
      addMetaRow(table, "SIZE", `${item.output_width || item.width || "-"}×${item.output_height || item.height || "-"}`);
      addMetaRow(table, "STEPS·CFG·SHIFT", `${displayValue(item.steps)} · ${displayValue(item.cfg)} · ${displayValue(item.shift ?? item.model_sampling?.shift)}`);
      addMetaRow(table, "SAMPLER·SCHEDULER", `${displayValue(item.sampler)} · ${displayValue(item.scheduler)}`);
      addMetaRow(table, "MODEL", modelFileName(item.model));
      addMetaRow(table, "RATING", item.rating || "-");
      addMetaRow(table, "CHARACTERS", characterSummary(item));
      addMetaRow(table, "LORA", loraSummary(item.loras || []));
      addMetaRow(table, "POSITIVE", historyPositiveText(item), true);
      addMetaRow(table, "NEGATIVE", historyNegativeText(item), true);
    }
    UI.openSheet("#frameSheet");
  }

  async function openFrameDetail(id) {
    const data = await api(`/api/history/${escapePathSegment(id)}`);
    renderFrameDetail(data.item);
  }

  async function toggleFrameFavorite() {
    if (!state.detailItem?.id) return;
    const nextFavorite = !state.detailItem.flags?.favorite;
    const data = await api(`/api/history/${escapePathSegment(state.detailItem.id)}/flags`, {
      method: "POST",
      body: JSON.stringify({ favorite: nextFavorite }),
    });
    state.detailItem = data.item;
    updateFrameFavoriteButton(data.item);
    text("#frameActionStatus", nextFavorite ? "お気に入りにしました" : "お気に入りを解除しました");
    await loadContact(true).catch(() => {});
  }

  function publicImageUrl(item = state.detailItem) {
    if (!item?.id) return "";
    return item.public_image_url || (item.public_save?.saved ? `/api/history/${escapePathSegment(item.id)}/public-image` : "");
  }

  function absoluteUrl(path) {
    return new URL(path, window.location.href).toString();
  }

  async function savePublicImage() {
    if (!state.detailItem?.id) return null;
    const data = await api(`/api/history/${escapePathSegment(state.detailItem.id)}/public-save`, {
      method: "POST",
      body: JSON.stringify({
        apply_watermark: checked("#watermarkEnabled"),
        watermark: collectWatermark(),
      }),
    });
    state.detailItem = data.item || state.detailItem;
    text("#frameActionStatus", "公開保存しました");
    return data;
  }

  async function shareFrame() {
    if (!state.detailItem?.id) return;
    try {
      text("#frameActionStatus", "共有用画像を準備中...");
      const data = await savePublicImage();
      const item = data?.item || state.detailItem;
      const imageUrl = data?.public_image_url || publicImageUrl(item);
      if (!imageUrl) throw new Error("公開画像URLを取得できませんでした");
      const response = await fetch(imageUrl, { credentials: "same-origin" });
      if (!response.ok) throw new Error("共有用画像を取得できませんでした");
      const blob = await response.blob();
      const filename = String(data?.filename || item.filename || `${item.id}_public.png`).replace(/[^\w.-]/g, "_");
      const file = new File([blob], filename, { type: blob.type || "image/png" });
      const canShare = Boolean(navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] })));
      if (!canShare) {
        window.open(absoluteUrl(imageUrl), "_blank", "noopener");
        text("#frameActionStatus", "共有非対応: 開いた画像を長押し保存してください");
        UI.toast("共有非対応です。画像を開きました");
        return;
      }
      await navigator.share({ files: [file] });
      text("#frameActionStatus", "共有シートを開きました");
      UI.toast("共有シートを開きました");
    } catch (error) {
      if (error?.name === "AbortError") {
        text("#frameActionStatus", "共有キャンセル");
        return;
      }
      text("#frameActionStatus", errorMessage(error));
      UI.toast(errorMessage(error), "error");
    }
  }

  function historyCharacterValue(char, targetSlot) {
    if (!char || typeof char !== "object") return "";
    const source = sourceForCharacter(char);
    const displayName = char.display_name || char.name || char.id || "";
    if (targetSlot === "original") return char.id || displayName;
    if (source === "original_character") return `original:${char.id || displayName}`;
    return displayName;
  }

  function applyHistoryToForm(item) {
    state.slots = { character1: null, character2: null, character3: null, original: null };
    for (const char of item.characters || []) {
      const slotNumber = Number(char.slot || 0);
      const slotName = slotNumber === 1 ? "character1" : slotNumber === 2 ? "character2" : slotNumber === 3 ? "character3" : slotNumber === 4 ? "original" : "";
      if (!slotName) continue;
      const normalized = normalizeCharacterItem({
        ...char,
        source: sourceForCharacter(char),
        kind: sourceForCharacter(char) === "original_character" ? "original" : "wai",
      });
      state.slots[slotName] = { ...normalized, value: historyCharacterValue(char, slotName) };
    }
    renderSlots();
    if (item.rating) UI.setSegValue("#ratingSeg", "rating", item.rating);
    if (item.quality_preset) UI.setSegValue("#qualitySeg", "quality", item.quality_preset);
    setValue("#positivePrompt", historyPositiveText(item));
    setValue("#negativePrompt", historyNegativeText(item));
    setValue("#negativeMode", "custom");
    if (item.negative_preset) setValue("#negativePreset", item.negative_preset);
    setValue("#naturalDescription", item.natural_description || "");
    setValue("#modelSelect", item.model || state.defaults.model || "");
    setValue("#widthInput", item.width || 1024);
    setValue("#heightInput", item.height || 1536);
    setValue("#stepsInput", item.steps || 32);
    setValue("#cfgInput", item.cfg || 4.5);
    setValue("#shiftInput", item.shift ?? item.model_sampling?.shift ?? state.defaults.shift ?? 4);
    if (item.sampler) setValue("#samplerSelect", item.sampler);
    if (item.scheduler) setValue("#schedulerSelect", item.scheduler);
    setValue("#seedInput", item.seed ?? -1);
    setValue("#seedModeSelect", "fixed");
    const official = item.official_loras || {};
    setChecked("#officialHighresEnabled", official.highres?.enabled);
    setValue("#officialHighresStrength", official.highres?.strength ?? 0.6);
    setChecked("#officialTurboEnabled", official.turbo?.enabled);
    setValue("#officialTurboStrength", official.turbo?.strength ?? 0.6);
    $("#loraSlots")?.replaceChildren();
    for (const lora of item.loras || []) addLoraRow(lora);
    updateSummaries();
    UI.closeSheets();
    UI.switchTab("expose");
    UI.toast("設定を再利用しました");
  }

  function settingsFromForm() {
    const next = clone(state.appSettings);
    Object.assign(next, {
      workflow_mode: "anima",
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
      generation_count: selectedQueueCount(),
      default_positive_prompt: value("#positivePrompt", ""),
      default_negative_prompt: value("#negativePrompt", ""),
      negative_prompt_mode: value("#negativeMode", "append"),
      negative_preset: value("#negativePreset", "anima_recommended"),
      rating: UI.segValue("#ratingSeg", "rating") || "safe",
      quality_preset: UI.segValue("#qualitySeg", "quality") || "standard",
      meta_prompt: value("#metaPrompt", "anime illustration"),
      year_prompt: value("#yearPrompt", ""),
      outfit_prompt: value("#outfitPrompt", ""),
      expression_prompt: value("#expressionPrompt", ""),
      pose_prompt: value("#posePrompt", ""),
      background_prompt: value("#backgroundPrompt", ""),
      camera_prompt: value("#cameraPrompt", ""),
      lighting_prompt: value("#lightingPrompt", ""),
      natural_description: value("#naturalDescription", ""),
      official_loras: collectOfficialLoras(),
      loras: collectLoras(),
      watermark: collectWatermark(),
      public_save: {
        ...(next.public_save || {}),
        apply_watermark: checked("#watermarkEnabled"),
      },
    });
    return next;
  }

  async function saveDefaults() {
    const settings = settingsFromForm();
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

  function renderDiagnostics(data) {
    const table = $("#connMeta");
    if (table) {
      table.replaceChildren();
      addMetaRow(table, "API_ADDR", data.api_addr || "-");
      addMetaRow(table, "WORKFLOW", data.anima_workflow_found ? "found" : "missing");
      addMetaRow(table, "MAPPING", data.anima_mapping_found ? "found" : "missing");
      addMetaRow(table, "MODELS_CACHE", data.models_cache || {});
      addMetaRow(table, "CATALOG", `${data.catalog_count ?? "-"} / original ${data.original_count ?? "-"}`);
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

  async function bootstrap(initialData = null) {
    const data = initialData || await api("/api/bootstrap");
    state.bootstrap = data;
    state.appSettings = data.settings || {};
    state.defaults = data.defaults || {};
    text("#catalogCount", `${data.catalog_count || 0} chars / original ${data.original_count || 0}`);
    applySettingsToForm(state.appSettings, state.defaults);

    const modelResult = await Promise.allSettled([loadModels(false), loadLoraCatalog()]);
    if (modelResult[0].status === "rejected") {
      console.warn(modelResult[0].reason);
      fillSelect("#modelSelect", [], state.defaults.model || state.appSettings.model || "Anima\\anima-preview3-base.safetensors");
      fillSelect("#samplerSelect", [], state.defaults.sampler || state.appSettings.sampler || "er_sde");
      fillSelect("#schedulerSelect", [], state.defaults.scheduler || state.appSettings.scheduler || "simple");
    }
    renderConfiguredLoras(state.appSettings);
    await Promise.allSettled([
      loadFavorites(),
      searchCharacters(),
      loadContact(true),
    ]);
    updateSummaries();
  }

  async function tryBootstrapSession() {
    try {
      const data = await api("/api/bootstrap");
      UI.enterDarkroom();
      await bootstrap(data);
    } catch {
      exitToLogin();
    }
  }

  async function handleAction(action, target) {
    if (action === "login") return login();
    if (action === "clear-slot") return clearSlot();
    if (action === "toggle-favorite-slot") return toggleFavoriteForArmedSlot();
    if (action === "add-lora") {
      if (!state.loraSelectable.length) await loadLoraCatalog().catch(() => {});
      addLoraRow();
      return;
    }
    if (action === "remove-lora") {
      target.closest("[data-lora-row]")?.remove();
      updateSummaries();
      return;
    }
    if (action === "preview") return previewPayload();
    if (action === "generate") return generate();
    if (action === "dynamic-wildcards") return loadDynamicWildcards();
    if (action === "dynamic-preview") return previewDynamicPrompt();
    if (action === "save-positive-fav") return savePositiveFavorite();
    if (action === "open-positive-favs") return openPositiveFavorites();
    if (action === "open-templates") return openPositiveTemplates();
    if (action === "load-more") return loadContact(false);
    if (action === "frame-favorite") return toggleFrameFavorite();
    if (action === "frame-public-save") return savePublicImage();
    if (action === "frame-share") return shareFrame();
    if (action === "frame-reuse") {
      if (state.detailItem) applyHistoryToForm(state.detailItem);
      return;
    }
    if (action === "frame-to-i2i") return setFrameAsI2iSource();
    if (action === "i2i-upload") return uploadI2iImage();
    if (action === "i2i-clear") return clearI2iImage();
    if (action === "outfit-upload") return uploadRefmodImage("outfit");
    if (action === "outfit-clear") return clearRefmodImage("outfit");
    if (action === "pose-upload") return uploadRefmodImage("pose");
    if (action === "pose-clear") return clearRefmodImage("pose");
    if (action === "save-defaults") return saveDefaults();
    if (action === "reset-defaults") return resetDefaults();
    if (action === "reload-models") return reloadModels();
  }

  function bindEvents() {
    UI.bindSeg("#ratingSeg", "rating", updateSummaries);
    UI.bindSeg("#qualitySeg", "quality", updateSummaries);
    UI.onTab((name) => {
      if (name === "contact" && !state.contactLoaded) {
        loadContact(true).catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    $("#pinInput")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") login();
    });

    $("#charSearch")?.addEventListener("input", scheduleCharacterSearch);

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

    $("#wildcardChips")?.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip[data-wildcard-name]");
      if (!chip) return;
      insertPositivePromptText(`__${chip.dataset.wildcardName}__, `);
    });

    $("#promptSheetList")?.addEventListener("click", (event) => {
      const deleteTarget = event.target.closest("[data-prompt-delete-id]");
      if (deleteTarget) {
        event.preventDefault();
        deletePositiveFavorite(deleteTarget.dataset.promptDeleteId).catch((error) => UI.toast(errorMessage(error), "error"));
        return;
      }
      const row = event.target.closest("[data-prompt-item-id]");
      if (!row) return;
      usePromptSheetItem(row.dataset.promptItemId).catch((error) => UI.toast(errorMessage(error), "error"));
    });

    $("#promptSheetQuery")?.addEventListener("input", () => {
      window.clearTimeout(state.promptSheetQueryTimer);
      if (state.promptSheetMode === "favorites") {
        renderPromptSheet();
        return;
      }
      state.promptSheetQueryTimer = window.setTimeout(() => {
        text("#promptSheetStatus", "読み込み中...");
        loadPositiveTemplates().catch((error) => {
          text("#promptSheetStatus", errorMessage(error));
          UI.toast(errorMessage(error), "error");
        });
      }, 250);
    });

    $("#charSlots")?.addEventListener("click", (event) => {
      const slot = event.target.closest(".slot[data-slot]");
      if (!slot) return;
      state.armedSlot = slot.dataset.slot;
      renderSlots();
    });

    $("#sizeChips")?.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip[data-size]");
      if (!chip) return;
      const [width, height] = chip.dataset.size.split("x").map(Number);
      setValue("#widthInput", width);
      setValue("#heightInput", height);
      updateSummaries();
    });

    $("#contactFilters")?.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip[data-filter]");
      if (!chip) return;
      state.contactFilter = chip.dataset.filter || "all";
      $$("#contactFilters .chip").forEach((item) => item.classList.toggle("is-active", item === chip));
      state.contactRevision = "";
      loadContact(true).catch((error) => UI.toast(errorMessage(error), "error"));
    });

    $("#contactGrid")?.addEventListener("click", (event) => {
      const frame = event.target.closest(".frame[data-history-id]");
      if (!frame?.dataset.historyId) return;
      openFrameDetail(frame.dataset.historyId).catch((error) => UI.toast(errorMessage(error), "error"));
    });

    document.addEventListener("click", (event) => {
      const favorite = event.target.closest("[data-favorite-id]");
      if (favorite) {
        applyCharacterToSlot({
          source: favorite.dataset.favoriteSource,
          id: favorite.dataset.favoriteId,
          display_name: favorite.dataset.favoriteName,
          prompt_tag: favorite.dataset.favoritePromptTag,
        });
        api(`/api/favorites/${escapePathSegment(favorite.dataset.favoriteSource)}/${escapePathSegment(favorite.dataset.favoriteId)}/use`, {
          method: "POST",
          body: "{}",
        }).then(setFavorites).catch(() => {});
        clearCharacterSearch();
        UI.toast(`${favorite.dataset.favoriteName} を反映しました`);
        return;
      }

      const result = event.target.closest("[data-character-id]");
      if (result) {
        applyCharacterToSlot({
          source: result.dataset.characterSource,
          id: result.dataset.characterId,
          display_name: result.dataset.characterName,
          kind: result.dataset.characterKind,
          prompt_tag: result.dataset.characterPromptTag,
        });
        clearCharacterSearch();
        UI.toast(`${result.dataset.characterName} を反映しました`);
        return;
      }

      const settingsTab = event.target.closest("#tabs button[data-tab='settings']");
      if (settingsTab) window.setTimeout(loadDiagnostics, 0);

      const actionTarget = event.target.closest("[data-action]");
      if (!actionTarget) return;
      const action = actionTarget.dataset.action;
      if (action === "close-sheet") return;
      handleAction(action, actionTarget).catch((error) => {
        UI.toast(errorMessage(error), "error");
        if (action?.startsWith("frame-")) text("#frameActionStatus", errorMessage(error));
        if (action?.startsWith("i2i-")) text("#i2iStatus", errorMessage(error));
        if (action?.startsWith("outfit-") || action?.startsWith("pose-")) text("#refModStatus", errorMessage(error));
        if (["save-defaults", "reset-defaults", "reload-models"].includes(action)) text("#settingsStatus", errorMessage(error));
      });
    });

    document.addEventListener("input", (event) => {
      if (event.target.closest("#settingsSheet")) {
        state.appSettings = { ...state.appSettings, watermark: collectWatermark() };
      }
      if (event.target.closest("#exposeView") || event.target.closest("#exposeBar")) updateSummaries();
    });

    document.addEventListener("change", (event) => {
      if (event.target.closest("#settingsSheet")) {
        state.appSettings = { ...state.appSettings, watermark: collectWatermark() };
      }
      if (event.target.closest("#exposeView") || event.target.closest("#exposeBar")) updateSummaries();
    });
  }

  function init() {
    bindEvents();
    clearCharacterSearch();
    renderI2iPreview();
    renderRefmodPreviews();
    renderSlots();
    updateSummaries();
    tryBootstrapSession();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
