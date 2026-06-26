import {
  $,
  $$,
  escapePathSegment,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.53-compact-generation-settings-20260626";
import { CHARACTER_FAVORITES_COLLAPSED_KEY, storeBoolean } from "./state.js?v=v1.53-compact-generation-settings-20260626";

const EMPTY_SLOT_LABELS = {
  character1: "未選択",
  character2: "未選択",
  character3: "未選択",
  original: "未選択",
};

export function createCharacterFeature({
  api,
  state,
  UI = window.UI,
  errorMessage = (error) => error?.message || String(error),
  updateSummaries = () => {},
} = {}) {
  function slotRequestValue(slotName) {
    const item = state.slots[slotName];
    if (item?.value) return item.value;
    return "None";
  }

  function sourceForCharacter(item) {
    const source = String(item?.source || "");
    if (source === "original_character" || item?.kind === "original") return "original_character";
    return "wai_characters";
  }

  function containsCjkText(textValue) {
    return /[\u3400-\u9fff\uf900-\ufaff]/.test(String(textValue || ""));
  }

  function containsKanaText(textValue) {
    return /[\u3040-\u30ff]/.test(String(textValue || ""));
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
    const promptTag = String(raw.prompt_tag || raw.promptTag || "").trim();
    const promptSafeName = String(raw.prompt_safe_name || raw.promptSafeName || "").trim();
    const fallbackDisplayName = String(raw.displayName || originalDisplayName).trim();
    const legacyCjkDisplay = source !== "original_character" && promptSafeName && containsCjkText(fallbackDisplayName) && !containsKanaText(fallbackDisplayName);
    const displayName = localizedDisplayName || (legacyCjkDisplay ? promptSafeName : fallbackDisplayName) || promptSafeName || promptTag;
    const id = String(raw.id || originalDisplayName || displayName).trim();
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
    const textValueString = String(textValue || "").replace(/\s+/g, " ").trim();
    const limit = 18;
    if (textValueString.length <= limit) return textValueString;
    return `${textValueString.slice(0, limit)}...`;
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

  function applySlots(slots = {}) {
    state.slots = {
      character1: slots.character1 || null,
      character2: slots.character2 || null,
      character3: slots.character3 || null,
      original: slots.original || null,
    };
    renderSlots();
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
    storeBoolean(CHARACTER_FAVORITES_COLLAPSED_KEY, state.characterFavoritesCollapsed);
    renderFavorites();
  }

  function renderCharacterResults(items, meta = {}) {
    const root = $("#charResults");
    if (!root) return;
    root.replaceChildren();
    const total = Number(meta.total ?? items.length);
    const shown = Number(meta.shown ?? items.length);
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "見つかりません";
      root.appendChild(empty);
      return;
    }
    const summary = document.createElement("p");
    summary.className = "hint";
    summary.textContent = total > shown ? `${shown} / ${total} 件を表示` : `${total} 件`;
    root.appendChild(summary);
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
    if (meta.hasMore) {
      const more = document.createElement("button");
      more.type = "button";
      more.dataset.action = "load-more-characters";
      more.textContent = `もっと見る (${Math.max(0, total - shown)}件)`;
      root.appendChild(more);
    }
  }

  function clearCharacterSearch() {
    setValue("#charSearch", "");
    state.characterSearch = { query: "", items: [], total: 0, offset: 0, limit: 60, hasMore: false };
    $("#charResults")?.replaceChildren();
  }

  async function searchCharacters({ append = false } = {}) {
    const query = value("#charSearch", "").trim();
    if (!query) {
      state.characterSearch = { query: "", items: [], total: 0, offset: 0, limit: 60, hasMore: false };
      $("#charResults")?.replaceChildren();
      return;
    }
    const limit = state.characterSearch.limit || 60;
    const offset = append && state.characterSearch.query === query ? state.characterSearch.items.length : 0;
    const data = await api(`/api/catalog?q=${encodeURIComponent(query)}&kind=all&limit=${limit}&offset=${offset}`);
    if (value("#charSearch", "").trim() !== query) return;
    const newItems = Array.isArray(data.items) ? data.items : [];
    const items = append && state.characterSearch.query === query ? [...state.characterSearch.items, ...newItems] : newItems;
    state.characterSearch = {
      query,
      items,
      total: Number(data.total ?? items.length),
      offset: Number(data.offset ?? offset),
      limit: Number(data.limit ?? limit),
      hasMore: Boolean(data.has_more),
    };
    renderCharacterResults(items, {
      total: state.characterSearch.total,
      shown: items.length,
      hasMore: state.characterSearch.hasMore,
    });
  }

  async function loadMoreCharacters() {
    if (!state.characterSearch.hasMore) return;
    await searchCharacters({ append: true });
  }

  function scheduleCharacterSearch() {
    window.clearTimeout(state.characterSearchTimer);
    state.characterSearchTimer = window.setTimeout(() => {
      searchCharacters().catch((error) => UI.toast(errorMessage(error), "error"));
    }, 250);
  }

  function historyCharacterValue(char, targetSlot) {
    if (!char || typeof char !== "object") return "";
    const source = sourceForCharacter(char);
    const displayName = char.display_name || char.name || char.id || "";
    if (targetSlot === "original") return char.id || displayName;
    if (source === "original_character") return `original:${char.id || displayName}`;
    return char.prompt_tag || displayName;
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
    const displayName = !original && containsCjkText(display) && !containsKanaText(display) ? "Legacy character" : display;
    return {
      source: original ? "original_character" : "wai_characters",
      id: display,
      displayName,
      originalDisplayName: display,
      promptTag: "",
      kind: original ? "original" : "wai",
      value: raw,
    };
  }

  function bindEvents() {
    $("#charSearch")?.addEventListener("input", scheduleCharacterSearch);

    $("#charSlots")?.addEventListener("click", (event) => {
      const slot = event.target.closest(".slot[data-slot]");
      if (!slot) return;
      state.armedSlot = slot.dataset.slot;
      renderSlots();
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
      }
    });
  }

  return {
    normalizeCharacterItem,
    sourceForCharacter,
    containsCjkText,
    containsKanaText,
    isRandomSlotItem,
    randomSlotItem,
    slotRequestValue,
    slotRequestValueFromData,
    slotItemFromRequest,
    historyCharacterValue,
    applyCharacterToSlot,
    applySlots,
    clearSlot,
    setRandomSlot,
    renderSlots,
    renderCharacterResults,
    clearCharacterSearch,
    searchCharacters,
    scheduleCharacterSearch,
    loadMoreCharacters,
    loadFavorites,
    renderFavorites,
    toggleFavoriteForArmedSlot,
    markFavoriteUsedWithRetry,
    toggleCharacterFavorites,
    bindEvents,
    actions: {
      "random-slot": () => setRandomSlot(),
      "clear-slot": () => clearSlot(),
      "toggle-character-favorites": () => toggleCharacterFavorites(),
      "load-more-characters": () => loadMoreCharacters(),
      "toggle-favorite-slot": () => toggleFavoriteForArmedSlot(),
    },
  };
}
