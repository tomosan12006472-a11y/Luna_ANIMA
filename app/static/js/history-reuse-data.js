import {
  intFrom,
  numberFrom,
  setChecked,
} from "./dom.js?v=v1.69-detailer-sampling-20260702";

export function createHistoryReuseDataFeature({
  state,
  characters,
  generationForm,
  promptPresets,
  promptRandom,
  loras,
  i2i,
  reference,
  detailers,
  historyText,
  updateSummaries = () => {},
} = {}) {
  function historyReuseData(item = {}) {
    const slots = { character1: null, character2: null, character3: null, original: null };
    for (const char of item.characters || []) {
      const slotNumber = Number(char.slot || 0);
      const slotName = slotNumber === 1 ? "character1" : slotNumber === 2 ? "character2" : slotNumber === 3 ? "character3" : slotNumber === 4 ? "original" : "";
      if (!slotName) continue;
      const normalized = characters.normalizeCharacterItem({
        ...char,
        source: characters.sourceForCharacter(char),
        kind: characters.sourceForCharacter(char) === "original_character" ? "original" : "wai",
      });
      slots[slotName] = { ...normalized, value: characters.historyCharacterValue(char, slotName) };
    }
    const qualityPreset = historyText.inferHistoryQualityPreset(item);
    return {
      slots,
      rating: item.rating || "safe",
      rating_prompt_overrides: promptPresets.ratingPromptOverrides(item),
      quality_preset: qualityPreset,
      quality_prompt_overrides: promptPresets.qualityPromptOverrides(item),
      meta_prompt: item.meta_prompt || "anime illustration",
      year_prompt: item.year_prompt || "",
      outfit_prompt: item.outfit_prompt || "",
      expression_prompt: item.expression_prompt || "",
      pose_prompt: item.pose_prompt || "",
      background_prompt: item.background_prompt || "",
      lighting_prompt: item.lighting_prompt || "",
      camera_prompt: item.camera_prompt || "",
      positive_prompt: historyText.stripGeneratedHistoryPositive(item, qualityPreset),
      negative_prompt: historyText.historyNegativeText(item),
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
      official_loras: loras.historyOfficial(item.official_loras || {}),
      loras: loras.history(item.loras || []),
      dynamic_prompt: { enabled: false },
      prompt_random_collect: { ...promptRandom.historyCollect(item.prompt_random_collect), enabled: false },
      hires_fix: generationForm.historyHiresFix(item),
      image_to_image: i2i.history(item),
      reference_modules: reference.historyModules(item),
      face_detailer: detailers.historyFaceRequest(item),
      hand_detailer: detailers.historyHandRequest(item),
      source_item: item,
    };
  }

  function applyHistoryReuseData(data) {
    characters.applySlots(data.slots);
    promptPresets.applyReuseData(data);
    generationForm.applyHistoryBasicsToForm(data);
    loras.applyOfficialToForm(data.official_loras);
    loras.renderRows(data.loras || []);
    setChecked("#dynamicEnabled", Boolean(data.dynamic_prompt?.enabled));
    promptRandom.applyToForm(data.prompt_random_collect || {});

    i2i.applyToForm(data.image_to_image || {}, { update: false });
    reference.applyModulesToForm(data.reference_modules || {}, { update: false });

    detailers.applyToForm(data);
    updateSummaries();
  }

  function reuseDataFromRequest(request = {}) {
    const req = request && typeof request === "object" ? request : {};
    const defaultPositive = state.appSettings.default_positive_prompt ?? state.defaults.positive_prompt ?? "";
    const defaultNegative = state.appSettings.default_negative_prompt ?? state.defaults.negative_prompt ?? "";
    return {
      slots: {
        character1: characters.slotItemFromRequest("character1", req.character1 ?? "None"),
        character2: characters.slotItemFromRequest("character2", req.character2 ?? "None"),
        character3: characters.slotItemFromRequest("character3", req.character3 ?? "None"),
        original: characters.slotItemFromRequest("original", req.original_character ?? "None"),
      },
      rating: req.rating || state.appSettings.rating || "safe",
      rating_prompt_overrides: promptPresets.ratingPromptOverrides(req),
      quality_preset: req.quality_preset || state.appSettings.quality_preset || "standard",
      quality_prompt_overrides: promptPresets.qualityPromptOverrides(req),
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
      official_loras: loras.historyOfficial(req.official_loras || {}),
      loras: loras.history(req.loras || []),
      dynamic_prompt: req.dynamic_prompt && typeof req.dynamic_prompt === "object" ? req.dynamic_prompt : { enabled: false },
      prompt_random_collect: promptRandom.historyCollect(req.prompt_random_collect),
      hires_fix: generationForm.historyHiresFix({ hires_fix: req.hires_fix }),
      image_to_image: i2i.history({ image_to_image: req.image_to_image }),
      reference_modules: reference.historyModules({ reference_modules: req.reference_modules }),
      face_detailer: detailers.historyFaceRequest({ face_detailer: req.face_detailer }),
      hand_detailer: detailers.historyHandRequest({ hand_detailer: req.hand_detailer }),
      source_item: req,
    };
  }

  return {
    historyReuseData,
    applyHistoryReuseData,
    reuseDataFromRequest,
  };
}
