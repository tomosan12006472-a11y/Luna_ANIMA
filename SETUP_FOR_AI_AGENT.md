# Setup Task For AI Coding Agents

Use this file when asking Codex, Claude Code, Cursor, or another local coding assistant to install and verify Luna ANIMA.

## Goal

Set up Luna ANIMA on this Windows machine, connect it to the existing local ComfyUI environment, and verify that the app starts.

## Hard Rules

- Do not modify program source files.
- Do not redistribute the package.
- Do not remove or edit `LUNA_DISTRIBUTION_TERMS.md` or `THIRD_PARTY_NOTICES.md`.
- Do not copy user history, generated images, settings, or favorites from another machine unless the user explicitly asks.
- Use the existing package directory as the working directory.

## Steps

1. Confirm Python is available:

   ```powershell
   py -3 --version
   ```

   If `py` is unavailable, try:

   ```powershell
   python --version
   ```

2. Create and install the local Python environment:

   ```powershell
   .\setup_venv.bat
   ```

3. Confirm ComfyUI is running:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8188/system_stats
   ```

   If this fails, start ComfyUI before continuing.

4. Start Luna ANIMA:

   ```powershell
   .\run_luna_anima.bat
   ```

5. In a second terminal, verify health:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:51031/health
   ```

6. Log in and verify bootstrap:

   ```powershell
   $s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
   Invoke-RestMethod http://127.0.0.1:51031/api/login -Method Post -ContentType 'application/json' -Body '{"pin":"2197"}' -WebSession $s
   Invoke-RestMethod http://127.0.0.1:51031/api/bootstrap -WebSession $s
   ```

7. Open the app in the browser:

   ```text
   http://127.0.0.1:51031/
   ```

## Optional Prompt Conversion

Prompt conversion requires LM Studio, Ollama, or llama.cpp exposing an OpenAI-compatible `/v1` endpoint. If it is unavailable, image generation can still work without prompt conversion.

## Report Back

Report:

- Python version
- Whether dependency installation succeeded
- Whether ComfyUI responded
- `/health` result
- `/api/bootstrap` result
- Any missing models or custom nodes shown by the app diagnostics
