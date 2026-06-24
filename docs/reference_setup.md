# Reference Setup

Reference Modules are optional ComfyUI integrations. Luna ANIMA does not bundle model files, custom nodes, or extension repositories.

Use Settings -> Reference Setup or `/api/diagnostics/full` to check what your local ComfyUI can see.

## Outfit Reference / IPAdapter

Outfit Reference uses an IPAdapter-style apply node.

Typical local setup:

- Install an IPAdapter extension through ComfyUI Manager or your own `custom_nodes` workflow.
- `ComfyUI_IPAdapter_plus` commonly uses `models/clip_vision` and `models/ipadapter`.
- Some Unified Loader setups depend on exact filename rules.
- Install a compatible `clip_vision` model when your IPAdapter node requires it.
- Install an IPAdapter model compatible with your base model and node pack.

Luna ANIMA only checks node and model availability. It does not automatically download IPAdapter extensions or models.

## Pose / ControlNet

Pose Reference uses ControlNet-style nodes.

Expected pieces:

- `ControlNetLoader`
- `ControlNetApplyAdvanced` or a compatible apply node
- Optional `SetUnionControlNetType` when using union ControlNet models
- A compatible OpenPose/DWPose/Union ControlNet model
- A pose preprocessor such as DWPose/OpenPose, or a prepared pose image

For Luna ANIMA, Pose Reference is conservative and remains non-breaking when the compatible route is not confirmed.

## Background Reference / ControlNet Aux

Background Reference uses ControlNet plus ControlNet Aux or equivalent preprocessors to create hint images.

Supported modes:

- `depth`
- `canny`
- `lineart`
- `softedge`
- `mlsd`

Each mode needs both a preprocessor node and a compatible ControlNet model. The current mapping lives in `config/anima_mapping.json` under `background_reference`.

You can adjust per-mode values there:

- `preprocessor_node_class`
- `controlnet_model`
- optional `preprocessor_inputs`

When `controlnet_model` is `auto`, Luna ANIMA chooses from ComfyUI `object_info` by mode keywords. If the mapping is disabled, nodes are missing, or a model is missing, Background Reference preserves the request and skips workflow application with diagnostics instead of crashing.

## Local Setup Helper

Dry-run:

```bat
python scripts\comfyui_reference_setup_plan.py
```

Create empty expected directories only:

```bat
python scripts\comfyui_reference_setup_plan.py --write-dirs
```

Plan downloads from a manifest without external access:

```bat
python scripts\comfyui_reference_setup_plan.py --download-manifest docs\reference_setup_manifest.example.json
```

Download is disabled unless both `--download-manifest` and `--allow-download` are provided. Only use a manifest you trust and only for files whose license you have checked.
