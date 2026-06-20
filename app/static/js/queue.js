import { $, text } from "./dom.js?v=v1.30-history-queue-module-20260620";

function fallbackErrorMessage(error) {
  return error?.data?.message || error?.data?.detail || error?.message || String(error);
}

export function createQueueFeature({
  api,
  state,
  UI = window.UI,
  confirmDanger = async () => false,
  errorMessage = fallbackErrorMessage,
  refreshHistory = async () => {},
} = {}) {
  function queueSheetIsOpen() {
    return Boolean($("#queueSheet")?.classList.contains("is-open"));
  }

  function stopQueuePolling() {
    if (state.queuePollTimer) {
      window.clearInterval(state.queuePollTimer);
      state.queuePollTimer = 0;
    }
  }

  function startQueuePolling() {
    stopQueuePolling();
    state.queuePollTimer = window.setInterval(() => {
      if (!queueSheetIsOpen()) {
        stopQueuePolling();
        return;
      }
      loadQueue(false).catch((error) => {
        text("#queueStatus", errorMessage(error));
      });
    }, 3000);
  }

  function setQueueLoading(message) {
    $("#queueList")?.replaceChildren();
    text("#queueCountLbl", "—");
    text("#queueStatus", message);
  }

  function queuePromptShort(promptId) {
    return String(promptId || "").slice(0, 8) || "unknown";
  }

  function queueRow(item = {}, stateName = "pending") {
    const row = document.createElement("div");
    row.style.display = "grid";
    row.style.gridTemplateColumns = stateName === "pending" ? "minmax(0, 1fr) auto" : "1fr";
    row.style.alignItems = "center";
    row.style.gap = "8px";

    const body = document.createElement("div");
    body.style.display = "flex";
    body.style.alignItems = "center";
    body.style.gap = "8px";
    body.style.minWidth = "0";

    const dot = document.createElement("span");
    dot.className = `queue-dot ${stateName === "running" ? "is-running" : ""}`.trim();
    dot.textContent = stateName === "running" ? "●" : "○";

    const label = document.createElement("span");
    label.textContent = `${stateName === "running" ? "実行中" : `#${item.position || "-"}`} · ${queuePromptShort(item.prompt_id)}`;

    body.append(dot, label);
    if (item.ours) {
      const ours = document.createElement("span");
      ours.className = "tag";
      ours.textContent = "このアプリ";
      body.appendChild(ours);
    }
    row.appendChild(body);

    if (stateName === "pending") {
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "ghost";
      cancel.dataset.queueCancelPromptId = item.prompt_id || "";
      cancel.textContent = "取消";
      row.appendChild(cancel);
    }
    return row;
  }

  function renderQueue(data = {}) {
    const root = $("#queueList");
    if (!root) return;
    const running = Array.isArray(data.running) ? data.running : [];
    const pending = Array.isArray(data.pending) ? data.pending : [];
    root.replaceChildren();
    for (const item of running) root.appendChild(queueRow(item, "running"));
    for (const item of pending) root.appendChild(queueRow(item, "pending"));
    text("#queueCountLbl", `実行中${running.length} · 待機${pending.length}`);
    text("#queueStatus", running.length || pending.length ? "" : "キューは空です");
  }

  async function loadQueue(showLoading = false) {
    if (showLoading) setQueueLoading("読み込み中...");
    const data = await api("/api/queue");
    renderQueue(data);
    return data;
  }

  async function openQueue() {
    UI.openSheet("#queueSheet");
    await loadQueue(true);
    startQueuePolling();
  }

  async function cancelQueuePrompt(promptId) {
    if (!promptId) return;
    const ok = await confirmDanger({
      title: "取消しますか?",
      message: `キュー ${queuePromptShort(promptId)} を取り消します。`,
      label: "取消する",
    });
    if (!ok) return;
    text("#queueStatus", "取消中...");
    await api("/api/queue/cancel", {
      method: "POST",
      body: JSON.stringify({ prompt_id: promptId }),
    });
    UI.toast("取消しました");
    await loadQueue(false);
    await refreshHistory().catch((error) => console.debug("history refresh after queue cancel failed", error));
  }

  async function interruptQueue() {
    const ok = await confirmDanger({
      title: "中断しますか?",
      message: "ComfyUIで実行中の生成を中断します。",
      label: "中断する",
    });
    if (!ok) return;
    text("#queueStatus", "中断を送信中...");
    await api("/api/queue/interrupt", {
      method: "POST",
      body: "{}",
    });
    UI.toast("中断しました");
    await loadQueue(false);
    await refreshHistory().catch((error) => console.debug("history refresh after interrupt failed", error));
  }

  function bindEvents() {
    $("#queueList")?.addEventListener("click", (event) => {
      const cancelTarget = event.target.closest("[data-queue-cancel-prompt-id]");
      if (!cancelTarget) return;
      cancelQueuePrompt(cancelTarget.dataset.queueCancelPromptId).catch((error) => {
        text("#queueStatus", errorMessage(error));
        UI.toast(errorMessage(error), "error");
      });
    });
  }

  return {
    actions: {
      "open-queue": () => openQueue(),
      "queue-refresh": () => loadQueue(true),
      "queue-interrupt": () => interruptQueue(),
    },
    bindEvents,
    cancelPrompt: cancelQueuePrompt,
    interrupt: interruptQueue,
    load: loadQueue,
    open: openQueue,
    render: renderQueue,
    startPolling: startQueuePolling,
    stopPolling: stopQueuePolling,
  };
}
