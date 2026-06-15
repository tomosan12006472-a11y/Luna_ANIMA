from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any
from urllib import error, request

from .character_names import display_name_ja, prompt_safe_character_name


PROVIDER_DEFAULT_URLS = {
    "lmstudio": "http://127.0.0.1:1234/v1",
    "ollama": "http://127.0.0.1:11434/v1",
    "llama.cpp": "http://127.0.0.1:8080/v1",
}

SCORE_TAG_RE = re.compile(r"^[\(\[\{]*score_\d+(?:_up)?(?::[0-9.]+)?[\)\]\}]*$", re.IGNORECASE)
LORA_RE = re.compile(r"<\s*lora:[^>]+>", re.IGNORECASE)
WILDCARD_RE = re.compile(r"__[^_\n]+__")


def _desktop_shortcut() -> str:
    home = Path.home()
    candidates = [
        home / "OneDrive" / "デスクトップ" / "LM Studio Qwen3.6.lnk",
        home / "Desktop" / "LM Studio Qwen3.6.lnk",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return ""


DEFAULT_PROMPT_CONVERTER_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "provider": "lmstudio",
    "base_url": "http://127.0.0.1:1234/v1",
    "model": "auto",
    "api_key": "",
    "timeout_sec": 240,
    "temperature": 0.2,
    "max_tokens": 1200,
    "auto_start": {
        "enabled": True,
        "command": _desktop_shortcut(),
        "health_timeout_sec": 60,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _normalize_provider(value: Any) -> str:
    provider = str(value or "lmstudio").strip().lower().replace(" ", "")
    if provider in {"lmstudio", "lm-studio"}:
        return "lmstudio"
    if provider == "ollama":
        return "ollama"
    if provider in {"llama", "llamacpp", "llama.cpp"}:
        return "llama.cpp"
    return "lmstudio"


def _normalize_base_url(value: Any, provider: str) -> str:
    text = str(value or PROVIDER_DEFAULT_URLS.get(provider) or PROVIDER_DEFAULT_URLS["lmstudio"]).strip().rstrip("/")
    if not text:
        text = PROVIDER_DEFAULT_URLS.get(provider) or PROVIDER_DEFAULT_URLS["lmstudio"]
    if provider in PROVIDER_DEFAULT_URLS and not text.endswith("/v1"):
        text = f"{text}/v1"
    return text.rstrip("/")


def sanitize_prompt_converter_settings(settings: Any) -> dict[str, Any]:
    raw = settings if isinstance(settings, dict) else {}
    result = _deep_merge(DEFAULT_PROMPT_CONVERTER_SETTINGS, raw)
    provider = _normalize_provider(result.get("provider"))
    result["enabled"] = bool(result.get("enabled", True))
    result["provider"] = provider
    result["base_url"] = _normalize_base_url(result.get("base_url"), provider)
    result["model"] = str(result.get("model") or "auto").strip() or "auto"
    result["api_key"] = str(result.get("api_key") or "")
    result["timeout_sec"] = _clamp_float(result.get("timeout_sec"), 240.0, 3.0, 300.0)
    result["temperature"] = _clamp_float(result.get("temperature"), 0.2, 0.0, 2.0)
    result["max_tokens"] = _clamp_int(result.get("max_tokens"), 1200, 64, 4096)
    auto_start = result.setdefault("auto_start", {})
    auto_start["enabled"] = bool(auto_start.get("enabled", True))
    auto_start["command"] = str(auto_start.get("command") or _desktop_shortcut()).strip()
    auto_start["health_timeout_sec"] = _clamp_float(auto_start.get("health_timeout_sec"), 60.0, 3.0, 300.0)
    return result


def _route(config: dict[str, Any], path: str) -> str:
    return f"{str(config.get('base_url') or '').rstrip('/')}/{path.lstrip('/')}"


def _json_request(method: str, url: str, payload: dict[str, Any] | None, config: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    api_key = str(config.get("api_key") or "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = request.Request(url, data=data, method=method, headers=headers)
    with request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    return json.loads(body) if body else {}


def _models_from_response(data: dict[str, Any]) -> list[str]:
    items = data.get("data")
    if not isinstance(items, list):
        return []
    models: list[str] = []
    for item in items:
        if isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or "").strip()
            if model_id:
                models.append(model_id)
    return models


def prompt_converter_status(settings: Any) -> dict[str, Any]:
    config = sanitize_prompt_converter_settings(settings)
    if not config["enabled"]:
        return {"ok": True, "enabled": False, "reachable": False, "provider": config["provider"], "base_url": config["base_url"], "models": []}
    try:
        data = _json_request("GET", _route(config, "models"), None, config, min(float(config["timeout_sec"]), 10.0))
        models = _models_from_response(data)
        configured = str(config.get("model") or "auto")
        active_model = models[0] if configured == "auto" and models else configured
        return {
            "ok": True,
            "enabled": True,
            "reachable": True,
            "provider": config["provider"],
            "base_url": config["base_url"],
            "model": configured,
            "active_model": active_model,
            "model_available": configured == "auto" or configured in models,
            "models": models,
        }
    except Exception as exc:
        return {
            "ok": True,
            "enabled": True,
            "reachable": False,
            "provider": config["provider"],
            "base_url": config["base_url"],
            "model": config.get("model") or "auto",
            "models": [],
            "message": str(exc),
        }


def _start_provider(config: dict[str, Any]) -> str:
    auto_start = config.get("auto_start") if isinstance(config.get("auto_start"), dict) else {}
    command = str(auto_start.get("command") or "").strip()
    if not command:
        return "auto_start command is empty"
    try:
        if os.name == "nt" and Path(command).exists():
            os.startfile(command)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(command, shell=True)
        return ""
    except Exception as exc:
        return str(exc)


def _ensure_ready(config: dict[str, Any]) -> dict[str, Any]:
    status = prompt_converter_status(config)
    if status.get("reachable"):
        return status
    auto_start = config.get("auto_start") if isinstance(config.get("auto_start"), dict) else {}
    if not auto_start.get("enabled"):
        return status
    start_error = _start_provider(config)
    if start_error:
        status["message"] = f"{status.get('message') or ''}; auto_start failed: {start_error}".strip("; ")
        return status
    deadline = time.time() + float(auto_start.get("health_timeout_sec") or 60.0)
    while time.time() < deadline:
        time.sleep(1.0)
        status = prompt_converter_status(config)
        if status.get("reachable"):
            return status
    return status


def _system_prompt(app_scope: str) -> str:
    scope = "ANIMA" if app_scope == "anima" else "SAA"
    return (
        "You are a prompt conversion engine for anime image generation. "
        f"The target app is {scope}. Convert Japanese or mixed-language source text into English prompts. "
        "Preserve the user's exact intent, including explicit adult terms when present. "
        "Do not censor, soften, euphemize, moralize, or add safety disclaimers. "
        "Do not add LoRA syntax, wildcard syntax, Dynamic Prompt syntax, model names, negative prompts, or explanations. "
        "Return strict JSON only with keys natural_en and tags_en. "
        "natural_en is one concise English natural-language prompt. "
        "tags_en is comma-separated English tags. Use spaces instead of underscores in tags, except score tags like score_9 and score_8_up. "
        "Translate literally and avoid adding generic filler tags that were not requested, such as hair, face, body, high quality, or anime style. "
        "Only use the source_text content. Do not infer or add characters, poses, clothing, camera, location, quality tags, or style terms that are absent from source_text. "
        "In Japanese prompts, ワンピース usually means a dress; translate it as dress or one-piece dress unless swimsuit, swimwear, bikini, or 水着 is explicitly present. "
        "Do not include Markdown or surrounding commentary."
    )


def _user_prompt(source_text: str, mode: str, existing_positive: str) -> str:
    return json.dumps(
        {
            "requested_output_mode": mode,
            "source_text": source_text,
        },
        ensure_ascii=False,
        indent=2,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
        candidates = list(reversed(fenced))
        candidates.extend(match.group(0) for match in reversed(list(re.finditer(r"\{.*?\}", raw, flags=re.DOTALL))))
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                data = json.loads(candidate)
                break
            except json.JSONDecodeError as exc:
                last_error = exc
        else:
            if last_error:
                raise last_error
            raise
    if not isinstance(data, dict):
        raise ValueError("converter response was not a JSON object")
    return data


def split_prompt_tags(text: Any) -> list[str]:
    return [
        part.strip()
        for part in re.split(r",|;|\n", str(text or ""))
        if part and part.strip()
    ]


def normalize_tag(tag: Any) -> str:
    text = LORA_RE.sub("", str(tag or ""))
    text = WILDCARD_RE.sub("", text)
    text = text.strip().strip(",;.")
    if not text:
        return ""
    if not SCORE_TAG_RE.fullmatch(text):
        text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip(" ,;.")
    return text


def _dedupe_key(tag: str) -> str:
    text = normalize_tag(tag).lower()
    text = re.sub(r"^[\(\[\{]+|[\)\]\}]+$", "", text)
    text = re.sub(r":[0-9.]+$", "", text)
    return re.sub(r"\s+", " ", text).strip(" ,;.")


def normalize_tag_prompt(text: Any, existing_positive: Any = "") -> str:
    existing_keys = {_dedupe_key(part) for part in split_prompt_tags(existing_positive)}
    existing_keys.discard("")
    seen = set(existing_keys)
    out: list[str] = []
    for raw in split_prompt_tags(text):
        tag = normalize_tag(raw)
        key = _dedupe_key(tag)
        if not tag or not key or key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return ", ".join(out)


def normalize_natural_prompt(text: Any) -> str:
    raw = LORA_RE.sub("", str(text or ""))
    raw = WILDCARD_RE.sub("", raw)
    return re.sub(r"\s+", " ", raw).strip(" ,")


def _candidate_terms(entry: Any) -> list[str]:
    terms: list[str] = []
    prompt_tag = str(getattr(entry, "prompt_tag", "") or "")
    display_name = str(getattr(entry, "display_name", "") or "").strip()
    for value in [
        display_name,
        display_name_ja(display_name, prompt_tag),
        prompt_safe_character_name(display_name, prompt_tag),
        str(getattr(entry, "id", "") or "").strip(),
    ]:
        if value:
            terms.append(value)
    first_tag = prompt_tag.split(",", 1)[0].strip()
    if first_tag:
        terms.append(first_tag)
    triggers = getattr(entry, "trigger_words", None) or []
    if isinstance(triggers, list):
        terms.extend(str(item) for item in triggers if item)
    return [term.strip() for term in terms if len(term.strip()) >= 3]


def _contains_term(haystack: str, term: str) -> bool:
    if term.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", haystack) is not None
    return term.lower() in haystack


def character_warnings(source_text: Any, natural_en: Any, tags_en: Any, catalog_entries: list[Any]) -> list[dict[str, Any]]:
    haystack = "\n".join([str(source_text or ""), str(natural_en or ""), str(tags_en or "")]).lower()
    matched: list[str] = []
    seen: set[str] = set()
    for entry in catalog_entries:
        display_name = str(getattr(entry, "display_name", "") or "").strip()
        prompt_tag = str(getattr(entry, "prompt_tag", "") or "").strip()
        label = display_name_ja(display_name, prompt_tag)
        if not display_name or label in seen:
            continue
        if any(_contains_term(haystack, term) for term in _candidate_terms(entry)):
            seen.add(label)
            matched.append(label)
        if len(matched) >= 5:
            break
    if not matched:
        return []
    return [
        {
            "code": "character_match",
            "message": f"キャラ名候補を検出: {', '.join(matched)}。キャラ指定欄と重複する場合は確認してください。",
            "characters": matched,
        }
    ]


def _chat_completion(config: dict[str, Any], model: str, source_text: str, mode: str, existing_positive: str, app_scope: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _system_prompt(app_scope)},
            {"role": "user", "content": _user_prompt(source_text, mode, existing_positive)},
        ],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "stream": False,
    }
    data = _json_request("POST", _route(config, "chat/completions"), payload, config, float(config["timeout_sec"]))
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ValueError("converter response did not include choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    reasoning_content = message.get("reasoning_content") if isinstance(message, dict) else ""
    return _parse_json_object(str(content or reasoning_content or ""))


def convert_prompt_text(
    settings: Any,
    *,
    source_text: str,
    mode: str,
    existing_positive: str,
    app_scope: str,
    catalog_entries: list[Any],
) -> dict[str, Any]:
    config = sanitize_prompt_converter_settings(settings)
    source = str(source_text or "").strip()
    output_mode = str(mode or "tags").strip().lower()
    if output_mode not in {"natural", "tags", "both"}:
        output_mode = "tags"
    if not config["enabled"]:
        return {"ok": False, "status": 400, "message": "Prompt converter is disabled."}
    if not source:
        return {"ok": False, "status": 400, "message": "変換する日本語テキストが空です。"}

    status = _ensure_ready(config)
    if not status.get("reachable"):
        return {"ok": False, "status": 502, "stage": "prompt_converter_provider", "message": status.get("message") or "Local prompt converter API is not reachable.", "provider_status": status}
    models = status.get("models") if isinstance(status.get("models"), list) else []
    model = str(config.get("model") or "auto")
    if model == "auto":
        model = str(models[0] if models else "")
    if not model:
        return {"ok": False, "status": 502, "stage": "prompt_converter_model", "message": "Prompt converter model is not loaded.", "provider_status": status}

    try:
        converted = _chat_completion(config, model, source, output_mode, existing_positive, app_scope)
    except (error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": 502, "stage": "prompt_converter_convert", "message": str(exc), "provider_status": status}

    natural_en = normalize_natural_prompt(converted.get("natural_en") or converted.get("natural") or "")
    tags_en = normalize_tag_prompt(converted.get("tags_en") or converted.get("tags") or "", existing_positive)
    warnings = character_warnings(source, natural_en, tags_en, catalog_entries)
    insert_text = natural_en if output_mode == "natural" else tags_en
    return {
        "ok": True,
        "mode": output_mode,
        "natural_en": natural_en,
        "tags_en": tags_en,
        "insert_text": insert_text,
        "warnings": warnings,
        "provider": {
            "provider": config["provider"],
            "base_url": config["base_url"],
            "model": model,
        },
    }
