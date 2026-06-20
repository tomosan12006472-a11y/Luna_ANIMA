import {
  $,
  escapePathSegment,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.38-prompt-library-split-20260620";
import {
  parsePromptTags,
  promptExcerpt,
  promptItemPrompt,
  promptItemTagsText,
  promptItemTitle,
} from "./prompt-library-utils.js?v=v1.38-prompt-library-split-20260620";

export function createPositivePromptsFeature({
  api,
  state,
  UI = window.UI,
  errorMessage = (error) => error?.message || String(error),
  confirmDanger = async () => false,
  helpers,
} = {}) {
  const { applyPositivePromptInsert } = helpers || {};

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

  function bindEvents() {
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
  }

  return {
    deletePositiveFavorite,
    loadMorePrompts,
    loadPositiveFavorites,
    loadPositiveTemplates,
    openPositiveFavorites,
    openPositiveTemplates,
    renderPositiveFavoriteEditor,
    renderPromptSheet,
    savePositiveFavorite,
    savePositiveFavoriteEdit,
    usePromptSheetItem,
    bindEvents,
    actions: {
      "save-positive-fav": () => savePositiveFavorite(),
      "open-positive-favs": () => openPositiveFavorites(),
      "open-templates": () => openPositiveTemplates(),
      "load-more-prompts": () => loadMorePrompts(),
    },
  };
}
