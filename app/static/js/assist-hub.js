import { $, $$ } from "./dom.js?v=v1.54-assist-hub-settings-20260626";

const ASSIST_HUB_TABS = ["official", "lora", "quick"];

export function createAssistHubFeature() {
  let activeTab = "official";

  function activate(tab = "official") {
    const next = ASSIST_HUB_TABS.includes(tab) ? tab : "official";
    activeTab = next;

    $$("#assistHubTabs [data-assist-hub-tab]").forEach((button) => {
      const isActive = button.dataset.assistHubTab === next;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-selected", isActive ? "true" : "false");
      button.tabIndex = isActive ? 0 : -1;
    });

    $$("[data-assist-hub-panel]").forEach((panel) => {
      const isActive = panel.dataset.assistHubPanel === next;
      panel.classList.toggle("hidden", !isActive);
      panel.toggleAttribute("hidden", !isActive);
    });
  }

  function moveBy(offset) {
    const current = ASSIST_HUB_TABS.indexOf(activeTab);
    const nextIndex = (current + offset + ASSIST_HUB_TABS.length) % ASSIST_HUB_TABS.length;
    activate(ASSIST_HUB_TABS[nextIndex]);
    $(`#assistHubTabs [data-assist-hub-tab="${ASSIST_HUB_TABS[nextIndex]}"]`)?.focus();
  }

  function bindEvents() {
    const tabs = $("#assistHubTabs");
    if (!tabs) return;

    tabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-assist-hub-tab]");
      if (!button) return;
      activate(button.dataset.assistHubTab);
    });

    tabs.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        moveBy(1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        moveBy(-1);
      } else if (event.key === "Home") {
        event.preventDefault();
        activate(ASSIST_HUB_TABS[0]);
        $(`#assistHubTabs [data-assist-hub-tab="${ASSIST_HUB_TABS[0]}"]`)?.focus();
      } else if (event.key === "End") {
        event.preventDefault();
        const last = ASSIST_HUB_TABS.at(-1);
        activate(last);
        $(`#assistHubTabs [data-assist-hub-tab="${last}"]`)?.focus();
      }
    });

    activate(activeTab);
  }

  return {
    activate,
    bindEvents,
    selectedTab: () => activeTab,
  };
}
