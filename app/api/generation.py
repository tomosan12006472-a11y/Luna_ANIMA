from __future__ import annotations

from fastapi import APIRouter

from .. import main as _main
from ..main import *  # noqa: F401,F403

globals().update(
    {name: getattr(_main, name) for name in dir(_main) if name.startswith("_") and not name.startswith("__")}
)

router = APIRouter()

@router.get("/api/models")
def models(addr: str = COMFYUI_ADDR_DEFAULT, refresh: bool = False, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    try:
        info, cache = cached_object_info(addr, refresh=refresh)
    except Exception as exc:
        return {"ok": False, "message": str(exc), "models": [], "samplers": [], "schedulers": [], "loras": [], "upscale_models": [], "upscale_methods": [], "cache": _model_cache_status(addr)}
    unets = _object_choice(info, "DiffusionModelLoaderKJ", "model_name")
    if not unets:
        unets = _object_choice(info, "UNETLoader", "unet_name")
    clips = _object_choice(info, "CLIPLoader", "clip_name")
    vaes = _object_choice(info, "VAELoader", "vae_name")
    ckpt = _object_choice(info, "CheckpointLoaderSimple", "ckpt_name")
    ksampler = info.get("KSampler", {}).get("input", {}).get("required", {})
    samplers = ksampler.get("sampler_name", [[]])[0]
    schedulers = ksampler.get("scheduler", [[]])[0]
    loras = _object_choice(info, "LoraLoader", "lora_name")
    upscale_models = _object_choice(info, "UpscaleModelLoader", "model_name")
    upscale_methods = _object_choice(info, "LatentUpscaleBy", "upscale_method")
    controlnet_models = _object_choice(info, "ControlNetLoader", "control_net_name")
    if not upscale_methods:
        upscale_methods = ["nearest-exact", "bilinear", "bicubic", "lanczos", "area"]
    return {
        "ok": True,
        "models": unets or ckpt,
        "checkpoints": ckpt,
        "text_encoders": clips,
        "vaes": vaes,
        "samplers": samplers,
        "schedulers": schedulers,
        "loras": loras,
        "upscale_models": upscale_models,
        "upscale_methods": upscale_methods,
        "controlnet_models": controlnet_models,
        "cache": cache,
    }


@router.post("/api/payload/preview")
def payload_preview(data: GenerateRequest, anima_claude_session: str | None = Cookie(default=None)) -> Any:
    require_auth(anima_claude_session)
    invalid_count = validate_queue_count(data)
    if invalid_count:
        return invalid_count
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    invalid = validate_hires_fix(data, addr)
    if invalid:
        return invalid
    invalid_loras = validate_official_loras(data, addr)
    if invalid_loras:
        return invalid_loras
    invalid_i2i = validate_image_to_image(data)
    if invalid_i2i:
        return invalid_i2i
    invalid_ref_modules = validate_reference_modules(data, addr)
    if invalid_ref_modules:
        return invalid_ref_modules
    client_id = f"anima-claude-preview-{uuid.uuid4()}"
    request_data = generation_request_dict(data)
    request_data["queue_index"] = 0
    random_error = apply_prompt_random_collect_or_error([request_data])
    if random_error:
        return random_error
    request_data = prepare_reference_request(request_data, addr, upload=False)
    request_data = prepare_reference_modules_request(request_data, addr, upload=False)
    request_data = prepare_i2i_request(request_data, addr, upload=True)
    payload = build_prompt_payload(request_data, client_id)
    prompts = build_prompts(request_data)
    size = compute_hires_size(request_data)
    shift_info = anima_shift_capability(addr)
    request_shift_info = request_data.get("model_sampling", {}) if isinstance(request_data.get("model_sampling"), dict) else {}
    shift_info = {
        **shift_info,
        "shift": request_shift_info.get("shift", shift_info.get("shift")),
        "shift_source": request_shift_info.get("shift_source", shift_info.get("shift_source")),
        "request_supported": request_shift_info.get("supported"),
        "request_warnings": request_shift_info.get("warnings", []),
    }
    return {
        "ok": True,
        "payload": payload,
        "prompts": prompts,
        "size": size,
        "official_loras": official_lora_summary(request_data),
        "loras": request_data.get("loras", []),
        "reference_assist": request_data.get("reference_assist", {"enabled": False}),
        "reference_modules": request_data.get("reference_modules", {}),
        "image_to_image": request_data.get("image_to_image", {"enabled": False}),
        "face_detailer": request_data.get("face_detailer", {"enabled": False}),
        "hand_detailer": request_data.get("hand_detailer", {"enabled": False}),
        "prompt_random_collect": request_data.get("prompt_random_collect", {"enabled": False}),
        "anima_shift": shift_info,
        "shift": shift_info.get("shift"),
        "shift_supported": bool(shift_info.get("supported")),
    }


@router.post("/api/generate")
def generate(
    data: GenerateRequest,
    background_tasks: BackgroundTasks,
    anima_claude_session: str | None = Cookie(default=None),
) -> JSONResponse:
    require_auth(anima_claude_session)
    invalid_count = validate_queue_count(data)
    if invalid_count:
        return invalid_count
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    invalid = validate_hires_fix(data, addr)
    if invalid:
        return invalid
    invalid_loras = validate_official_loras(data, addr)
    if invalid_loras:
        return invalid_loras
    invalid_i2i = validate_image_to_image(data)
    if invalid_i2i:
        return invalid_i2i
    invalid_ref_modules = validate_reference_modules(data, addr)
    if invalid_ref_modules:
        return invalid_ref_modules
    cache_reset_error = reset_comfy_cache_for_character_prompt(addr, data)
    if cache_reset_error:
        return cache_reset_error
    if not data.wait:
        items: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        item_requests = []
        request_data_items: list[dict[str, Any]] = []
        for index in range(data.count):
            item_request = request_for_queue_item(data, index, wait=False)
            request_data = generation_request_dict(item_request)
            request_data["queue_index"] = index
            item_requests.append(item_request)
            request_data_items.append(request_data)
        random_error = apply_prompt_random_collect_or_error(request_data_items)
        if random_error:
            return random_error
        for index, (item_request, request_data) in enumerate(zip(item_requests, request_data_items)):
            request_data = prepare_reference_request(request_data, addr, upload=True)
            request_data = prepare_reference_modules_request(request_data, addr, upload=True)
            request_data = prepare_i2i_request(request_data, addr, upload=True)
            client_id = f"anima-claude-{uuid.uuid4()}"
            try:
                payload = build_prompt_payload(request_data, client_id)
                dump_path = save_mobile_payload_data(payload, request_data, item_request.workflow_mode)
                prompts = build_prompts(request_data)
            except Exception as exc:
                errors.append(
                    {
                        "index": index,
                        "stage": "build_payload",
                        "message": str(exc),
                        "traceback_short": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
                    }
                )
                break
            result = comfy_client.run_generation(addr, payload, wait=False)
            if result.ok:
                pending_item = None
                if result.prompt_id:
                    pending_item = create_pending_history_item(
                        request_data=request_data,
                        prompts=prompts,
                        prompt_id=result.prompt_id,
                        payload_path=dump_path,
                        workflow_mode=item_request.workflow_mode,
                        index=index,
                    )
                    background_tasks.add_task(
                        save_completed_generation_history,
                        addr=addr,
                        request_data=request_data,
                        prompts=prompts,
                        prompt_id=result.prompt_id,
                        payload_path=str(dump_path),
                        workflow_mode=item_request.workflow_mode,
                        history_id=pending_item["id"],
                    )
                items.append(
                    {
                        "index": index,
                        "prompt_id": result.prompt_id,
                        "seed": prompts.get("seed"),
                        "status": "queued",
                        "history_id": pending_item["id"] if pending_item else None,
                        "payload_dump": str(dump_path),
                        "prompt_random_collect": request_data.get("prompt_random_collect", {"enabled": False}),
                    }
                )
            else:
                errors.append(
                    {
                        "index": index,
                        "stage": result.stage or "submit_prompt",
                        "message": result.error or "generation failed",
                        "comfy_status": result.status,
                        "comfy_response_text": result.response_text or "",
                        "comfy_node_errors": result.node_errors,
                    }
                )
        response_status = "queued" if len(items) == data.count and not errors else "partial" if items else "failed"
        return JSONResponse(
            status_code=200 if items else 502,
            content={
                "ok": bool(items),
                "status": response_status,
                "count": data.count,
                "queued_count": len(items),
                "items": items,
                "errors": errors,
                "size": compute_hires_size(generation_request_dict(data)),
                "official_loras": official_lora_summary(generation_request_dict(data)),
                "prompt_random_collect": request_data_items[0].get("prompt_random_collect", {"enabled": False}) if request_data_items else {"enabled": False},
                "reference_assist": generation_request_dict(data).get("reference_assist", {"enabled": False}),
                "reference_modules": generation_request_dict(data).get("reference_modules", {}),
                "image_to_image": generation_request_dict(data).get("image_to_image", {"enabled": False}),
                "hand_detailer": generation_request_dict(data).get("hand_detailer", {"enabled": False}),
                "anima_shift": generation_request_dict(data).get("model_sampling", {}),
                "shift": generation_request_dict(data).get("shift"),
            },
        )
    client_id = f"anima-claude-{uuid.uuid4()}"
    request_data = generation_request_dict(data)
    request_data["queue_index"] = 0
    random_error = apply_prompt_random_collect_or_error([request_data])
    if random_error:
        return random_error
    request_data = prepare_reference_request(request_data, addr, upload=True)
    request_data = prepare_reference_modules_request(request_data, addr, upload=True)
    request_data = prepare_i2i_request(request_data, addr, upload=True)
    try:
        payload = build_prompt_payload(request_data, client_id)
        dump_path = save_mobile_payload_data(payload, request_data, data.workflow_mode)
        prompts = build_prompts(request_data)
    except Exception as exc:
        traceback.print_exc()
        return error_response(
            status_code=400,
            message=str(exc),
            stage="build_payload",
            data=data,
            traceback_short="".join(traceback.format_exception_only(type(exc), exc)).strip(),
            retryable=False,
        )
    result = comfy_client.run_generation(addr, payload, wait=data.wait)
    history_item = None
    if result.ok and data.wait:
        try:
            history_item = create_history_item(
                request_data=request_data,
                prompts=prompts,
                result=result,
                payload_path=dump_path,
                workflow_mode=data.workflow_mode,
            )
        except Exception as exc:
            traceback.print_exc()
            return error_response(
                status_code=502,
                message=str(exc),
                stage="history_save",
                data=data,
                traceback_short="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                retryable=False,
            )
    if not result.ok:
        return error_response(
            status_code=502,
            message=result.error or "generation failed",
            stage=result.stage or "comfy_response",
            data=data,
            comfy_status=result.status,
            comfy_response_text=result.response_text or "",
            comfy_node_errors=result.node_errors,
            traceback_short=result.traceback_short,
            retryable=True,
        )
    status = 200 if result.ok else 502
    return JSONResponse(
        status_code=status,
        content={
            "ok": result.ok,
            "prompt_id": result.prompt_id,
            "image_url": result.image_url,
            "image_data_url": result.image_data_url,
            "error": result.error,
            "response_text": result.response_text,
            "payload_dump": str(dump_path),
            "history_item": history_item,
            "size": compute_hires_size(request_data),
            "official_loras": official_lora_summary(request_data),
            "reference_assist": request_data.get("reference_assist", {"enabled": False}),
            "image_to_image": request_data.get("image_to_image", {"enabled": False}),
            "hand_detailer": request_data.get("hand_detailer", {"enabled": False}),
            "prompt_random_collect": request_data.get("prompt_random_collect", {"enabled": False}),
            "anima_shift": request_data.get("model_sampling", {}),
            "shift": request_data.get("shift"),
        },
    )


@router.get("/api/queue")
def queue_status(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    try:
        queue = comfy_client.queue_info(addr)
    except Exception as exc:
        return {"ok": False, "message": str(exc), "running": [], "pending": []}
    history_by_prompt_id = _pending_history_by_prompt_id()
    running = _queue_rows(queue.get("queue_running"), history_by_prompt_id, include_position=False)
    pending = _queue_rows(queue.get("queue_pending"), history_by_prompt_id, include_position=True)
    return {"ok": True, "running": running, "pending": pending}


@router.post("/api/queue/cancel")
def queue_cancel(data: QueueCancelRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    prompt_id = str(data.prompt_id or "").strip()
    if not prompt_id:
        return {"ok": False, "message": "prompt_id is required"}
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    result = comfy_client.queue_delete(addr, [prompt_id])
    if not result.get("ok"):
        return {"ok": False, "message": result.get("text") or "ComfyUI queue delete failed", "result": result}
    history_item = _pending_history_by_prompt_id().get(prompt_id)
    updated = None
    if history_item and history_item.get("id"):
        updated = update_pending_history_status(str(history_item["id"]), "failed", "Cancelled by user")
    return {
        "ok": True,
        "result": result,
        "history_id": history_item.get("id") if history_item else None,
        "history_updated": bool(updated),
    }


@router.post("/api/queue/interrupt")
def queue_interrupt(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    settings = load_settings()
    addr = settings.get("api_addr") or COMFYUI_ADDR_DEFAULT
    result = comfy_client.interrupt(addr)
    if not result.get("ok"):
        return {"ok": False, "message": result.get("text") or "ComfyUI interrupt failed", "result": result}
    return {"ok": True, "result": result}
