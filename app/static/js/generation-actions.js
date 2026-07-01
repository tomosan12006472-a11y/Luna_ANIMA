import {
  $,
  checked,
  setChecked,
  text,
} from "./dom.js?v=v1.67-lora-strength-max-3-20260702";

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
      $("#payloadPreviewPanel")?.classList.remove("hidden");
    }
  }

  function closePayloadPreview() {
    $("#payloadPreviewPanel")?.classList.add("hidden");
  }

  function assertGenerateQueued(data) {
    if (data.status !== "queued" && data.status !== "partial") {
      throw Object.assign(new Error(data.message || "露光できませんでした"), { data });
    }
  }

  function generateQueuedCount(data, request) {
    return Number(data.queued_count || data.items?.length || request.count || 1);
  }

  function comfyCacheResetStatusMessage(metadata = {}) {
    if (metadata.applied) return "ComfyUI cacheを解放してから投入しました";
    if (metadata.skipped && metadata.reason === "no_fixed_character") return "固定キャラ指定がないためcache解放はスキップされました";
    if (metadata.skipped) return `cache解放はスキップされました${metadata.reason ? `: ${metadata.reason}` : ""}`;
    if (metadata.reason === "queue_not_empty") return "queueが空ではないためcache解放できませんでした";
    if (metadata.reason || metadata.error) return `cache解放できませんでした${metadata.reason ? `: ${metadata.reason}` : ""}`;
    if (metadata.requested) return "ComfyUI cache解放リクエストを送信しました";
    return "";
  }

  function finishComfyCacheResetStatus(data = {}, request = {}) {
    if (!request.reset_comfy_cache) {
      text("#comfyCacheResetStatus", "");
      return;
    }
    const message = comfyCacheResetStatusMessage(data.comfy_cache_reset || {});
    if (message) {
      text("#comfyCacheResetStatus", message);
      UI.toast(message);
    }
    setChecked("#resetComfyCache", false);
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
    finishComfyCacheResetStatus(data, request);
    state.pollHadActive = true;
    await history.loadContact(true, { preserveLoadedWindow: true, reason: "generate" });
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
    closePayloadPreview,
    generate,
    generateFrameVariations,
    assertGenerateQueued,
    finishGenerateQueued,
    actions: {
      preview: () => previewPayload(),
      "payload-preview-close": () => closePayloadPreview(),
      generate: () => generate(),
      "frame-variations": () => generateFrameVariations(),
    },
  };
}
