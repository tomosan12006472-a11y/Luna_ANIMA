import { clone, setChecked, text } from "./dom.js?v=v1.47-mobile-ops-public-save-20260625";

const SNAPSHOT_KEYS = [
  "official_loras",
  "official_lora_preset",
  "loras",
  "reference_modules",
  "image_to_image",
  "prompt_random_collect",
  "hires_fix",
  "face_detailer",
  "hand_detailer",
  "dynamic_prompt",
];

function copySnapshot(value) {
  try {
    return clone(value);
  } catch {
    return JSON.parse(JSON.stringify(value || {}));
  }
}

function compactOnOff(value) {
  return value ? "ON" : "OFF";
}

export function createTuningControlsFeature({
  UI = window.UI,
  loras,
  reference,
  detailers,
  promptRandom,
  i2i,
  generationForm,
  collectRequest = () => ({}),
  updateSummaries = () => {},
} = {}) {
  let tuningSnapshot = null;
  let assistSnapshot = null;
  let lastMessage = "snapshot未保存";

  function status(message) {
    if (message) {
      lastMessage = message;
      UI?.toast?.(message);
    }
    renderStatus();
  }

  function collectAssistSnapshot() {
    const request = collectRequest() || {};
    const snapshot = {};
    for (const key of SNAPSHOT_KEYS) {
      if (request[key] !== undefined) snapshot[key] = copySnapshot(request[key]);
    }
    return snapshot;
  }

  function restoreAssistSnapshot(snapshot = {}) {
    if (snapshot.official_loras) {
      loras?.applyOfficialToForm?.(copySnapshot(snapshot.official_loras), snapshot.official_lora_preset || "custom");
    }
    if (Array.isArray(snapshot.loras)) loras?.restoreRows?.(copySnapshot(snapshot.loras));
    if (snapshot.reference_modules) reference?.restoreModules?.(copySnapshot(snapshot.reference_modules), { update: false });
    if (snapshot.image_to_image) i2i?.restore?.(copySnapshot(snapshot.image_to_image), { update: false });
    if (snapshot.prompt_random_collect) promptRandom?.applyToForm?.(copySnapshot(snapshot.prompt_random_collect));
    if (snapshot.hires_fix) generationForm?.restoreHires?.(copySnapshot(snapshot.hires_fix));
    if (snapshot.face_detailer || snapshot.hand_detailer) {
      detailers?.applyToForm?.({
        face_detailer: copySnapshot(snapshot.face_detailer || {}),
        hand_detailer: copySnapshot(snapshot.hand_detailer || {}),
      });
    }
    if (snapshot.dynamic_prompt && snapshot.dynamic_prompt.enabled !== undefined) {
      generationForm?.setDynamicPromptEnabled?.(snapshot.dynamic_prompt.enabled);
    }
    updateSummaries();
  }

  function snapshot() {
    tuningSnapshot = collectAssistSnapshot();
    status("snapshot saved");
  }

  function restore() {
    if (!tuningSnapshot) {
      status("snapshotがありません");
      return;
    }
    restoreAssistSnapshot(tuningSnapshot);
    status("restored");
  }

  function setPromptRandomEnabled(enabled) {
    promptRandom?.setEnabled?.(enabled);
  }

  function setHiresEnabled(enabled) {
    generationForm?.setHiresEnabled?.(enabled);
  }

  function setDynamicEnabled(enabled) {
    if (generationForm?.setDynamicPromptEnabled) {
      generationForm.setDynamicPromptEnabled(enabled);
      return;
    }
    setChecked("#dynamicEnabled", Boolean(enabled));
  }

  function disableAllAssist() {
    assistSnapshot = collectAssistSnapshot();
    loras?.setAllEnabled?.(false);
    reference?.setAllEnabled?.(false);
    detailers?.setAllEnabled?.(false);
    setPromptRandomEnabled(false);
    setHiresEnabled(false);
    i2i?.setEnabled?.(false);
    setDynamicEnabled(false);
    updateSummaries();
    status("assist off");
  }

  function restoreAssist() {
    if (!assistSnapshot) {
      status("assist snapshotがありません");
      return;
    }
    restoreAssistSnapshot(assistSnapshot);
    status("assist restored");
  }

  function loraSummary() {
    const enabled = loras?.countEnabled?.() ?? 0;
    const disabled = loras?.countDisabled?.() ?? 0;
    return `LoRA ${enabled} ON / ${disabled} OFF`;
  }

  function referenceSummary(request) {
    const modules = request.reference_modules || {};
    const parts = [];
    if (modules.outfit?.enabled) parts.push("Outfit");
    if (modules.pose?.enabled) parts.push("Pose");
    if (modules.background?.enabled) parts.push("BG");
    return `Ref ${parts.length ? parts.join("+") : "OFF"}`;
  }

  function detailerSummary(request) {
    const parts = [];
    if (request.face_detailer?.enabled) parts.push("Face");
    if (request.hand_detailer?.enabled) parts.push("Hand");
    return `Detailer ${parts.length ? parts.join("+") : "OFF"}`;
  }

  function assistSummary(request = collectRequest()) {
    const req = request || {};
    const bits = [
      loraSummary(),
      referenceSummary(req),
      detailerSummary(req),
      `PR ${compactOnOff(req.prompt_random_collect?.enabled)}`,
      `Hires ${compactOnOff(req.hires_fix?.enabled)}`,
      `i2i ${compactOnOff(req.image_to_image?.enabled)}`,
      `Dyn ${compactOnOff(req.dynamic_prompt?.enabled)}`,
    ];
    return bits.join(" · ");
  }

  function renderStatus(request) {
    const target = "#tuningQuickStatus";
    if (!document.querySelector(target)) return;
    let summary = "";
    try {
      summary = assistSummary(request || collectRequest());
    } catch {
      summary = "状態を取得できません";
    }
    text(target, `${lastMessage} · ${summary}`);
  }

  return {
    actions: {
      "tuning-snapshot": () => snapshot(),
      "tuning-restore": () => restore(),
      "lora-enable-all": () => {
        loras?.setAllEnabled?.(true);
        status("LoRA all on");
      },
      "lora-disable-all": () => {
        loras?.setAllEnabled?.(false);
        status("LoRA all off");
      },
      "reference-enable-all": () => {
        reference?.setAllEnabled?.(true);
        status("Reference all on");
      },
      "reference-disable-all": () => {
        reference?.setAllEnabled?.(false);
        status("Reference all off");
      },
      "detailers-enable-all": () => {
        detailers?.setAllEnabled?.(true);
        status("Detailer all on");
      },
      "detailers-disable-all": () => {
        detailers?.setAllEnabled?.(false);
        status("Detailer all off");
      },
      "assist-disable-all": () => disableAllAssist(),
      "assist-restore": () => restoreAssist(),
    },
    disableAllAssist,
    renderStatus,
    restore,
    snapshot,
  };
}
