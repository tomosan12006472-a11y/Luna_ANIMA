"""Payload regression check: compare generation payloads between a git ref and the working tree.

Usage (from the repo root, either repo):

    .venv\\Scripts\\python.exe tools\\payload_regression_check.py --base HEAD
    .venv\\Scripts\\python.exe tools\\payload_regression_check.py --base HEAD~1

The script builds the same fixed request matrix against two versions of `app.payload_builder`:
the given --base git ref (checked out into a temporary worktree) and the current working tree.
It reports per-case differences and writes full dumps under user_data/diff_reports/.

Exit codes: 0 = all cases identical, 1 = differences found, 2 = execution error.

Notes:
- stdlib only. ComfyUI does not need to be running.
- Date-dependent output naming is stubbed so runs are deterministic.
- Original-character cases pick names from the catalog at runtime; if no original
  characters exist they are skipped (skipped on both sides counts as identical).
- The matrix lives in saa_cases()/anima_cases(). When you add a feature that changes
  payload building on purpose, run this BEFORE the change, apply the change, run it
  again, confirm only the intended cases differ, then extend the matrix to cover the
  new feature.
"""
from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SKIPPED = "__skipped__"


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def detect_kind(root: Path) -> str:
    return "anima" if (root / "app" / "anima_adapter.py").exists() else "saa"


# ---------------------------------------------------------------------------
# Request matrices (kept deliberately explicit; do not depend on CSV contents)
# ---------------------------------------------------------------------------

def _mk(base: dict[str, Any], **over: Any) -> dict[str, Any]:
    req = json.loads(json.dumps(base))
    req.update(over)
    return req


def saa_cases(orig_names: list[str]) -> dict[str, Any]:
    base: dict[str, Any] = {
        "workflow_mode": "saa_compatible",
        "model": "waiIllustriousSDXL_v160.safetensors",
        "sampler": "euler_ancestral",
        "scheduler": "normal",
        "steps": 24,
        "cfg": 6.5,
        "width": 896,
        "height": 1152,
        "seed": 123456789,
        "vpred": "Auto",
        "character1": "totally_unknown_tag (fake)",
        "character2": "None",
        "character3": "None",
        "original_character": "None",
        "character1_weight": 1.0,
        "character2_weight": 1.0,
        "character3_weight": 1.0,
        "original_weight": 1.0,
        "common_prompt": "masterpiece, best quality",
        "view_prompt": "upper body",
        "positive_prompt": "silver armor, glowing sword",
        "negative_prompt": "text, logo",
        "negative_prompt_raw": "text, logo",
        "negative_prompt_mode": "custom",
        "negative_source_default": "bad quality,worst quality",
        "prompt_ban": "",
        "loras": [],
        "dynamic_prompt": {"enabled": False},
        "hires_fix": {"enabled": False},
        "reference_assist": {"enabled": False, "apply_to_payload": False},
        "reference_modules": {"enabled": True, "outfit": {"enabled": False}, "pose": {"enabled": False}},
        "image_to_image": {"enabled": False, "apply_to_payload": False},
        "face_detailer": {"enabled": False},
        "queue_index": 0,
    }
    cases: dict[str, Any] = {
        "standard": _mk(base),
        "neg_source": _mk(base, negative_prompt_mode="source"),
        "neg_append": _mk(base, negative_prompt_mode="append"),
        "weighted_chars": _mk(base, character2="another_fake_tag", character2_weight=0.85),
        "prompt_ban": _mk(base, prompt_ban="glowing sword, silver", positive_prompt="silver armor, glowing sword, ruins"),
        "lora_modes": _mk(base, loras=[
            {"enabled": True, "name": "a/all.safetensors", "mode": "ALL", "strength_model": 0.8, "strength_clip": 0.35},
            {"enabled": True, "name": "b/base.safetensors", "mode": "Base", "strength_model": 0.7, "strength_clip": 0.6},
            {"enabled": True, "name": "c/hifix.safetensors", "mode": "HiFix", "strength_model": 0.5, "strength_clip": 0.4},
            {"enabled": True, "name": "d/off.safetensors", "mode": "OFF", "strength_model": 0.5, "strength_clip": 0.5},
            {"enabled": False, "name": "e/disabled.safetensors", "mode": "ALL"},
            {"enabled": True, "name": "f/legacy.safetensors", "weight": 0.9},
        ]),
        "dynamic_on": _mk(base, dynamic_prompt={"enabled": True, "wildcard_seed": 24680}, positive_prompt="armor, __pose__"),
        "hires_latent": _mk(base, workflow_mode="saa_mobile_extended", hires_fix={"enabled": True, "mode": "latent", "upscale_factor": 1.5, "latent_upscale_method": "bicubic", "denoise": 0.42, "steps": 18}),
        "hires_model": _mk(base, workflow_mode="saa_mobile_extended", hires_fix={"enabled": True, "mode": "model", "target_width": 1344, "target_height": 1728, "upscale_model": "RealESRGAN_x4.pth", "denoise": 0.35, "steps": 15}),
        "hires_ignored_compat": _mk(base, workflow_mode="saa_compatible", hires_fix={"enabled": True, "mode": "latent", "upscale_factor": 1.5}),
        "vpred_explicit": _mk(base, vpred="v_prediction"),
        "vpred_zsnr": _mk(base, vpred="zsnr"),
        "vpred_auto_name": _mk(base, model="someModel_vPred10.safetensors"),
        "i2i_applied": _mk(base, image_to_image={"enabled": True, "apply_to_payload": True, "denoise": 0.5, "comfyui_image": {"name": "i2i_src.png", "subfolder": "", "type": "input"}, "image_id": "x"}),
        "ref_assist_advanced": _mk(base, reference_assist={"enabled": True, "apply_to_payload": True, "comfyui_image": {"name": "ref.png"}, "controlnet_model": "control_v11p.safetensors", "apply_node_type": "ControlNetApplyAdvanced", "strength": 0.55, "start_percent": 0.05, "end_percent": 0.7, "has_union_type": True, "union_type": "openpose"}),
        "ref_assist_legacy": _mk(base, reference_assist={"enabled": True, "apply_to_payload": True, "comfyui_image": {"name": "ref.png"}, "controlnet_model": "control_v11p.safetensors", "apply_node_type": "ControlNetApply", "strength": 0.5}),
        "face_detailer_gen": _mk(base, face_detailer={"enabled": True, "steps": 12, "cfg": 5.0, "denoise": 0.3}, queue_index=1),
        "fd_with_i2i": _mk(
            base,
            face_detailer={"enabled": True, "steps": 12},
            image_to_image={"enabled": True, "apply_to_payload": True, "denoise": 0.5, "comfyui_image": {"name": "i2i_src.png"}, "image_id": "x"},
        ),
    }
    if orig_names:
        cases["original_slot4"] = _mk(base, original_character=orig_names[0], original_weight=1.15)
    else:
        cases["original_slot4"] = SKIPPED
    return cases


