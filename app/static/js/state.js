export const CHARACTER_FAVORITES_COLLAPSED_KEY = "lunaAnimaCharacterFavoritesCollapsedV1";

export function storedBoolean(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (raw === "true") return true;
    if (raw === "false") return false;
  } catch {}
  return fallback;
}

export function storeBoolean(key, value) {
  try {
    localStorage.setItem(key, String(Boolean(value)));
  } catch {}
}

export function createInitialState() {
  return {
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
    characterFavoritesCollapsed: storedBoolean(CHARACTER_FAVORITES_COLLAPSED_KEY, true),
    ratingPromptDrafts: {},
    qualityPromptDrafts: {},
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
    characterSearch: { query: "", items: [], total: 0, offset: 0, limit: 60, hasMore: false },
    promptSheetMode: "favorites",
    promptSheetItems: [],
    promptSheetEditingId: "",
    promptSheetPage: { query: "", total: 0, limit: 50, hasMore: false },
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
}
