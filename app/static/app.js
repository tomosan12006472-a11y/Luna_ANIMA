(() => {
  "use strict";

  const UI = window.UI;
  const { $, $$ } = UI;

  const CONTACT_LIMIT = 24;
  const ACTIVE_STATUSES = new Set(["queued", "running"]);
  const EMPTY_SLOT_LABELS = {
    character1: "未選択",
    character2: "未選択",
    character3: "未選択",
    original: "未選択",
  };
  const I2I_EMPTY_TEXT = "下絵は未選択です。履歴の「下絵にする」からも選べます。";
  const REFMOD_EMPTY_TEXT = {
    outfit: "Outfit参照は未選択です。",
    pose: "Pose参照は未選択です。",
  };
  const SCORE_TAG_RE = /^[([{]*score_\d+(?:_up)?(?::[0-9.]+)?[\])}]*$/i;

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
    characterFavoritesCollapsed: false,
    contactFilter: "all",
    contactSearch: {
      q: "",
      dateFrom: "",
      dateTo: "",
      model: "",
      lora: "",
      seed: "",
      rating: "",
      hiresMode: "",
      reference: "",
      sampler: "",
      scheduler: "",
      character: "",
      requestSeq: 0,
    },
    contactItems: [],
    contactOffset: 0,
    contactTotal: 0,
    contactRevision: "",
    contactLoaded: false,
    contactStatusById: new Map(),
    contactPollTimer: 0,
    contactPollFailures: 0,
    queuePollTimer: 0,
    pollHadActive: false,
    detailItem: null,
    characterSearchTimer: 0,
    promptSheetMode: "favorites",
    promptSheetItems: [],
    promptSheetEditingId: "",
    recipes: [],
    promptSheetQueryTimer: 0,
    dictQueryTimer: 0,
    dictStatusLoaded: false,
    promptConverterStatusLoaded: false,
    promptConverterLast: null,
    promptRandomStatusLoaded: false,
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

  function numberFrom(raw, fallback = 0) {
    const value = Number(raw);
    return Number.isFinite(value) ? value : fallback;
  }

  function intFrom(raw, fallback = 0) {
    return Math.trunc(numberFrom(raw, fallback));
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

  function isUnauthorized(error) {
    return Number(error?.status || error?.data?.status || 0) === 401;
  }

  function authExpiredMessage() {
    return "ログインが切れました。PINで入り直してください。";
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

  async function fetchWithAuthHandling(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
    });
    if (response.status === 401) {
      const message = authExpiredMessage();
      exitToLogin(message);
      const error = new Error(message);
      error.status = response.status;
      error.data = { ok: false, status: response.status, message };
      throw error;
    }
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      const error = new Error(response.statusText || "Request failed");
      error.status = response.status;
      error.data = { ok: false, status: response.status, body: body.slice(0, 300) };
      throw error;
    }
    return response;
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
    const contentType = response.headers.get("content-type") || "";
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = {
        ok: false,
        message: "Response was not JSON",
        status: response.status,
        content_type: contentType,
        body: raw.slice(0, 300),
      };
    }
    if (response.status === 401) {
      exitToLogin(authExpiredMessage());
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

  function selectedVariationCount() {
    const count = Math.trunc(Number(value("#variationCount", 2)));
    return Number.isFinite(count) && count > 0 ? count : 2;
  }

  function normalizeHiresMode(mode) {
    return String(mode || "latent").toLowerCase() === "model" ? "model" : "latent";
  }

  function normalizeHiresFix(hires = {}) {
    const source = hires && typeof hires === "object" ? hires : {};
    const latentMethod = String(source.latent_upscale_method || source.upscale_method || "nearest-exact").trim() || "nearest-exact";
    return {
      enabled: Boolean(source.enabled),
      mode: normalizeHiresMode(source.mode),
      upscale_factor: numberFrom(source.upscale_factor ?? source.factor, 1.5),
      denoise: numberFrom(source.denoise, 0.45),
      steps: intFrom(source.steps, 15),
      latent_upscale_method: latentMethod,
      upscale_model: String(source.upscale_model || "").trim(),
      target_width: intFrom(source.target_width, 0),
      target_height: intFrom(source.target_height, 0),
    };
  }

  function collectHiresFix() {
    return normalizeHiresFix({
      enabled: checked("#hiresEnabled"),
      mode: value("#hiresMode", "latent"),
      upscale_factor: numberValue("#hiresFactor", 1.5),
      denoise: numberValue("#hiresDenoise", 0.45),
      steps: intFrom(numberValue("#hiresSteps", 15), 15),
      latent_upscale_method: value("#hiresMethod", "nearest-exact"),
      upscale_model: value("#hiresModel", ""),
      target_width: intFrom(numberValue("#hiresTargetW", 0), 0),
      target_height: intFrom(numberValue("#hiresTargetH", 0), 0),
    });
  }

  function applyHiresFixToForm(hires = {}) {
    const next = normalizeHiresFix(hires);
    setChecked("#hiresEnabled", next.enabled);
    setValue("#hiresMode", next.mode);
    setValue("#hiresFactor", next.upscale_factor);
    setValue("#hiresDenoise", next.denoise);
    setValue("#hiresSteps", next.steps);
    fillSelect("#hiresMethod", state.models.upscale_methods || [], next.latent_upscale_method);
    fillSelect("#hiresModel", state.models.upscale_models || [], next.upscale_model);
    setValue("#hiresTargetW", next.target_width);
    setValue("#hiresTargetH", next.target_height);
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
    return "None";
  }

  function defaultPromptRandomCollect() {
    return {
      enabled: false,
      instruction: "衣装、表情、背景、小物をランダムに足す",
      strength: "standard",
      include_characters: true,
    };
  }

  function collectPromptRandomCollect() {
    return {
      enabled: checked("#promptRandomEnabled"),
      instruction: value("#promptRandomInstruction", defaultPromptRandomCollect().instruction),
      strength: value("#promptRandomStrength", "standard"),
      include_characters: checked("#promptRandomIncludeCharacters"),
    };
  }

  function promptRandomOnSummary() {
    return checked("#promptRandomIncludeCharacters") ? "ON / CHAR" : "ON / NO CHAR";
  }

  function applyPromptRandomCollectToForm(config = {}) {
    const defaults = defaultPromptRandomCollect();
    setChecked("#promptRandomEnabled", Boolean(config.enabled));
    setValue("#promptRandomInstruction", config.instruction || defaults.instruction);
    setValue("#promptRandomStrength", config.strength || defaults.strength);
    setChecked("#promptRandomIncludeCharacters", config.include_characters !== false);
  }

  function collectRequest() {
    const negative = value("#negativePrompt", "");
    const seedMode = value("#seedModeSelect", "fixed");
    const i2iEnabled = checked("#i2iEnabled") && Boolean(state.i2i.imageId);
    const outfitEnabled = checked("#outfitEnabled");
    const poseEnabled = checked("#poseEnabled");
    const hiresFix = collectHiresFix();
    return {
      workflow_mode: hiresFix.enabled ? "anima_mobile_extended" : "anima",
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
      prompt_random_collect: collectPromptRandomCollect(),
      hires_fix: hiresFix,
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
      face_detailer: collectFaceDetailerSettings(checked("#fdEnabled"), "generation"),
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

  function isRandomSlotItem(item) {
    return String(item?.kind || "").toLowerCase() === "random" || String(item?.value || "").toLowerCase() === "random";
  }

  function randomSlotItem(slotName = state.armedSlot) {
    const original = slotName === "original";
    const displayName = original ? "Original Random" : "Random";
    return {
      source: original ? "original_character" : "wai_characters",
      id: "Random",
      displayName,
      originalDisplayName: displayName,
      promptTag: "",
      promptSafeName: "",
      kind: "random",
      value: "Random",
    };
  }

  function normalizeCharacterItem(raw = {}) {
    const source = sourceForCharacter(raw);
    const originalDisplayName = String(raw.display_name_original || raw.display_name || raw.name || raw.id || "").trim();
    const localizedDisplayName = String(raw.display_name_ja || raw.localized_display_name || raw.displayNameJa || "").trim();
    const fallbackDisplayName = String(raw.displayName || originalDisplayName).trim();
    const displayName = localizedDisplayName || fallbackDisplayName;
    const id = String(raw.id || originalDisplayName || displayName).trim();
    const promptTag = String(raw.prompt_tag || raw.promptTag || "").trim();
    const promptSafeName = String(raw.prompt_safe_name || raw.promptSafeName || "").trim();
    const kind = raw.kind || (source === "original_character" ? "original" : "wai");
    return { source, id, displayName, originalDisplayName, promptTag, promptSafeName, kind };
  }

  function valueForSlot(slotName, item) {
    if (isRandomSlotItem(item)) return "Random";
    if (slotName === "original") return item.id || item.displayName || "None";
    if (item.source === "original_character" || item.kind === "original") {
      return `original:${item.id || item.displayName}`;
    }
    return item.promptTag || item.originalDisplayName || item.id || item.displayName || "None";
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

  function slotShortLabel(slotName) {
    return { character1: "C1", character2: "C2", character3: "C3", original: "ORIGINAL" }[slotName] || slotName;
  }

  function setRandomSlot(slotName = state.armedSlot) {
    state.slots[slotName] = randomSlotItem(slotName);
    renderSlots();
    updateSummaries();
    UI.toast(`${slotShortLabel(slotName)} をRandomにしました`);
  }

  function compactSlotName(textValue) {
    const text = String(textValue || "").replace(/\s+/g, " ").trim();
    const limit = 18;
    if (text.length <= limit) return text;
    return `${text.slice(0, limit)}...`;
  }

  function renderSlots() {
    $$(".slot", $("#charSlots")).forEach((slot) => {
      const slotName = slot.dataset.slot;
      const item = state.slots[slotName];
      const fullName = item?.displayName || EMPTY_SLOT_LABELS[slotName] || "未選択";
      slot.classList.toggle("is-armed", slotName === state.armedSlot);
      slot.classList.toggle("is-empty", !item);
      slot.classList.toggle("is-random", isRandomSlotItem(item));
      const name = slot.querySelector(".name");
      if (name) {
        name.textContent = compactSlotName(fullName);
        name.title = fullName;
      }
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
    if (isRandomSlotItem(slotItem)) return false;
    const fav = normalizeCharacterItem(favorite);
    if (fav.source !== slotItem.source) return false;
    if (fav.source === "original_character") {
      return fav.id === slotItem.id || fav.originalDisplayName === slotItem.originalDisplayName || fav.displayName === slotItem.displayName;
    }
    return (
      (fav.promptTag && fav.promptTag === slotItem.promptTag) ||
      fav.originalDisplayName === slotItem.originalDisplayName ||
      fav.displayName === slotItem.displayName
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
    text("#favCount", `${favorites.length}件`);
    const toggle = $("#favToggle");
    if (toggle) {
      toggle.textContent = `★ お気に入り ${state.characterFavoritesCollapsed ? "▸" : "▾"}`;
      toggle.setAttribute("aria-expanded", String(!state.characterFavoritesCollapsed));
    }
    root.hidden = Boolean(state.characterFavoritesCollapsed);
    if (state.characterFavoritesCollapsed) return;
    if (!favorites.length) {
      const empty = document.createElement("span");
      empty.className = "lbl";
      empty.textContent = "お気に入りなし";
      root.appendChild(empty);
      return;
    }
    for (const favorite of favorites) {
      const item = normalizeCharacterItem(favorite);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.dataset.favoriteId = favorite.id || "";
      button.dataset.favoriteSource = item.source || "";
      button.dataset.favoriteName = item.originalDisplayName || item.displayName || "";
      button.dataset.favoriteDisplayName = item.displayName || "";
      button.dataset.favoritePromptTag = item.promptTag || "";
      button.dataset.favoritePromptSafeName = item.promptSafeName || "";
      button.textContent = `★ ${item.displayName || item.originalDisplayName || item.id}`;
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

  async function markFavoriteUsedWithRetry(source, favoriteId) {
    if (!source || !favoriteId) return;
    const path = `/api/favorites/${escapePathSegment(source)}/${escapePathSegment(favoriteId)}/use`;
    const options = { method: "POST", body: "{}" };
    try {
      setFavorites(await api(path, options));
    } catch (error) {
      console.debug("favorite use update failed; retrying", error);
      try {
        setFavorites(await api(path, options));
      } catch (retryError) {
        console.debug("favorite use update failed", retryError);
      }
    }
  }

  async function toggleFavoriteForArmedSlot() {
    const slotItem = state.slots[state.armedSlot];
    if (!slotItem) {
      UI.toast("選択中スロットが空です", "error");
      return;
    }
    if (isRandomSlotItem(slotItem)) {
      UI.toast("Randomはお気に入り登録できません", "error");
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

  function toggleCharacterFavorites() {
    state.characterFavoritesCollapsed = !state.characterFavoritesCollapsed;
    renderFavorites();
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

  function joinPositivePromptParts(parts = []) {
    return parts.map((part) => String(part || "").trim()).filter(Boolean).join(", ");
  }

  function applyPositivePromptInsert(prompt, mode) {
    const nextPrompt = String(prompt || "").trim();
    if (!nextPrompt) return;
    const current = value("#positivePrompt", "").trim();
    if (mode === "replace") {
      setValue("#positivePrompt", nextPrompt);
    } else if (mode === "prepend") {
      setValue("#positivePrompt", joinPositivePromptParts([nextPrompt, current]));
    } else {
      setValue("#positivePrompt", joinPositivePromptParts([current, nextPrompt]));
    }
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

  function promptItemTagsText(item = {}) {
    if (Array.isArray(item.tags)) return item.tags.join(", ");
    return String(item.tags || "");
  }

  function parsePromptTags(valueText) {
    return String(valueText || "")
      .replace(/;/g, ",")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
  }

  function promptSheetQueryField() {
    return $("#promptSheetQuery")?.closest(".field") || null;
  }

  function showPromptSheetList() {
    state.promptSheetEditingId = "";
    $("#promptSheetEditor")?.classList.add("hidden");
    $("#promptSheetEditor")?.replaceChildren();
    $("#promptSheetList")?.classList.remove("hidden");
    promptSheetQueryField()?.classList.remove("hidden");
  }

  function showPromptSheetEditor() {
    $("#promptSheetEditor")?.classList.remove("hidden");
    $("#promptSheetList")?.classList.add("hidden");
    promptSheetQueryField()?.classList.add("hidden");
  }

  function promptEditorField(labelText, control) {
    const label = document.createElement("label");
    label.className = "field";
    const labelSpan = document.createElement("span");
    labelSpan.className = "lbl";
    labelSpan.textContent = labelText;
    label.append(labelSpan, control);
    return label;
  }

  function renderPositiveFavoriteEditor(item) {
    if (state.promptSheetMode !== "favorites" || !item?.id) return;
    const root = $("#promptSheetEditor");
    if (!root) return;
    state.promptSheetEditingId = String(item.id || "");
    root.replaceChildren();

    const title = document.createElement("input");
    title.name = "title";
    title.type = "text";
    title.value = promptItemTitle(item);

    const prompt = document.createElement("textarea");
    prompt.name = "prompt";
    prompt.rows = 7;
    prompt.value = promptItemPrompt(item);

    const tags = document.createElement("input");
    tags.name = "tags";
    tags.type = "text";
    tags.value = promptItemTagsText(item);

    const note = document.createElement("textarea");
    note.name = "note";
    note.rows = 3;
    note.value = String(item.note || "");

    const actions = document.createElement("div");
    actions.className = "row";
    const save = document.createElement("button");
    save.type = "submit";
    save.className = "ghost";
    save.textContent = "保存";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ghost";
    cancel.textContent = "キャンセル";
    cancel.addEventListener("click", () => {
      showPromptSheetList();
      renderPromptSheet();
    });
    actions.append(save, cancel);

    const form = document.createElement("form");
    form.append(
      promptEditorField("TITLE", title),
      promptEditorField("POSITIVE", prompt),
      promptEditorField("TAGS", tags),
      promptEditorField("NOTE", note),
      actions,
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      savePositiveFavoriteEdit(item.id, form).catch((error) => UI.toast(errorMessage(error), "error"));
    });
    root.appendChild(form);
    showPromptSheetEditor();
    text("#promptSheetCount", "編集中");
    text("#promptSheetStatus", "");
    prompt.focus();
  }

  async function confirmDanger({ title = "確認しますか?", message = "", label = "実行する" } = {}) {
    const choice = await UI.ask({
      title,
      message,
      choices: [{ label, value: "yes", kind: "danger" }],
    });
    return choice === "yes";
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
    showPromptSheetList();
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

  async function savePositiveFavoriteEdit(favoriteId, form) {
    const fields = form.elements;
    const prompt = String(fields.prompt?.value || "").trim();
    if (!prompt) {
      UI.toast("Positiveが空です", "error");
      return;
    }
    const data = await api(`/api/prompts/positive-favorites/${escapePathSegment(favoriteId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: String(fields.title?.value || "").trim(),
        prompt,
        tags: parsePromptTags(fields.tags?.value),
        note: String(fields.note?.value || "").trim(),
      }),
    });
    state.promptSheetItems = Array.isArray(data.items) ? data.items : [];
    showPromptSheetList();
    renderPromptSheet();
    UI.toast("更新しました");
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
    const choices = [
      { label: "先頭に挿入", value: "prepend" },
      { label: "末尾に追記", value: "append", kind: "primary" },
    ];
    if (state.promptSheetMode === "favorites" && item?.id) {
      choices.push({ label: "編集", value: "edit" });
    }
    choices.push({ label: "置換", value: "replace", kind: "danger" });
    const mode = await UI.ask({
      title: "どこに入れますか?",
      message: `${promptItemTitle(item)}\n${promptExcerpt(prompt, 120)}`,
      choices,
    });
    if (!mode) return;
    if (mode === "edit") {
      renderPositiveFavoriteEditor(item);
      return;
    }
    applyPositivePromptInsert(prompt, mode);
    if (state.promptSheetMode === "favorites" && item?.id) {
      await api(`/api/prompts/positive-favorites/${escapePathSegment(item.id)}/used`, {
        method: "POST",
        body: "{}",
      });
    }
    UI.closeSheets();
    UI.toast("Positiveに反映しました");
  }

  async function deletePositiveFavorite(favoriteId) {
    if (!favoriteId) return;
    const item = state.promptSheetItems.find((candidate) => String(candidate.id || "") === String(favoriteId || ""));
    const ok = await confirmDanger({
      title: "削除しますか?",
      message: `${promptItemTitle(item)}\n${promptExcerpt(promptItemPrompt(item), 120)}`,
      label: "削除する",
    });
    if (!ok) return;
    const data = await api(`/api/prompts/positive-favorites/${escapePathSegment(favoriteId)}`, {
      method: "DELETE",
    });
    state.promptSheetItems = Array.isArray(data.items) ? data.items : [];
    renderPromptSheet();
    UI.toast(data.removed ? "削除しました" : "見つかりませんでした");
  }

  function recipeAutoName(request) {
    const selectedCharacter = state.slots.character1;
    const character = selectedCharacter?.displayName || (request.character1 === "None" ? "未選択" : request.character1) || "未選択";
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    return `${character || "Random"} / ${request.quality_preset || "standard"} / ${request.width}x${request.height} / ${hh}:${mm}`.slice(0, 60);
  }

  function recipeSummary(request) {
    return [
      request.rating || "safe",
      request.quality_preset || "standard",
      `${request.width || 0}x${request.height || 0}`,
      `${request.steps || 0}steps`,
    ].join(" · ").slice(0, 120);
  }

  function setRecipeListLoading(message) {
    $("#recipeList")?.replaceChildren();
    text("#recipeCountLbl", "-");
    text("#recipeStatus", message);
  }

  function renderRecipes(items = state.recipes) {
    const root = $("#recipeList");
    if (!root) return;
    const recipes = Array.isArray(items) ? items : [];
    root.replaceChildren();
    if (!recipes.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "レシピはまだありません";
      root.appendChild(empty);
    } else {
      for (const item of recipes) {
        const row = document.createElement("div");
        row.style.display = "grid";
        row.style.gridTemplateColumns = "minmax(0, 1fr) auto";
        row.style.alignItems = "stretch";
        row.style.gap = "8px";

        const apply = document.createElement("button");
        apply.type = "button";
        apply.dataset.recipeId = item.id || "";
        apply.style.textAlign = "left";

        const label = document.createElement("span");
        label.textContent = item.name || "Untitled Recipe";

        const summary = document.createElement("span");
        summary.className = "tag";
        summary.textContent = item.summary || "";
        apply.append(label, summary);

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "ghost";
        remove.dataset.recipeDeleteId = item.id || "";
        remove.textContent = "削除";

        row.append(apply, remove);
        root.appendChild(row);
      }
    }
    text("#recipeCountLbl", String(recipes.length));
    text("#recipeStatus", "");
  }

  async function saveRecipe() {
    const request = collectRequest();
    const data = await api("/api/recipes", {
      method: "POST",
      body: JSON.stringify({
        name: recipeAutoName(request),
        summary: recipeSummary(request),
        request,
      }),
    });
    state.recipes = Array.isArray(data.items) ? data.items : state.recipes;
    text("#recipeStatus", "保存しました");
    text("#recipeCountLbl", String(data.count ?? state.recipes.length));
    UI.toast("レシピを保存しました");
    if ($("#recipeSheet")?.classList.contains("is-open")) renderRecipes();
  }

  async function openRecipes() {
    state.recipes = [];
    setRecipeListLoading("読み込み中...");
    UI.openSheet("#recipeSheet");
    const data = await api("/api/recipes");
    state.recipes = Array.isArray(data.items) ? data.items : [];
    renderRecipes();
  }

  async function applyRecipe(recipeId) {
    const item = state.recipes.find((recipe) => String(recipe.id || "") === String(recipeId || ""));
    if (!item || !item.request || typeof item.request !== "object") {
      UI.toast("レシピを適用できませんでした", "error");
      return;
    }
    applyHistoryReuseData(reuseDataFromRequest(item.request));
    UI.closeSheets();
    UI.switchTab("expose");
    UI.toast("レシピを適用しました");
    try {
      const data = await api(`/api/recipes/${escapePathSegment(item.id)}/used`, {
        method: "POST",
        body: "{}",
      });
      if (data.item) {
        state.recipes = state.recipes.map((recipe) => recipe.id === data.item.id ? data.item : recipe);
      }
    } catch (error) {
      console.debug("recipe used update failed", error);
    }
  }

  async function deleteRecipeItem(recipeId) {
    if (!recipeId) return;
    const item = state.recipes.find((recipe) => String(recipe.id || "") === String(recipeId || ""));
    const ok = await confirmDanger({
      title: "削除しますか?",
      message: `${item?.name || "Untitled Recipe"}\n${item?.summary || ""}`,
      label: "削除する",
    });
    if (!ok) return;
    const data = await api(`/api/recipes/${escapePathSegment(recipeId)}`, {
      method: "DELETE",
    });
    if (data.removed) state.recipes = state.recipes.filter((item) => item.id !== recipeId);
    renderRecipes();
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

  function collectFaceDetailerSettings(enabled = checked("#fdEnabled"), mode = "generation") {
    return {
      enabled: Boolean(enabled),
      mode,
      detector: "bbox/face_yolov8m.pt",
      steps: Math.trunc(numberValue("#fdSteps", 12)),
      cfg: numberValue("#fdCfg", 4.0),
      denoise: numberValue("#fdDenoise", 0.3),
      guide_size: 512,
      max_size: 1024,
      bbox_threshold: numberValue("#fdBbox", 0.5),
      bbox_dilation: 10,
      bbox_crop_factor: 3.0,
      sam_enabled: false,
      seed_policy: "image_seed_plus_offset",
      seed_offset: 100000,
    };
  }

  async function queueFrameFaceDetailer() {
    if (!state.detailItem?.id) return;
    text("#frameActionStatus", "顔補正をキュー投入中...");
    const data = await api("/api/face-detailer/postprocess", {
      method: "POST",
      body: JSON.stringify({
        history_id: state.detailItem.id,
        settings: collectFaceDetailerSettings(true, "postprocess"),
      }),
    });
    UI.closeSheets();
    text("#fdStatus", "顔補正をキューに入れました");
    UI.toast("顔補正をキューに入れました");
    UI.safelight("developing", "FACE DETAILING");
    state.pollHadActive = true;
    await loadContact(true);
    if (Array.isArray(data.warnings) && data.warnings.length) {
      UI.toast(data.warnings.slice(0, 2).join(" / "));
    }
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
      button.dataset.characterOriginalName = item.originalDisplayName || "";
      button.dataset.characterKind = item.kind || "";
      button.dataset.characterSource = item.source || "";
      button.dataset.characterPromptTag = item.promptTag || "";
      button.dataset.characterPromptSafeName = item.promptSafeName || "";
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
    applyPromptRandomCollectToForm(settings.prompt_random_collect || {});
    applyWatermark(settings.watermark || {});
    applyHiresFixToForm(settings.hires_fix || {});

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
    fillSelect("#hiresMethod", data.upscale_methods || [], value("#hiresMethod", state.appSettings.hires_fix?.latent_upscale_method || state.appSettings.hires_fix?.upscale_method || "nearest-exact"));
    fillSelect("#hiresModel", data.upscale_models || [], value("#hiresModel", state.appSettings.hires_fix?.upscale_model || ""));
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
    text(
      "#promptRandomSummary",
      req.prompt_random_collect.enabled ? promptRandomOnSummary() : "OFF",
    );
    text("#hiresSummary", req.hires_fix.enabled ? `ON · ×${Number(req.hires_fix.upscale_factor || 1.5)} · ${req.hires_fix.mode || "latent"}` : "OFF");
    text("#i2iSummary", checked("#i2iEnabled") ? `ON · ${req.image_to_image.denoise}` : "OFF");
    const refParts = [];
    if (checked("#outfitEnabled")) refParts.push("OUTFIT");
    if (checked("#poseEnabled")) refParts.push("POSE");
    text("#refModSummary", refParts.length ? refParts.join("+") : "OFF");
    text("#fdSummary", checked("#fdEnabled") ? `ON · ${Number(req.face_detailer.denoise).toFixed(2)}` : "OFF");
    updateSizeChips();
  }

  async function previewPayload() {
    const request = collectRequest();
    if (request.prompt_random_collect?.enabled) text("#promptRandomStatus", "Random Collect中...");
    const data = await api("/api/payload/preview", {
      method: "POST",
      body: JSON.stringify(request),
    });
    if (request.prompt_random_collect?.enabled) text("#promptRandomStatus", "Previewに反映しました");
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

  function contactSearchFieldValue(selector) {
    return String($(selector)?.value || "").trim();
  }

  function collectContactSearchFromUi() {
    return {
      q: contactSearchFieldValue("#contactSearchQ"),
      dateFrom: contactSearchFieldValue("#contactDateFrom"),
      dateTo: contactSearchFieldValue("#contactDateTo"),
      model: contactSearchFieldValue("#contactSearchModel"),
      lora: contactSearchFieldValue("#contactSearchLora"),
      seed: contactSearchFieldValue("#contactSearchSeed"),
      rating: contactSearchFieldValue("#contactSearchRating"),
      hiresMode: contactSearchFieldValue("#contactSearchHires"),
      reference: contactSearchFieldValue("#contactSearchReference"),
      sampler: contactSearchFieldValue("#contactSearchSampler"),
      scheduler: contactSearchFieldValue("#contactSearchScheduler"),
      character: contactSearchFieldValue("#contactSearchCharacter"),
      requestSeq: state.contactSearch?.requestSeq || 0,
    };
  }

  function contactSearchParams() {
    const params = {
      q: state.contactSearch.q,
      date_from: state.contactSearch.dateFrom,
      date_to: state.contactSearch.dateTo,
      model: state.contactSearch.model,
      lora: state.contactSearch.lora,
      seed: state.contactSearch.seed,
      rating: state.contactSearch.rating,
      hires_mode: state.contactSearch.hiresMode,
      reference: state.contactSearch.reference,
      sampler: state.contactSearch.sampler,
      scheduler: state.contactSearch.scheduler,
      character: state.contactSearch.character,
    };
    return Object.fromEntries(Object.entries(params).filter(([, value]) => String(value || "").trim()));
  }

  function hasActiveContactSearch() {
    return Object.keys(contactSearchParams()).length > 0;
  }

  function updateContactSearchStatus(total = state.contactTotal) {
    const badge = $("#contactSearchBadge");
    const status = $("#contactSearchStatus");
    const active = hasActiveContactSearch();
    if (badge) badge.textContent = active ? "適用中" : "";
    if (!status) return;
    status.textContent = active ? `検索結果: ${Number(total || 0)}件` : "";
  }

  function clearContactSearchForm() {
    for (const selector of [
      "#contactSearchQ",
      "#contactDateFrom",
      "#contactDateTo",
      "#contactSearchModel",
      "#contactSearchLora",
      "#contactSearchSeed",
      "#contactSearchRating",
      "#contactSearchHires",
      "#contactSearchReference",
      "#contactSearchSampler",
      "#contactSearchScheduler",
      "#contactSearchCharacter",
    ]) {
      const el = $(selector);
      if (el) el.value = "";
    }
  }

  async function applyContactSearch() {
    state.contactSearch = collectContactSearchFromUi();
    state.contactSearch.requestSeq += 1;
    state.contactLoaded = true;
    state.contactRevision = "";
    return loadContact(true);
  }

  async function clearContactSearch() {
    clearContactSearchForm();
    state.contactSearch = { ...state.contactSearch, ...collectContactSearchFromUi(), requestSeq: (state.contactSearch?.requestSeq || 0) + 1 };
    state.contactRevision = "";
    return loadContact(true);
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
    updateContactSearchStatus();
  }

  function stopContactPolling(message = "") {
    if (state.contactPollTimer) {
      window.clearInterval(state.contactPollTimer);
      state.contactPollTimer = 0;
    }
    state.pollHadActive = false;
    if (message) text("#contactCount", message);
  }

  function handleContactPollingError(error) {
    console.warn(error);
    if (isUnauthorized(error)) {
      stopContactPolling("履歴更新停止: ログイン切れ");
      return;
    }
    state.contactPollFailures += 1;
    if (state.contactPollFailures >= 3) {
      stopContactPolling("履歴更新停止: 通信エラー");
      UI.toast("履歴更新に連続失敗したため自動更新を停止しました", "error");
    }
  }

  function updateContactPolling(activeCount) {
    if (activeCount > 0) {
      state.pollHadActive = true;
      if (!state.contactPollTimer) {
        state.contactPollTimer = window.setInterval(() => {
          loadContact(false, { polling: true, knownRevision: true }).catch(handleContactPollingError);
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
    const seq = state.contactSearch.requestSeq || 0;
    for (const [key, value] of Object.entries(contactSearchParams())) {
      params.set(key, value);
    }
    if (options.knownRevision && state.contactRevision) params.set("known_revision", state.contactRevision);
    const data = await api(`/api/history?${params.toString()}`);
    if (seq !== (state.contactSearch.requestSeq || 0)) return data;
    state.contactPollFailures = 0;
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
    updateContactSearchStatus(state.contactTotal);
    renderContact();
    const activeCount = Number(data.summary?.active ?? state.contactItems.filter(isActiveItem).length);
    updateContactPolling(activeCount);
    return data;
  }

  function queueSheetIsOpen() {
    return Boolean($("#queueSheet")?.classList.contains("is-open"));
  }

  function stopQueuePolling() {
    if (state.queuePollTimer) {
      window.clearInterval(state.queuePollTimer);
      state.queuePollTimer = 0;
    }
  }

  function startQueuePolling() {
    stopQueuePolling();
    state.queuePollTimer = window.setInterval(() => {
      if (!queueSheetIsOpen()) {
        stopQueuePolling();
        return;
      }
      loadQueue(false).catch((error) => {
        text("#queueStatus", errorMessage(error));
      });
    }, 3000);
  }

  function setQueueLoading(message) {
    $("#queueList")?.replaceChildren();
    text("#queueCountLbl", "—");
    text("#queueStatus", message);
  }

  function queuePromptShort(promptId) {
    return String(promptId || "").slice(0, 8) || "unknown";
  }

  function queueRow(item = {}, stateName = "pending") {
    const row = document.createElement("div");
    row.style.display = "grid";
    row.style.gridTemplateColumns = stateName === "pending" ? "minmax(0, 1fr) auto" : "1fr";
    row.style.alignItems = "center";
    row.style.gap = "8px";

    const body = document.createElement("div");
    body.style.display = "flex";
    body.style.alignItems = "center";
    body.style.gap = "8px";
    body.style.minWidth = "0";

    const dot = document.createElement("span");
    dot.className = `queue-dot ${stateName === "running" ? "is-running" : ""}`.trim();
    dot.textContent = stateName === "running" ? "●" : "○";

    const label = document.createElement("span");
    label.textContent = `${stateName === "running" ? "実行中" : `#${item.position || "-"}`} · ${queuePromptShort(item.prompt_id)}`;

    body.append(dot, label);
    if (item.ours) {
      const ours = document.createElement("span");
      ours.className = "tag";
      ours.textContent = "このアプリ";
      body.appendChild(ours);
    }
    row.appendChild(body);

    if (stateName === "pending") {
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "ghost";
      cancel.dataset.queueCancelPromptId = item.prompt_id || "";
      cancel.textContent = "取消";
      row.appendChild(cancel);
    }
    return row;
  }

  function renderQueue(data = {}) {
    const root = $("#queueList");
    if (!root) return;
    const running = Array.isArray(data.running) ? data.running : [];
    const pending = Array.isArray(data.pending) ? data.pending : [];
    root.replaceChildren();
    for (const item of running) root.appendChild(queueRow(item, "running"));
    for (const item of pending) root.appendChild(queueRow(item, "pending"));
    text("#queueCountLbl", `実行中${running.length} · 待機${pending.length}`);
    text("#queueStatus", running.length || pending.length ? "" : "キューは空です");
  }

  async function loadQueue(showLoading = false) {
    if (showLoading) setQueueLoading("読み込み中...");
    const data = await api("/api/queue");
    renderQueue(data);
    return data;
  }

  async function openQueue() {
    UI.openSheet("#queueSheet");
    await loadQueue(true);
    startQueuePolling();
  }

  async function cancelQueuePrompt(promptId) {
    if (!promptId) return;
    const ok = await confirmDanger({
      title: "取消しますか?",
      message: `キュー ${queuePromptShort(promptId)} を取り消します。`,
      label: "取消する",
    });
    if (!ok) return;
    text("#queueStatus", "取消中...");
    await api("/api/queue/cancel", {
      method: "POST",
      body: JSON.stringify({ prompt_id: promptId }),
    });
    UI.toast("取消しました");
    await loadQueue(false);
    await loadContact(true).catch((error) => console.debug("history refresh after queue cancel failed", error));
  }

  async function interruptQueue() {
    const ok = await confirmDanger({
      title: "中断しますか?",
      message: "ComfyUIで実行中の生成を中断します。",
      label: "中断する",
    });
    if (!ok) return;
    text("#queueStatus", "中断を送信中...");
    await api("/api/queue/interrupt", {
      method: "POST",
      body: "{}",
    });
    UI.toast("中断しました");
    await loadQueue(false);
    await loadContact(true).catch((error) => console.debug("history refresh after interrupt failed", error));
  }

  function assertGenerateQueued(data) {
    if (data.status !== "queued" && data.status !== "partial") {
      throw Object.assign(new Error(data.message || "露光できませんでした"), { data });
    }
  }

  function generateQueuedCount(data, request) {
    return Number(data.queued_count || data.items?.length || request.count || 1);
  }

  async function finishGenerateQueued(data, request, options = {}) {
    const queued = generateQueuedCount(data, request);
    const toastMessage = typeof options.toast === "function"
      ? options.toast(queued)
      : options.toast || `${queued}枚 露光しました`;
    const safelightMessage = typeof options.safelight === "function"
      ? options.safelight(queued)
      : options.safelight || `${queued} FRAMES DEVELOPING`;
    UI.toast(toastMessage);
    UI.safelight("developing", safelightMessage);
    state.pollHadActive = true;
    await loadContact(true);
    return queued;
  }

  async function generate() {
    if (!canSubmitGenerateRequest()) return;
    const button = $("#exposeBtn");
    button?.setAttribute("disabled", "disabled");
    try {
      const request = collectRequest();
      if (request.prompt_random_collect?.enabled) {
        text("#promptRandomStatus", "Random Collect中...");
        UI.safelight("developing", "RANDOM COLLECT");
      }
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(request),
      });
      if (request.prompt_random_collect?.enabled) text("#promptRandomStatus", "Random Collectを反映して投入しました");
      assertGenerateQueued(data);
      await finishGenerateQueued(data, request);
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

  function historyRawPositiveText(item = {}) {
    return firstHistoryText(item, [
      "request.positive_prompt",
      "request_data.positive_prompt",
      "positive_prompt",
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
      const response = await fetchWithAuthHandling(imageUrl);
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
    return char.prompt_tag || displayName;
  }

  function historyOfficialLoras(official = {}) {
    return {
      highres: {
        enabled: Boolean(official.highres?.enabled),
        strength: numberFrom(official.highres?.strength, 0.6),
      },
      turbo: {
        enabled: Boolean(official.turbo?.enabled),
        version: "auto",
        strength: numberFrom(official.turbo?.strength, 0.6),
      },
    };
  }

  function historyLoras(loras = []) {
    return (Array.isArray(loras) ? loras : []).filter((lora) => lora && typeof lora === "object").map((lora) => ({
      enabled: true,
      name: loraNameFromItem(lora),
      application: normalizeLoraApplication(lora.application || lora.mode),
      strength_model: numberFrom(lora.strength_model ?? lora.model_strength ?? lora.weight, 1),
      strength_clip: numberFrom(lora.strength_clip ?? lora.clip_strength ?? lora.weight, 1),
    })).filter((lora) => lora.name);
  }

  function historyHiresFixRequest(item = {}) {
    return normalizeHiresFix(item.hires_fix || {});
  }

  function historyImageToImageRequest(item = {}) {
    const image = item.image_to_image && typeof item.image_to_image === "object" ? item.image_to_image : {};
    return {
      enabled: Boolean(image.enabled && image.image_id),
      image_id: String(image.image_id || ""),
      denoise: numberFrom(image.denoise, 0.45),
      resize_mode: String(image.resize_mode || "fit"),
      use_source_size: Boolean(image.use_source_size),
      allow_with_hires_fix: false,
      allow_with_reference_assist: false,
    };
  }

  function historyReferenceModulesRequest(item = {}) {
    const modules = item.reference_modules && typeof item.reference_modules === "object" ? item.reference_modules : {};
    const outfit = modules.outfit && typeof modules.outfit === "object" ? modules.outfit : {};
    const pose = modules.pose && typeof modules.pose === "object" ? modules.pose : {};
    const outfitEnabled = Boolean(outfit.enabled && outfit.image_id);
    const poseEnabled = Boolean(pose.enabled && pose.image_id);
    return {
      enabled: true,
      preset: outfitEnabled && poseEnabled ? "outfit_pose" : outfitEnabled ? "outfit_only" : poseEnabled ? "pose_only" : "off",
      outfit: {
        enabled: outfitEnabled,
        image_id: String(outfit.image_id || ""),
        image_name: String(outfit.image_name || ""),
        strength: numberFrom(outfit.strength, 0.45),
        mode: String(outfit.mode || "image_prompt"),
        strategy: String(outfit.strategy || "ip_adapter"),
        crop_mode: String(outfit.crop_mode || "user_prepared"),
        start_at: numberFrom(outfit.start_at, 0),
        end_at: numberFrom(outfit.end_at, 0.75),
      },
      pose: {
        enabled: poseEnabled,
        image_id: String(pose.image_id || ""),
        image_name: String(pose.image_name || ""),
        mode: String(pose.mode || "pose_image"),
        strength: numberFrom(pose.strength, 0.75),
        strategy: String(pose.strategy || "controlnet_openpose"),
        start_at: numberFrom(pose.start_at, 0),
        end_at: numberFrom(pose.end_at, 0.85),
      },
    };
  }

  function historyFaceDetailerRequest(item = {}) {
    const face = item.face_detailer && typeof item.face_detailer === "object" ? item.face_detailer : {};
    return {
      enabled: Boolean(face.enabled),
      mode: String(face.mode || "generation"),
      detector: String(face.detector || "bbox/face_yolov8m.pt"),
      steps: intFrom(face.steps, 12),
      cfg: numberFrom(face.cfg, 4.0),
      denoise: numberFrom(face.denoise, 0.3),
      guide_size: intFrom(face.guide_size, 512),
      max_size: intFrom(face.max_size, 1024),
      bbox_threshold: numberFrom(face.bbox_threshold, 0.5),
      bbox_dilation: intFrom(face.bbox_dilation, 10),
      bbox_crop_factor: numberFrom(face.bbox_crop_factor, 3.0),
      sam_enabled: Boolean(face.sam_enabled),
      seed_policy: String(face.seed_policy || "image_seed_plus_offset"),
      seed_offset: intFrom(face.seed_offset, 100000),
    };
  }

  const HISTORY_QUALITY_PROMPTS = {
    standard: "masterpiece, best quality, score_7",
    high: "masterpiece, best quality, high quality, highly detailed, score_8, score_7",
    character_check: "best quality, clean character design, clear face, full body",
  };
  const HISTORY_RATING_TAGS = {
    safe: "safe",
    sensitive: "sensitive",
    nsfw: "nsfw",
    explicit: "explicit",
  };
  function promptTerms(textValue) {
    return String(textValue || "").split(/,|\n/).map((term) => term.trim()).filter(Boolean);
  }

  function normalizePromptTerm(term) {
    return String(term || "").replace(/\s+/g, " ").trim().toLowerCase();
  }

  function historyPromptRandomGeneratedParts(item = {}) {
    const candidates = [
      item.prompt_random_collect,
      item.request_data?.prompt_random_collect,
      item.request?.prompt_random_collect,
    ];
    const parts = [];
    for (const candidate of candidates) {
      const data = candidate && typeof candidate === "object" ? candidate : {};
      const generatedItem = data.generated_item && typeof data.generated_item === "object" ? data.generated_item : {};
      if (typeof data.generated_tags === "string" && data.generated_tags.trim()) parts.push(data.generated_tags);
      if (typeof generatedItem.tags === "string" && generatedItem.tags.trim()) parts.push(generatedItem.tags);
    }
    return parts;
  }

  function appendUniquePromptTerms(baseText, extraParts = []) {
    const terms = promptTerms(baseText);
    const seen = new Set(terms.map(normalizePromptTerm).filter(Boolean));
    for (const part of extraParts || []) {
      for (const term of promptTerms(part)) {
        const normalized = normalizePromptTerm(term);
        if (!normalized || seen.has(normalized)) continue;
        seen.add(normalized);
        terms.push(term);
      }
    }
    return terms.join(", ");
  }

  const HISTORY_GENERIC_AUTO_TERMS = new Set(
    [
      ...Object.values(HISTORY_QUALITY_PROMPTS).flatMap(promptTerms),
      ...Object.values(HISTORY_RATING_TAGS),
      "anime illustration",
    ].map(normalizePromptTerm).filter(Boolean),
  );
  const HISTORY_AUTO_BLOCK_START_TERMS = new Set([
    "masterpiece",
    "best quality",
    "anime illustration",
    "score_7",
    "score_8",
    "score_9",
  ]);

  function isHistoryPeopleTag(term) {
    return /^\d+\s*(?:girl|girls|boy|boys)$/i.test(normalizePromptTerm(term));
  }

  function isGeneratedNaturalDescriptionTerm(term) {
    return /^an anime illustration of .+ in a clean, expressive composition\.?$/i.test(normalizePromptTerm(term));
  }

  function isGeneratedNaturalDescriptionStart(term) {
    return /^an anime illustration of .+ in a clean$/i.test(normalizePromptTerm(term));
  }

  function isGeneratedNaturalDescriptionEnd(term) {
    return /^expressive composition\.?$/i.test(normalizePromptTerm(term));
  }

  function generatedNaturalEndIndex(terms, index) {
    if (isGeneratedNaturalDescriptionTerm(terms[index])) return index;
    if (isGeneratedNaturalDescriptionStart(terms[index]) && isGeneratedNaturalDescriptionEnd(terms[index + 1])) return index + 1;
    return -1;
  }

  function stripHistoryGeneratedBlocks(terms = []) {
    const kept = [];
    for (let index = 0; index < terms.length; index += 1) {
      const term = terms[index];
      const normalized = normalizePromptTerm(term);
      if (HISTORY_AUTO_BLOCK_START_TERMS.has(normalized)) {
        const limit = Math.min(terms.length, index + 64);
        let endIndex = -1;
        for (let cursor = index; cursor < limit; cursor += 1) {
          const naturalEnd = generatedNaturalEndIndex(terms, cursor);
          if (naturalEnd >= 0) {
            endIndex = naturalEnd;
            break;
          }
        }
        if (endIndex >= 0) {
          index = endIndex;
          continue;
        }
      }
      kept.push(term);
    }
    return kept;
  }

  function stripGeneratedNaturalFragments(terms = []) {
    const kept = [];
    for (let index = 0; index < terms.length; index += 1) {
      const term = terms[index];
      const naturalEnd = generatedNaturalEndIndex(terms, index);
      if (naturalEnd >= 0) {
        if (kept.length) kept.pop();
        index = naturalEnd;
        continue;
      }
      if (isGeneratedNaturalDescriptionEnd(term)) continue;
      kept.push(term);
    }
    return kept;
  }

  function escapeHistoryCharacterTag(tag) {
    return String(tag || "").replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
  }

  function inferHistoryQualityPreset(item = {}) {
    if (item.quality_preset) return item.quality_preset;
    const terms = new Set(promptTerms(historyPositiveText(item)).map(normalizePromptTerm));
    if (terms.has("clean character design") || terms.has("clear face") || terms.has("full body")) return "character_check";
    if (terms.has("score_8") || terms.has("high quality") || terms.has("highly detailed")) return "high";
    return "standard";
  }

  function historyGeneratedPositiveParts(item = {}, qualityPreset = "standard") {
    const parts = [
      HISTORY_QUALITY_PROMPTS[qualityPreset] || HISTORY_QUALITY_PROMPTS.standard,
      item.meta_prompt || "anime illustration",
      item.year_prompt || "",
      HISTORY_RATING_TAGS[item.rating || "safe"] || "safe",
      item.common || "",
      item.outfit_prompt || "",
      item.expression_prompt || "",
      item.pose_prompt || "",
      item.background_prompt || "",
      item.camera_prompt || "",
      item.lighting_prompt || "",
      item.natural_description || "",
    ];
    const characters = Array.isArray(item.characters) ? item.characters : [];
    const characterCount = characters.length;
    if (characterCount === 1) parts.push("1girl");
    if (characterCount > 1) parts.push(`${characterCount}girls`);
    for (const char of characters) {
      if (!char || typeof char !== "object") continue;
      parts.push(char.prompt_tag || "");
      parts.push(escapeHistoryCharacterTag(char.prompt_tag || ""));
      parts.push(char.identity_prompt || "");
      parts.push(char.prompt_safe_name || "");
    }
    parts.push(item.natural_description || "");
    return parts;
  }

  function stripGeneratedHistoryPositive(item = {}, qualityPreset = "standard") {
    const positive = historyPositiveText(item);
    if (!positive) return "";
    const rawPositive = historyRawPositiveText(item);
    if (rawPositive) return appendUniquePromptTerms(rawPositive, historyPromptRandomGeneratedParts(item));
    const generated = new Set(
      historyGeneratedPositiveParts(item, qualityPreset)
        .flatMap(promptTerms)
        .map(normalizePromptTerm)
        .filter(Boolean),
    );
    const terms = stripGeneratedNaturalFragments(
      stripHistoryGeneratedBlocks(promptTerms(positive))
        .filter((term) => {
          const normalized = normalizePromptTerm(term);
          return !generated.has(normalized) && !HISTORY_GENERIC_AUTO_TERMS.has(normalized) && !isHistoryPeopleTag(term);
        }),
    );
    return terms.join(", ");
  }

  function historyReuseData(item = {}) {
    const slots = { character1: null, character2: null, character3: null, original: null };
    for (const char of item.characters || []) {
      const slotNumber = Number(char.slot || 0);
      const slotName = slotNumber === 1 ? "character1" : slotNumber === 2 ? "character2" : slotNumber === 3 ? "character3" : slotNumber === 4 ? "original" : "";
      if (!slotName) continue;
      const normalized = normalizeCharacterItem({
        ...char,
        source: sourceForCharacter(char),
        kind: sourceForCharacter(char) === "original_character" ? "original" : "wai",
      });
      slots[slotName] = { ...normalized, value: historyCharacterValue(char, slotName) };
    }
    const qualityPreset = inferHistoryQualityPreset(item);
    return {
      slots,
      rating: item.rating || "safe",
      quality_preset: qualityPreset,
      meta_prompt: item.meta_prompt || "anime illustration",
      year_prompt: item.year_prompt || "",
      outfit_prompt: item.outfit_prompt || "",
      expression_prompt: item.expression_prompt || "",
      pose_prompt: item.pose_prompt || "",
      background_prompt: item.background_prompt || "",
      lighting_prompt: item.lighting_prompt || "",
      camera_prompt: item.camera_prompt || "",
      positive_prompt: stripGeneratedHistoryPositive(item, qualityPreset),
      negative_prompt: historyNegativeText(item),
      negative_prompt_mode: "custom",
      negative_preset: item.negative_preset || "anima_recommended",
      prompt_ban: item.prompt_ban || "",
      natural_description: item.natural_description || "",
      model: item.model || state.defaults.model || "",
      width: numberFrom(item.width, 1024),
      height: numberFrom(item.height, 1536),
      steps: intFrom(item.steps, 32),
      cfg: numberFrom(item.cfg, 4.5),
      shift: numberFrom(item.shift ?? item.model_sampling?.shift, numberFrom(state.defaults.shift, 4)),
      sampler: item.sampler || state.defaults.sampler || "er_sde",
      scheduler: item.scheduler || state.defaults.scheduler || "simple",
      seed: intFrom(item.seed, -1),
      seed_mode: "fixed",
      official_loras: historyOfficialLoras(item.official_loras || {}),
      loras: historyLoras(item.loras || []),
      dynamic_prompt: { enabled: false },
      prompt_random_collect: { ...historyPromptRandomCollect(item.prompt_random_collect), enabled: false },
      hires_fix: historyHiresFixRequest(item),
      image_to_image: historyImageToImageRequest(item),
      reference_modules: historyReferenceModulesRequest(item),
      face_detailer: historyFaceDetailerRequest(item),
      source_item: item,
    };
  }

  function applyHistoryReuseData(data) {
    state.slots = {
      character1: data.slots.character1,
      character2: data.slots.character2,
      character3: data.slots.character3,
      original: data.slots.original,
    };
    renderSlots();
    UI.setSegValue("#ratingSeg", "rating", data.rating);
    UI.setSegValue("#qualitySeg", "quality", data.quality_preset);
    setValue("#metaPrompt", data.meta_prompt);
    setValue("#yearPrompt", data.year_prompt);
    setValue("#outfitPrompt", data.outfit_prompt);
    setValue("#expressionPrompt", data.expression_prompt);
    setValue("#posePrompt", data.pose_prompt);
    setValue("#backgroundPrompt", data.background_prompt);
    setValue("#cameraPrompt", data.camera_prompt);
    setValue("#lightingPrompt", data.lighting_prompt);
    setValue("#positivePrompt", data.positive_prompt);
    setValue("#negativePrompt", data.negative_prompt);
    setValue("#negativeMode", data.negative_prompt_mode);
    setValue("#negativePreset", data.negative_preset);
    setValue("#promptBan", data.prompt_ban);
    setValue("#naturalDescription", data.natural_description);
    setValue("#modelSelect", data.model);
    setValue("#widthInput", data.width);
    setValue("#heightInput", data.height);
    setValue("#stepsInput", data.steps);
    setValue("#cfgInput", data.cfg);
    setValue("#shiftInput", data.shift);
    setValue("#samplerSelect", data.sampler);
    setValue("#schedulerSelect", data.scheduler);
    setValue("#seedInput", data.seed);
    setValue("#seedModeSelect", data.seed_mode);
    setChecked("#officialHighresEnabled", data.official_loras.highres.enabled);
    setValue("#officialHighresStrength", data.official_loras.highres.strength);
    setChecked("#officialTurboEnabled", data.official_loras.turbo.enabled);
    setValue("#officialTurboStrength", data.official_loras.turbo.strength);
    $("#loraSlots")?.replaceChildren();
    for (const lora of data.loras || []) addLoraRow(lora);
    setChecked("#dynamicEnabled", Boolean(data.dynamic_prompt?.enabled));
    applyPromptRandomCollectToForm(data.prompt_random_collect || {});
    applyHiresFixToForm(data.hires_fix || {});

    const i2i = data.image_to_image || {};
    const i2iImageId = i2i.enabled ? String(i2i.image_id || "") : "";
    state.i2i = { imageId: i2iImageId, thumb: "", name: String(i2i.image_name || i2iImageId || "") };
    setChecked("#i2iEnabled", Boolean(i2iImageId));
    setValue("#i2iDenoise", i2i.denoise ?? 0.45);
    setValue("#i2iResize", i2i.resize_mode || "fit");
    setChecked("#i2iUseSource", Boolean(i2i.use_source_size));
    renderI2iPreview();

    const modules = data.reference_modules || {};
    const outfit = modules.outfit || {};
    const pose = modules.pose || {};
    const outfitImageId = outfit.enabled ? String(outfit.image_id || "") : "";
    const poseImageId = pose.enabled ? String(pose.image_id || "") : "";
    state.refmod.outfit = { imageId: outfitImageId, thumb: "", name: String(outfit.image_name || outfitImageId || "") };
    state.refmod.pose = { imageId: poseImageId, thumb: "", name: String(pose.image_name || poseImageId || "") };
    setChecked("#outfitEnabled", Boolean(outfitImageId));
    setValue("#outfitStrength", outfit.strength ?? 0.45);
    setValue("#outfitStart", outfit.start_at ?? 0);
    setValue("#outfitEnd", outfit.end_at ?? 0.75);
    setChecked("#poseEnabled", Boolean(poseImageId));
    setValue("#poseMode", pose.mode || "pose_image");
    setValue("#poseStrength", pose.strength ?? 0.75);
    setValue("#poseStart", pose.start_at ?? 0);
    setValue("#poseEnd", pose.end_at ?? 0.85);
    renderRefmodPreviews();

    const face = data.face_detailer || {};
    setChecked("#fdEnabled", Boolean(face.enabled));
    setValue("#fdSteps", face.steps ?? 12);
    setValue("#fdCfg", face.cfg ?? 4.0);
    setValue("#fdDenoise", face.denoise ?? 0.3);
    setValue("#fdBbox", face.bbox_threshold ?? 0.5);
    updateSummaries();
  }

  function slotRequestValueFromData(data, slotName) {
    const item = data.slots[slotName];
    if (item?.value) return item.value;
    return "None";
  }

  function slotItemFromRequest(slotName, rawValue) {
    const raw = String(rawValue || "").trim();
    if (!raw || raw === "None") return null;
    if (raw.toLowerCase() === "random") return randomSlotItem(slotName);
    const original = slotName === "original";
    const display = raw.startsWith("original:") ? raw.slice("original:".length) : raw;
    return {
      source: original ? "original_character" : "wai_characters",
      id: display,
      displayName: display,
      originalDisplayName: display,
      promptTag: "",
      kind: original ? "original" : "wai",
      value: raw,
    };
  }

  function historyPromptRandomCollect(raw = {}) {
    const data = raw && typeof raw === "object" ? raw : {};
    const defaults = defaultPromptRandomCollect();
    return {
      enabled: Boolean(data.enabled),
      instruction: data.instruction || defaults.instruction,
      strength: data.strength || defaults.strength,
      include_characters: data.include_characters !== false,
    };
  }

  function reuseDataFromRequest(request = {}) {
    const req = request && typeof request === "object" ? request : {};
    const defaultPositive = state.appSettings.default_positive_prompt ?? state.defaults.positive_prompt ?? "";
    const defaultNegative = state.appSettings.default_negative_prompt ?? state.defaults.negative_prompt ?? "";
    return {
      slots: {
        character1: slotItemFromRequest("character1", req.character1 ?? "None"),
        character2: slotItemFromRequest("character2", req.character2 ?? "None"),
        character3: slotItemFromRequest("character3", req.character3 ?? "None"),
        original: slotItemFromRequest("original", req.original_character ?? "None"),
      },
      rating: req.rating || state.appSettings.rating || "safe",
      quality_preset: req.quality_preset || state.appSettings.quality_preset || "standard",
      meta_prompt: req.meta_prompt ?? state.appSettings.meta_prompt ?? "anime illustration",
      year_prompt: req.year_prompt ?? state.appSettings.year_prompt ?? "",
      outfit_prompt: req.outfit_prompt ?? state.appSettings.outfit_prompt ?? "",
      expression_prompt: req.expression_prompt ?? state.appSettings.expression_prompt ?? "",
      pose_prompt: req.pose_prompt ?? state.appSettings.pose_prompt ?? "",
      background_prompt: req.background_prompt ?? state.appSettings.background_prompt ?? "",
      lighting_prompt: req.lighting_prompt ?? state.appSettings.lighting_prompt ?? "",
      camera_prompt: req.camera_prompt ?? state.appSettings.camera_prompt ?? "",
      positive_prompt: req.positive_prompt ?? defaultPositive,
      negative_prompt: req.negative_prompt_raw ?? req.negative_prompt ?? defaultNegative,
      negative_prompt_mode: req.negative_prompt_mode || state.appSettings.negative_prompt_mode || "append",
      negative_preset: req.negative_preset || state.appSettings.negative_preset || "anima_recommended",
      prompt_ban: req.prompt_ban ?? "",
      natural_description: req.natural_description ?? state.appSettings.natural_description ?? "",
      model: req.model || state.appSettings.model || state.defaults.model || "",
      width: numberFrom(req.width, numberFrom(state.appSettings.width ?? state.defaults.width, 1024)),
      height: numberFrom(req.height, numberFrom(state.appSettings.height ?? state.defaults.height, 1536)),
      steps: intFrom(req.steps, intFrom(state.appSettings.steps ?? state.defaults.steps, 32)),
      cfg: numberFrom(req.cfg, numberFrom(state.appSettings.cfg ?? state.defaults.cfg, 4.5)),
      shift: numberFrom(req.shift, numberFrom(state.appSettings.shift ?? state.defaults.shift, 4)),
      sampler: req.sampler || state.appSettings.sampler || state.defaults.sampler || "er_sde",
      scheduler: req.scheduler || state.appSettings.scheduler || state.defaults.scheduler || "simple",
      seed: intFrom(req.seed, intFrom(state.appSettings.seed ?? state.defaults.seed, -1)),
      seed_mode: req.seed_mode || state.appSettings.seed_mode || "fixed",
      official_loras: historyOfficialLoras(req.official_loras || {}),
      loras: historyLoras(req.loras || []),
      dynamic_prompt: req.dynamic_prompt && typeof req.dynamic_prompt === "object" ? req.dynamic_prompt : { enabled: false },
      prompt_random_collect: historyPromptRandomCollect(req.prompt_random_collect),
      hires_fix: historyHiresFixRequest({ hires_fix: req.hires_fix }),
      image_to_image: historyImageToImageRequest({ image_to_image: req.image_to_image }),
      reference_modules: historyReferenceModulesRequest({ reference_modules: req.reference_modules }),
      face_detailer: historyFaceDetailerRequest({ face_detailer: req.face_detailer }),
      source_item: req,
    };
  }

  function historyRequestFromItem(item = {}) {
    const data = historyReuseData(item);
    return {
      workflow_mode: data.hires_fix.enabled ? "anima_mobile_extended" : "anima",
      character1: slotRequestValueFromData(data, "character1"),
      character2: slotRequestValueFromData(data, "character2"),
      character3: slotRequestValueFromData(data, "character3"),
      original_character: slotRequestValueFromData(data, "original"),
      character1_weight: 1.0,
      character2_weight: 1.0,
      character3_weight: 1.0,
      original_weight: 1.0,
      character1_role: "main",
      character2_role: "left",
      character3_role: "right",
      rating: data.rating,
      quality_preset: data.quality_preset,
      meta_prompt: item.meta_prompt || "anime illustration",
      year_prompt: item.year_prompt || "",
      outfit_prompt: item.outfit_prompt || "",
      expression_prompt: item.expression_prompt || "",
      pose_prompt: item.pose_prompt || "",
      background_prompt: item.background_prompt || "",
      lighting_prompt: item.lighting_prompt || "",
      camera_prompt: item.camera_prompt || "",
      natural_description: data.natural_description,
      positive_prompt: data.positive_prompt,
      negative_prompt: data.negative_prompt,
      negative_prompt_raw: data.negative_prompt,
      negative_prompt_mode: data.negative_prompt_mode,
      negative_preset: data.negative_preset,
      prompt_ban: item.prompt_ban || "",
      common_prompt: item.common || "",
      model: data.model,
      text_encoder: state.appSettings.text_encoder || state.defaults.text_encoder || "qwen_3_06b_base.safetensors",
      vae: state.appSettings.vae || state.defaults.vae || "qwen_image_vae.safetensors",
      width: data.width,
      height: data.height,
      steps: data.steps,
      cfg: data.cfg,
      shift: data.shift,
      sampler: data.sampler,
      scheduler: data.scheduler,
      seed: data.seed,
      seed_mode: data.seed_mode,
      official_loras: data.official_loras,
      loras: data.loras,
      count: 1,
      wait: false,
      dynamic_prompt: { enabled: false },
      prompt_random_collect: historyPromptRandomCollect(data.prompt_random_collect),
      hires_fix: data.hires_fix,
      reference_assist: { enabled: false },
      image_to_image: historyImageToImageRequest(item),
      face_detailer: historyFaceDetailerRequest(item),
      reference_modules: historyReferenceModulesRequest(item),
    };
  }

  function applyHistoryToForm(item) {
    applyHistoryReuseData(historyReuseData(item));
    UI.closeSheets();
    UI.switchTab("expose");
    UI.toast("設定を再利用しました");
  }

  async function generateFrameVariations() {
    if (!state.detailItem?.id) return;
    const count = selectedVariationCount();
    const request = {
      ...historyRequestFromItem(state.detailItem),
      seed_mode: "random",
      seed: -1,
      count,
      wait: false,
    };
    try {
      text("#frameActionStatus", "バリエーションをキュー投入中...");
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(request),
      });
      assertGenerateQueued(data);
      UI.closeSheets();
      await finishGenerateQueued(data, request, {
        toast: (queued) => `🎲 ${queued}枚キューに入れました`,
      });
    } catch (error) {
      text("#frameActionStatus", errorMessage(error));
      UI.toast(errorMessage(error), "error");
    }
  }

  function settingsFromForm() {
    const next = clone(state.appSettings);
    const hiresFix = collectHiresFix();
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
      prompt_random_collect: collectPromptRandomCollect(),
      hires_fix: hiresFix,
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

    const modelResult = await Promise.allSettled([loadModels(false), loadLoraCatalog()]);
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
    renderConfiguredLoras(state.appSettings);
    const optionalResults = await Promise.allSettled([
      loadFavorites(),
      searchCharacters(),
      loadContact(true),
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

  async function handleAction(action, target) {
    if (action === "login") return login();
    if (action === "random-slot") return setRandomSlot();
    if (action === "clear-slot") return clearSlot();
    if (action === "toggle-character-favorites") return toggleCharacterFavorites();
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
    if (action === "prompt-convert") return convertPromptFromJapanese();
    if (action === "prompt-converter-status") return loadPromptConverterStatus(true);
    if (action === "prompt-random-status") return loadPromptRandomStatus(true);
    if (action === "save-positive-fav") return savePositiveFavorite();
    if (action === "open-positive-favs") return openPositiveFavorites();
    if (action === "open-templates") return openPositiveTemplates();
    if (action === "save-recipe") return saveRecipe();
    if (action === "open-recipes") return openRecipes();
    if (action === "open-queue") return openQueue();
    if (action === "queue-refresh") return loadQueue(true);
    if (action === "queue-interrupt") return interruptQueue();
    if (action === "load-more") return loadContact(false);
    if (action === "contact-search") return applyContactSearch();
    if (action === "contact-search-clear") return clearContactSearch();
    if (action === "frame-favorite") return toggleFrameFavorite();
    if (action === "frame-public-save") return savePublicImage();
    if (action === "frame-share") return shareFrame();
    if (action === "frame-variations") return generateFrameVariations();
    if (action === "frame-reuse") {
      if (state.detailItem) applyHistoryToForm(state.detailItem);
      return;
    }
    if (action === "frame-to-i2i") return setFrameAsI2iSource();
    if (action === "frame-face-detail") return queueFrameFaceDetailer();
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

    $("details[data-fold='prompt-converter']")?.addEventListener("toggle", (event) => {
      if (event.target.open) {
        loadPromptConverterStatus().catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    $("details[data-fold='prompt-random']")?.addEventListener("toggle", (event) => {
      if (event.target.open) {
        loadPromptRandomStatus().catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    $("#promptRandomEnabled")?.addEventListener("change", updateSummaries);
    $("#promptRandomIncludeCharacters")?.addEventListener("change", updateSummaries);
    $("#promptRandomInstruction")?.addEventListener("input", updateSummaries);
    $("#promptRandomStrength")?.addEventListener("change", updateSummaries);

    $("#dictQuery")?.addEventListener("input", schedulePromptDictionarySearch);

    $("#promptConvertSource")?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || (!event.ctrlKey && !event.metaKey)) return;
      event.preventDefault();
      convertPromptFromJapanese().catch((error) => {
        text("#promptConverterStatus", errorMessage(error));
        UI.toast(errorMessage(error), "error");
      });
    });

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

    $("#recipeList")?.addEventListener("click", (event) => {
      const deleteTarget = event.target.closest("[data-recipe-delete-id]");
      if (deleteTarget) {
        event.preventDefault();
        deleteRecipeItem(deleteTarget.dataset.recipeDeleteId).catch((error) => {
          text("#recipeStatus", errorMessage(error));
          UI.toast(errorMessage(error), "error");
        });
        return;
      }
      const row = event.target.closest("[data-recipe-id]");
      if (!row) return;
      applyRecipe(row.dataset.recipeId).catch((error) => {
        text("#recipeStatus", errorMessage(error));
        UI.toast(errorMessage(error), "error");
      });
    });

    $("#queueList")?.addEventListener("click", (event) => {
      const cancelTarget = event.target.closest("[data-queue-cancel-prompt-id]");
      if (!cancelTarget) return;
      cancelQueuePrompt(cancelTarget.dataset.queueCancelPromptId).catch((error) => {
        text("#queueStatus", errorMessage(error));
        UI.toast(errorMessage(error), "error");
      });
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

    $("#contactSearchPanel")?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const target = event.target;
      if (!target?.matches?.("input, select")) return;
      event.preventDefault();
      applyContactSearch().catch((error) => UI.toast(errorMessage(error), "error"));
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
          display_name_ja: favorite.dataset.favoriteDisplayName,
          prompt_tag: favorite.dataset.favoritePromptTag,
          prompt_safe_name: favorite.dataset.favoritePromptSafeName,
        });
        markFavoriteUsedWithRetry(favorite.dataset.favoriteSource, favorite.dataset.favoriteId);
        clearCharacterSearch();
        UI.toast(`${favorite.dataset.favoriteDisplayName || favorite.dataset.favoriteName} を反映しました`);
        return;
      }

      const result = event.target.closest("[data-character-id]");
      if (result) {
        applyCharacterToSlot({
          source: result.dataset.characterSource,
          id: result.dataset.characterId,
          display_name: result.dataset.characterOriginalName || result.dataset.characterName,
          display_name_ja: result.dataset.characterName,
          kind: result.dataset.characterKind,
          prompt_tag: result.dataset.characterPromptTag,
          prompt_safe_name: result.dataset.characterPromptSafeName,
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
      if (action === "close-sheet") {
        stopQueuePolling();
        return;
      }
      handleAction(action, actionTarget).catch((error) => {
        UI.toast(errorMessage(error), "error");
        if (action?.startsWith("frame-")) text("#frameActionStatus", errorMessage(error));
        if (action?.startsWith("i2i-")) text("#i2iStatus", errorMessage(error));
        if (action?.startsWith("outfit-") || action?.startsWith("pose-")) text("#refModStatus", errorMessage(error));
        if (action?.startsWith("prompt-convert")) text("#promptConverterStatus", errorMessage(error));
        if (action?.startsWith("prompt-random")) text("#promptRandomStatus", errorMessage(error));
        if (["save-defaults", "reset-defaults", "reload-models"].includes(action)) text("#settingsStatus", errorMessage(error));
        if (["save-recipe", "open-recipes"].includes(action)) text("#recipeStatus", errorMessage(error));
        if (["open-queue", "queue-refresh", "queue-interrupt"].includes(action)) text("#queueStatus", errorMessage(error));
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") stopQueuePolling();
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
