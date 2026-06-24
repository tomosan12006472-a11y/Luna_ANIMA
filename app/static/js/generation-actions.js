import {
  $,
  checked,
  text,
} from "./dom.js?v=v1.42-lora-ux-controls-20260624";

export function createGenerationActionsFeature({
  api,
  state,
  UI = window.UI,
  errorMessage,
  collectRequest = () => ({}),
  generationForm,
  history,
  historyReuse,
  promptRandom,
} = {}) {
  function canSubmitGenerateRequest() {
    if (checked("#i2iEnabled") && !state.i2i.imageId) {
      text("#i2iStatus", "下絵が未選択です");
      UI.toast("下絵が未選択です", "error");
      return false;
    }
    if (checked("#outfitEnabled") && !state.refmod.outfit.imageId) {
      text("#refModStatus", "Outfit参照が未選択です");
      UI.toast("Outfit参照が未選択です", "error");
      return false;
    }
    if (checked("#poseEnabled") && !state.refmod.pose.imageId) {
      text("#refModStatus", "Pose参照が未選択です");
      UI.toast("Pose参照が未選択です", "error");
      return false;
    }
    if (checked("#backgroundEnabled") && !state.refmod.background.imageId) {
      text("#refModStatus", "Background Referenceが未選択です");
      UI.toast("Background Referenceが未選択です", "error");
      return false;
    }
    return true;
  }

  async function previewPayload() {
    const request = collectRequest();
    if (request.prompt_random_collect?.enabled) promptRandom.setStatus("AIタグ生成中...");
    const data = await api("/api/payload/preview", {
      method: "POST",
      body: JSON.stringify(request),
    });
    if (request.prompt_random_collect?.enabled) promptRandom.setStatus("AIタグをPreviewに反映しました");
    const preview = $("#payloadPreview");
    if (preview) {
      preview.textContent = JSON.stringify(data, null, 2);
      preview.classList.remove("hidden");
    }
  }

  function assertGenerateQueued(data) {
    if (data.status !== "queued" && data.status !== "partial") {
      throw Object.assign(new Error(data.message || "露光できませんでした"), { data });
    }
  }

  function generateQueuedCount(data, request) {
    return Number(data.queued_count || data.items?.length || request.count || 1);
  }

  async function finishGenerateQueued(data, request, options = {}) {
    const queued = generateQueuedCount(data, request);
    const toastMessage = typeof options.toast === "function"
      ? options.toast(queued)
      : options.toast || `${queued}枚 露光しました`;
    const safelightMessage = typeof options.safelight === "function"
      ? options.safelight(queued)
      : options.safelight || `${queued} FRAMES DEVELOPING`;
    UI.toast(toastMessage);
    UI.safelight("developing", safelightMessage);
    state.pollHadActive = true;
    await history.loadContact(true);
    return queued;
  }

  async function generate() {
    if (!canSubmitGenerateRequest()) return;
    const button = $("#exposeBtn");
    button?.setAttribute("disabled", "disabled");
    try {
      const request = collectRequest();
      if (request.prompt_random_collect?.enabled) {
        promptRandom.setStatus("AIタグ生成中...");
        UI.safelight("developing", "RANDOM COLLECT");
      }
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(request),
      });
      if (request.prompt_random_collect?.enabled) promptRandom.setStatus("AIタグを反映して投入しました");
      assertGenerateQueued(data);
      await finishGenerateQueued(data, request);
    } catch (error) {
      UI.toast(errorMessage(error), "error");
      UI.safelight("error");
    } finally {
      button?.removeAttribute("disabled");
    }
  }

  async function generateFrameVariations() {
    if (!state.detailItem?.id) return;
    const count = generationForm.selectedVariationCount();
    const request = historyReuse.buildVariationRequest(state.detailItem, count);
    try {
      text("#frameActionStatus", "バリエーションをキュー投入中...");
      const data = await api("/api/generate", {
        method: "POST",
        body: JSON.stringify(request),
      });
      assertGenerateQueued(data);
      UI.closeSheets();
      await finishGenerateQueued(data, request, {
        toast: (queued) => `🎲 ${queued}枚キューに入れました`,
      });
    } catch (error) {
      text("#frameActionStatus", errorMessage(error));
      UI.toast(errorMessage(error), "error");
    }
  }

  return {
    canSubmitGenerateRequest,
    previewPayload,
    generate,
    generateFrameVariations,
    assertGenerateQueued,
    finishGenerateQueued,
    actions: {
      preview: () => previewPayload(),
      generate: () => generate(),
      "frame-variations": () => generateFrameVariations(),
    },
  };
}
