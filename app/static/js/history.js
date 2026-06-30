import {
  $,
  $$,
  checked,
  displayValue,
  escapePathSegment,
  formatDate,
  modelFileName,
  text,
} from "./dom.js?v=v1.63-history-generation-metrics-20260630";

const CONTACT_LIMIT = 24;
const ACTIVE_STATUSES = new Set(["queued", "running"]);
const PUBLIC_SAVE_POLL_INTERVAL_MS = 1200;
const PUBLIC_SAVE_MAX_POLLS = 90;
const HISTORY_RUNTIME_TOKEN = "v1.63-history-generation-metrics-20260630";
const HISTORY_DEBUG_EVENT_LIMIT = 20;

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
  collectPublicSaveFinish = () => ({ finish_enabled: false, finish_preset: "krita_itsumono" }),
  collectPublicSaveRequestSettings = null,
} = {}) {
  const textProviders = {
    historyPositiveText: typeof historyPositiveText === "function" ? historyPositiveText : () => "",
    historyNegativeText: typeof historyNegativeText === "function" ? historyNegativeText : () => "",
  };
  let publicSavePollSeq = 0;
  let shareBlobPrefetchSeq = 0;
  let shareBlobCache = null;
  let contactListRequestSeq = 0;
  let contactListContextSeq = Number(state.contactListContextSeq || 0);

  function setTextProviders(providers = {}) {
    if (typeof providers.historyPositiveText === "function") {
      textProviders.historyPositiveText = providers.historyPositiveText;
    }
    if (typeof providers.historyNegativeText === "function") {
      textProviders.historyNegativeText = providers.historyNegativeText;
    }
  }

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

  function historyDebugEnabled() {
    try {
      const params = new URLSearchParams(window.location.search || "");
      if (params.get("debug_history") === "1") return true;
      const flag = localStorage.getItem("lunaAnimaHistoryDebug");
      return flag === "1" || flag === "true";
    } catch {
      return false;
    }
  }

  function domFrameCount() {
    return $("#contactGrid")?.querySelectorAll(".frame").length || 0;
  }

  function activeSearchParamCount() {
    return Object.keys(contactSearchParams()).length;
  }

  function loadedWindowLimit() {
    return Math.max(
      CONTACT_LIMIT,
      Number(state.contactLoadedWindowLimit || 0),
      Number(state.contactOffset || 0),
      Array.isArray(state.contactItems) ? state.contactItems.length : 0,
    );
  }

  function historyDebugSnapshot(extra = {}) {
    return {
      token: HISTORY_RUNTIME_TOKEN,
      contactItems: Array.isArray(state.contactItems) ? state.contactItems.length : 0,
      domFrames: domFrameCount(),
      contactOffset: Number(state.contactOffset || 0),
      contactLoadedWindowLimit: Number(state.contactLoadedWindowLimit || 0),
      contactTotal: Number(state.contactTotal || 0),
      contactHasMore: Boolean(state.contactHasMore),
      contactFilter: state.contactFilter || "all",
      activeSearchParams: activeSearchParamCount(),
      contactRevisionLimit: Number(state.contactRevisionLimit || 0),
      contactRevisionOffset: Number(state.contactRevisionOffset || 0),
      contactLoadMoreInFlight: Boolean(state.contactLoadMoreInFlight),
      contactRefreshInFlight: Boolean(state.contactRefreshInFlight),
      contactPollingInFlight: Boolean(state.contactPollingInFlight),
      lastRequest: state.contactLastRequest || {},
      lastResponse: state.contactLastResponse || {},
      lastApplied: state.contactLastApplied || {},
      lastIgnored: state.contactLastIgnored || {},
      lastRender: state.contactLastRender || {},
      ...extra,
    };
  }

  function renderHistoryDebug() {
    const panel = $("#historyDebugPanel");
    const meta = $("#historyDebugMeta");
    if (!panel || !meta) return;
    const enabled = historyDebugEnabled();
    panel.classList.toggle("hidden", !enabled);
    if (!enabled) return;
    const snapshot = historyDebugSnapshot();
    const events = (state.historyDebugEvents || []).slice(-6).map((event) => (
      `${event.time} ${event.event} ${JSON.stringify(event.data || {})}`
    ));
    meta.textContent = [
      `token ${snapshot.token}`,
      `items/dom ${snapshot.contactItems}/${snapshot.domFrames} offset ${snapshot.contactOffset} window ${snapshot.contactLoadedWindowLimit}`,
      `total ${snapshot.contactTotal} hasMore ${snapshot.contactHasMore} filter ${snapshot.contactFilter} search ${snapshot.activeSearchParams}`,
      `inFlight loadMore=${snapshot.contactLoadMoreInFlight} refresh=${snapshot.contactRefreshInFlight} polling=${snapshot.contactPollingInFlight}`,
      `last request ${JSON.stringify(snapshot.lastRequest)}`,
      `last response ${JSON.stringify(snapshot.lastResponse)}`,
      `last applied ${JSON.stringify(snapshot.lastApplied)}`,
      `last ignored ${JSON.stringify(snapshot.lastIgnored)}`,
      `last render ${JSON.stringify(snapshot.lastRender)}`,
      ...events,
    ].join("\n");
  }

  function historyTrace(event, data = {}) {
    const entry = {
      time: new Date().toISOString().slice(11, 23),
      event,
      data,
    };
    const events = Array.isArray(state.historyDebugEvents) ? state.historyDebugEvents : [];
    events.push(entry);
    state.historyDebugEvents = events.slice(-HISTORY_DEBUG_EVENT_LIMIT);
    if (event === "request:start") state.contactLastRequest = data;
    if (event === "request:response") state.contactLastResponse = data;
    if (event === "request:applied") state.contactLastApplied = data;
    if (event === "request:ignored") state.contactLastIgnored = data;
    if (event === "render") state.contactLastRender = data;
    if (historyDebugEnabled() && typeof console !== "undefined" && typeof console.debug === "function") {
      console.debug("history trace", entry);
    }
    renderHistoryDebug();
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

  function debugContactStale(reason, details = {}) {
    const payload = { reason, ...details };
    historyTrace("request:ignored", payload);
    if (typeof console !== "undefined" && typeof console.debug === "function") {
      console.debug("Ignored stale history list response", payload);
    }
  }

  function beginContactListContext() {
    contactListContextSeq += 1;
    state.contactListContextSeq = contactListContextSeq;
    state.contactRevision = "";
    state.contactRevisionLimit = 0;
    state.contactRevisionOffset = 0;
    state.contactLoadedWindowLimit = 0;
    historyTrace("context:reset", { contextSeq: contactListContextSeq });
    return contactListContextSeq;
  }

  function contactItemId(item) {
    return String(item?.id || "");
  }

  function normalizeContactItemIndices(items) {
    return (Array.isArray(items) ? items : []).map((item, index) => ({
      ...item,
      _absoluteIndex: index,
    }));
  }

  function mergeAppendContactItems(currentItems, incomingItems) {
    const nextItems = Array.isArray(currentItems) ? [...currentItems] : [];
    const indexById = new Map();
    nextItems.forEach((item, index) => {
      const id = contactItemId(item);
      if (id) indexById.set(id, index);
    });
    for (const item of incomingItems) {
      const id = contactItemId(item);
      if (id && indexById.has(id)) {
        const index = indexById.get(id);
        nextItems[index] = { ...nextItems[index], ...item };
      } else {
        if (id) indexById.set(id, nextItems.length);
        nextItems.push(item);
      }
    }
    return normalizeContactItemIndices(nextItems);
  }

  function mergeWindowContactItems(currentItems, incomingItems) {
    const incomingIds = new Set(incomingItems.map(contactItemId).filter(Boolean));
    const tailItems = (Array.isArray(currentItems) ? currentItems : []).filter((item) => {
      const id = contactItemId(item);
      return !id || !incomingIds.has(id);
    });
    return normalizeContactItemIndices([...incomingItems, ...tailItems]);
  }

  function setLoadMoreLoading(loading) {
    state.contactLoadMoreInFlight = Boolean(loading);
    historyTrace(loading ? "load-more:start" : "load-more:end", {
      items: state.contactItems.length,
      offset: state.contactOffset,
      total: state.contactTotal,
    });
    updateLoadMoreButton();
  }

  function updateLoadMoreButton() {
    const button = $("#loadMoreBtn");
    if (!button) return;
    const hidden = state.contactFilter === "active" || !state.contactHasMore;
    button.classList.toggle("hidden", hidden);
    button.disabled = Boolean(state.contactLoadMoreInFlight || state.contactRefreshInFlight);
    button.textContent = state.contactLoadMoreInFlight ? "読み込み中..." : "さらに読み込む";
  }

  async function applyContactSearch() {
    state.contactSearch = collectContactSearchFromUi();
    state.contactSearch.requestSeq += 1;
    state.contactLoaded = true;
    state.contactRevision = "";
    historyTrace("search:reset", { activeSearchParams: activeSearchParamCount(), seq: state.contactSearch.requestSeq });
    return loadContact(true, { resetContext: true, reason: "search" });
  }

  async function clearContactSearch() {
    clearContactSearchForm();
    state.contactSearch = { ...state.contactSearch, ...collectContactSearchFromUi(), requestSeq: (state.contactSearch?.requestSeq || 0) + 1 };
    state.contactRevision = "";
    historyTrace("search:reset", { clear: true, seq: state.contactSearch.requestSeq });
    return loadContact(true, { resetContext: true, reason: "search-clear" });
  }

  async function refreshContact(options = {}) {
    state.contactRevision = "";
    state.contactPollFailures = 0;
    state.contactLoaded = true;
    text("#contactCount", "更新中...");
    const data = await loadContact(true, { reason: "manual-refresh", preserveLoadedWindow: true });
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

  function renderContact(options = {}) {
    const root = $("#contactGrid");
    if (!root) return;
    const preserveScroll = Boolean(options.preserveScroll);
    const previousScrollY = window.scrollY;
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
    updateLoadMoreButton();
    const renderData = {
      mode: options.mode || "",
      items: state.contactItems.length,
      domFrames: domFrameCount(),
      offset: state.contactOffset,
      total: state.contactTotal,
      scrollY: window.scrollY,
      preservedScrollY: preserveScroll ? previousScrollY : null,
    };
    state.contactLastRender = renderData;
    if (preserveScroll && window.scrollY !== previousScrollY) {
      window.requestAnimationFrame(() => {
        window.scrollTo({ top: previousScrollY });
        historyTrace("scroll:restore", {
          mode: options.mode || "",
          from: renderData.scrollY,
          to: previousScrollY,
        });
      });
    }
    historyTrace("render", renderData);
  }

  function stopContactPolling(message = "") {
    if (state.contactPollTimer) {
      window.clearInterval(state.contactPollTimer);
      state.contactPollTimer = 0;
    }
    state.pollHadActive = false;
    state.contactPollingInFlight = false;
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
          if (state.contactPollingInFlight) {
            historyTrace("polling:skip", {
              reason: "polling already in flight",
              items: state.contactItems.length,
              offset: state.contactOffset,
            });
            return;
          }
          state.contactPollingInFlight = true;
          historyTrace("polling:start", {
            items: state.contactItems.length,
            offset: state.contactOffset,
            activeCount,
          });
          loadContact(false, { polling: true, knownRevision: true })
            .catch(handleContactPollingError)
            .finally(() => {
              state.contactPollingInFlight = false;
              renderHistoryDebug();
            });
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
    const preserveLoadedWindow = Boolean(options.preserveLoadedWindow || options.polling);
    const resetContext = Boolean(options.resetContext || (reset && !preserveLoadedWindow));
    const mode = options.polling ? "polling" : reset ? (resetContext ? "reset" : "refresh") : "append";
    if (mode === "append" && (state.contactFilter === "active" || state.contactLoadMoreInFlight || state.contactRefreshInFlight)) {
      historyTrace("load-more:skip", {
        filter: state.contactFilter,
        loadMoreInFlight: state.contactLoadMoreInFlight,
        refreshInFlight: state.contactRefreshInFlight,
      });
      return null;
    }
    const contextSeq = mode === "reset" ? beginContactListContext() : contactListContextSeq;
    const requestId = ++contactListRequestSeq;
    const expectedOffset = mode === "append" ? Number(state.contactOffset || 0) : 0;
    const offset = mode === "append" ? expectedOffset : 0;
    const currentWindowLimit = loadedWindowLimit();
    const limit = mode === "polling" || mode === "refresh"
      ? (state.contactFilter === "active" ? 100 : currentWindowLimit)
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
    const canUseKnownRevision = options.knownRevision
      && mode === "polling"
      && state.contactRevision
      && Number(state.contactRevisionLimit || 0) === Number(limit || 0)
      && Number(state.contactRevisionOffset || 0) === Number(offset || 0);
    if (canUseKnownRevision) params.set("known_revision", state.contactRevision);

    historyTrace("request:start", {
      requestId,
      mode,
      reason: options.reason || "",
      offset,
      limit,
      contextSeq,
      expectedOffset,
      currentOffset: state.contactOffset,
      currentItems: state.contactItems.length,
      currentWindowLimit,
      filter: state.contactFilter,
      activeSearchParams: activeSearchParamCount(),
      knownRevision: Boolean(canUseKnownRevision),
      scrollY: window.scrollY,
    });

    if (mode === "append") setLoadMoreLoading(true);
    if (mode === "reset" || mode === "refresh") {
      state.contactRefreshInFlight = true;
      updateLoadMoreButton();
    }

    try {
      const data = await api(`/api/history?${params.toString()}`);
      historyTrace("request:response", {
        requestId,
        mode,
        offset: Number(data.offset || 0),
        limit: Number(data.limit || limit),
        itemCount: Array.isArray(data.items) ? data.items.length : 0,
        hasMore: Boolean(data.has_more),
        filteredTotal: Number(data.filtered_total ?? data.total ?? 0),
        total: Number(data.total ?? 0),
        unchanged: Boolean(data.unchanged),
      });
      if (seq !== (state.contactSearch.requestSeq || 0)) {
        debugContactStale("search sequence changed", { requestId, mode });
        return data;
      }
      if (contextSeq !== contactListContextSeq) {
        debugContactStale("history context changed", { requestId, mode, contextSeq, currentContextSeq: contactListContextSeq });
        return data;
      }
      if (mode === "append" && expectedOffset !== Number(state.contactOffset || 0)) {
        debugContactStale("load-more offset changed", { requestId, expectedOffset, currentOffset: state.contactOffset });
        return data;
      }

      state.contactPollFailures = 0;
      if (data.unchanged) {
        historyTrace("request:applied", {
          requestId,
          mode,
          unchanged: true,
          items: state.contactItems.length,
          offset: state.contactOffset,
        });
        renderHistoryDebug();
        updateContactPolling((state.contactItems || []).filter(isActiveItem).length);
        return data;
      }

      const pageOffset = Number(data.offset || 0);
      const pageItems = (Array.isArray(data.items) ? data.items : []).map((item, index) => ({
        ...item,
        _absoluteIndex: pageOffset + index,
      }));
      const visibleItems = visibleContactItems(pageItems);
      const previousOffset = Number(state.contactOffset || 0);
      const serverHighWater = pageOffset + pageItems.length;

      if (mode === "append") {
        state.contactItems = mergeAppendContactItems(state.contactItems, visibleItems);
      } else if (mode === "polling") {
        state.contactItems = mergeWindowContactItems(state.contactItems, visibleItems);
      } else if (mode === "refresh") {
        state.contactItems = mergeWindowContactItems(state.contactItems, visibleItems);
      } else {
        state.contactItems = normalizeContactItemIndices(visibleItems);
      }

      state.contactOffset = mode === "reset"
        ? visibleItems.length
        : Math.max(previousOffset, serverHighWater, state.contactItems.length);
      state.contactLoadedWindowLimit = Math.max(
        Number(state.contactLoadedWindowLimit || 0),
        Number(state.contactOffset || 0),
        state.contactItems.length,
      );
      state.contactLoaded = true;
      state.contactTotal = state.contactFilter === "active"
        ? Number(data.summary?.active ?? visibleItems.length)
        : Number(data.filtered_total ?? data.total ?? visibleItems.length);
      state.contactHasMore = mode === "polling"
        ? Boolean(data.has_more || Number(state.contactOffset || 0) < Number(state.contactTotal || 0))
        : Boolean(data.has_more || (mode !== "reset" && Number(state.contactOffset || 0) < Number(state.contactTotal || 0)));
      if (pageOffset === 0 && Number(limit || 0) >= Number(state.contactOffset || 0)) {
        state.contactRevision = data.revision || state.contactRevision;
        state.contactRevisionLimit = Number(limit || 0);
        state.contactRevisionOffset = pageOffset;
      }

      updateContactSearchStatus(state.contactTotal);
      const applied = {
        requestId,
        mode,
        pageOffset,
        pageItems: pageItems.length,
        visibleItems: visibleItems.length,
        items: state.contactItems.length,
        domFramesBeforeRender: domFrameCount(),
        offset: state.contactOffset,
        total: state.contactTotal,
        hasMore: state.contactHasMore,
        serverHighWater,
        previousOffset,
      };
      historyTrace("request:applied", applied);
      renderContact({ mode, preserveScroll: mode !== "reset" });
      const activeCount = Number(data.summary?.active ?? state.contactItems.filter(isActiveItem).length);
      updateContactPolling(activeCount);
      return data;
    } finally {
      if (mode === "append") setLoadMoreLoading(false);
      if ((mode === "reset" || mode === "refresh") && contextSeq === contactListContextSeq) {
        state.contactRefreshInFlight = false;
        updateLoadMoreButton();
        renderHistoryDebug();
      }
    }
  }

  function updateFrameFavoriteButton(item = state.detailItem) {
    const button = $("[data-action='frame-favorite']");
    const favorite = Boolean(item?.flags?.favorite);
    if (button) button.textContent = `${favorite ? "★" : "☆"} お気に入り`;
  }

  function isObject(value) {
    return value && typeof value === "object" && !Array.isArray(value);
  }

  function historySources(item = {}) {
    return [item, item.request_data, item.request, item.metadata].filter(isObject);
  }

  function historyObject(item, key) {
    for (const source of historySources(item)) {
      if (isObject(source[key])) return source[key];
    }
    return {};
  }

  function historyValue(item, key, fallback = "") {
    for (const source of historySources(item)) {
      const next = source[key];
      if (next !== undefined && next !== null && next !== "") return next;
    }
    return fallback;
  }

  function shortText(value, limit = 96) {
    const raw = Array.isArray(value) ? value.join(", ") : String(value ?? "");
    const compact = raw.replace(/\s+/g, " ").trim();
    if (!compact) return "";
    return compact.length > limit ? `${compact.slice(0, Math.max(0, limit - 3))}...` : compact;
  }

  function numberText(value) {
    if (value === null || value === undefined || value === "") return "-";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return Number.isInteger(number) ? String(number) : String(Math.round(number * 1000) / 1000);
  }

  function onOff(value) {
    return value ? "ON" : "OFF";
  }

  function warningsText(value, limit = 96) {
    const list = Array.isArray(value) ? value : value ? [value] : [];
    return shortText(list.filter(Boolean).join("; "), limit);
  }

  function tagCount(tags) {
    return String(tags || "").split(",").map((tag) => tag.trim()).filter(Boolean).length;
  }

  function officialLoraPresetSummary(item = {}) {
    const preset = shortText(historyValue(item, "official_lora_preset", ""), 40);
    return preset || "-";
  }

  function officialLoraPart(label, data = {}) {
    const source = isObject(data) ? data : {};
    const parts = [`${label} ${onOff(source.enabled)}`];
    if (source.strength !== undefined) parts.push(numberText(source.strength));
    if (source.version) parts.push(`version ${source.version}`);
    if (source.preset_applied !== undefined) parts.push(`preset ${source.preset_applied ? "yes" : "no"}`);
    if (source.found === false) parts.push("missing");
    return parts.join(" ");
  }

  function officialLorasSummary(item = {}) {
    const official = historyObject(item, "official_loras");
    if (!Object.keys(official).length) return "not recorded";
    return [
      officialLoraPart("Highres", official.highres),
      officialLoraPart("Turbo", official.turbo),
      officialLoraPart("ColorFix", official.colorfix),
    ].join("; ");
  }

  function promptRandomSummary(item = {}) {
    const data = historyObject(item, "prompt_random_collect");
    if (!Object.keys(data).length) return "not recorded";
    if (!data.enabled) return "OFF";
    const strategy = isObject(data.generation_strategy) ? data.generation_strategy : {};
    const provider = isObject(data.provider) ? data.provider : {};
    const generatedItem = isObject(data.generated_item) ? data.generated_item : {};
    const generatedTags = String(data.generated_tags || generatedItem.tags || "").trim();
    const fallback = strategy.fallback === true;
    const fallbackReason = warningsText(strategy.errors || strategy.reason || data.fallback_reason || data.warning, 72);
    const providerText = shortText([provider.provider, provider.model].filter(Boolean).join(" / "), 44);
    const parts = [
      `ON ${data.mode || "-"}`,
      `strategy ${strategy.mode || "-"}`,
      `fallback ${fallback ? "yes" : "no"}`,
    ];
    if (providerText) parts.push(`provider ${providerText}`);
    if (fallback && fallbackReason) parts.push(`reason ${fallbackReason}`);
    if (generatedItem.title) parts.push(`item ${shortText(generatedItem.title, 36)}`);
    if (generatedTags) parts.push(`${tagCount(generatedTags)} tags: ${shortText(generatedTags, 72)}`);
    if (data.instruction) parts.push(`instruction ${shortText(data.instruction, 56)}`);
    return parts.join("; ");
  }

  function moduleStatus(data = {}) {
    if (!data.enabled) return "OFF";
    if (data.applied === true) return "applied";
    if (data.apply_to_payload === false || data.applied === false) return "skipped";
    return "enabled";
  }

  function moduleReason(data = {}) {
    return shortText(data.unsupported_reason || warningsText(data.warnings, 72), 72);
  }

  function referenceModulePart(label, data = {}) {
    const source = isObject(data) ? data : {};
    const parts = [`${label} ${moduleStatus(source)}`];
    const reason = moduleReason(source);
    if (reason) parts.push(reason);
    return parts.join(" ");
  }

  function referenceModulesSummary(item = {}) {
    const modules = historyObject(item, "reference_modules");
    if (!Object.keys(modules).length) return "not recorded";
    return [
      referenceModulePart("Outfit", modules.outfit),
      referenceModulePart("Pose", modules.pose),
      referenceModulePart("BG", modules.background),
    ].join("; ");
  }

  function backgroundReferenceSummary(item = {}) {
    const modules = historyObject(item, "reference_modules");
    const background = isObject(modules.background) ? modules.background : {};
    if (!Object.keys(background).length) return "not recorded";
    if (!background.enabled) return "OFF";
    const parts = [
      moduleStatus(background),
      background.mode || "-",
      `strength ${numberText(background.strength)}`,
      `range ${numberText(background.start_at)}-${numberText(background.end_at)}`,
      `resize ${background.resize_mode || "-"}`,
    ];
    if (background.image_name) parts.push(`image ${shortText(background.image_name, 36)}`);
    if (background.apply_to_payload !== undefined) parts.push(`apply_to_payload ${background.apply_to_payload ? "true" : "false"}`);
    const reason = moduleReason(background);
    if (reason) parts.push(`reason ${reason}`);
    return parts.join("; ");
  }

  function hiresSummary(item = {}) {
    const hires = historyObject(item, "hires_fix");
    if (!Object.keys(hires).length) return "not recorded";
    if (!hires.enabled) return "OFF";
    const target = hires.target_width || hires.target_height
      ? `${hires.target_width || "-"}x${hires.target_height || "-"}`
      : `${hires.final_width || "-"}x${hires.final_height || "-"}`;
    const parts = [`ON ${hires.mode || "-"}`, `factor ${numberText(hires.factor ?? hires.upscale_factor)}`, `target ${target}`];
    if (hires.applied !== undefined) parts.push(hires.applied ? "applied" : "skipped");
    return parts.join("; ");
  }

  function i2iSummary(item = {}) {
    const i2i = historyObject(item, "image_to_image");
    if (!Object.keys(i2i).length) return "not recorded";
    if (!i2i.enabled) return "OFF";
    const parts = [`ON denoise ${numberText(i2i.denoise)}`, `resize ${i2i.resize_mode || "-"}`];
    if (i2i.applied !== undefined) parts.push(i2i.applied ? "applied" : "skipped");
    if (i2i.apply_to_payload === false) parts.push("apply_to_payload false");
    if (i2i.unsupported_reason) parts.push(shortText(i2i.unsupported_reason, 72));
    return parts.join("; ");
  }

  function dynamicPromptSummary(item = {}) {
    const dynamicPrompt = historyObject(item, "dynamic_prompt");
    if (!Object.keys(dynamicPrompt).length) return "not recorded";
    return onOff(dynamicPrompt.enabled !== false);
  }

  function detailerPart(label, data = {}) {
    const source = isObject(data) ? data : {};
    if (!Object.keys(source).length) return `${label} not recorded`;
    const parts = [`${label} ${onOff(source.enabled)}`];
    if (source.mode) parts.push(source.mode);
    if (source.preset) parts.push(`preset ${source.preset}`);
    if (source.bbox_threshold !== undefined) parts.push(`bbox ${Number(source.bbox_threshold).toFixed(2)}`);
    if (source.max_detections !== undefined) parts.push(`max ${source.max_detections}`);
    if (source.runaway_guard_enabled !== undefined) {
      parts.push(source.runaway_guard_enabled ? `guard ${source.runaway_action || "on"}` : "guard OFF");
    }
    if (source.candidates_detected !== undefined && source.candidates_detected !== null) parts.push(`${source.candidates_detected} detected`);
    if (source.candidates_processed !== undefined && source.candidates_processed !== null) parts.push(`${source.candidates_processed} processed`);
    if (source.elapsed_seconds !== undefined && source.elapsed_seconds !== null) parts.push(`${Number(source.elapsed_seconds).toFixed(1)}s`);
    if (source.applied !== undefined) parts.push(source.applied ? "applied" : "skipped");
    const reason = shortText(source.skip_reason || source.unsupported_reason || warningsText(source.warnings, 56), 56);
    if (reason) parts.push(reason);
    return parts.join(" ");
  }

  function detailersSummary(item = {}) {
    return [
      detailerPart("Face", historyObject(item, "face_detailer")),
      detailerPart("Hand", historyObject(item, "hand_detailer")),
    ].join("; ");
  }

  function generationAssistSummary(item = {}) {
    const markers = [];
    const preset = officialLoraPresetSummary(item);
    if (preset !== "-" && preset !== "off") markers.push(`preset ${preset}`);
    const official = historyObject(item, "official_loras");
    if (["highres", "turbo", "colorfix"].some((key) => Boolean(official[key]?.enabled))) markers.push("official LoRA");
    if (historyObject(item, "prompt_random_collect").enabled) markers.push("Prompt Random");
    const modules = historyObject(item, "reference_modules");
    if (["outfit", "pose", "background"].some((key) => Boolean(modules[key]?.enabled))) markers.push("Reference Modules");
    if (historyObject(item, "hires_fix").enabled) markers.push("Hires.fix");
    if (historyObject(item, "image_to_image").enabled) markers.push("i2i");
    if (historyObject(item, "face_detailer").enabled || historyObject(item, "hand_detailer").enabled) markers.push("Detailer");
    if (historyObject(item, "dynamic_prompt").enabled !== undefined) markers.push("Dynamic Prompt");
    return markers.length ? markers.join("; ") : "no assist recorded";
  }

  function generationMetricSeconds(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds)) return "";
    return `${seconds.toFixed(2)}s`;
  }

  function generationMetricsSummary(item = {}) {
    const metrics = item?.generation_metrics && typeof item.generation_metrics === "object"
      ? item.generation_metrics
      : {};
    const parts = [
      ["total", metrics.total_seconds],
      ["wait", metrics.queue_wait_seconds],
      ["submit", metrics.submit_seconds],
      ["fetch", metrics.image_fetch_seconds],
    ].map(([label, value]) => {
      const seconds = generationMetricSeconds(value);
      return seconds ? `${label} ${seconds}` : "";
    }).filter(Boolean);
    return parts.length ? parts.join(" · ") : "not recorded";
  }

  function renderFrameDetail(item) {
    const previousId = state.detailItem?.id || "";
    state.detailItem = item;
    if (previousId && previousId !== item?.id) invalidateShareBlobCache();
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
      addMetaRow(table, "CREATED", formatDate(item.created_at));
      addMetaRow(table, "GEN TIME", generationMetricsSummary(item), true);
      addMetaRow(table, "SEED", item.seed);
      addMetaRow(table, "SIZE", `${item.output_width || item.width || "-"}×${item.output_height || item.height || "-"}`);
      addMetaRow(table, "STEPS·CFG·SHIFT", `${displayValue(item.steps)} · ${displayValue(item.cfg)} · ${displayValue(item.shift ?? item.model_sampling?.shift)}`);
      addMetaRow(table, "SAMPLER·SCHEDULER", `${displayValue(item.sampler)} · ${displayValue(item.scheduler)}`);
      addMetaRow(table, "MODEL", modelFileName(item.model));
      addMetaRow(table, "RATING", item.rating || "-");
      addMetaRow(table, "CHARACTERS", characterSummary(item));
      addMetaRow(table, "LORA", loras.summary(item.loras || []));
      addMetaRow(table, "ASSIST SUMMARY", generationAssistSummary(item), true);
      addMetaRow(table, "OFFICIAL PRESET", officialLoraPresetSummary(item));
      addMetaRow(table, "OFFICIAL LORA", officialLorasSummary(item), true);
      addMetaRow(table, "PROMPT RANDOM", promptRandomSummary(item), true);
      addMetaRow(table, "REF MODULES", referenceModulesSummary(item), true);
      addMetaRow(table, "BG REF", backgroundReferenceSummary(item), true);
      addMetaRow(table, "GEN MODES", `Hires ${hiresSummary(item)}; i2i ${i2iSummary(item)}; Dynamic ${dynamicPromptSummary(item)}`, true);
      addMetaRow(table, "DETAILERS", detailersSummary(item), true);
      addMetaRow(table, "POSITIVE", textProviders.historyPositiveText(item), true);
      addMetaRow(table, "NEGATIVE", textProviders.historyNegativeText(item), true);
    }
    UI.openSheet("#frameSheet");
    if (isPublicImageReady(item)) prefetchShareBlob(item);
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
    return item.public_image_url || item.public_save?.url || (item.public_save?.saved ? `/api/history/${escapePathSegment(item.id)}/public-image` : "");
  }

  function isPublicImageReady(item = state.detailItem) {
    return Boolean(item?.id && publicImageUrl(item) && (item.public_image_url || item.public_save?.saved));
  }

  function shareBlobCacheKey(item = state.detailItem) {
    if (!item?.id) return "";
    const publicSave = item.public_save && typeof item.public_save === "object" ? item.public_save : {};
    const imageUrl = publicImageUrl(item);
    if (!imageUrl) return "";
    const filename = publicSave.filename || item.filename || `${item.id}_public.png`;
    return [
      item.id,
      imageUrl,
      filename,
      publicSave.updated_at || "",
      publicSave.size_bytes || "",
      publicSave.width || "",
      publicSave.height || "",
      publicSave.watermark_text || "",
      publicSave.watermark_position || "",
      publicSave.watermark_mode || "",
      publicSave.signature_image_id || "",
      publicSave.signature_scale || "",
      publicSave.finish_enabled ? "finish" : "",
      publicSave.finish_preset || "",
      publicSave.finish_content_hash || "",
    ].join("|");
  }

  function invalidateShareBlobCache(historyId = "") {
    if (!historyId || shareBlobCache?.historyId === historyId) {
      shareBlobCache = null;
    }
    shareBlobPrefetchSeq += 1;
  }

  function absoluteUrl(path) {
    return new URL(path, window.location.href).toString();
  }

  function setPublicSaveBusy(busy) {
    ["frame-public-save", "frame-share"].forEach((action) => {
      $$(`[data-action="${action}"]`).forEach((button) => {
        button.disabled = Boolean(busy);
      });
    });
  }

  function isCachedPublicSave(data = {}) {
    return Boolean(data.public_save?.cached || data.message === "cached");
  }

  function publicSaveDoneMessage(data = {}, options = {}) {
    if (options.purpose === "share") {
      return isCachedPublicSave(data)
        ? "保存済み画像を再利用できます。もう一度「共有」を押してください"
        : "共有用画像を準備しました。画像を先読み中です。もう一度「共有」を押してください";
    }
    if (isCachedPublicSave(data)) return "保存済み画像を再利用しました";
    return "公開保存しました";
  }

  function publicSaveProgressMessage(options = {}) {
    return options.purpose === "share" ? "共有用画像を準備中..." : "公開保存中...";
  }

  function isCurrentFrame(historyId) {
    return String(state.detailItem?.id || "") === String(historyId || "");
  }

  function mergePublicSaveResult(historyId, data = {}, options = {}) {
    const publicSave = data.public_save && typeof data.public_save === "object" ? data.public_save : {};
    const publicImageUrl = data.public_image_url || publicSave.url || "";
    const patch = {};
    if (publicImageUrl) patch.public_image_url = publicImageUrl;
    if (Object.keys(publicSave).length) {
      patch.public_save = publicSave;
    }
    if (!Object.keys(patch).length) return null;
    state.contactItems = (state.contactItems || []).map((item) => (
      String(item?.id || "") === String(historyId || "") ? { ...item, ...patch } : item
    ));
    if (!isCurrentFrame(historyId)) return null;
    state.detailItem = {
      ...(state.detailItem || {}),
      ...patch,
      public_save: { ...(state.detailItem?.public_save || {}), ...publicSave },
    };
    if (options.status) text("#frameActionStatus", publicSaveDoneMessage(data, options));
    if (isPublicImageReady(state.detailItem)) {
      prefetchShareBlob(state.detailItem, { updateStatus: options.purpose === "share" });
    }
    return state.detailItem;
  }

  function publicSaveStatusPath(historyId, jobId) {
    const suffix = jobId ? `?job_id=${encodeURIComponent(jobId)}` : "";
    return `/api/history/${escapePathSegment(historyId)}/public-save/status${suffix}`;
  }

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  async function pollPublicSave(historyId, jobId, options = {}) {
    const seq = ++publicSavePollSeq;
    for (let attempt = 0; attempt < PUBLIC_SAVE_MAX_POLLS; attempt += 1) {
      if (seq !== publicSavePollSeq) return null;
      const data = await api(publicSaveStatusPath(historyId, jobId));
      if (data.status === "done") {
        mergePublicSaveResult(historyId, data, { ...options, status: true });
        return data;
      }
      if (data.status === "failed") {
        invalidateShareBlobCache(historyId);
        const error = new Error(data.error || data.message || "公開保存に失敗しました");
        error.data = data;
        throw error;
      }
      text("#frameActionStatus", data.message === "public save already running" ? "保存処理を待っています..." : publicSaveProgressMessage(options));
      await sleep(PUBLIC_SAVE_POLL_INTERVAL_MS);
    }
    const error = new Error("公開保存がタイムアウトしました");
    error.data = { ok: false, status: "timeout", job_id: jobId };
    throw error;
  }

  async function ensurePublicImagePrepared(historyId = state.detailItem?.id, options = {}) {
    if (!historyId) return null;
    invalidateShareBlobCache(historyId);
    setPublicSaveBusy(true);
    text("#frameActionStatus", options.startMessage || publicSaveProgressMessage(options));
    try {
      const data = await api(`/api/history/${escapePathSegment(historyId)}/public-save`, {
        method: "POST",
        body: JSON.stringify({
          ...(typeof collectPublicSaveRequestSettings === "function"
            ? collectPublicSaveRequestSettings()
            : {
              apply_watermark: checked("#watermarkEnabled"),
              watermark: collectWatermark(),
              watermark_client: "current",
              ...collectPublicSaveFinish(),
            }),
          async_save: true,
        }),
      });
      if (data.status === "done") {
        mergePublicSaveResult(historyId, data, { ...options, status: true });
        return data;
      }
      const done = await pollPublicSave(historyId, data.job_id, options);
      return done || data;
    } finally {
      setPublicSaveBusy(false);
    }
  }

  async function savePublicImage() {
    return ensurePublicImagePrepared(state.detailItem?.id, { purpose: "save" });
  }

  function shareFileFromCache(item = state.detailItem) {
    const key = shareBlobCacheKey(item);
    if (!key || shareBlobCache?.key !== key) return null;
    return shareBlobCache.file || null;
  }

  async function fetchShareFile(item = state.detailItem, { cache = true, store = true } = {}) {
    const cachedFile = cache ? shareFileFromCache(item) : null;
    if (cachedFile) return { file: cachedFile, cacheHit: true };
    const imageUrl = publicImageUrl(item);
    if (!imageUrl) throw new Error("公開画像URLを取得できませんでした");
    const response = await fetchWithAuthHandling(imageUrl);
    const blob = await response.blob();
    const filename = String(item.public_save?.filename || item.filename || `${item.id}_public.png`).replace(/[^\w.-]/g, "_");
    const file = new File([blob], filename, { type: blob.type || "image/png" });
    const key = shareBlobCacheKey(item);
    if (key && store) shareBlobCache = { key, historyId: item.id, file };
    return { file, cacheHit: false };
  }

  function prefetchShareBlob(item = state.detailItem, options = {}) {
    if (!isPublicImageReady(item)) return;
    const key = shareBlobCacheKey(item);
    if (!key || shareBlobCache?.key === key) {
      if (options.updateStatus) text("#frameActionStatus", "共有用画像を準備しました。もう一度「共有」を押してください");
      return;
    }
    const snapshot = {
      id: item.id,
      public_image_url: publicImageUrl(item),
      public_save: { ...(item.public_save || {}) },
      filename: item.filename,
    };
    const seq = ++shareBlobPrefetchSeq;
    fetchShareFile(snapshot, { cache: false, store: false })
      .then(({ file }) => {
        if (seq !== shareBlobPrefetchSeq) return;
        if (!isCurrentFrame(snapshot.id)) return;
        if (shareBlobCacheKey(state.detailItem) !== key) return;
        shareBlobCache = { key, historyId: snapshot.id, file };
        if (options.updateStatus) text("#frameActionStatus", "共有用画像を準備しました。もう一度「共有」を押してください");
      })
      .catch(() => {
        if (seq === shareBlobPrefetchSeq && shareBlobCache?.key === key) shareBlobCache = null;
      });
  }

  async function shareReadyPublicImage(item = state.detailItem) {
    if (!item?.id) return;
    const imageUrl = publicImageUrl(item);
    if (!imageUrl) throw new Error("公開画像URLを取得できませんでした");
    const cachedFile = shareFileFromCache(item);
    text("#frameActionStatus", cachedFile ? "共有シートを開いています..." : "共有用画像を取得中...");
    try {
      const { file } = await fetchShareFile(item);
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
      if (!isUnauthorized(error)) {
        window.open(absoluteUrl(imageUrl), "_blank", "noopener");
        text("#frameActionStatus", "共有できませんでした。画像を開きました");
        UI.toast("画像を開きました");
        return;
      }
      throw error;
    }
  }

  async function shareFrame() {
    if (!state.detailItem?.id) return;
    const historyId = state.detailItem.id;
    try {
      if (isPublicImageReady(state.detailItem)) {
        await shareReadyPublicImage(state.detailItem);
        return;
      }
      const data = await ensurePublicImagePrepared(historyId, {
        purpose: "share",
        startMessage: "共有用画像を準備しています。完了後にもう一度「共有」を押してください",
      });
      if (!data) return;
      if (!isCurrentFrame(historyId)) {
        UI.toast("別の履歴を開いたため共有を中断しました");
        return;
      }
      const message = shareFileFromCache(state.detailItem)
        ? "共有用画像を準備しました。もう一度「共有」を押してください"
        : publicSaveDoneMessage(data, { purpose: "share" });
      text("#frameActionStatus", message);
      UI.toast(message);
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
    try {
      window.__historyDebugState = () => ({
        ...historyDebugSnapshot(),
        events: state.historyDebugEvents || [],
      });
    } catch {}
    renderHistoryDebug();

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
      historyTrace("filter:reset", { filter: state.contactFilter });
      loadContact(true, { resetContext: true, reason: "filter" }).catch((error) => UI.toast(errorMessage(error), "error"));
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
    setTextProviders,
    shareFrame,
    toggleFrameFavorite,
  };
}
