import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const failures = [];
const fileCache = new Map();

function relative(file) {
  return path.relative(root, file).replaceAll(path.sep, "/");
}

function collectFiles(dir, predicate) {
  if (!existsSync(dir)) return [];
  const entries = readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFiles(fullPath, predicate));
    } else if (entry.isFile() && predicate(fullPath)) {
      files.push(fullPath);
    }
  }
  return files;
}

function readRelative(file) {
  const fullPath = path.join(root, file);
  if (!existsSync(fullPath)) {
    failures.push(`${file}: file is missing`);
    return "";
  }
  if (!fileCache.has(file)) fileCache.set(file, readFileSync(fullPath, "utf8"));
  return fileCache.get(file);
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function fail(file, message) {
  failures.push(`${file}: ${message}`);
}

function requireRegex(file, regex, label) {
  const content = readRelative(file);
  if (!regex.test(content)) fail(file, `missing ${label}`);
}

function requireIncludes(file, needle, label = needle) {
  const content = readRelative(file);
  if (!content.includes(needle)) fail(file, `missing ${label}`);
}

function requireAnyIncludes(files, needle, label = needle) {
  if (!files.some((file) => readRelative(file).includes(needle))) {
    fail(files.join(", "), `missing ${label}`);
  }
}

const staticJsFiles = collectFiles(path.join(root, "app", "static", "js"), (file) => file.endsWith(".js"))
  .map(relative)
  .sort((left, right) => left.localeCompare(right));
const staticJsBundle = staticJsFiles.map((file) => readRelative(file)).join("\n");
const actionTargetBundle = [
  readRelative("app/static/index.html"),
  staticJsBundle,
].join("\n");

const factoryContracts = [
  ["app/static/js/app-shell.js", ["createAppShell"]],
  ["app/static/js/actions.js", ["registerActions", { name: "dispatchAction", async: true }]],
  ["app/static/js/api.js", ["createApiClient"]],
  ["app/static/js/characters.js", ["createCharacterFeature"]],
  ["app/static/js/detailers.js", ["createDetailerFeature"]],
  ["app/static/js/dynamic-prompt.js", ["createDynamicPromptFeature"]],
  ["app/static/js/generation-actions.js", ["createGenerationActionsFeature"]],
  ["app/static/js/generation-form.js", ["createGenerationFormFeature"]],
  ["app/static/js/history.js", ["createHistoryFeature"]],
  ["app/static/js/history-reuse.js", ["createHistoryReuseFeature"]],
  ["app/static/js/history-text.js", ["createHistoryTextFeature"]],
  ["app/static/js/history-reuse-data.js", ["createHistoryReuseDataFeature"]],
  ["app/static/js/history-request.js", ["createHistoryRequestFeature"]],
  ["app/static/js/i2i.js", ["createI2iFeature"]],
  ["app/static/js/loras.js", ["createLoraFeature"]],
  ["app/static/js/positive-prompts.js", ["createPositivePromptsFeature"]],
  ["app/static/js/prompt-converter.js", ["createPromptConverterFeature"]],
  ["app/static/js/prompt-dictionary.js", ["createPromptDictionaryFeature"]],
  ["app/static/js/prompt-library.js", ["createPromptLibraryFeature"]],
  ["app/static/js/prompt-library-utils.js", ["createPositivePromptHelpers"]],
  ["app/static/js/prompt-presets.js", ["createPromptPresetsFeature"]],
  ["app/static/js/prompt-random.js", ["createPromptRandomUi"]],
  ["app/static/js/queue.js", ["createQueueFeature"]],
  ["app/static/js/recipes.js", ["createRecipesFeature"]],
  ["app/static/js/reference.js", ["createReferenceFeature"]],
  ["app/static/js/settings.js", ["createSettingsFeature"]],
];

for (const [file, names] of factoryContracts) {
  for (const contract of names) {
    const name = typeof contract === "string" ? contract : contract.name;
    const asyncPrefix = typeof contract === "object" && contract.async ? "async\\s+" : "(?:async\\s+)?";
    requireRegex(file, new RegExp(`export\\s+${asyncPrefix}function\\s+${escapeRegExp(name)}\\s*\\(`), `factory export ${name}`);
  }
}

for (const file of staticJsFiles) {
  requireRegex(file, /^(?![\s\S]*\bexport\s+default\b)[\s\S]*$/, "no default export");
}

const actionContracts = [
  "login",
  "preview",
  "generate",
  "frame-reuse",
  "frame-to-i2i",
  "frame-face-detail",
  "frame-hand-detail",
  "frame-variations",
  "save-auto-prompts",
  "add-lora",
  "refresh-lora-catalog",
  "remove-lora",
  "duplicate-lora",
  "move-lora-up",
  "move-lora-down",
  "prompt-random-status",
  "prompt-random-favorite-apply",
  "prompt-random-favorite-save",
  "prompt-random-favorite-delete",
  "history-refresh",
  "contact-search",
  "contact-search-clear",
  "load-more",
  "frame-favorite",
  "frame-public-save",
  "frame-share",
  "open-queue",
  "queue-refresh",
  "queue-interrupt",
  "i2i-upload",
  "i2i-clear",
  "outfit-upload",
  "outfit-clear",
  "pose-upload",
  "pose-clear",
  "background-upload",
  "background-clear",
  "background-apply-mode-defaults",
  "save-defaults",
  "reset-defaults",
  "reload-models",
  "reload-ui",
  "prompt-convert",
  "prompt-converter-status",
  "save-positive-fav",
  "open-positive-favs",
  "open-templates",
  "load-more-prompts",
  "save-recipe",
  "open-recipes",
  "dynamic-wildcards",
  "dynamic-preview",
  "random-slot",
  "clear-slot",
  "toggle-character-favorites",
  "load-more-characters",
  "toggle-favorite-slot",
  "close-sheet",
];

function hasActionTarget(action) {
  const escaped = escapeRegExp(action);
  return [
    new RegExp(`data-action=["']${escaped}["']`),
    new RegExp(`dataset\\.action\\s*=\\s*["']${escaped}["']`),
    new RegExp(`\\[data-action=["']${escaped}["']\\]`),
  ].some((regex) => regex.test(actionTargetBundle));
}

function hasActionHandler(action) {
  const escaped = escapeRegExp(action);
  return [
    new RegExp(`(?:["']${escaped}["']|\\b${escaped}\\b)\\s*:`),
    new RegExp(`action\\s*={2,3}\\s*["']${escaped}["']`),
  ].some((regex) => regex.test(staticJsBundle));
}

for (const action of actionContracts) {
  if (!hasActionTarget(action)) fail("app/static/index.html, app/static/js", `missing data-action target ${action}`);
  if (!hasActionHandler(action)) fail("app/static/js", `missing action handler ${action}`);
}

const apiPathContracts = [
  ["app/static/js/app-shell.js", "/api/login"],
  ["app/static/js/app-shell.js", "/api/bootstrap"],
  ["app/static/js/generation-actions.js", "/api/payload/preview"],
  ["app/static/js/generation-actions.js", "/api/generate"],
  ["app/static/js/history.js", "/api/history"],
  ["app/static/js/queue.js", "/api/queue"],
  ["app/static/js/queue.js", "/api/queue/cancel"],
  ["app/static/js/queue.js", "/api/queue/interrupt"],
  ["app/static/js/i2i.js", "/api/i2i/upload"],
  ["app/static/js/i2i.js", "/api/i2i/from-history"],
  ["app/static/js/reference.js", "/api/reference-modules/upload"],
  ["app/static/js/loras.js", "/api/loras/catalog"],
  ["app/static/js/loras.js", "/api/loras/catalog/refresh"],
  ["app/static/js/settings.js", "/api/settings"],
  ["app/static/js/settings.js", "/api/settings/reset"],
  ["app/static/js/settings.js", "/api/diagnostics"],
  ["app/static/js/main.js", "/api/models"],
  ["app/static/js/prompt-dictionary.js", "/api/prompt-dictionary/status"],
  ["app/static/js/prompt-dictionary.js", "/api/prompt-dictionary/search"],
  ["app/static/js/prompt-converter.js", "/api/prompt-converter/status"],
  ["app/static/js/prompt-converter.js", "/api/prompt-converter/convert"],
  ["app/static/js/prompt-random.js", "/api/prompt-random-collect/status"],
  ["app/static/js/positive-prompts.js", "/api/prompts/positive-favorites"],
  ["app/static/js/positive-prompts.js", "/api/prompts/positive-templates"],
  ["app/static/js/recipes.js", "/api/recipes"],
  ["app/static/js/dynamic-prompt.js", "/api/dynamic-prompts/wildcards"],
  ["app/static/js/dynamic-prompt.js", "/api/dynamic-prompts/preview"],
  ["app/static/js/characters.js", "/api/catalog"],
  ["app/static/js/characters.js", "/api/favorites"],
  ["app/static/js/detailers.js", "/api/face-detailer/postprocess"],
  ["app/static/js/detailers.js", "/api/hand-detailer/postprocess"],
];

for (const [file, apiPath] of apiPathContracts) {
  requireIncludes(file, apiPath, `API path ${apiPath}`);
}

const requestBuilderFiles = [
  "app/static/js/generation-form.js",
  "app/static/js/loras.js",
  "app/static/js/history-request.js",
  "app/static/js/generation-actions.js",
  "app/static/js/history-reuse-data.js",
  "app/static/js/reference.js",
];
const payloadKeys = [
  "workflow_mode",
  "character1",
  "character2",
  "character3",
  "original_character",
  "rating",
  "rating_prompt_overrides",
  "quality_preset",
  "quality_prompt_overrides",
  "positive_prompt",
  "negative_prompt",
  "negative_prompt_raw",
  "negative_prompt_mode",
  "model",
  "text_encoder",
  "vae",
  "width",
  "height",
  "steps",
  "cfg",
  "shift",
  "sampler",
  "scheduler",
  "seed",
  "seed_mode",
  "official_loras",
  "preset_applied",
  "colorfix",
  "loras",
  "enabled",
  "count",
  "wait",
  "dynamic_prompt",
  "prompt_random_collect",
  "hires_fix",
  "reference_assist",
  "image_to_image",
  "face_detailer",
  "hand_detailer",
  "reference_modules",
  "background",
];

// These hints are deliberately string-based; future snapshot tests can tighten values.
for (const key of payloadKeys) {
  requireAnyIncludes(requestBuilderFiles, key, `payload key hint ${key}`);
}

const domIds = [
  "#positivePrompt",
  "#negativePrompt",
  "#payloadPreview",
  "#promptSheet",
  "#recipeSheet",
  "#dictQuery",
  "#dictResults",
  "#promptConvertSource",
  "#promptConvertResult",
  "#charSearch",
  "#charResults",
  "#charSlots",
  "#favRow",
  "#i2iStatus",
  "#refModStatus",
  "#backgroundEnabled",
  "#backgroundMode",
  "#backgroundStrength",
  "#backgroundStart",
  "#backgroundEnd",
  "#backgroundResize",
  "#backgroundPreview",
  "#officialColorfixEnabled",
  "#officialColorfixStrength",
  "#frameActionStatus",
  "#queueStatus",
  "#settingsStatus",
  "#fdEnabled",
  "#hdEnabled",
];

for (const selector of domIds) {
  if (!staticJsBundle.includes(selector)) fail("app/static/js", `missing DOM id contract ${selector}`);
}

const stateKeys = [
  "state.slots",
  "state.detailItem",
  "state.i2i",
  "state.refmod",
  "state.appSettings",
  "state.defaults",
  "state.promptSheetItems",
  "state.recipes",
];

for (const key of stateKeys) {
  if (!staticJsBundle.includes(key)) fail("app/static/js", `missing state key contract ${key}`);
}

if (failures.length) {
  console.error("frontend contract check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log(`checked frontend contracts: ${factoryContracts.length} factory files, ${actionContracts.length} actions, ${apiPathContracts.length} API paths, ${payloadKeys.length} payload keys`);
