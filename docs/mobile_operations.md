# Mobile Operations

This note covers small operational controls intended for phone or tablet use.

## ComfyUI Restart Control

Luna ANIMA can expose an authenticated ComfyUI restart button in Settings, but it is disabled by default.

Required server-side settings:

```bat
set LUNA_COMFY_RESTART_ENABLED=1
set COMFYUI_RESTART_COMMAND=path\to\your\restart-comfyui-script.bat
```

Optional settings:

```bat
set COMFYUI_RESTART_TIMEOUT_SECONDS=180
set COMFYUI_RESTART_POLL_INTERVAL_SECONDS=3
set COMFYUI_RESTART_CWD=D:\AI\ComfyUI
set COMFYUI_RESTART_SHELL=0
```

Safety rules:

- The browser never sends a command.
- Only the server-configured command is used.
- The restart APIs require the Luna ANIMA session cookie.
- The button shows a confirmation because running ComfyUI jobs may be lost.
- API responses expose only a command label, not the full command line.
- Restart stdout/stderr is not returned in status responses.

On Windows, `.bat` and `.cmd` restart scripts are run through `cmd /c` with `shell=False`.
Use `COMFYUI_RESTART_SHELL=1` only when your local restart script really requires shell behavior.

The UI polls restart status until ComfyUI `/object_info` becomes reachable or the timeout is reached.

## Async Public Save

The existing synchronous public-save API remains compatible:

```http
POST /api/history/{history_id}/public-save
```

When the request includes `async_save: true`, Luna ANIMA queues an in-memory public-save job and returns quickly:

```json
{
  "apply_watermark": true,
  "watermark_client": "current",
  "watermark": {},
  "async_save": true
}
```

The UI then polls:

```http
GET /api/history/{history_id}/public-save/status?job_id=...
```

If the same source image and watermark settings were already saved, the async API can return `done` immediately with `cached: true`.

The job registry is process-local memory. It does not change generation payload shape and does not write new user settings.
