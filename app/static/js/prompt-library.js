import { createDynamicPromptFeature } from "./dynamic-prompt.js?v=v1.55-frequency-workbench-layout-20260626";
import { createPositivePromptsFeature } from "./positive-prompts.js?v=v1.55-frequency-workbench-layout-20260626";
import { createPromptConverterFeature } from "./prompt-converter.js?v=v1.55-frequency-workbench-layout-20260626";
import { createPromptDictionaryFeature } from "./prompt-dictionary.js?v=v1.55-frequency-workbench-layout-20260626";
import { createPositivePromptHelpers } from "./prompt-library-utils.js?v=v1.55-frequency-workbench-layout-20260626";
import { createRecipesFeature } from "./recipes.js?v=v1.55-frequency-workbench-layout-20260626";

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
  const helpers = createPositivePromptHelpers({ updateSummaries });

  const positivePrompts = createPositivePromptsFeature({
    api,
    state,
    UI,
    errorMessage,
    confirmDanger,
    helpers,
  });
  const recipes = createRecipesFeature({
    api,
    state,
    UI,
    errorMessage,
    confirmDanger,
    collectRequest,
    applyHistoryReuseData,
    reuseDataFromRequest,
  });
  const dynamicPrompt = createDynamicPromptFeature({
    api,
    UI,
    helpers,
  });
  const promptDictionary = createPromptDictionaryFeature({
    api,
    state,
    UI,
    errorMessage,
    helpers,
    updateSummaries,
  });
  const promptConverter = createPromptConverterFeature({
    api,
    state,
    UI,
    errorMessage,
    helpers,
  });

  function bindEvents() {
    positivePrompts.bindEvents();
    recipes.bindEvents();
    dynamicPrompt.bindEvents();
    promptDictionary.bindEvents();
    promptConverter.bindEvents();
  }

  return {
    loadDynamicWildcards: dynamicPrompt.loadDynamicWildcards,
    previewDynamicPrompt: dynamicPrompt.previewDynamicPrompt,
    loadPromptDictionaryStatus: promptDictionary.loadPromptDictionaryStatus,
    schedulePromptDictionarySearch: promptDictionary.schedulePromptDictionarySearch,
    insertPromptDictionaryTag: promptDictionary.insertPromptDictionaryTag,
    convertPromptFromJapanese: promptConverter.convertPromptFromJapanese,
    loadPromptConverterStatus: promptConverter.loadPromptConverterStatus,
    savePositiveFavorite: positivePrompts.savePositiveFavorite,
    openPositiveFavorites: positivePrompts.openPositiveFavorites,
    openPositiveTemplates: positivePrompts.openPositiveTemplates,
    loadPositiveTemplates: positivePrompts.loadPositiveTemplates,
    loadMorePrompts: positivePrompts.loadMorePrompts,
    deletePositiveFavorite: positivePrompts.deletePositiveFavorite,
    usePromptSheetItem: positivePrompts.usePromptSheetItem,
    saveRecipe: recipes.saveRecipe,
    openRecipes: recipes.openRecipes,
    deleteRecipeItem: recipes.deleteRecipeItem,
    applyRecipe: recipes.applyRecipe,
    renderPromptSheet: positivePrompts.renderPromptSheet,
    renderRecipes: recipes.renderRecipes,
    bindEvents,
    actions: {
      ...dynamicPrompt.actions,
      ...promptDictionary.actions,
      ...promptConverter.actions,
      ...positivePrompts.actions,
      ...recipes.actions,
    },
  };
}
