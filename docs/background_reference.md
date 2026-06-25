# Background Reference v1

Background Reference adds a third Reference Module alongside Outfit and Pose. It sends settings as `reference_modules.background` and is intended as ControlNet-like background guidance for composition, depth, silhouettes, room layout, and building structure.

## Request Shape

`reference_modules.background` accepts:

- `enabled`
- `image_id`
- `mode`: `depth`, `canny`, `lineart`, `softedge`, or `mlsd`
- `strength`
- `start_at`
- `end_at`
- `resize_mode`: `crop`, `fit`, or `stretch`
- `controlnet_model`: optional, defaults to `auto`

Old requests and history entries without `background` are filled with a disabled default.

## ComfyUI Requirements

v1 expects local ComfyUI support for ControlNet-style guidance:

- ControlNet loader/apply nodes
- ControlNet Aux or equivalent preprocessors
- Depth, Canny, Lineart, SoftEdge, or MLSD preprocessors
- Compatible ControlNet models for the selected mode

The mapping lives in `config/anima_mapping.json` under `background_reference`. Node class names and model choices can be adjusted there for the local ComfyUI environment. If the mapping, nodes, or models are missing, Background Reference stays non-breaking: the request is preserved, the workflow application is skipped, and diagnostics/warnings describe what is missing.

`resize_mode` is applied through the mapped image resize node, currently `ImageScale` by default. `crop` uses center crop before scaling, `stretch` uses exact non-crop scaling, and `fit` is a best-effort non-crop scale with a warning when only the standard `ImageScale` node is available. A padding-based fit workflow can be mapped later without changing the request shape.

See `docs/reference_setup.md` for the Reference Setup diagnostics and local ControlNet / ControlNet Aux setup notes.

## Scope

v1 is not a background compositing or masking feature. It does not fully lock the background image, isolate conditioning to background-only regions, generate SAM/GroundingDINO masks, or install ComfyUI extensions. Strong settings can affect characters and overall composition, so the defaults use low to medium strength.

Future candidates include IPAdapter Plus for style/composition reference, SAM/GroundingDINO for person/background masks, and LayerStyle/ImageCompositeMasked workflows for direct background composites.
