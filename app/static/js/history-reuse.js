import { createHistoryRequestFeature } from "./history-request.js?v=v1.59-public-image-url-version-20260628";
import { createHistoryReuseDataFeature } from "./history-reuse-data.js?v=v1.59-public-image-url-version-20260628";
import { createHistoryTextFeature } from "./history-text.js?v=v1.59-public-image-url-version-20260628";

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
  const historyText = createHistoryTextFeature({
    promptPresets,
  });
  const reuseDataFeature = createHistoryReuseDataFeature({
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
    updateSummaries,
  });
  const requestFeature = createHistoryRequestFeature({
    state,
    characters,
    promptRandom,
    i2i,
    reference,
    detailers,
    reuseDataFeature,
  });

  function applyHistoryToForm(item) {
    reuseDataFeature.applyHistoryReuseData(reuseDataFeature.historyReuseData(item));
    UI.closeSheets();
    UI.switchTab("expose");
    UI.toast("設定を再利用しました");
  }

  return {
    ...historyText,
    ...reuseDataFeature,
    ...requestFeature,
    applyHistoryToForm,
  };
}
