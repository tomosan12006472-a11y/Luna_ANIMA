from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve


DEFAULT_ROOTS = [Path(r"D:\AI\ComfyUI\ComfyUI"), Path(r"D:\AI\ComfyUI")]
REQUIRED_DIRS = [
    "custom_nodes",
    "models/controlnet",
    "models/ipadapter",
    "models/ipadapter-flux",
    "models/clip_vision",
    "models/loras",
]
ALLOWED_DOWNLOAD_DIRS = {directory.replace("\\", "/") for directory in REQUIRED_DIRS if directory.startswith("models/")}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else []
    return [item for item in items if isinstance(item, dict)]


def root_status(root: Path, *, write_dirs: bool) -> dict[str, Any]:
    dirs = []
    for relative in REQUIRED_DIRS:
        path = root / relative
        if write_dirs:
            path.mkdir(parents=True, exist_ok=True)
        dirs.append({"path": str(path), "exists": path.exists()})
    custom_nodes = root / "custom_nodes"
    installed_nodes = []
    if custom_nodes.exists():
        installed_nodes = [child.name for child in sorted(custom_nodes.iterdir(), key=lambda item: item.name.lower()) if child.is_dir()]
    return {"root": str(root), "exists": root.exists(), "dirs": dirs, "custom_nodes": installed_nodes[:100]}


def download_manifest_items(root: Path, manifest: list[dict[str, Any]], *, allow_download: bool) -> list[dict[str, Any]]:
    results = []
    resolved_root = root.resolve()
    for item in manifest:
        target_subdir = str(item.get("target_subdir") or "").strip().replace("\\", "/")
        filename = str(item.get("filename") or "").strip()
        url = str(item.get("url") or "").strip()
        expected_sha = str(item.get("sha256") or "").strip().lower()
        target = root / target_subdir / filename
        plan = {
            "name": item.get("name") or filename,
            "kind": item.get("kind") or "",
            "target": str(target),
            "url": url,
            "exists": target.exists(),
            "downloaded": False,
            "sha256_ok": None,
        }
        if not target_subdir or not filename or not url:
            plan["error"] = "manifest item requires target_subdir, filename, and url"
            results.append(plan)
            continue
        target_subdir_path = Path(target_subdir)
        filename_path = Path(filename)
        if target_subdir_path.is_absolute() or filename_path.is_absolute() or ".." in target_subdir_path.parts or ".." in filename_path.parts:
            plan["error"] = "target_subdir and filename must be relative paths without '..'"
            results.append(plan)
            continue
        if target_subdir not in ALLOWED_DOWNLOAD_DIRS:
            plan["error"] = f"target_subdir must be one of: {', '.join(sorted(ALLOWED_DOWNLOAD_DIRS))}"
            results.append(plan)
            continue
        resolved_target = target.resolve()
        try:
            resolved_target.relative_to(resolved_root)
        except ValueError:
            plan["error"] = "target must stay inside the selected ComfyUI root"
            results.append(plan)
            continue
        plan["target"] = str(resolved_target)
        if not allow_download:
            plan["planned_only"] = True
            results.append(plan)
            continue
        resolved_target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = resolved_target.with_name(f"{resolved_target.name}.tmp")
        urlretrieve(url, temp_target)
        if expected_sha:
            actual_sha = sha256_file(temp_target).lower()
            if actual_sha != expected_sha:
                temp_target.unlink(missing_ok=True)
                plan["sha256_ok"] = False
                plan["error"] = "sha256 mismatch"
                results.append(plan)
                continue
            plan["sha256_ok"] = True
        temp_target.replace(resolved_target)
        plan["downloaded"] = True
        plan["exists"] = resolved_target.exists()
        results.append(plan)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run Reference Module setup checks for local ComfyUI.")
    parser.add_argument("--comfyui-root", action="append", default=[], help="ComfyUI root to inspect. Can be repeated.")
    parser.add_argument("--write-dirs", action="store_true", help="Create empty expected directories.")
    parser.add_argument("--download-manifest", help="Optional manifest path. Planned only unless --allow-download is set.")
    parser.add_argument("--allow-download", action="store_true", help="Allow downloads from --download-manifest URLs.")
    args = parser.parse_args()

    roots = [Path(value) for value in args.comfyui_root] if args.comfyui_root else DEFAULT_ROOTS
    statuses = [root_status(root, write_dirs=args.write_dirs) for root in roots]
    primary = next((Path(item["root"]) for item in statuses if item["exists"]), roots[0])
    manifest_results = []
    if args.download_manifest:
        manifest = load_manifest(Path(args.download_manifest))
        manifest_results = download_manifest_items(primary, manifest, allow_download=args.allow_download)
    output = {
        "ok": True,
        "dry_run": not args.write_dirs and not args.allow_download,
        "write_dirs": bool(args.write_dirs),
        "allow_download": bool(args.allow_download),
        "roots": statuses,
        "manifest": manifest_results,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