def anima_cases(orig_names: list[str]) -> dict[str, Any]:
    base: dict[str, Any] = {
        "workflow_mode": "anima",
        "model": "Anima\\anima-preview3-base.safetensors",
        "text_encoder": "qwen_3_06b_base.safetensors",
        "vae": "qwen_image_vae.safetensors",
        "sampler": "er_sde",
        "scheduler": "simple",
        "steps": 28,
        "cfg": 4.5,
        "shift": None,
        "width": 1024,
        "height": 1536,
        "seed": 123456789,
        "rating": "safe",
        "quality_preset": "standard",
        "negative_preset": "anima_recommended",
        "meta_prompt": "anime illustration",
        "year_prompt": "",
        "outfit_prompt": "white dress",
        "expression_prompt": "soft smile",
        "pose_prompt": "",
        "background_prompt": "library",
        "camera_prompt": "",
        "lighting_prompt": "",
        "natural_description": "",
        "character1": "totally_unknown_tag (fake)",
        "character2": "None",
        "character3": "None",
        "character1_role": "main",
        "character2_role": "left",
        "character3_role": "right",
        "original_character": "None",
        "character1_weight": 1.0,
        "character2_weight": 1.0,
        "character3_weight": 1.0,
        "original_weight": 1.0,
        "common_prompt": "",
        "positive_prompt": "ornate details",
        "negative_prompt": "text, logo",
        "negative_prompt_raw": "text, logo",
        "negative_prompt_mode": "append",
        "prompt_ban": "",
        "loras": [],
        "official_loras": {"highres": {"enabled": False}, "turbo": {"enabled": False}},
        "dynamic_prompt": {"enabled": False},
        "hires_fix": {"enabled": False},
        "reference_assist": {"enabled": False, "apply_to_payload": False},
        "reference_modules": {"enabled": True, "outfit": {"enabled": False}, "pose": {"enabled": False}},
        "image_to_image": {"enabled": False, "apply_to_payload": False},
        "face_detailer": {"enabled": False},
        "queue_index": 0,
    }
    cases: dict[str, Any] = {
        "standard": _mk(base),
        "neg_custom": _mk(base, negative_prompt_mode="custom"),
        "neg_preset": _mk(base, negative_prompt_mode="preset"),
        "quality_high": _mk(base, quality_preset="high"),
        "quality_freeform": _mk(base, quality_preset="my custom quality words"),
        "rating_nsfw": _mk(base, rating="nsfw"),
        "two_girls": _mk(base, character2="second_fake_tag"),
        "shift_request": _mk(base, shift=2.5),
        "shift_invalid": _mk(base, shift="abc"),
        "official_loras_resolved_only": {"__resolve_only__": True, "request": _mk(base, official_loras={"highres": {"enabled": True, "strength": 0.55}, "turbo": {"enabled": True, "version": "auto", "strength": 0.45}})},
        "catalog_loras": _mk(base, loras=[
            {"enabled": True, "name": "x/clip_pair.safetensors", "application": "model_clip", "strength_model": 0.8, "strength_clip": 0.3},
            {"enabled": True, "name": "y/model_only.safetensors", "application": "model_only", "strength_model": 0.65},
            {"enabled": True, "name": "z/off.safetensors", "application": "off"},
            {"enabled": True, "name": "w/legacy_mode.safetensors", "mode": "Base", "strength_model": 0.7, "strength_clip": 0.7},
            {"enabled": True, "name": "v/model_only_legacy.safetensors", "application": "model_clip", "model_strength": 0.65},
        ]),
        "dynamic_on": _mk(base, dynamic_prompt={"enabled": True, "wildcard_seed": 24680}, positive_prompt="ornate, __pose__"),
        "i2i_applied": _mk(base, image_to_image={"enabled": True, "apply_to_payload": True, "denoise": 0.5, "comfyui_image": {"name": "i2i_src.png"}, "image_id": "x"}),
        "ref_assist": _mk(base, reference_assist={"enabled": True, "apply_to_payload": True, "comfyui_image": {"name": "ref.png"}, "controlnet_model": "ctl.safetensors", "apply_node_type": "ControlNetApplyAdvanced", "strength": 0.3, "start_percent": 0.0, "end_percent": 0.6, "has_union_type": False}),
        "face_detailer_gen": _mk(base, face_detailer={"enabled": True, "steps": 12, "cfg": 4.0, "denoise": 0.3}, queue_index=2),
        "lora_sample": _mk(base, workflow_mode="anima_lora_sample", positive_prompt="", common_prompt="cute girl", negative_prompt_mode="custom", negative_prompt_raw=""),
    }
    if orig_names:
        cases["original_slot4"] = _mk(base, original_character=orig_names[0])
        cases["original_custom_role"] = _mk(base, character2=f"original:{orig_names[0]}", character2_role="behind")
        cases["natural_manual"] = _mk(base, natural_description="Hand written description.", character2=f"original:{orig_names[0]}")
    else:
        cases["original_slot4"] = SKIPPED
        cases["original_custom_role"] = SKIPPED
        cases["natural_manual"] = SKIPPED
    if len(orig_names) >= 3:
        cases["original_roles"] = _mk(
            base,
            character1=f"original:{orig_names[0]}",
            character2=f"original:{orig_names[1]}",
            character3=f"original:{orig_names[2]}",
        )
    else:
        cases["original_roles"] = SKIPPED
    return cases


