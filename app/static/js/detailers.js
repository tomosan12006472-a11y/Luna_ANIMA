import {
  checked,
  intFrom,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
  text,
} from "./dom.js?v=v1.61-history-pagination-diagnostics-hardfix-20260629";

export function createDetailerFeature({
  api,
  state,
  UI = window.UI,
  history,
  updateSummaries = () => {},
} = {}) {
  function collectFaceSettings(enabled = checked("#fdEnabled"), mode = "generation") {
    return {
      enabled: Boolean(enabled),
      mode,
      detector: "bbox/face_yolov8m.pt",
      steps: Math.trunc(numberValue("#fdSteps", 12)),
      cfg: numberValue("#fdCfg", 4.0),
      denoise: numberValue("#fdDenoise", 0.3),
      guide_size: 512,
      max_size: 1024,
      bbox_threshold: numberValue("#fdBbox", 0.5),
      bbox_dilation: 10,
      bbox_crop_factor: 3.0,
      sam_enabled: false,
      seed_policy: "image_seed_plus_offset",
      seed_offset: 100000,
    };
  }

  function collectHandSettings(enabled = checked("#hdEnabled"), mode = "generation") {
    return {
      enabled: Boolean(enabled),
      mode,
      detector: "bbox/hand_yolov8s.pt",
      steps: Math.trunc(numberValue("#hdSteps", 14)),
      cfg: numberValue("#hdCfg", 4.0),
      denoise: numberValue("#hdDenoise", 0.45),
      guide_size: 512,
      max_size: 1024,
      bbox_threshold: numberValue("#hdBbox", 0.35),
      bbox_dilation: 16,
      bbox_crop_factor: 2.5,
      drop_size: 24,
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
      detector: String(face.detector || "bbox/face_yolov8m.pt"),
      steps: intFrom(face.steps, 12),
      cfg: numberFrom(face.cfg, 4.0),
      denoise: numberFrom(face.denoise, 0.3),
      guide_size: intFrom(face.guide_size, 512),
      max_size: intFrom(face.max_size, 1024),
      bbox_threshold: numberFrom(face.bbox_threshold, 0.5),
      bbox_dilation: intFrom(face.bbox_dilation, 10),
      bbox_crop_factor: numberFrom(face.bbox_crop_factor, 3.0),
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
      detector: String(hand.detector || "bbox/hand_yolov8s.pt"),
      steps: intFrom(hand.steps, 14),
      cfg: numberFrom(hand.cfg, 4.0),
      denoise: numberFrom(hand.denoise, 0.45),
      guide_size: intFrom(hand.guide_size, 512),
      max_size: intFrom(hand.max_size, 1024),
      bbox_threshold: numberFrom(hand.bbox_threshold, 0.35),
      bbox_dilation: intFrom(hand.bbox_dilation, 16),
      bbox_crop_factor: numberFrom(hand.bbox_crop_factor, 2.5),
      drop_size: intFrom(hand.drop_size, 24),
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
    setValue("#fdSteps", face.steps ?? 12);
    setValue("#fdCfg", face.cfg ?? 4.0);
    setValue("#fdDenoise", face.denoise ?? 0.3);
    setValue("#fdBbox", face.bbox_threshold ?? 0.5);
  }

  function applyHandToForm(hand = {}) {
    setChecked("#hdEnabled", Boolean(hand.enabled));
    setValue("#hdSteps", hand.steps ?? 14);
    setValue("#hdCfg", hand.cfg ?? 4.0);
    setValue("#hdDenoise", hand.denoise ?? 0.45);
    setValue("#hdBbox", hand.bbox_threshold ?? 0.35);
    setValue("#hdLlliteStrength", hand.lllite_strength ?? hand.lllite?.strength ?? 0.85);
  }

  function applyToForm(data = {}) {
    applyFaceToForm(data.face_detailer || {});
    applyHandToForm(data.hand_detailer || {});
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
