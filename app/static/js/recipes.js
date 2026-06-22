import { $, escapePathSegment, text } from "./dom.js?v=v1.41-turbo-presets-20260622";

export function createRecipesFeature({
  api,
  state,
  UI = window.UI,
  errorMessage = (error) => error?.message || String(error),
  confirmDanger = async () => false,
  collectRequest = () => ({}),
  applyHistoryReuseData = () => {},
  reuseDataFromRequest = () => ({}),
} = {}) {
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

  function bindEvents() {
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
    applyRecipe,
    deleteRecipeItem,
    openRecipes,
    renderRecipes,
    saveRecipe,
    bindEvents,
    actions: {
      "save-recipe": () => saveRecipe(),
      "open-recipes": () => openRecipes(),
    },
  };
}
