import {
  checked,
  intFrom,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
  value,
} from "./dom.js?v=v1.55-frequency-workbench-layout-20260626";

const DEFAULT_MODEL = "Anima\\anima-preview3-base.safetensors";
const DEFAULT_TEXT_ENCODER = "qwen_3_06b_base.safetensors";
const DEFAULT_VAE = "qwen_image_vae.safetensors";

export function createGenerationFormFeature({
  state,
  UI = window.UI,
  fillSelect = () => {},
  slotRequestValue = () => "None",
  collectRatingPromptOverrides = () => ({}),
  collectQualityPromptOverrides = () => ({}),
  collectFaceDetailerSettings = () => ({}),
  collectHandDetailerSettings = () => ({}),
  promptRandom,
  loras,
  i2i,
  reference,
} = {}) {
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
    fillSelect("#hiresMethod", state?.models?.upscale_methods || [], next.latent_upscale_method);
    fillSelect("#hiresModel", state?.models?.upscale_models || [], next.upscale_model);
    setValue("#hiresTargetW", next.target_width);
    setValue("#hiresTargetH", next.target_height);
  }

  function setHiresEnabled(enabled) {
    setChecked("#hiresEnabled", Boolean(enabled));
  }

  function setDynamicPromptEnabled(enabled) {
    setChecked("#dynamicEnabled", Boolean(enabled));
  }

  function collectPromptFields() {
    const negative = value("#negativePrompt", "");
    return {
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
    };
  }

  function collectModelFields() {
    return {
      model: value("#modelSelect", state?.appSettings?.model || state?.defaults?.model || DEFAULT_MODEL),
      text_encoder: state?.appSettings?.text_encoder || state?.defaults?.text_encoder || DEFAULT_TEXT_ENCODER,
      vae: state?.appSettings?.vae || state?.defaults?.vae || DEFAULT_VAE,
      sampler: value("#samplerSelect", "er_sde"),
      scheduler: value("#schedulerSelect", "simple"),
    };
  }

  function collectSizeFields() {
    return {
      width: numberValue("#widthInput", 1024),
      height: numberValue("#heightInput", 1536),
      steps: numberValue("#stepsInput", 32),
      cfg: numberValue("#cfgInput", 4.5),
      shift: numberValue("#shiftInput", 4),
    };
  }

  function collectSeedFields() {
    const seedMode = value("#seedModeSelect", "fixed");
    return {
      seed: seedMode === "random" ? -1 : Math.trunc(numberValue("#seedInput", -1)),
      seed_mode: seedMode,
    };
  }

  function collectBaseRequest() {
    const modelFields = collectModelFields();
    return {
      ...collectPromptFields(),
      model: modelFields.model,
      text_encoder: modelFields.text_encoder,
      vae: modelFields.vae,
      ...collectSizeFields(),
      sampler: modelFields.sampler,
      scheduler: modelFields.scheduler,
      ...collectSeedFields(),
    };
  }

  function collectRequest() {
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
      rating_prompt_overrides: collectRatingPromptOverrides(),
      quality_preset: UI.segValue("#qualitySeg", "quality") || "standard",
      quality_prompt_overrides: collectQualityPromptOverrides(),
      ...collectBaseRequest(),
      official_loras: loras.collectOfficial(),
      official_lora_preset: loras.collectOfficialPreset(),
      loras: loras.collect(),
      count: selectedQueueCount(),
      wait: false,
      dynamic_prompt: { enabled: checked("#dynamicEnabled") },
      prompt_random_collect: promptRandom.collect(),
      hires_fix: hiresFix,
      reference_assist: { enabled: false },
      image_to_image: i2i.collect(),
      face_detailer: collectFaceDetailerSettings(checked("#fdEnabled"), "generation"),
      hand_detailer: collectHandDetailerSettings(checked("#hdEnabled"), "generation"),
      reference_modules: reference.collectModules(),
    };
  }

  function applySettingsBasicsToForm(settings = {}, defaults = state?.defaults || {}) {
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
    applyHiresFixToForm(settings.hires_fix || {});
    fillSelect("#modelSelect", state?.models?.models || [], settings.model ?? defaults.model ?? DEFAULT_MODEL);
    fillSelect("#samplerSelect", state?.models?.samplers || [], settings.sampler ?? defaults.sampler ?? "er_sde");
    fillSelect("#schedulerSelect", state?.models?.schedulers || [], settings.scheduler ?? defaults.scheduler ?? "simple");
  }

  function applyHistoryBasicsToForm(data = {}) {
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
    applyHiresFixToForm(data.hires_fix || {});
  }

  function historyHiresFix(item = {}) {
    return normalizeHiresFix(item.hires_fix || {});
  }

  return {
    selectedQueueCount,
    selectedVariationCount,
    normalizeHiresMode,
    normalizeHiresFix,
    collectHiresFix,
    applyHiresFixToForm,
    restoreHires: applyHiresFixToForm,
    setDynamicPromptEnabled,
    setHiresEnabled,
    snapshotHires: collectHiresFix,
    collectPromptFields,
    collectModelFields,
    collectSizeFields,
    collectSeedFields,
    collectBaseRequest,
    collectRequest,
    applySettingsBasicsToForm,
    applyHistoryBasicsToForm,
    historyHiresFix,
  };
}
