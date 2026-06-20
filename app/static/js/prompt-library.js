import {
  $,
  escapePathSegment,
  numberValue,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.36-main-shell-cleanup-20260620";

const SCORE_TAG_RE = /^[([{]*score_\d+(?:_up)?(?::[0-9.]+)?[\])}]*$/i;

export function createPromptLibraryFeature({
  api,
  state,
  UI = window.UI,
  errorMessage = (error) => error?.message || String(error),
  confirmDanger = async () => false,
  updateSummaries = () => {},
  collectRequest = () => ({}),
  applyHistoryReuseData = () => {},
  reuseDataFromRequest = () => ({}),
} = {}) {
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

    if (state.promptSheetMode === "templates") {
      const page = state.promptSheetPage || {};
      const total = Number(page.total ?? visibleItems.length);
      text("#promptSheetCount", total > visibleItems.length ? `${visibleItems.length} / ${total}` : String(total));
      if (page.hasMore) {
        const more = document.createElement("button");
        more.type = "button";
        more.className = "ghost";
        more.dataset.action = "load-more-prompts";
        more.textContent = `もっと見る (${Math.max(0, total - visibleItems.length)}件)`;
        root.appendChild(more);
      }
    } else {
      text("#promptSheetCount", String(visibleItems.length));
    }
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
    state.promptSheetPage = { query: "", total: state.promptSheetItems.length, limit: 50, hasMore: false };
    renderPromptSheet();
    return data;
  }

  async function loadPositiveTemplates(query = value("#promptSheetQuery", ""), { append = false } = {}) {
    const normalizedQuery = String(query || "").trim();
    const limit = Number(state.promptSheetPage?.limit || 50);
    const offset = append && state.promptSheetPage?.query === normalizedQuery ? state.promptSheetItems.length : 0;
    const params = new URLSearchParams({
      query: normalizedQuery,
      limit: String(limit),
      offset: String(offset),
    });
    const data = await api(`/api/prompts/positive-templates?${params.toString()}`);
    if (value("#promptSheetQuery", "").trim() !== normalizedQuery) return data;
    const pageItems = Array.isArray(data.items) ? data.items : [];
    state.promptSheetItems = append && state.promptSheetPage?.query === normalizedQuery
      ? [...state.promptSheetItems, ...pageItems]
      : pageItems;
    state.promptSheetPage = {
      query: normalizedQuery,
      total: Number(data.total ?? state.promptSheetItems.length),
      limit: Number(data.limit ?? limit),
      hasMore: Boolean(data.has_more),
    };
    renderPromptSheet();
    return data;
  }

  async function loadMorePrompts() {
    text("#promptSheetStatus", "読み込み中...");
    await loadPositiveTemplates(value("#promptSheetQuery", ""), { append: true });
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
    state.promptSheetPage = { query: "", total: 0, limit: 50, hasMore: false };
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
      const moreTarget = event.target.closest("[data-action='load-more-prompts']");
      if (moreTarget) {
        event.preventDefault();
        event.stopPropagation();
        loadMorePrompts().catch((error) => {
          text("#promptSheetStatus", errorMessage(error));
          UI.toast(errorMessage(error), "error");
        });
        return;
      }
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
        loadPositiveTemplates(value("#promptSheetQuery", ""), { append: false }).catch((error) => {
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
  }

  return {
    loadDynamicWildcards,
    previewDynamicPrompt,
    loadPromptDictionaryStatus,
    schedulePromptDictionarySearch,
    insertPromptDictionaryTag,
    convertPromptFromJapanese,
    loadPromptConverterStatus,
    savePositiveFavorite,
    openPositiveFavorites,
    openPositiveTemplates,
    loadPositiveTemplates,
    loadMorePrompts,
    deletePositiveFavorite,
    usePromptSheetItem,
    saveRecipe,
    openRecipes,
    deleteRecipeItem,
    applyRecipe,
    renderPromptSheet,
    renderRecipes,
    bindEvents,
    actions: {
      "dynamic-wildcards": () => loadDynamicWildcards(),
      "dynamic-preview": () => previewDynamicPrompt(),
      "prompt-convert": () => convertPromptFromJapanese(),
      "prompt-converter-status": () => loadPromptConverterStatus(true),
      "save-positive-fav": () => savePositiveFavorite(),
      "open-positive-favs": () => openPositiveFavorites(),
      "open-templates": () => openPositiveTemplates(),
      "load-more-prompts": () => loadMorePrompts(),
      "save-recipe": () => saveRecipe(),
      "open-recipes": () => openRecipes(),
    },
  };
}
