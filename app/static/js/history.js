import {
  $,
  $$,
  checked,
  displayValue,
  escapePathSegment,
  formatDate,
  modelFileName,
  text,
} from "./dom.js?v=v1.35-detailer-module-20260620";

const CONTACT_LIMIT = 24;
const ACTIVE_STATUSES = new Set(["queued", "running"]);

function fallbackErrorMessage(error) {
  return error?.data?.message || error?.data?.detail || error?.message || String(error);
}

export function createHistoryFeature({
  api,
  fetchWithAuthHandling,
  state,
  UI = window.UI,
  errorMessage = fallbackErrorMessage,
  isUnauthorized = () => false,
  loras,
  addMetaRow,
  characterSummary,
  historyPositiveText,
  historyNegativeText,
  collectWatermark,
} = {}) {
  function isActiveItem(item) {
    return ACTIVE_STATUSES.has(String(item?.status || ""));
  }

  function isCompletedItem(item) {
    const status = String(item?.status || "completed");
    return status === "completed" || Boolean(item?.thumbnail_url || item?.thumbnail_small_url);
  }

  function contactServerFilter() {
    return state.contactFilter === "favorite" ? "favorite" : "all";
  }

  function contactSearchFieldValue(selector) {
    return String($(selector)?.value || "").trim();
  }

  function collectContactSearchFromUi() {
    return {
      q: contactSearchFieldValue("#contactSearchQ"),
      dateFrom: contactSearchFieldValue("#contactDateFrom"),
      dateTo: contactSearchFieldValue("#contactDateTo"),
      model: contactSearchFieldValue("#contactSearchModel"),
      lora: contactSearchFieldValue("#contactSearchLora"),
      seed: contactSearchFieldValue("#contactSearchSeed"),
      rating: contactSearchFieldValue("#contactSearchRating"),
      hiresMode: contactSearchFieldValue("#contactSearchHires"),
      reference: contactSearchFieldValue("#contactSearchReference"),
      sampler: contactSearchFieldValue("#contactSearchSampler"),
      scheduler: contactSearchFieldValue("#contactSearchScheduler"),
      character: contactSearchFieldValue("#contactSearchCharacter"),
      requestSeq: state.contactSearch?.requestSeq || 0,
    };
  }

  function contactSearchParams() {
    const params = {
      q: state.contactSearch.q,
      date_from: state.contactSearch.dateFrom,
      date_to: state.contactSearch.dateTo,
      model: state.contactSearch.model,
      lora: state.contactSearch.lora,
      seed: state.contactSearch.seed,
      rating: state.contactSearch.rating,
      hires_mode: state.contactSearch.hiresMode,
      reference: state.contactSearch.reference,
      sampler: state.contactSearch.sampler,
      scheduler: state.contactSearch.scheduler,
      character: state.contactSearch.character,
    };
    return Object.fromEntries(Object.entries(params).filter(([, value]) => String(value || "").trim()));
  }

  function hasActiveContactSearch() {
    return Object.keys(contactSearchParams()).length > 0;
  }

  function updateContactSearchStatus(total = state.contactTotal) {
    const badge = $("#contactSearchBadge");
    const status = $("#contactSearchStatus");
    const active = hasActiveContactSearch();
    if (badge) badge.textContent = active ? "適用中" : "";
    if (!status) return;
    status.textContent = active ? `検索結果: ${Number(total || 0)}件` : "";
  }

  function clearContactSearchForm() {
    for (const selector of [
      "#contactSearchQ",
      "#contactDateFrom",
      "#contactDateTo",
      "#contactSearchModel",
      "#contactSearchLora",
      "#contactSearchSeed",
      "#contactSearchRating",
      "#contactSearchHires",
      "#contactSearchReference",
      "#contactSearchSampler",
      "#contactSearchScheduler",
      "#contactSearchCharacter",
    ]) {
      const el = $(selector);
      if (el) el.value = "";
    }
  }

  async function applyContactSearch() {
    state.contactSearch = collectContactSearchFromUi();
    state.contactSearch.requestSeq += 1;
    state.contactLoaded = true;
    state.contactRevision = "";
    return loadContact(true);
  }

  async function clearContactSearch() {
    clearContactSearchForm();
    state.contactSearch = { ...state.contactSearch, ...collectContactSearchFromUi(), requestSeq: (state.contactSearch?.requestSeq || 0) + 1 };
    state.contactRevision = "";
    return loadContact(true);
  }

  async function refreshContact(options = {}) {
    state.contactRevision = "";
    state.contactPollFailures = 0;
    state.contactLoaded = true;
    text("#contactCount", "更新中...");
    const data = await loadContact(true);
    if (!options.silent) UI.toast("履歴を更新しました");
    return data;
  }

  function visibleContactItems(items) {
    if (state.contactFilter !== "active") return items;
    return items.filter(isActiveItem);
  }

  function frameNumber(item, fallbackIndex) {
    const absoluteIndex = Number.isFinite(item?._absoluteIndex) ? item._absoluteIndex : fallbackIndex;
    const no = Math.max(1, Number(state.contactTotal || 0) - absoluteIndex);
    return `#${String(no).padStart(4, "0")}`;
  }

  function renderContact() {
    const root = $("#contactGrid");
    if (!root) return;
    root.replaceChildren();
    if (!state.contactItems.length) {
      const frame = document.createElement("div");
      frame.className = "frame is-pending";
      const label = document.createElement("span");
      label.className = "no";
      label.textContent = "EMPTY";
      frame.appendChild(label);
      root.appendChild(frame);
    }

    state.contactItems.forEach((item, index) => {
      const previousStatus = state.contactStatusById.get(item.id);
      const status = String(item.status || (item.thumbnail_url ? "completed" : "queued"));
      const button = document.createElement("button");
      button.type = "button";
      button.className = "frame";
      button.dataset.historyId = item.id || "";

      if (isCompletedItem(item)) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.decoding = "async";
        img.alt = item.filename || item.id || "";
        img.src = item.thumbnail_small_url || item.thumbnail_url || `/api/history/${escapePathSegment(item.id)}/thumbnail-small`;
        button.appendChild(img);
        if (previousStatus && ACTIVE_STATUSES.has(previousStatus) && status === "completed") {
          window.setTimeout(() => UI.markDeveloping(img), 0);
        }
      } else {
        button.classList.add(status === "failed" || status === "stale" || status === "missing" ? "is-failed" : "is-pending");
        const dot = document.createElement("span");
        dot.className = "dev-dot";
        button.appendChild(dot);
      }

      const no = document.createElement("span");
      no.className = "no";
      no.textContent = `${frameNumber(item, index)} · ${status || "completed"}`;
      button.appendChild(no);
      root.appendChild(button);
      if (item.id) state.contactStatusById.set(item.id, status);
    });
    text("#contactCount", `${state.contactItems.length} / ${state.contactTotal || 0}`);
    updateContactSearchStatus();
  }

  function stopContactPolling(message = "") {
    if (state.contactPollTimer) {
      window.clearInterval(state.contactPollTimer);
      state.contactPollTimer = 0;
    }
    state.pollHadActive = false;
    if (message) text("#contactCount", message);
  }

  function handleContactPollingError(error) {
    console.warn(error);
    if (isUnauthorized(error)) {
      stopContactPolling("履歴更新停止: ログイン切れ");
      return;
    }
    state.contactPollFailures += 1;
    if (state.contactPollFailures >= 3) {
      stopContactPolling("履歴更新停止: 通信エラー");
      UI.toast("履歴更新に連続失敗したため自動更新を停止しました", "error");
    }
  }

  function updateContactPolling(activeCount) {
    if (activeCount > 0) {
      state.pollHadActive = true;
      if (!state.contactPollTimer) {
        state.contactPollTimer = window.setInterval(() => {
          loadContact(false, { polling: true, knownRevision: true }).catch(handleContactPollingError);
        }, 3000);
      }
      return;
    }
    if (state.contactPollTimer) {
      window.clearInterval(state.contactPollTimer);
      state.contactPollTimer = 0;
    }
    if (state.pollHadActive) {
      state.pollHadActive = false;
      UI.safelight("idle");
      UI.toast("現像完了");
    }
  }

  async function loadContact(reset = false, options = {}) {
    const replaceItems = reset || options.polling;
    const offset = replaceItems ? 0 : state.contactOffset;
    const limit = options.polling
      ? Math.max(state.contactOffset || CONTACT_LIMIT, CONTACT_LIMIT)
      : state.contactFilter === "active" ? 100 : CONTACT_LIMIT;
    const params = new URLSearchParams({
      view: "list",
      limit: String(limit),
      offset: String(offset),
      filter: contactServerFilter(),
    });
    const seq = state.contactSearch.requestSeq || 0;
    for (const [key, value] of Object.entries(contactSearchParams())) {
      params.set(key, value);
    }
    if (options.knownRevision && state.contactRevision) params.set("known_revision", state.contactRevision);
    const data = await api(`/api/history?${params.toString()}`);
    if (seq !== (state.contactSearch.requestSeq || 0)) return data;
    state.contactPollFailures = 0;
    if (data.unchanged) {
      updateContactPolling((state.contactItems || []).filter(isActiveItem).length);
      return data;
    }

    const pageItems = (Array.isArray(data.items) ? data.items : []).map((item, index) => ({
      ...item,
      _absoluteIndex: Number(data.offset || 0) + index,
    }));
    const visibleItems = visibleContactItems(pageItems);
    state.contactItems = replaceItems ? visibleItems : [...state.contactItems, ...visibleItems];
    state.contactOffset = Number(data.offset || 0) + pageItems.length;
    state.contactRevision = data.revision || state.contactRevision;
    state.contactLoaded = true;
    state.contactTotal = state.contactFilter === "active"
      ? Number(data.summary?.active ?? visibleItems.length)
      : Number(data.filtered_total ?? data.total ?? visibleItems.length);

    $("#loadMoreBtn")?.classList.toggle("hidden", !data.has_more || state.contactFilter === "active");
    updateContactSearchStatus(state.contactTotal);
    renderContact();
    const activeCount = Number(data.summary?.active ?? state.contactItems.filter(isActiveItem).length);
    updateContactPolling(activeCount);
    return data;
  }

  function updateFrameFavoriteButton(item = state.detailItem) {
    const button = $("[data-action='frame-favorite']");
    const favorite = Boolean(item?.flags?.favorite);
    if (button) button.textContent = `${favorite ? "★" : "☆"} お気に入り`;
  }

  function renderFrameDetail(item) {
    state.detailItem = item;
    text("#frameActionStatus", "");
    const image = $("#frameImage");
    const imageUrl = item.image_url || item.thumbnail_url || item.thumbnail_small_url || "";
    if (image && imageUrl) {
      image.src = imageUrl;
      image.alt = item.filename || item.id || "生成画像";
    } else if (image) {
      image.removeAttribute("src");
      image.alt = "画像なし";
    }
    updateFrameFavoriteButton(item);
    const table = $("#frameMeta");
    if (table) {
      table.replaceChildren();
      addMetaRow(table, "FRAME", item.id);
      addMetaRow(table, "TIME", formatDate(item.created_at));
      addMetaRow(table, "SEED", item.seed);
      addMetaRow(table, "SIZE", `${item.output_width || item.width || "-"}×${item.output_height || item.height || "-"}`);
      addMetaRow(table, "STEPS·CFG·SHIFT", `${displayValue(item.steps)} · ${displayValue(item.cfg)} · ${displayValue(item.shift ?? item.model_sampling?.shift)}`);
      addMetaRow(table, "SAMPLER·SCHEDULER", `${displayValue(item.sampler)} · ${displayValue(item.scheduler)}`);
      addMetaRow(table, "MODEL", modelFileName(item.model));
      addMetaRow(table, "RATING", item.rating || "-");
      addMetaRow(table, "CHARACTERS", characterSummary(item));
      addMetaRow(table, "LORA", loras.summary(item.loras || []));
      addMetaRow(table, "POSITIVE", historyPositiveText(item), true);
      addMetaRow(table, "NEGATIVE", historyNegativeText(item), true);
    }
    UI.openSheet("#frameSheet");
  }

  async function openFrameDetail(id) {
    const data = await api(`/api/history/${escapePathSegment(id)}`);
    renderFrameDetail(data.item);
  }

  async function toggleFrameFavorite() {
    if (!state.detailItem?.id) return;
    const nextFavorite = !state.detailItem.flags?.favorite;
    const data = await api(`/api/history/${escapePathSegment(state.detailItem.id)}/flags`, {
      method: "POST",
      body: JSON.stringify({ favorite: nextFavorite }),
    });
    state.detailItem = data.item;
    updateFrameFavoriteButton(data.item);
    text("#frameActionStatus", nextFavorite ? "お気に入りにしました" : "お気に入りを解除しました");
    await loadContact(true).catch(() => {});
  }

  function publicImageUrl(item = state.detailItem) {
    if (!item?.id) return "";
    return item.public_image_url || (item.public_save?.saved ? `/api/history/${escapePathSegment(item.id)}/public-image` : "");
  }

  function absoluteUrl(path) {
    return new URL(path, window.location.href).toString();
  }

  async function savePublicImage() {
    if (!state.detailItem?.id) return null;
    const data = await api(`/api/history/${escapePathSegment(state.detailItem.id)}/public-save`, {
      method: "POST",
      body: JSON.stringify({
        apply_watermark: checked("#watermarkEnabled"),
        watermark: collectWatermark(),
        watermark_client: "current",
      }),
    });
    state.detailItem = data.item || state.detailItem;
    text("#frameActionStatus", "公開保存しました");
    return data;
  }

  async function shareFrame() {
    if (!state.detailItem?.id) return;
    try {
      text("#frameActionStatus", "共有用画像を準備中...");
      const data = await savePublicImage();
      const item = data?.item || state.detailItem;
      const imageUrl = data?.public_image_url || publicImageUrl(item);
      if (!imageUrl) throw new Error("公開画像URLを取得できませんでした");
      const response = await fetchWithAuthHandling(imageUrl);
      const blob = await response.blob();
      const filename = String(data?.filename || item.filename || `${item.id}_public.png`).replace(/[^\w.-]/g, "_");
      const file = new File([blob], filename, { type: blob.type || "image/png" });
      const canShare = Boolean(navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] })));
      if (!canShare) {
        window.open(absoluteUrl(imageUrl), "_blank", "noopener");
        text("#frameActionStatus", "共有非対応: 開いた画像を長押し保存してください");
        UI.toast("共有非対応です。画像を開きました");
        return;
      }
      await navigator.share({ files: [file] });
      text("#frameActionStatus", "共有シートを開きました");
      UI.toast("共有シートを開きました");
    } catch (error) {
      if (error?.name === "AbortError") {
        text("#frameActionStatus", "共有キャンセル");
        return;
      }
      text("#frameActionStatus", errorMessage(error));
      UI.toast(errorMessage(error), "error");
    }
  }

  function bindEvents() {
    UI.onTab((name) => {
      if (name === "contact" && !state.contactLoaded) {
        loadContact(true).catch((error) => UI.toast(errorMessage(error), "error"));
      }
    });

    $("#contactFilters")?.addEventListener("click", (event) => {
      const chip = event.target.closest(".chip[data-filter]");
      if (!chip) return;
      state.contactFilter = chip.dataset.filter || "all";
      $$("#contactFilters .chip").forEach((item) => item.classList.toggle("is-active", item === chip));
      state.contactRevision = "";
      loadContact(true).catch((error) => UI.toast(errorMessage(error), "error"));
    });

    $("#contactSearchPanel")?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      const target = event.target;
      if (!target?.matches?.("input, select")) return;
      event.preventDefault();
      applyContactSearch().catch((error) => UI.toast(errorMessage(error), "error"));
    });

    $("#contactGrid")?.addEventListener("click", (event) => {
      const frame = event.target.closest(".frame[data-history-id]");
      if (!frame?.dataset.historyId) return;
      openFrameDetail(frame.dataset.historyId).catch((error) => UI.toast(errorMessage(error), "error"));
    });
  }

  return {
    actions: {
      "history-refresh": () => refreshContact(),
      "load-more": () => loadContact(false),
      "contact-search": () => applyContactSearch(),
      "contact-search-clear": () => clearContactSearch(),
      "frame-favorite": () => toggleFrameFavorite(),
      "frame-public-save": () => savePublicImage(),
      "frame-share": () => shareFrame(),
    },
    applyContactSearch,
    bindEvents,
    clearContactSearch,
    loadContact,
    openFrameDetail,
    refreshContact,
    renderContact,
    renderFrameDetail,
    savePublicImage,
    shareFrame,
    toggleFrameFavorite,
  };
}
