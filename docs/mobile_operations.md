# Mobile Operations

This note covers small operational controls intended for phone or tablet use.

## ComfyUI Restart Control

Luna ANIMA can expose an authenticated ComfyUI restart button in Settings, but it is disabled by default.

### Windows local setup

For the normal Windows setup, generate a machine-local restart config from the ComfyUI process that is currently listening on your configured ComfyUI port:

```bat
configure_comfyui_restart.bat --detect --dry-run
configure_comfyui_restart.bat --write
```

`--detect` inspects the current listener process, command line, `main.py`, port, and ComfyUI `/system_stats` argv. `--dry-run` prints the detected launch spec without writing files. `--write` creates:

- `user_data/comfyui_restart.local.json`
- `user_data/comfyui_restart_env.bat`

These files are machine-local and ignored by Git. They can contain absolute paths for your local ComfyUI checkout and Python executable.

`run_luna_anima.bat` loads `user_data/comfyui_restart_env.bat` when it exists, so restart capability is available immediately after Luna ANIMA is relaunched. Re-run setup whenever you move ComfyUI, change the Python executable, change launch arguments, or change the port.

The generated env file only points Luna ANIMA at `user_data/comfyui_restart.local.json`. That JSON is the source of truth for managed local restart mode.

To disable the button, set `"enabled": false` in `user_data/comfyui_restart.local.json`, then restart Luna ANIMA. You can also delete or rename `user_data/comfyui_restart_env.bat` to stop loading the managed local config.

The Windows wrapper stops only the verified ComfyUI listener process tree. It checks the listener PID, `main.py`, ComfyUI root, and configured Python executable before stopping anything. It never kills all `python.exe` processes.

Restart logs are written under `user_data/logs/comfyui_restart/`, with small job status files under `user_data/logs/comfyui_restart_jobs/`. The API reports only safe status fields and does not expose full commands or local absolute paths.

Before using restart, make sure the ComfyUI queue is empty. Luna ANIMA also checks `/queue` and refuses restart if ComfyUI is busy or if queue state cannot be inspected.

Optional local smoke:

```bat
configure_comfyui_restart.bat --test
```

`--test` performs a real restart after confirming the queue is empty, then waits for `/object_info` to return.

### Legacy command setup

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
- Queue busy or queue inspection failure refuses restart.

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
