# Frontend Modules

Luna ANIMA keeps the frontend as vanilla JavaScript modules under `app/static/js`. There is no build step, bundler, framework, or npm runtime dependency.

## Completion Line

After the frontend contract check PR is merged green, the large structural refactoring is complete. Future work should normally be feature improvement, observability, regression hardening, or bugfix work. Additional module splits should be small and justified by a clear maintenance or testing need.

Refactors must preserve API paths, request bodies, response shapes, `user_data` formats, workflow/prompt payloads, and ComfyUI payload structure unless a future task explicitly changes those contracts.

## Module Map

- `app.js`: compatibility bootstrap that loads `js/main.js`.
- `bootstrap.js`: DOM-ready startup helper.
- `main.js`: feature wiring, action registration, global events, and startup orchestration.
- `app-shell.js`: login, bootstrap, and app startup state application.
- `actions.js`: action registry and dispatch.
- `api.js`: authenticated API client and API error helpers.
- `state.js`: initial frontend state.
- `dom.js`: small DOM, value, formatting, and conversion utilities.
- `render-helpers.js`: shared render helpers for selects, metadata rows, and character summaries.
- `generation-form.js`: generate request collection, Hires.fix helpers, and form basics.
- `generation-actions.js`: payload preview, generate, and frame variations.
- `history.js`: history list, search, detail sheet, frame flags, public save, and sharing.
- `history-reuse.js`: compatibility facade for history reuse.
- `history-text.js`: history text extraction, generated prompt stripping, prompt terms, and quality inference.
- `history-reuse-data.js`: reuse data construction and applying reuse data to the form.
- `history-request.js`: history item to generate request and frame variation request construction.
- `prompt-library.js`: facade for prompt library submodules.
- `prompt-library-utils.js`: shared positive prompt helpers and prompt library utility functions.
- `positive-prompts.js`: positive prompt favorites and templates sheet.
- `prompt-dictionary.js`: prompt dictionary status, search, and insert.
- `prompt-converter.js`: Japanese-to-prompt conversion.
- `recipes.js`: recipe save, list, apply, used marking, and delete.
- `dynamic-prompt.js`: wildcard list and dynamic prompt preview.
- `prompt-presets.js`: rating, quality, negative, and auto prompt presets.
- `prompt-random.js`: Prompt Random Collect UI, settings, status, and instruction favorites.
- `characters.js`: character search, favorites, slots, and random slot selection.
- `loras.js`: LoRA catalog loading, configured LoRAs, rows, and request collection.
- `i2i.js`: image-to-image upload, history source, preview state, and request collection.
- `reference.js`: outfit/pose/background reference module upload, preview state, and request collection.
- `detailers.js`: face and hand detailer settings and postprocess actions.
- `settings.js`: settings, diagnostics, watermark, model reload, reset, and UI reload.
- `queue.js`: queue sheet, queue polling, cancel, refresh, and interrupt actions.

## Maintenance Rules

- Keep `main.js` focused on wiring and orchestration; feature logic belongs in feature modules.
- Keep `app/static/app.js` as the compatibility bootstrap.
- Keep `history-reuse.js` and `prompt-library.js` as compatibility facades for their submodules.
- Update static import cache tokens only when runtime JS changes.
- Run the local frontend checks before opening PRs that touch frontend code:
  - `node scripts/check_frontend_js.mjs`
  - `node scripts/check_static_import_tokens.mjs`
  - `node scripts/check_frontend_contracts.mjs`
