import {
  $,
  checked,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
  text,
  value,
} from "./dom.js?v=v1.41-background-reference-20260623";

const I2I_EMPTY_TEXT = "下絵は未選択です。履歴の「下絵にする」からも選べます。";

export function createI2iFeature({
  api,
  state,
  UI = window.UI,
  updateSummaries = () => {},
} = {}) {
  function collect() {
    const enabled = checked("#i2iEnabled") && Boolean(state.i2i.imageId);
    return {
      enabled,
      image_id: state.i2i.imageId,
      denoise: numberValue("#i2iDenoise", 0.45),
      resize_mode: value("#i2iResize", "fit"),
      use_source_size: checked("#i2iUseSource"),
      allow_with_hires_fix: false,
      allow_with_reference_assist: false,
    };
  }

  function history(item = {}) {
    const image = item.image_to_image && typeof item.image_to_image === "object" ? item.image_to_image : {};
    return {
      enabled: Boolean(image.enabled && image.image_id),
      image_id: String(image.image_id || ""),
      denoise: numberFrom(image.denoise, 0.45),
      resize_mode: String(image.resize_mode || "fit"),
      use_source_size: Boolean(image.use_source_size),
      allow_with_hires_fix: false,
      allow_with_reference_assist: false,
    };
  }

  function itemState(item = {}) {
    const imageId = String(item.image_id || "").trim();
    return {
      imageId,
      thumb: String(item.thumbnail_url || item.thumb || "").trim(),
      name: String(item.original_filename || item.filename || item.name || imageId || "").trim(),
    };
  }

  function renderPreview() {
    const root = $("#i2iPreview");
    if (!root) return;
    root.replaceChildren();
    if (!state.i2i.imageId) {
      root.classList.add("is-empty");
      root.textContent = I2I_EMPTY_TEXT;
      return;
    }
    root.classList.remove("is-empty");
    if (state.i2i.thumb) {
      const img = document.createElement("img");
      img.src = state.i2i.thumb;
      img.alt = state.i2i.name || "i2i source";
      img.loading = "lazy";
      img.decoding = "async";
      root.appendChild(img);
    }
    const label = document.createElement("span");
    label.textContent = state.i2i.name || state.i2i.imageId;
    root.appendChild(label);
  }

  function applyItem(item = {}, options = {}) {
    state.i2i = itemState(item);
    setChecked("#i2iEnabled", Boolean(state.i2i.imageId));
    renderPreview();
    if (options.update !== false) updateSummaries();
  }

  function applyToForm(image = {}, options = {}) {
    const imageId = image.enabled ? String(image.image_id || "") : "";
    state.i2i = { imageId, thumb: "", name: String(image.image_name || imageId || "") };
    setChecked("#i2iEnabled", Boolean(imageId));
    setValue("#i2iDenoise", image.denoise ?? 0.45);
    setValue("#i2iResize", image.resize_mode || "fit");
    setChecked("#i2iUseSource", Boolean(image.use_source_size));
    renderPreview();
    if (options.update !== false) updateSummaries();
  }

  function clearImage() {
    state.i2i = { imageId: "", thumb: "", name: "" };
    setChecked("#i2iEnabled", false);
    setValue("#i2iFile", "");
    text("#i2iStatus", "");
    renderPreview();
    updateSummaries();
  }

  async function uploadImage() {
    const input = $("#i2iFile");
    const file = input?.files?.[0];
    if (!file) {
      text("#i2iStatus", "下絵ファイルを選択してください");
      UI.toast("下絵ファイルを選択してください", "error");
      return;
    }
    text("#i2iStatus", "アップロード中...");
    const form = new FormData();
    form.append("file", file);
    const data = await api("/api/i2i/upload", {
      method: "POST",
      body: form,
    });
    applyItem(data.item);
    text("#i2iStatus", "下絵を設定しました");
    UI.toast("下絵を設定しました");
  }

  async function setFromHistoryItem(item = state.detailItem) {
    if (!item?.id) return;
    text("#frameActionStatus", "下絵を準備中...");
    const data = await api("/api/i2i/from-history", {
      method: "POST",
      body: JSON.stringify({ history_id: item.id }),
    });
    applyItem(data.item);
    UI.closeSheets();
    UI.switchTab("expose");
    const fold = $("details[data-fold='i2i']");
    if (fold) fold.open = true;
    text("#i2iStatus", "下絵を設定しました");
    UI.toast("下絵に設定しました");
  }

  function bindEvents() {}

  return {
    actions: {
      "i2i-upload": () => uploadImage(),
      "i2i-clear": () => clearImage(),
    },
    applyItem,
    applyToForm,
    bindEvents,
    clearImage,
    collect,
    history,
    renderPreview,
    setFromHistoryItem,
    uploadImage,
  };
}
