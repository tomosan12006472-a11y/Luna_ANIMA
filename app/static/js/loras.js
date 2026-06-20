import {
  $,
  $$,
  checked,
  numberFrom,
  numberValue,
  setChecked,
  setValue,
} from "./dom.js?v=v1.31-reference-i2i-module-20260620";

function normalizeLoraApplication(value) {
  const raw = String(value || "model_clip").toLowerCase();
  if (raw === "model_only" || raw === "model") return "model_only";
  return "model_clip";
}

function loraNameFromItem(item = {}) {
  return String(item.name || item.relative_path || item.file_name || item.lora_id || "").trim();
}

function addLoraOption(select, value, label) {
  if (!value) return;
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label || value;
  select.appendChild(option);
}

export function createLoraFeature({
  api,
  state,
  updateSummaries = () => {},
} = {}) {
  function selectableLoras() {
    return Array.isArray(state?.loraSelectable) ? state.loraSelectable : [];
  }

  function fillLoraSelect(select, selectedValue) {
    const selected = String(selectedValue || "").trim();
    select.replaceChildren();
    addLoraOption(select, "", "LoRAを選択");
    const seen = new Set([""]);
    for (const item of selectableLoras()) {
      const optionValue = String(item.relative_path || item.file_name || item.name || item.lora_id || "").trim();
      if (!optionValue || seen.has(optionValue)) continue;
      seen.add(optionValue);
      addLoraOption(select, optionValue, item.display_name || item.file_name || optionValue);
    }
    if (selected && !seen.has(selected)) addLoraOption(select, selected, selected);
    select.value = selected;
  }

  function collectOfficialLoras() {
    return {
      highres: {
        enabled: checked("#officialHighresEnabled"),
        strength: numberValue("#officialHighresStrength", 0.6),
      },
      turbo: {
        enabled: checked("#officialTurboEnabled"),
        version: "auto",
        strength: numberValue("#officialTurboStrength", 0.6),
      },
    };
  }

  function collectLoras() {
    return $$("[data-lora-row]", $("#loraSlots")).map((row) => {
      const name = row.querySelector("[data-lora-field='name']")?.value || "";
      const application = row.querySelector("[data-lora-field='application']")?.value || "model_clip";
      const strengthModel = Number(row.querySelector("[data-lora-field='strength_model']")?.value || 1);
      const strengthClip = Number(row.querySelector("[data-lora-field='strength_clip']")?.value || 1);
      return {
        enabled: true,
        name,
        application,
        strength_model: Number.isFinite(strengthModel) ? strengthModel : 1,
        strength_clip: Number.isFinite(strengthClip) ? strengthClip : 1,
      };
    }).filter((item) => item.name);
  }

  function applyOfficialToForm(official = {}) {
    setChecked("#officialHighresEnabled", official.highres?.enabled);
    setValue("#officialHighresStrength", official.highres?.strength ?? 0.6);
    setChecked("#officialTurboEnabled", official.turbo?.enabled);
    setValue("#officialTurboStrength", official.turbo?.strength ?? 0.6);
  }

  function addLoraRow(initial = {}) {
    const root = $("#loraSlots");
    if (!root) return;
    const row = document.createElement("div");
    row.className = "tray";
    row.dataset.loraRow = "1";

    const grid = document.createElement("div");
    grid.className = "grid2";

    const nameLabel = document.createElement("label");
    nameLabel.className = "field";
    nameLabel.innerHTML = "<span class=\"lbl\">LORA</span>";
    const select = document.createElement("select");
    select.dataset.loraField = "name";
    fillLoraSelect(select, loraNameFromItem(initial));
    nameLabel.appendChild(select);

    const modelLabel = document.createElement("label");
    modelLabel.className = "field";
    modelLabel.innerHTML = "<span class=\"lbl\">MODEL</span>";
    const model = document.createElement("input");
    model.type = "number";
    model.min = "0";
    model.max = "1";
    model.step = "0.05";
    model.value = initial.strength_model ?? initial.model_strength ?? initial.weight ?? "1";
    model.dataset.loraField = "strength_model";
    modelLabel.appendChild(model);

    const clipLabel = document.createElement("label");
    clipLabel.className = "field";
    clipLabel.innerHTML = "<span class=\"lbl\">CLIP</span>";
    const clip = document.createElement("input");
    clip.type = "number";
    clip.min = "0";
    clip.max = "1";
    clip.step = "0.05";
    clip.value = initial.strength_clip ?? initial.clip_strength ?? initial.weight ?? "1";
    clip.dataset.loraField = "strength_clip";
    clipLabel.appendChild(clip);

    const appLabel = document.createElement("label");
    appLabel.className = "field";
    appLabel.innerHTML = "<span class=\"lbl\">APPLY</span>";
    const application = document.createElement("select");
    application.dataset.loraField = "application";
    addLoraOption(application, "model_clip", "model + clip");
    addLoraOption(application, "model_only", "model only");
    application.value = normalizeLoraApplication(initial.application || initial.mode);
    appLabel.appendChild(application);

    grid.append(nameLabel, modelLabel, clipLabel, appLabel);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost";
    remove.dataset.action = "remove-lora";
    remove.textContent = "削除";

    row.append(grid, remove);
    root.appendChild(row);
    updateSummaries();
  }

  function renderLoraRows(loras = []) {
    $("#loraSlots")?.replaceChildren();
    for (const lora of loras || []) addLoraRow(lora);
  }

  function renderConfiguredLoras(settings = state?.appSettings || {}) {
    const configured = Array.isArray(settings?.loras) && settings.loras.length
      ? settings.loras
      : (settings?.lora_settings?.slots || []).filter((item) => item?.enabled && item?.lora_id !== "none");
    renderLoraRows(configured);
  }

  async function loadLoraCatalog() {
    const data = await api("/api/loras/catalog");
    state.loraSelectable = Array.isArray(data.selectable) ? data.selectable : [];
    return data;
  }

  async function refreshLoraCatalog() {
    const data = await api("/api/loras/catalog/refresh", { method: "POST", body: "{}" });
    state.loraSelectable = Array.isArray(data.selectable) ? data.selectable : [];
    renderConfiguredLoras(state.appSettings);
    return data;
  }

  function historyOfficialLoras(official = {}) {
    return {
      highres: {
        enabled: Boolean(official.highres?.enabled),
        strength: numberFrom(official.highres?.strength, 0.6),
      },
      turbo: {
        enabled: Boolean(official.turbo?.enabled),
        version: "auto",
        strength: numberFrom(official.turbo?.strength, 0.6),
      },
    };
  }

  function historyLoras(loras = []) {
    return (Array.isArray(loras) ? loras : []).filter((lora) => lora && typeof lora === "object").map((lora) => ({
      enabled: true,
      name: loraNameFromItem(lora),
      application: normalizeLoraApplication(lora.application || lora.mode),
      strength_model: numberFrom(lora.strength_model ?? lora.model_strength ?? lora.weight, 1),
      strength_clip: numberFrom(lora.strength_clip ?? lora.clip_strength ?? lora.weight, 1),
    })).filter((lora) => lora.name);
  }

  function loraSummary(loras = []) {
    if (!Array.isArray(loras) || !loras.length) return "-";
    return loras.map((lora) => {
      const name = lora.name || lora.display_name || lora.relative_path || lora.file_name || "LoRA";
      const model = lora.strength_model ?? lora.model_strength ?? lora.weight ?? "-";
      const clip = lora.strength_clip ?? lora.clip_strength ?? lora.weight ?? "-";
      return `${name} (M ${model} / C ${clip})`;
    }).join(", ");
  }

  function removeLoraRow(target) {
    target.closest("[data-lora-row]")?.remove();
    updateSummaries();
  }

  return {
    actions: {
      "add-lora": async () => {
        if (!selectableLoras().length) await loadLoraCatalog().catch(() => {});
        addLoraRow();
      },
      "remove-lora": (target) => removeLoraRow(target),
    },
    addLoraRow,
    applyOfficialToForm,
    collect: collectLoras,
    collectOfficial: collectOfficialLoras,
    history: historyLoras,
    historyOfficial: historyOfficialLoras,
    loadCatalog: loadLoraCatalog,
    refreshCatalog: refreshLoraCatalog,
    renderConfigured: renderConfiguredLoras,
    renderRows: renderLoraRows,
    summary: loraSummary,
  };
}
