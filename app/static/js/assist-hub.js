import { $, $$ } from "./dom.js?v=v1.62-detailer-detection-controls-20260630";

export function createAssistHubFeature() {
  const activeTabs = new Map();

  function groupTabs(group) {
    return $$(`[data-workbench-tabs="${group}"] [data-workbench-tab]`);
  }

  function groupPanels(group) {
    const root = $(`[data-workbench-tabs="${group}"]`)?.closest(".workbench");
    return root ? Array.from(root.querySelectorAll("[data-workbench-panel]")) : [];
  }

  function activate(group = "tuning", tab = "") {
    const buttons = groupTabs(group);
    if (!buttons.length) return;
    const tabs = buttons.map((button) => button.dataset.workbenchTab);
    const next = tabs.includes(tab) ? tab : (activeTabs.get(group) || tabs[0]);
    activeTabs.set(group, next);

    buttons.forEach((button) => {
      const isActive = button.dataset.workbenchTab === next;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-selected", isActive ? "true" : "false");
      button.tabIndex = isActive ? 0 : -1;
    });

    groupPanels(group).forEach((panel) => {
      const isActive = panel.dataset.workbenchPanel === next;
      panel.classList.toggle("hidden", !isActive);
      panel.toggleAttribute("hidden", !isActive);
    });
  }

  function moveBy(group, offset) {
    const buttons = groupTabs(group);
    if (!buttons.length) return;
    const tabs = buttons.map((button) => button.dataset.workbenchTab);
    const current = Math.max(0, tabs.indexOf(activeTabs.get(group)));
    const nextIndex = (current + offset + tabs.length) % tabs.length;
    activate(group, tabs[nextIndex]);
    buttons[nextIndex]?.focus();
  }

  function bindEvents() {
    $$("[data-workbench-tabs]").forEach((tabs) => {
      const group = tabs.dataset.workbenchTabs;

      tabs.addEventListener("click", (event) => {
        const button = event.target.closest("[data-workbench-tab]");
        if (!button) return;
        activate(group, button.dataset.workbenchTab);
      });

      tabs.addEventListener("keydown", (event) => {
        const buttons = groupTabs(group);
        if (!buttons.length) return;
        const first = buttons[0]?.dataset.workbenchTab;
        const last = buttons.at(-1)?.dataset.workbenchTab;
        if (event.key === "ArrowRight") {
          event.preventDefault();
          moveBy(group, 1);
        } else if (event.key === "ArrowLeft") {
          event.preventDefault();
          moveBy(group, -1);
        } else if (event.key === "Home") {
          event.preventDefault();
          activate(group, first);
          buttons[0]?.focus();
        } else if (event.key === "End") {
          event.preventDefault();
          activate(group, last);
          buttons.at(-1)?.focus();
        }
      });

      activate(group, tabs.querySelector("[data-workbench-tab]")?.dataset.workbenchTab);
    });
  }

  return {
    activate,
    bindEvents,
    selectedTab: (group = "tuning") => activeTabs.get(group),
  };
}
