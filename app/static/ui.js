/* ui.js — interaction primitives (owned by design; app.js wires data into these).
   Contract: window.UI.{$, $$, switchTab, openSheet, closeSheets, toast,
             safelight, bindSeg, segValue, setSegValue, markDeveloping, onTab} */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ---------- tabs ---------- */
  const tabHandlers = [];
  function switchTab(name) {
    if (name === "settings") { openSheet("#settingsSheet"); return; }
    for (const v of $$(".view[data-view]")) v.classList.toggle("is-active", v.dataset.view === name);
    for (const b of $$("#tabs button")) b.classList.toggle("is-active", b.dataset.tab === name);
    window.scrollTo({ top: 0 });
    for (const fn of tabHandlers) { try { fn(name); } catch (e) { console.error(e); } }
  }
  function onTab(fn) { tabHandlers.push(fn); }
  document.addEventListener("click", (event) => {
    const tab = event.target.closest("#tabs button[data-tab], [data-tab-jump]");
    if (tab) switchTab(tab.dataset.tab || tab.dataset.tabJump);
  });

  /* ---------- sheets ---------- */
  function openSheet(sel) {
    const sheet = $(sel);
    if (!sheet) return;
    sheet.classList.add("is-open");
    sheet.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }
  function closeSheets() {
    for (const sheet of $$(".sheet.is-open")) {
      sheet.classList.remove("is-open");
      sheet.setAttribute("aria-hidden", "true");
    }
    document.body.style.overflow = "";
  }
  document.addEventListener("click", (event) => {
    if (event.target.closest('[data-action="close-sheet"]')) closeSheets();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !document.querySelector("#askSheet.is-open")) closeSheets();
  });

  /* ---------- toast ---------- */
  let toastTimer = 0;
  function toast(message, kind = "info") {
    const el = $("#toast");
    if (!el) return;
    el.textContent = String(message || "");
    el.classList.toggle("is-error", kind === "error");
    el.classList.add("is-show");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => el.classList.remove("is-show"), 2800);
  }

  /* ---------- safelight (global status) ---------- */
  /* mode: "idle" | "developing" | "error" */
  function safelight(mode, text) {
    document.body.classList.toggle("is-developing", mode === "developing");
    document.body.classList.toggle("is-error", mode === "error");
    const label = $("#safelightText");
    if (label) {
      label.textContent = text || (
        mode === "developing" ? "DEVELOPING…" :
        mode === "error" ? "LIGHTS ON — CHECK" : "SAFELIGHT ON");
    }
  }

  /* ---------- segmented controls ---------- */
  function bindSeg(sel, attr, onChange) {
    const seg = $(sel);
    if (!seg) return;
    seg.addEventListener("click", (event) => {
      const btn = event.target.closest(`button[data-${attr}]`);
      if (!btn) return;
      for (const b of $$(`button[data-${attr}]`, seg)) b.classList.toggle("is-active", b === btn);
      if (onChange) onChange(btn.dataset[camel(attr)]);
    });
  }
  function camel(value) { return value.replace(/-([a-z])/g, (_, c) => c.toUpperCase()); }
  function segValue(sel, attr) {
    const active = $(`${sel} button[data-${attr}].is-active`);
    return active ? active.dataset[camel(attr)] : "";
  }
  function setSegValue(sel, attr, value) {
    for (const b of $$(`${sel} button[data-${attr}]`)) {
      b.classList.toggle("is-active", b.dataset[camel(attr)] === String(value));
    }
  }

  /* ---------- fold persistence ---------- */
  const FOLD_KEY = "lunaAnimaFoldsV1";
  function restoreFolds() {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(FOLD_KEY) || "{}") || {}; } catch {}
    for (const el of $$("details[data-fold]")) {
      const id = el.dataset.fold;
      if (Object.prototype.hasOwnProperty.call(saved, id)) el.open = Boolean(saved[id]);
    }
  }
  document.addEventListener("toggle", (event) => {
    const el = event.target;
    if (!(el instanceof HTMLDetailsElement) || !el.dataset.fold) return;
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(FOLD_KEY) || "{}") || {}; } catch {}
    saved[el.dataset.fold] = el.open;
    localStorage.setItem(FOLD_KEY, JSON.stringify(saved));
  }, true);

  /* ---------- development reveal for new frames ---------- */
  function markDeveloping(img) {
    if (!(img instanceof HTMLImageElement)) return;
    const reveal = () => {
      img.classList.add("developing");
      img.addEventListener("animationend", () => img.classList.remove("developing"), { once: true });
    };
    if (img.complete) reveal(); else img.addEventListener("load", reveal, { once: true });
  }

  /* ---------- app shell after login ---------- */
  function enterDarkroom() {
    $("#loginView").classList.remove("is-active");
    $("#tabs").classList.remove("hidden");
    $("#exposeBar").classList.remove("hidden");
    restoreFolds();
    switchTab("expose");
  }

  /* ---------- ask: darkroom choice/confirm dialog ---------- */
  function ask({ title = "確認", message = "", choices = [] } = {}) {
    return new Promise((resolve) => {
      const sheet = $("#askSheet");
      if (!sheet) { resolve(null); return; }
      $("#askTitle").textContent = title;
      $("#askMessage").textContent = message;
      const wrap = $("#askChoices");
      wrap.replaceChildren();
      let settled = false;
      const done = (value) => {
        if (settled) return;
        settled = true;
        sheet.classList.remove("is-open");
        sheet.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
        document.removeEventListener("keydown", onKey, true);
        resolve(value);
      };
      const onKey = (event) => { if (event.key === "Escape") { event.stopPropagation(); done(null); } };
      for (const choice of choices) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ask-choice" + (choice.kind ? ` is-${choice.kind}` : "");
        btn.textContent = choice.label;
        btn.addEventListener("click", () => done(choice.value));
        wrap.appendChild(btn);
      }
      const cancel = document.createElement("button");
      cancel.type = "button";
      cancel.className = "ask-choice is-cancel";
      cancel.textContent = "キャンセル";
      cancel.addEventListener("click", () => done(null));
      wrap.appendChild(cancel);
      sheet.querySelector(".backdrop").onclick = () => done(null);
      document.addEventListener("keydown", onKey, true);
      sheet.classList.add("is-open");
      sheet.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    });
  }

  window.UI = {
    $, $$, switchTab, onTab, openSheet, closeSheets, toast, safelight, ask,
    bindSeg, segValue, setSegValue, restoreFolds, markDeveloping, enterDarkroom,
  };
})();
