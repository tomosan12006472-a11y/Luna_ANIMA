import {
  checked,
  intFrom,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.69-detailer-sampling-20260702";
import { fillSelect } from "./render-helpers.js?v=v1.69-detailer-sampling-20260702";

export function createDetailerFeature({
  api,
  state,
  UI = window.UI,
  history,
  updateSummaries = () => {},
} = {}) {
  const detectionPresets = {
    face: {
      safe: { bbox_threshold: 0.75, min_area_ratio: 0.001, max_area_ratio: 1.0, max_detections: 4, runaway_guard_enabled: true, runaway_max_candidates: 12, runaway_action: "skip" },
      normal: { bbox_threshold: 0.65, min_area_ratio: 0.0008, max_area_ratio: 1.0, max_detections: 8, runaway_guard_enabled: true, runaway_max_candidates: 20, runaway_action: "skip" },
      aggressive: { bbox_threshold: 0.5, min_area_ratio: 0.0004, max_area_ratio: 1.0, max_detections: 16, runaway_guard_enabled: true, runaway_max_candidates: 40, runaway_action: "limit" },
    },
    hand: {
      safe: { bbox_threshold: 0.55, min_area_ratio: 0.0008, max_area_ratio: 0.35, max_detections: 6, runaway_guard_enabled: true, runaway_max_candidates: 16, runaway_action: "skip" },
      normal: { bbox_threshold: 0.45, min_area_ratio: 0.0005, max_area_ratio: 0.35, max_detections: 12, runaway_guard_enabled: true, runaway_max_candidates: 30, runaway_action: "skip" },
      aggressive: { bbox_threshold: 0.35, min_area_ratio: 0.0003, max_area_ratio: 0.45, max_detections: 20, runaway_guard_enabled: true, runaway_max_candidates: 50, runaway_action: "limit" },
    },
  };

  const defaults = {
    face: { preset: "normal", bbox_threshold: 0.65, min_area_ratio: 0.0008, max_area_ratio: 1.0, max_detections: 8, runaway_guard_enabled: true, runaway_max_candidates: 20, runaway_action: "skip", sampler_mode: "custom", sampler: "euler", scheduler: "normal" },
    hand: { preset: "normal", bbox_threshold: 0.45, min_area_ratio: 0.0005, max_area_ratio: 0.35, max_detections: 12, runaway_guard_enabled: true, runaway_max_candidates: 30, runaway_action: "skip", sampler_mode: "custom", sampler: "euler", scheduler: "normal" },
  };

  function prefixFor(kind) {
    return kind === "hand" ? "hd" : "fd";
  }

  function validPreset(value) {
    const preset = String(value || "normal").trim().toLowerCase();
    return ["safe", "normal", "aggressive", "custom"].includes(preset) ? preset : "normal";
  }

  function validSamplerMode(nextValue) {
    const mode = String(nextValue || "custom").trim().toLowerCase();
    return ["source", "inherit", "same"].includes(mode) ? "source" : "custom";
  }

  function fillSamplingSelects(kind, data = {}) {
    const prefix = prefixFor(kind);
    const fallback = defaults[kind] || defaults.face;
    fillSelect(`#${prefix}SamplerSelect`, state?.models?.samplers || [], data.sampler ?? fallback.sampler);
    fillSelect(`#${prefix}SchedulerSelect`, state?.models?.schedulers || [], data.scheduler ?? fallback.scheduler);
  }

  function applyDetectionPreset(kind, presetValue) {
    const prefix = prefixFor(kind);
    const preset = validPreset(presetValue);
    const values = detectionPresets[kind]?.[preset];
    if (!values) return;
    setValue(`#${prefix}Bbox`, values.bbox_threshold);
    setValue(`#${prefix}MinAreaRatio`, values.min_area_ratio);
    setValue(`#${prefix}MaxAreaRatio`, values.max_area_ratio);
    setValue(`#${prefix}MaxDetections`, values.max_detections);
    setChecked(`#${prefix}RunawayGuard`, values.runaway_guard_enabled);
    setValue(`#${prefix}RunawayMaxCandidates`, values.runaway_max_candidates);
    setValue(`#${prefix}RunawayAction`, values.runaway_action);
  }

  function markDetectionCustom(kind) {
    setValue(`#${prefixFor(kind)}Preset`, "custom");
  }

  function collectFaceSettings(enabled = checked("#fdEnabled"), mode = "generation") {
    return {
      enabled: Boolean(enabled),
      mode,
      preset: validPreset(value("#fdPreset", "normal")),
      detector: "bbox/face_yolov8m.pt",
      steps: Math.trunc(numberValue("#fdSteps", 12)),
      cfg: numberValue("#fdCfg", 4.0),
      denoise: numberValue("#fdDenoise", 0.3),
      sampler_mode: validSamplerMode(value("#fdSamplerMode", "custom")),
      sampler: value("#fdSamplerSelect", "euler"),
      scheduler: value("#fdSchedulerSelect", "normal"),
      guide_size: 512,
      max_size: 1024,
      bbox_threshold: numberValue("#fdBbox", 0.65),
      bbox_dilation: 10,
      bbox_crop_factor: 3.0,
      drop_size: 64,
      min_area_ratio: numberValue("#fdMinAreaRatio", 0.0008),
      max_area_ratio: numberValue("#fdMaxAreaRatio", 1.0),
      max_detections: Math.trunc(numberValue("#fdMaxDetections", 8)),
      runaway_guard_enabled: checked("#fdRunawayGuard"),
      runaway_max_candidates: Math.trunc(numberValue("#fdRunawayMaxCandidates", 20)),
      runaway_action: value("#fdRunawayAction", "skip"),
      sam_enabled: false,
      seed_policy: "image_seed_plus_offset",
      seed_offset: 100000,
    };
  }

  function collectHandSettings(enabled = checked("#hdEnabled"), mode = "generation") {
    return {
      enabled: Boolean(enabled),
      mode,
      preset: validPreset(value("#hdPreset", "normal")),
      detector: "bbox/hand_yolov8s.pt",
      steps: Math.trunc(numberValue("#hdSteps", 14)),
      cfg: numberValue("#hdCfg", 4.0),
      denoise: numberValue("#hdDenoise", 0.45),
      sampler_mode: validSamplerMode(value("#hdSamplerMode", "custom")),
      sampler: value("#hdSamplerSelect", "euler"),
      scheduler: value("#hdSchedulerSelect", "normal"),
      guide_size: 512,
      max_size: 1024,
      bbox_threshold: numberValue("#hdBbox", 0.45),
      bbox_dilation: 16,
      bbox_crop_factor: 2.5,
      drop_size: 24,
      min_area_ratio: numberValue("#hdMinAreaRatio", 0.0005),
      max_area_ratio: numberValue("#hdMaxAreaRatio", 0.35),
      max_detections: Math.trunc(numberValue("#hdMaxDetections", 12)),
      runaway_guard_enabled: checked("#hdRunawayGuard"),
      runaway_max_candidates: Math.trunc(numberValue("#hdRunawayMaxCandidates", 30)),
      runaway_action: value("#hdRunawayAction", "skip"),
      sam_enabled: false,
      seed_policy: "image_seed_plus_offset",
      seed_offset: 200000,
      lllite_enabled: true,
      lllite_model: "anima-lllite-inpainting-v2.safetensors",
      lllite_strength: numberValue("#hdLlliteStrength", 0.85),
      lllite_start: 0,
      lllite_end: 1,
    };
  }

  function historyFaceRequest(item = {}) {
    const face = item.face_detailer && typeof item.face_detailer === "object" ? item.face_detailer : {};
    return {
      enabled: Boolean(face.enabled),
      mode: String(face.mode || "generation"),
      preset: validPreset(face.preset),
      detector: String(face.detector || "bbox/face_yolov8m.pt"),
      steps: intFrom(face.steps, 12),
      cfg: numberFrom(face.cfg, 4.0),
      denoise: numberFrom(face.denoise, 0.3),
      sampler_mode: validSamplerMode(face.sampler_mode),
      sampler: String(face.sampler || "euler"),
      scheduler: String(face.scheduler || "normal"),
      guide_size: intFrom(face.guide_size, 512),
      max_size: intFrom(face.max_size, 1024),
      bbox_threshold: numberFrom(face.bbox_threshold, 0.65),
      bbox_dilation: intFrom(face.bbox_dilation, 10),
      bbox_crop_factor: numberFrom(face.bbox_crop_factor, 3.0),
      drop_size: intFrom(face.drop_size, 64),
      min_area_ratio: numberFrom(face.min_area_ratio, 0.0008),
      max_area_ratio: numberFrom(face.max_area_ratio, 1.0),
      max_detections: intFrom(face.max_detections, 8),
      runaway_guard_enabled: face.runaway_guard_enabled !== false,
      runaway_max_candidates: intFrom(face.runaway_max_candidates, 20),
      runaway_action: String(face.runaway_action || "skip"),
      sam_enabled: Boolean(face.sam_enabled),
      seed_policy: String(face.seed_policy || "image_seed_plus_offset"),
      seed_offset: intFrom(face.seed_offset, 100000),
    };
  }

  function historyHandRequest(item = {}) {
    const hand = item.hand_detailer && typeof item.hand_detailer === "object" ? item.hand_detailer : {};
    const lllite = hand.lllite && typeof hand.lllite === "object" ? hand.lllite : {};
    return {
      enabled: Boolean(hand.enabled),
      mode: String(hand.mode || "generation"),
      preset: validPreset(hand.preset),
      detector: String(hand.detector || "bbox/hand_yolov8s.pt"),
      steps: intFrom(hand.steps, 14),
      cfg: numberFrom(hand.cfg, 4.0),
      denoise: numberFrom(hand.denoise, 0.45),
      sampler_mode: validSamplerMode(hand.sampler_mode),
      sampler: String(hand.sampler || "euler"),
      scheduler: String(hand.scheduler || "normal"),
      guide_size: intFrom(hand.guide_size, 512),
      max_size: intFrom(hand.max_size, 1024),
      bbox_threshold: numberFrom(hand.bbox_threshold, 0.45),
      bbox_dilation: intFrom(hand.bbox_dilation, 16),
      bbox_crop_factor: numberFrom(hand.bbox_crop_factor, 2.5),
      drop_size: intFrom(hand.drop_size, 24),
      min_area_ratio: numberFrom(hand.min_area_ratio, 0.0005),
      max_area_ratio: numberFrom(hand.max_area_ratio, 0.35),
      max_detections: intFrom(hand.max_detections, 12),
      runaway_guard_enabled: hand.runaway_guard_enabled !== false,
      runaway_max_candidates: intFrom(hand.runaway_max_candidates, 30),
      runaway_action: String(hand.runaway_action || "skip"),
      sam_enabled: Boolean(hand.sam_enabled),
      seed_policy: String(hand.seed_policy || "image_seed_plus_offset"),
      seed_offset: intFrom(hand.seed_offset, 200000),
      lllite_enabled: hand.lllite_enabled !== false && lllite.enabled !== false,
      lllite_model: String(hand.lllite_model || lllite.model || "anima-lllite-inpainting-v2.safetensors"),
      lllite_strength: numberFrom(hand.lllite_strength ?? lllite.strength, 0.85),
      lllite_start: numberFrom(hand.lllite_start ?? lllite.start_percent, 0),
      lllite_end: numberFrom(hand.lllite_end ?? lllite.end_percent, 1),
    };
  }

  function applyFaceToForm(face = {}) {
    setChecked("#fdEnabled", Boolean(face.enabled));
    setValue("#fdPreset", validPreset(face.preset));
    setValue("#fdSteps", face.steps ?? 12);
    setValue("#fdCfg", face.cfg ?? 4.0);
    setValue("#fdDenoise", face.denoise ?? 0.3);
    setValue("#fdSamplerMode", validSamplerMode(face.sampler_mode ?? defaults.face.sampler_mode));
    fillSamplingSelects("face", face);
    setValue("#fdBbox", face.bbox_threshold ?? defaults.face.bbox_threshold);
    setValue("#fdMinAreaRatio", face.min_area_ratio ?? defaults.face.min_area_ratio);
    setValue("#fdMaxAreaRatio", face.max_area_ratio ?? defaults.face.max_area_ratio);
    setValue("#fdMaxDetections", face.max_detections ?? defaults.face.max_detections);
    setChecked("#fdRunawayGuard", face.runaway_guard_enabled ?? defaults.face.runaway_guard_enabled);
    setValue("#fdRunawayMaxCandidates", face.runaway_max_candidates ?? defaults.face.runaway_max_candidates);
    setValue("#fdRunawayAction", face.runaway_action ?? defaults.face.runaway_action);
  }

  function applyHandToForm(hand = {}) {
    setChecked("#hdEnabled", Boolean(hand.enabled));
    setValue("#hdPreset", validPreset(hand.preset));
    setValue("#hdSteps", hand.steps ?? 14);
    setValue("#hdCfg", hand.cfg ?? 4.0);
    setValue("#hdDenoise", hand.denoise ?? 0.45);
    setValue("#hdSamplerMode", validSamplerMode(hand.sampler_mode ?? defaults.hand.sampler_mode));
    fillSamplingSelects("hand", hand);
    setValue("#hdBbox", hand.bbox_threshold ?? defaults.hand.bbox_threshold);
    setValue("#hdMinAreaRatio", hand.min_area_ratio ?? defaults.hand.min_area_ratio);
    setValue("#hdMaxAreaRatio", hand.max_area_ratio ?? defaults.hand.max_area_ratio);
    setValue("#hdMaxDetections", hand.max_detections ?? defaults.hand.max_detections);
    setChecked("#hdRunawayGuard", hand.runaway_guard_enabled ?? defaults.hand.runaway_guard_enabled);
    setValue("#hdRunawayMaxCandidates", hand.runaway_max_candidates ?? defaults.hand.runaway_max_candidates);
    setValue("#hdRunawayAction", hand.runaway_action ?? defaults.hand.runaway_action);
    setValue("#hdLlliteStrength", hand.lllite_strength ?? hand.lllite?.strength ?? 0.85);
  }

  function applyToForm(data = {}) {
    applyFaceToForm(data.face_detailer || {});
    applyHandToForm(data.hand_detailer || {});
  }

  function refreshSamplingOptions() {
    fillSamplingSelects("face", collectFaceSettings(checked("#fdEnabled"), "generation"));
    fillSamplingSelects("hand", collectHandSettings(checked("#hdEnabled"), "generation"));
  }

  function snapshot() {
    return {
      face_detailer: collectFaceSettings(checked("#fdEnabled"), "generation"),
      hand_detailer: collectHandSettings(checked("#hdEnabled"), "generation"),
    };
  }

  function restore(snapshotData = {}) {
    applyToForm(snapshotData);
    updateSummaries();
  }

  function setAllEnabled(enabled) {
    setChecked("#fdEnabled", Boolean(enabled));
    setChecked("#hdEnabled", Boolean(enabled));
    updateSummaries();
  }

  function bindEvents() {
    ["face", "hand"].forEach((kind) => {
      const prefix = prefixFor(kind);
      const preset = document.querySelector(`#${prefix}Preset`);
      preset?.addEventListener("change", () => {
        applyDetectionPreset(kind, preset.value);
        updateSummaries();
      });
      [
        `#${prefix}Bbox`,
        `#${prefix}MinAreaRatio`,
        `#${prefix}MaxAreaRatio`,
        `#${prefix}MaxDetections`,
        `#${prefix}RunawayGuard`,
        `#${prefix}RunawayMaxCandidates`,
        `#${prefix}RunawayAction`,
      ].forEach((selector) => {
        document.querySelector(selector)?.addEventListener("change", () => {
          markDetectionCustom(kind);
          updateSummaries();
        });
      });
      [
        `#${prefix}SamplerMode`,
        `#${prefix}SamplerSelect`,
        `#${prefix}SchedulerSelect`,
      ].forEach((selector) => {
        document.querySelector(selector)?.addEventListener("change", () => {
          updateSummaries();
        });
      });
    });
  }

  async function queueFrameFaceDetailer() {
    if (!state?.detailItem?.id) return;
    text("#frameActionStatus", "顔補正をキュー投入中...");
    const data = await api("/api/face-detailer/postprocess", {
      method: "POST",
      body: JSON.stringify({
        history_id: state.detailItem.id,
        settings: collectFaceSettings(true, "postprocess"),
      }),
    });
    UI.closeSheets();
    text("#fdStatus", "顔補正をキューに入れました");
    UI.toast("顔補正をキューに入れました");
    UI.safelight("developing", "FACE DETAILING");
    state.pollHadActive = true;
    await history.loadContact(true, { preserveLoadedWindow: true, reason: "face-detailer" });
    if (Array.isArray(data.warnings) && data.warnings.length) {
      UI.toast(data.warnings.slice(0, 2).join(" / "));
    }
  }

  async function queueFrameHandDetailer() {
    if (!state?.detailItem?.id) return;
    text("#frameActionStatus", "手補正をキュー投入中...");
    const data = await api("/api/hand-detailer/postprocess", {
      method: "POST",
      body: JSON.stringify({
        history_id: state.detailItem.id,
        settings: collectHandSettings(true, "postprocess"),
      }),
    });
    UI.closeSheets();
    text("#hdStatus", "手補正をキューに入れました");
    UI.toast("手補正をキューに入れました");
    UI.safelight("developing", "HAND DETAILING");
    state.pollHadActive = true;
    await history.loadContact(true, { preserveLoadedWindow: true, reason: "hand-detailer" });
    if (Array.isArray(data.warnings) && data.warnings.length) {
      UI.toast(data.warnings.slice(0, 2).join(" / "));
    }
  }

  return {
    collectFaceSettings,
    collectFaceDetailerSettings: collectFaceSettings,
    collectHandSettings,
    collectHandDetailerSettings: collectHandSettings,
    historyFaceRequest,
    historyFaceDetailerRequest: historyFaceRequest,
    historyHandRequest,
    historyHandDetailerRequest: historyHandRequest,
    applyFaceToForm,
    applyHandToForm,
    applyToForm,
    bindEvents,
    refreshSamplingOptions,
    restore,
    queueFrameFaceDetailer,
    queueFrameHandDetailer,
    setAllEnabled,
    snapshot,
    actions: {
      "frame-face-detail": () => queueFrameFaceDetailer(),
      "frame-hand-detail": () => queueFrameHandDetailer(),
      "detailers-enable-all": () => setAllEnabled(true),
      "detailers-disable-all": () => setAllEnabled(false),
    },
  };
}