# ---------------------------------------------------------------------------
# Child mode: dump payloads for one repo root
# ---------------------------------------------------------------------------

def run_dump(root: Path) -> int:
    sys.path.insert(0, str(root))
    from app import payload_builder  # type: ignore

    def stable_subfolder(*, panel_id: str, generation_method: str, now=None) -> str:
        return f"20990101/{panel_id}/{generation_method}"

    def stable_prefix(*, panel_id: str, generation_method: str, original_prefix: str, now=None) -> str:
        return f"20990101/{panel_id}/{generation_method}/{original_prefix}"

    payload_builder.build_output_subfolder = stable_subfolder
    payload_builder.build_output_prefix = stable_prefix

    orig_names = sorted(
        str(getattr(entry, "display_name", "") or "")
        for entry in getattr(payload_builder.catalog, "original", [])
        if str(getattr(entry, "display_name", "") or "")
    )[:3]

    kind = detect_kind(root)
    cases = anima_cases(orig_names) if kind == "anima" else saa_cases(orig_names)
    out: dict[str, Any] = {"__kind__": kind, "__original_names__": orig_names}
    for name, req in cases.items():
        if req == SKIPPED:
            out[name] = SKIPPED
            continue
        try:
            if isinstance(req, dict) and req.get("__resolve_only__"):
                out[name] = payload_builder.resolve_official_loras(req["request"])
                continue
            out[name] = {
                "prompts": payload_builder.build_prompts(json.loads(json.dumps(req))),
                "payload": payload_builder.build_prompt_payload(json.loads(json.dumps(req)), "regression-client"),
            }
        except Exception as exc:
            out[name] = {"__error__": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# Parent mode: worktree management and comparison
# ---------------------------------------------------------------------------

def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True)


