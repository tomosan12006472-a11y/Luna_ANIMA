from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import time
import urllib.parse
import urllib.request
import traceback
from typing import Any


@dataclass
class ComfyResult:
    ok: bool
    prompt_id: str | None = None
    image_url: str | None = None
    image_data_url: str | None = None
    history: dict[str, Any] | None = None
    error: str | None = None
    response_text: str | None = None
    stage: str = ""
    status: int | None = None
    node_errors: Any = None
    traceback_short: str = ""


def _http_json(url: str, timeout: float = 10) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def object_info(addr: str) -> dict[str, Any]:
    return _http_json(f"http://{addr}/object_info", timeout=10)


def queue_info(addr: str) -> dict[str, Any]:
    data = _http_json(f"http://{addr}/queue", timeout=10)
    return data if isinstance(data, dict) else {}


def history_item(addr: str, prompt_id: str) -> dict[str, Any] | None:
    history = _http_json(f"http://{addr}/history/{prompt_id}", timeout=10)
    if isinstance(history, dict) and prompt_id in history and isinstance(history[prompt_id], dict):
        return history[prompt_id]
    return None


def _contains_prompt_id(value: Any, prompt_id: str) -> bool:
    if isinstance(value, str):
        return value == prompt_id
    if isinstance(value, dict):
        return any(_contains_prompt_id(item, prompt_id) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_prompt_id(item, prompt_id) for item in value)
    return False


def queued_prompt_status(queue: dict[str, Any], prompt_id: str) -> str | None:
    if _contains_prompt_id(queue.get("queue_running"), prompt_id):
        return "running"
    if _contains_prompt_id(queue.get("queue_pending"), prompt_id):
        return "queued"
    return None


def queue_prompt(addr: str, payload: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"http://{addr}/prompt",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return {"ok": True, "status": response.status, "json": json.loads(text), "text": text}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return {"ok": False, "status": exc.code, "json": parsed, "text": text}
    except Exception as exc:
        return {"ok": False, "status": 0, "json": None, "text": str(exc)}


def upload_image(
    addr: str,
    *,
    filename: str,
    data: bytes,
    image_type: str = "input",
    subfolder: str = "",
    overwrite: bool = True,
    timeout: float = 60,
) -> dict[str, Any]:
    boundary = f"----anima-mobile-{int(time.time() * 1000)}"

    def field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode("utf-8")

    body = bytearray()
    body += field("type", image_type)
    body += field("subfolder", subfolder)
    body += field("overwrite", "true" if overwrite else "false")
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{PathSafeName(filename)}"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("utf-8")
    body += data
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(
        f"http://{addr}/upload/image",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            parsed = json.loads(text) if text else {}
            return {"ok": True, "status": response.status, "json": parsed, "text": text}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        return {"ok": False, "status": exc.code, "json": parsed, "text": text}
    except Exception as exc:
        return {"ok": False, "status": 0, "json": None, "text": str(exc)}


def PathSafeName(value: str) -> str:
    return str(value or "reference.png").replace("\\", "_").replace("/", "_").replace('"', "_")


def wait_history(addr: str, prompt_id: str, timeout: float = 600, interval: float = 1.5) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            history = _http_json(f"http://{addr}/history/{prompt_id}", timeout=10)
            if prompt_id in history:
                return history[prompt_id]
        except Exception:
            pass
        time.sleep(interval)
    return None


def first_output_image(history: dict[str, Any]) -> dict[str, Any] | None:
    outputs = history.get("outputs") if isinstance(history, dict) else None
    if not isinstance(outputs, dict):
        return None
    for node_output in outputs.values():
        images = node_output.get("images") if isinstance(node_output, dict) else None
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                return first
    return None


def fetch_image_data_url(addr: str, image: dict[str, Any]) -> tuple[str, str]:
    params = urllib.parse.urlencode(
        {
            "filename": image.get("filename", ""),
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
    )
    url = f"http://{addr}/view?{params}"
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type") or "image/png"
    return url, f"data:{content_type};base64,{base64.b64encode(raw).decode('ascii')}"


def run_generation(addr: str, payload: dict[str, Any], wait: bool = True) -> ComfyResult:
    try:
        queued = queue_prompt(addr, payload)
        if not queued["ok"]:
            parsed = queued.get("json") if isinstance(queued.get("json"), dict) else {}
            return ComfyResult(
                ok=False,
                error=f"ComfyUI /prompt failed: {queued['status']}",
                response_text=queued["text"],
                stage="submit_prompt",
                status=queued["status"],
                node_errors=parsed.get("node_errors"),
            )
        prompt_id = queued["json"].get("prompt_id") if isinstance(queued["json"], dict) else None
        if not wait or not prompt_id:
            return ComfyResult(ok=True, prompt_id=prompt_id, response_text=queued["text"], stage="queued", status=queued["status"])
        history = wait_history(addr, prompt_id)
        if not history:
            return ComfyResult(ok=False, prompt_id=prompt_id, error="Timed out waiting for ComfyUI history", stage="queue_wait")
        image = first_output_image(history)
        if not image:
            return ComfyResult(ok=False, prompt_id=prompt_id, history=history, error="No output image in ComfyUI history", stage="result_fetch")
        image_url, image_data_url = fetch_image_data_url(addr, image)
        return ComfyResult(ok=True, prompt_id=prompt_id, image_url=image_url, image_data_url=image_data_url, history=history, stage="result_fetch")
    except Exception as exc:
        return ComfyResult(
            ok=False,
            error=str(exc),
            stage="comfy_client",
            traceback_short="".join(traceback.format_exception_only(type(exc), exc)).strip(),
        )
