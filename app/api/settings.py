from __future__ import annotations

from fastapi import APIRouter

from .. import main as _main
from ..main import *  # noqa: F401,F403

globals().update(
    {name: getattr(_main, name) for name in dir(_main) if name.startswith("_") and not name.startswith("__")}
)

router = APIRouter()

@router.get("/api/settings")
def get_settings(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "settings": load_app_settings()}


@router.post("/api/settings")
def post_settings(data: SettingsRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "mode": data.mode, "reason": data.reason, "settings": save_app_settings(data.settings)}


@router.post("/api/settings/reset")
def post_settings_reset(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "settings": reset_app_settings()}


@router.get("/api/catalog")
def search_catalog(
    q: str = "",
    kind: str = "all",
    limit: int = 80,
    offset: int = 0,
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    page = catalog.search_page(q, kind, max(1, min(limit, 300)), max(0, offset))
    return {"ok": True, **page}


@router.get("/api/original-characters")
def get_original_characters(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    payload = original_characters.original_characters_payload()
    for item in payload["items"]:
        item["lora_candidates"] = original_character_lora_candidates(item)
    return payload


@router.post("/api/original-characters")
def post_original_character(data: OriginalCharacterRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    item = original_characters.upsert_original_character(data.model_dump())
    catalog.reload()
    return {"ok": True, "item": item, **original_characters.original_characters_payload()}


@router.put("/api/original-characters/{character_id}")
def put_original_character(character_id: str, data: OriginalCharacterRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    raw = data.model_dump()
    raw["id"] = character_id
    item = original_characters.upsert_original_character(raw)
    catalog.reload()
    return {"ok": True, "item": item, **original_characters.original_characters_payload()}


@router.get("/api/favorites")
def favorites(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    data = localized_favorites(load_favorites())
    return {"ok": True, **data}


@router.post("/api/favorites")
def post_favorite(data: FavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        action, favorite, favorites_data = add_favorite(data.model_dump())
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "status": 400, "stage": "validate_favorite", "message": str(exc), "source": data.source},
        )
    return JSONResponse(status_code=200, content={"ok": True, "status": "ok", "action": action, "favorite": localized_favorite_item(favorite), **localized_favorites(favorites_data)})


@router.delete("/api/favorites/{source}/{favorite_id}")
def delete_favorite(source: str, favorite_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        removed, favorites_data = remove_favorite(source, favorite_id)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "status": 400, "stage": "validate_favorite", "message": str(exc), "source": source},
        )
    return JSONResponse(status_code=200, content={"ok": True, "status": "ok", "removed": removed, **localized_favorites(favorites_data)})


@router.post("/api/favorites/{source}/{favorite_id}/use")
def use_favorite(source: str, favorite_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    favorite = mark_favorite_used(source, favorite_id)
    return JSONResponse(status_code=200, content={"ok": True, "favorite": localized_favorite_item(favorite), **localized_favorites(load_favorites())})


@router.get("/api/prompts/positive-favorites")
def positive_prompt_favorites(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    data = list_positive_prompt_favorites()
    return {"ok": True, "count": len(data["items"]), **data}


@router.post("/api/prompts/positive-favorites")
def post_positive_prompt_favorite(data: PositivePromptFavoriteRequest, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = add_positive_prompt_favorite(data.model_dump())
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "status": 400, "stage": "positive_prompt_favorite_add", "message": str(exc)})
    payload = list_positive_prompt_favorites()
    return JSONResponse(status_code=201, content={"ok": True, "item": item, "count": len(payload["items"]), **payload})


@router.patch("/api/prompts/positive-favorites/{favorite_id}")
def patch_positive_prompt_favorite(favorite_id: str, data: PositivePromptFavoritePatch, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = update_positive_prompt_favorite(favorite_id, data.model_dump(exclude_unset=True))
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "status": 404, "stage": "positive_prompt_favorite_update", "message": "Favorite not found"})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "status": 400, "stage": "positive_prompt_favorite_update", "message": str(exc)})
    payload = list_positive_prompt_favorites()
    return JSONResponse(status_code=200, content={"ok": True, "item": item, "count": len(payload["items"]), **payload})


@router.delete("/api/prompts/positive-favorites/{favorite_id}")
def delete_positive_prompt_favorite_route(favorite_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    removed = delete_positive_prompt_favorite(favorite_id)
    payload = list_positive_prompt_favorites()
    return JSONResponse(status_code=200, content={"ok": True, "removed": removed, "count": len(payload["items"]), **payload})


@router.post("/api/prompts/positive-favorites/{favorite_id}/used")
def use_positive_prompt_favorite(favorite_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = mark_positive_prompt_favorite_used(favorite_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "status": 404, "stage": "positive_prompt_favorite_used", "message": "Favorite not found"})
    payload = list_positive_prompt_favorites()
    return JSONResponse(status_code=200, content={"ok": True, "item": item, "count": len(payload["items"]), **payload})


@router.get("/api/recipes")
def recipes(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    payload = list_recipes()
    return {"ok": True, "count": len(payload["items"]), **payload}


@router.post("/api/recipes")
def post_recipe(data: RecipeRequest, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = add_recipe(data.name, data.summary, data.request)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "status": 400, "stage": "recipe_add", "message": str(exc)})
    payload = list_recipes()
    return JSONResponse(status_code=201, content={"ok": True, "item": item, "count": len(payload["items"]), **payload})


@router.delete("/api/recipes/{recipe_id}")
def delete_recipe_route(recipe_id: str, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, "removed": delete_recipe(recipe_id)}


@router.post("/api/recipes/{recipe_id}/used")
def use_recipe(recipe_id: str, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    try:
        item = mark_recipe_used(recipe_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "status": 404, "stage": "recipe_used", "message": "Recipe not found"})
    return JSONResponse(status_code=200, content={"ok": True, "item": item})


@router.get("/api/prompts/positive-templates")
def positive_prompt_templates(
    query: str = Query("", max_length=160),
    category: str = Query("", max_length=80),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return list_positive_prompt_templates(query=query, category=category, limit=limit, offset=offset)


@router.get("/api/prompt-dictionary/status")
def prompt_dictionary_status_route(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return prompt_dictionary_status()


@router.get("/api/prompt-dictionary/search")
def prompt_dictionary_search_route(
    q: str = Query("", max_length=160),
    limit: int = Query(50, ge=1, le=50),
    anima_claude_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return search_prompt_dictionary(q, limit=limit)


@router.get("/api/prompt-converter/status")
def prompt_converter_status_route(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, **prompt_converter_status(load_app_settings().get("prompt_converter"))}


@router.post("/api/prompt-converter/convert")
def prompt_converter_convert_route(data: PromptConverterRequest, anima_claude_session: str | None = Cookie(default=None)) -> JSONResponse:
    require_auth(anima_claude_session)
    result = convert_prompt_text(
        load_app_settings().get("prompt_converter"),
        source_text=data.source_text,
        mode=data.mode,
        existing_positive=data.existing_positive,
        app_scope="anima",
        catalog_entries=[*catalog.wai, *catalog.original],
    )
    if not result.get("ok"):
        return JSONResponse(status_code=int(result.get("status") or 502), content=result)
    return JSONResponse(status_code=200, content=result)


@router.get("/api/prompt-random-collect/status")
def prompt_random_collect_status_route(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {"ok": True, **prompt_random_collect_status(load_app_settings())}


@router.get("/api/dynamic-prompts/wildcards")
def dynamic_prompt_wildcards(anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {
        "ok": True,
        **list_wildcards(
            config_dir=ROOT_DIR / "config" / "dynamic_prompt_wildcards",
            user_dir=ROOT_DIR / "user_data" / "dynamic_prompt_wildcards",
        ),
    }


@router.post("/api/dynamic-prompts/preview")
def dynamic_prompt_preview(data: DynamicPromptPreviewRequest, anima_claude_session: str | None = Cookie(default=None)) -> dict[str, Any]:
    require_auth(anima_claude_session)
    return {
        "ok": True,
        **expand_dynamic_prompt(
            positive_prompt=data.positive_prompt,
            negative_prompt=data.negative_prompt,
            seed=data.seed,
            enabled=data.enabled,
            config_dir=ROOT_DIR / "config" / "dynamic_prompt_wildcards",
            user_dir=ROOT_DIR / "user_data" / "dynamic_prompt_wildcards",
        ),
    }
