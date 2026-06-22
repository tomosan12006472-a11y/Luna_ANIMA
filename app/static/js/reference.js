import {
  $,
  checked,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.41-turbo-presets-20260622";

const REFERENCE_MODULES = ["outfit", "pose"];
const REFMOD_EMPTY_TEXT = {
  outfit: "Outfit参照は未選択です。",
  pose: "Pose参照は未選択です。",
};

function refmodLabel(module) {
  return module === "pose" ? "Pose" : "Outfit";
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
    return {
      enabled: true,
      preset: outfitEnabled && poseEnabled ? "outfit_pose" : outfitEnabled ? "outfit_only" : poseEnabled ? "pose_only" : "off",
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
    };
  }

  function historyModules(item = {}) {
    const modules = item.reference_modules && typeof item.reference_modules === "object" ? item.reference_modules : {};
    const outfit = modules.outfit && typeof modules.outfit === "object" ? modules.outfit : {};
    const pose = modules.pose && typeof modules.pose === "object" ? modules.pose : {};
    const outfitEnabled = Boolean(outfit.enabled && outfit.image_id);
    const poseEnabled = Boolean(pose.enabled && pose.image_id);
    return {
      enabled: true,
      preset: outfitEnabled && poseEnabled ? "outfit_pose" : outfitEnabled ? "outfit_only" : poseEnabled ? "pose_only" : "off",
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
    const root = $(`#${module}Preview`);
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
    const outfitImageId = outfit.enabled ? String(outfit.image_id || "") : "";
    const poseImageId = pose.enabled ? String(pose.image_id || "") : "";
    state.refmod.outfit = { imageId: outfitImageId, thumb: "", name: String(outfit.image_name || outfitImageId || "") };
    state.refmod.pose = { imageId: poseImageId, thumb: "", name: String(pose.image_name || poseImageId || "") };
    setChecked("#outfitEnabled", Boolean(outfitImageId));
    setValue("#outfitStrength", outfit.strength ?? 0.45);
    setValue("#outfitStart", outfit.start_at ?? 0);
    setValue("#outfitEnd", outfit.end_at ?? 0.75);
    setChecked("#poseEnabled", Boolean(poseImageId));
    setValue("#poseMode", pose.mode || "pose_image");
    setValue("#poseStrength", pose.strength ?? 0.75);
    setValue("#poseStart", pose.start_at ?? 0);
    setValue("#poseEnd", pose.end_at ?? 0.85);
    renderPreviews();
    if (options.update !== false) updateSummaries();
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

  function bindEvents() {}

  return {
    actions: {
      "outfit-upload": () => uploadModuleImage("outfit"),
      "outfit-clear": () => clearModuleImage("outfit"),
      "pose-upload": () => uploadModuleImage("pose"),
      "pose-clear": () => clearModuleImage("pose"),
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
    uploadModuleImage,
  };
}