def copy_user_inputs(worktree: Path) -> list[str]:
    copied: list[str] = []
    src_dir = REPO_ROOT / "user_data"
    dst_dir = worktree / "user_data"
    oc = src_dir / "original_characters.json"
    if oc.is_file():
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(oc, dst_dir / oc.name)
        copied.append(str(oc.relative_to(REPO_ROOT)))
    wc = src_dir / "dynamic_prompt_wildcards"
    if wc.is_dir():
        shutil.copytree(wc, dst_dir / wc.name, dirs_exist_ok=True)
        copied.append(str(wc.relative_to(REPO_ROOT)))
    return copied


def dump_for(root: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--dump-only", str(root)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"dump failed for {root}:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def main() -> int:
    _utf8_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="HEAD", help="git ref to compare against (default: HEAD)")
    parser.add_argument("--dump-only", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.dump_only:
        return run_dump(Path(args.dump_only))

    resolved = git("rev-parse", "--short", args.base)
    if resolved.returncode != 0:
        print(f"[error] unknown git ref: {args.base}\n{resolved.stderr.strip()}")
        return 2
    base_ref = resolved.stdout.strip()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = REPO_ROOT / "user_data" / "diff_reports" / f"payload_regression_{stamp}_{base_ref}"
    report_dir.mkdir(parents=True, exist_ok=True)

    worktree = Path(tempfile.mkdtemp(prefix="payload_regression_")) / "base"
    added = git("worktree", "add", "--detach", str(worktree), base_ref)
    if added.returncode != 0:
        print(f"[error] git worktree add failed:\n{added.stderr.strip()}")
        return 2
    try:
        copied = copy_user_inputs(worktree)
        base_dump = dump_for(worktree)
        current_dump = dump_for(REPO_ROOT)
    finally:
        git("worktree", "remove", "--force", str(worktree))
        git("worktree", "prune")
        shutil.rmtree(worktree.parent, ignore_errors=True)

    (report_dir / "base.json").write_text(json.dumps(base_dump, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (report_dir / "current.json").write_text(json.dumps(current_dump, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    names = sorted(set(base_dump) | set(current_dump))
    identical: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    different: list[str] = []
    for name in names:
        if name.startswith("__"):
            continue
        old_value = base_dump.get(name, "__missing__")
        new_value = current_dump.get(name, "__missing__")
        if old_value == SKIPPED and new_value == SKIPPED:
            skipped.append(name)
            continue
        if isinstance(old_value, dict) and "__error__" in old_value or isinstance(new_value, dict) and "__error__" in new_value:
            if old_value == new_value:
                errors.append(f"{name} (same error on both sides)")
                continue
            errors.append(name)
        if old_value == new_value:
            identical.append(name)
            continue
        different.append(name)
        old_text = json.dumps(old_value, ensure_ascii=False, indent=1, sort_keys=True).splitlines(keepends=True)
        new_text = json.dumps(new_value, ensure_ascii=False, indent=1, sort_keys=True).splitlines(keepends=True)
        diff_text = "".join(difflib.unified_diff(old_text, new_text, fromfile=f"{name}@{base_ref}", tofile=f"{name}@working-tree"))
        (report_dir / f"diff_{name}.txt").write_text(diff_text, encoding="utf-8")

    summary_lines = [
        f"base ref      : {args.base} ({base_ref})",
        f"repo          : {REPO_ROOT}",
        f"kind          : {current_dump.get('__kind__')}",
        f"original names: {current_dump.get('__original_names__')}",
        f"copied inputs : {copied or 'none'}",
        f"identical     : {len(identical)}",
        f"different     : {len(different)} {different or ''}",
        f"skipped       : {len(skipped)} {skipped or ''}",
        f"errors        : {len(errors)} {errors or ''}",
        f"report dir    : {report_dir}",
    ]
    summary = "\n".join(str(line) for line in summary_lines)
    (report_dir / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    print(summary)
    if different:
        print("\n--- first differing case preview ---")
        preview = (report_dir / f"diff_{different[0]}.txt").read_text(encoding="utf-8").splitlines()
        print("\n".join(preview[:40]))
        print(f"\nNG: {len(different)} case(s) differ. Full diffs in {report_dir}")
        return 1
    print("\nOK: all cases identical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
