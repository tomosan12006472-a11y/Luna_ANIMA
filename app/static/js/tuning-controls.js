import { clone, setChecked, text } from "./dom.js?v=v2.1-polish-20260702";

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
  let lastMessage = "記録なし";

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
    if (loras?.snapshotOfficialUiState) snapshot.official_ui_state = copySnapshot(loras.snapshotOfficialUiState());
    return snapshot;
  }

  function restoreAssistSnapshot(snapshot = {}) {
    if (snapshot.official_ui_state && loras?.restoreOfficialUiState) {
      loras.restoreOfficialUiState(copySnapshot(snapshot.official_ui_state));
    } else if (snapshot.official_loras) {
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
    status("記録しました");
  }

  function restore() {
    if (!tuningSnapshot) {
      status("記録がありません");
      return;
    }
    restoreAssistSnapshot(tuningSnapshot);
    status("復元しました");
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
    status("補助をOFFにしました");
  }

  function restoreAssist() {
    if (!assistSnapshot) {
      status("補助の記録がありません");
      return;
    }
    restoreAssistSnapshot(assistSnapshot);
    status("補助を復元しました");
  }

  function loraSummary() {
    const enabled = loras?.countEnabled?.() ?? 0;
    const disabled = loras?.countDisabled?.() ?? 0;
    return `LoRA ${enabled}/${enabled + disabled}`;
  }

  function referenceSummary(request) {
    const modules = request.reference_modules || {};
    const parts = [];
    if (modules.outfit?.enabled) parts.push("Outfit");
    if (modules.pose?.enabled) parts.push("Pose");
    if (modules.background?.enabled) parts.push("BG");
    return `参照 ${parts.length ? parts.join("+") : "OFF"}`;
  }

  function detailerSummary(request) {
    const parts = [];
    if (request.face_detailer?.enabled) parts.push("顔");
    if (request.hand_detailer?.enabled) parts.push("手");
    return `補正 ${parts.length ? parts.join("+") : "OFF"}`;
  }

  function assistSummary(request = collectRequest()) {
    const req = request || {};
    const bits = [
      loraSummary(),
      referenceSummary(req),
      detailerSummary(req),
      `ランダム ${compactOnOff(req.prompt_random_collect?.enabled)}`,
      `高解像 ${compactOnOff(req.hires_fix?.enabled)}`,
      `下絵 ${compactOnOff(req.image_to_image?.enabled)}`,
      `動的 ${compactOnOff(req.dynamic_prompt?.enabled)}`,
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
        status("LoRAをONにしました");
      },
      "lora-disable-all": () => {
        loras?.setAllEnabled?.(false);
        status("LoRAをOFFにしました");
      },
      "reference-enable-all": () => {
        reference?.setAllEnabled?.(true);
        status("参照をONにしました");
      },
      "reference-disable-all": () => {
        reference?.setAllEnabled?.(false);
        status("参照をOFFにしました");
      },
      "detailers-enable-all": () => {
        detailers?.setAllEnabled?.(true);
        status("補正をONにしました");
      },
      "detailers-disable-all": () => {
        detailers?.setAllEnabled?.(false);
        status("補正をOFFにしました");
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
