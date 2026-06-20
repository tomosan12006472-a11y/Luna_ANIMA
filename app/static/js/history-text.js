export function createHistoryTextFeature({
  promptPresets,
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
  };
}
