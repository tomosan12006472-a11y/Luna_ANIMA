import {
  $,
  checked,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.55-frequency-workbench-layout-20260626";

const REFERENCE_MODULES = ["outfit", "pose", "background"];
const REFMOD_EMPTY_TEXT = {
  outfit: "Outfit参照は未選択です。",
  pose: "Pose参照は未選択です。",
  background: "Background Referenceは未選択です。",
};
const REFMOD_PREVIEW_IDS = {
  outfit: "#outfitPreview",
  pose: "#posePreview",
  background: "#backgroundPreview",
};
const BACKGROUND_MODE_DEFAULTS = Object.freeze({
  depth: { strength: 0.45, start_at: 0.0, end_at: 0.75 },
  canny: { strength: 0.35, start_at: 0.0, end_at: 0.65 },
  lineart: { strength: 0.30, start_at: 0.0, end_at: 0.60 },
  softedge: { strength: 0.35, start_at: 0.0, end_at: 0.70 },
  mlsd: { strength: 0.35, start_at: 0.0, end_at: 0.70 },
});

function refmodLabel(module) {
  if (module === "pose") return "Pose";
  if (module === "background") return "Background";
  return "Outfit";
}

function referencePreset(outfitEnabled, poseEnabled, backgroundEnabled) {
  if (outfitEnabled && poseEnabled && backgroundEnabled) return "outfit_pose_background";
  if (outfitEnabled && backgroundEnabled) return "outfit_background";
  if (poseEnabled && backgroundEnabled) return "pose_background";
  if (backgroundEnabled) return "background_only";
  if (outfitEnabled && poseEnabled) return "outfit_pose";
  if (outfitEnabled) return "outfit_only";
  if (poseEnabled) return "pose_only";
  return "off";
}

export function createReferenceFeature({
  api,
  state,
  UI = window.UI,
  updateSummaries = () => {},
} = {}) {
  function collectModules() {
    const outfitEnabled = checked("#outfitEnabled");
    const poseEnabled = checked("#poseEnabled");
    const backgroundEnabled = checked("#backgroundEnabled");
    return {
      enabled: true,
      preset: referencePreset(outfitEnabled, poseEnabled, backgroundEnabled),
      outfit: {
        enabled: outfitEnabled,
        image_id: state.refmod.outfit.imageId,
        image_name: state.refmod.outfit.name,
        strength: numberValue("#outfitStrength", 0.45),
        mode: "image_prompt",
        strategy: "ip_adapter",
        crop_mode: "user_prepared",
        start_at: numberValue("#outfitStart", 0),
        end_at: numberValue("#outfitEnd", 0.75),
      },
      pose: {
        enabled: poseEnabled,
        image_id: state.refmod.pose.imageId,
        image_name: state.refmod.pose.name,
        mode: value("#poseMode", "pose_image"),
        strength: numberValue("#poseStrength", 0.75),
        strategy: "controlnet_openpose",
        start_at: numberValue("#poseStart", 0),
        end_at: numberValue("#poseEnd", 0.85),
      },
      background: {
        enabled: backgroundEnabled,
        image_id: state.refmod.background.imageId,
        image_name: state.refmod.background.name,
        mode: value("#backgroundMode", "depth"),
        strength: numberValue("#backgroundStrength", 0.45),
        start_at: numberValue("#backgroundStart", 0),
        end_at: numberValue("#backgroundEnd", 0.75),
        resize_mode: value("#backgroundResize", "crop"),
        controlnet_model: "auto",
      },
    };
  }

  function historyModules(item = {}) {
    const modules = item.reference_modules && typeof item.reference_modules === "object" ? item.reference_modules : {};
    const outfit = modules.outfit && typeof modules.outfit === "object" ? modules.outfit : {};
    const pose = modules.pose && typeof modules.pose === "object" ? modules.pose : {};
    const background = modules.background && typeof modules.background === "object" ? modules.background : {};
    const outfitEnabled = Boolean(outfit.enabled && outfit.image_id);
    const poseEnabled = Boolean(pose.enabled && pose.image_id);
    const backgroundEnabled = Boolean(background.enabled && background.image_id);
    return {
      enabled: true,
      preset: referencePreset(outfitEnabled, poseEnabled, backgroundEnabled),
      outfit: {
        enabled: outfitEnabled,
        image_id: String(outfit.image_id || ""),
        image_name: String(outfit.image_name || ""),
        strength: numberFrom(outfit.strength, 0.45),
        mode: String(outfit.mode || "image_prompt"),
        strategy: String(outfit.strategy || "ip_adapter"),
        crop_mode: String(outfit.crop_mode || "user_prepared"),
        start_at: numberFrom(outfit.start_at, 0),
        end_at: numberFrom(outfit.end_at, 0.75),
      },
      pose: {
        enabled: poseEnabled,
        image_id: String(pose.image_id || ""),
        image_name: String(pose.image_name || ""),
        mode: String(pose.mode || "pose_image"),
        strength: numberFrom(pose.strength, 0.75),
        strategy: String(pose.strategy || "controlnet_openpose"),
        start_at: numberFrom(pose.start_at, 0),
        end_at: numberFrom(pose.end_at, 0.85),
      },
      background: {
        enabled: backgroundEnabled,
        image_id: String(background.image_id || ""),
        image_name: String(background.image_name || ""),
        mode: String(background.mode || "depth"),
        strength: numberFrom(background.strength, 0.45),
        strategy: String(background.strategy || "controlnet_background"),
        start_at: numberFrom(background.start_at, 0),
        end_at: numberFrom(background.end_at, 0.75),
        resize_mode: String(background.resize_mode || "crop"),
        controlnet_model: String(background.controlnet_model || "auto"),
      },
    };
  }

  function itemState(item = {}) {
    const imageId = String(item.image_id || "").trim();
    return {
      imageId,
      thumb: String(item.thumbnail_url || item.image_url || item.thumb || "").trim(),
      name: String(item.original_filename || item.filename || item.name || imageId || "").trim(),
    };
  }

  function renderPreview(module) {
    const root = $(REFMOD_PREVIEW_IDS[module] || `#${module}Preview`);
    if (!root) return;
    const item = state.refmod[module] || { imageId: "", thumb: "", name: "" };
    root.replaceChildren();
    if (!item.imageId) {
      root.classList.add("is-empty");
      root.textContent = REFMOD_EMPTY_TEXT[module] || "参照は未選択です。";
      return;
    }
    root.classList.remove("is-empty");
    if (item.thumb) {
      const img = document.createElement("img");
      img.src = item.thumb;
      img.alt = item.name || `${module} reference`;
      img.loading = "lazy";
      img.decoding = "async";
      root.appendChild(img);
    }
    const label = document.createElement("span");
    label.textContent = item.name || item.imageId;
    root.appendChild(label);
  }

  function renderPreviews() {
    renderPreview("outfit");
    renderPreview("pose");
    renderPreview("background");
  }

  function applyItem(module, item = {}, options = {}) {
    if (!state.refmod[module]) return;
    state.refmod[module] = itemState(item);
    setChecked(`#${module}Enabled`, Boolean(state.refmod[module].imageId));
    renderPreview(module);
    if (options.update !== false) updateSummaries();
  }

  function applyModulesToForm(modules = {}, options = {}) {
    const outfit = modules.outfit || {};
    const pose = modules.pose || {};
    const background = modules.background || {};
    const outfitImageId = String(outfit.image_id || "");
    const poseImageId = String(pose.image_id || "");
    const backgroundImageId = String(background.image_id || "");
    state.refmod.outfit = { imageId: outfitImageId, thumb: "", name: String(outfit.image_name || outfitImageId || "") };
    state.refmod.pose = { imageId: poseImageId, thumb: "", name: String(pose.image_name || poseImageId || "") };
    state.refmod.background = { imageId: backgroundImageId, thumb: "", name: String(background.image_name || backgroundImageId || "") };
    setChecked("#outfitEnabled", Boolean(outfit.enabled && outfitImageId));
    setValue("#outfitStrength", outfit.strength ?? 0.45);
    setValue("#outfitStart", outfit.start_at ?? 0);
    setValue("#outfitEnd", outfit.end_at ?? 0.75);
    setChecked("#poseEnabled", Boolean(pose.enabled && poseImageId));
    setValue("#poseMode", pose.mode || "pose_image");
    setValue("#poseStrength", pose.strength ?? 0.75);
    setValue("#poseStart", pose.start_at ?? 0);
    setValue("#poseEnd", pose.end_at ?? 0.85);
    setChecked("#backgroundEnabled", Boolean(background.enabled && backgroundImageId));
    setValue("#backgroundMode", background.mode || "depth");
    setValue("#backgroundStrength", background.strength ?? 0.45);
    setValue("#backgroundStart", background.start_at ?? 0);
    setValue("#backgroundEnd", background.end_at ?? 0.75);
    setValue("#backgroundResize", background.resize_mode || "crop");
    renderPreviews();
    if (options.update !== false) updateSummaries();
  }

  function setEnabled(module, enabled) {
    if (!REFERENCE_MODULES.includes(module)) return;
    const hasImage = Boolean(state.refmod?.[module]?.imageId);
    setChecked(`#${module}Enabled`, Boolean(enabled && hasImage));
  }

  function setAllEnabled(enabled) {
    for (const module of REFERENCE_MODULES) setEnabled(module, enabled);
    updateSummaries();
  }

  function clearModuleImage(module) {
    if (!state.refmod[module]) return;
    state.refmod[module] = { imageId: "", thumb: "", name: "" };
    setChecked(`#${module}Enabled`, false);
    setValue(`#${module}File`, "");
    text("#refModStatus", "");
    renderPreview(module);
    updateSummaries();
  }

  function applyBackgroundModeDefaults() {
    const defaults = BACKGROUND_MODE_DEFAULTS[value("#backgroundMode", "depth")] || BACKGROUND_MODE_DEFAULTS.depth;
    setValue("#backgroundStrength", defaults.strength);
    setValue("#backgroundStart", defaults.start_at);
    setValue("#backgroundEnd", defaults.end_at);
    text("#refModStatus", "Background Referenceの推奨値を適用しました");
    updateSummaries();
  }

  async function uploadModuleImage(module) {
    if (!state.refmod[module]) return;
    const label = refmodLabel(module);
    const input = $(`#${module}File`);
    const file = input?.files?.[0];
    if (!file) {
      text("#refModStatus", `${label}参照画像を選択してください`);
      UI.toast(`${label}参照画像を選択してください`, "error");
      return;
    }
    text("#refModStatus", `${label}参照をアップロード中...`);
    const form = new FormData();
    form.append("file", file);
    const data = await api(`/api/reference-modules/upload?module=${encodeURIComponent(module)}`, {
      method: "POST",
      body: form,
    });
    applyItem(module, data.item);
    text("#refModStatus", `${label}参照を設定しました`);
    UI.toast(`${label}参照を設定しました`);
  }

  function bindEvents() {
    ["#backgroundMode", "#backgroundStrength", "#backgroundStart", "#backgroundEnd", "#backgroundResize"].forEach((selector) => {
      $(selector)?.addEventListener("change", updateSummaries);
    });
  }

  return {
    actions: {
      "outfit-upload": () => uploadModuleImage("outfit"),
      "outfit-clear": () => clearModuleImage("outfit"),
      "pose-upload": () => uploadModuleImage("pose"),
      "pose-clear": () => clearModuleImage("pose"),
      "background-upload": () => uploadModuleImage("background"),
      "background-clear": () => clearModuleImage("background"),
      "background-apply-mode-defaults": () => applyBackgroundModeDefaults(),
      "reference-enable-all": () => setAllEnabled(true),
      "reference-disable-all": () => setAllEnabled(false),
    },
    applyItem,
    applyModulesToForm,
    bindEvents,
    clearModuleImage,
    collectModules,
    historyModules,
    modules: REFERENCE_MODULES,
    renderPreview,
    renderPreviews,
    restoreModules: applyModulesToForm,
    setAllEnabled,
    setEnabled,
    snapshotModules: collectModules,
    uploadModuleImage,
  };
}
