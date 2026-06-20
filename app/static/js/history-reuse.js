import {
  intFrom,
  numberFrom,
  setChecked,
} from "./dom.js?v=v1.36-main-shell-cleanup-20260620";

export function createHistoryReuseFeature({
  state,
  UI = window.UI,
  characters,
  generationForm,
  promptPresets,
  promptRandom,
  loras,
  i2i,
  reference,
  detailers,
  updateSummaries = () => {},
} = {}) {
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
      ...Object.values(promptPresets.QUALITY_PROMPTS).flatMap(promptTerms),
      ...Object.values(promptPresets.RATING_PROMPTS),
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
      promptPresets.qualityPromptForPreset(qualityPreset, promptPresets.qualityPromptOverrides(item)),
      item.meta_prompt || "anime illustration",
      item.year_prompt || "",
      promptPresets.ratingPromptForPreset(item.rating || "safe", promptPresets.ratingPromptOverrides(item)),
      item.common || "",
      item.outfit_prompt || "",
      item.expression_prompt || "",
      item.pose_prompt || "",
      item.background_prompt || "",
      item.camera_prompt || "",
      item.lighting_prompt || "",
      item.natural_description || "",
    ];
    const historyCharacters = Array.isArray(item.characters) ? item.characters : [];
    const characterCount = historyCharacters.length;
    if (characterCount === 1) parts.push("1girl");
    if (characterCount > 1) parts.push(`${characterCount}girls`);
    for (const char of historyCharacters) {
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
      const normalized = characters.normalizeCharacterItem({
        ...char,
        source: characters.sourceForCharacter(char),
        kind: characters.sourceForCharacter(char) === "original_character" ? "original" : "wai",
      });
      slots[slotName] = { ...normalized, value: characters.historyCharacterValue(char, slotName) };
    }
    const qualityPreset = inferHistoryQualityPreset(item);
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

  function historyRequestFromItem(item = {}) {
    const data = historyReuseData(item);
    return {
      workflow_mode: data.hires_fix.enabled ? "anima_mobile_extended" : "anima",
      character1: characters.slotRequestValueFromData(data, "character1"),
      character2: characters.slotRequestValueFromData(data, "character2"),
      character3: characters.slotRequestValueFromData(data, "character3"),
      original_character: characters.slotRequestValueFromData(data, "original"),
      character1_weight: 1.0,
      character2_weight: 1.0,
      character3_weight: 1.0,
      original_weight: 1.0,
      character1_role: "main",
      character2_role: "left",
      character3_role: "right",
      rating: data.rating,
      rating_prompt_overrides: data.rating_prompt_overrides,
      quality_preset: data.quality_preset,
      quality_prompt_overrides: data.quality_prompt_overrides,
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
      prompt_random_collect: promptRandom.historyCollect(data.prompt_random_collect),
      hires_fix: data.hires_fix,
      reference_assist: { enabled: false },
      image_to_image: i2i.history(item),
      face_detailer: detailers.historyFaceRequest(item),
      hand_detailer: detailers.historyHandRequest(item),
      reference_modules: reference.historyModules(item),
    };
  }

  function buildVariationRequest(item = {}, count = 1) {
    return {
      ...historyRequestFromItem(item),
      seed_mode: "random",
      seed: -1,
      count,
      wait: false,
    };
  }

  function applyHistoryToForm(item) {
    applyHistoryReuseData(historyReuseData(item));
    UI.closeSheets();
    UI.switchTab("expose");
    UI.toast("設定を再利用しました");
  }

  return {
    historyPositiveText,
    historyNegativeText,
    historyRawPositiveText,
    historyPromptRandomGeneratedParts,
    promptTerms,
    normalizePromptTerm,
    appendUniquePromptTerms,
    stripGeneratedHistoryPositive,
    inferHistoryQualityPreset,
    historyGeneratedPositiveParts,
    historyReuseData,
    applyHistoryReuseData,
    reuseDataFromRequest,
    historyRequestFromItem,
    buildVariationRequest,
    applyHistoryToForm,
  };
}
