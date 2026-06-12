# build-spec v4 — ANIMA版 Hires.fix(新規payload機能)

ANIMA系列では未実装だった機能の新規実装。**hires OFF時のpayloadは現状と1バイトも変わらないこと**(回帰ツールで担保)。

共通厳守: 検証コマンド・git操作禁止(node --check / py_compile のみ可)。repo直下に一時ファイル禁止。index.html/styles.css/ui.js 変更禁止(hires foldシェル実装済み: #hiresEnabled/#hiresMode/#hiresFactor/#hiresDenoise/#hiresSteps/#hiresMethod/#hiresModel/#hiresTargetW/#hiresTargetH/#hiresSummary)。

## 1. backend: `app/payload_builder.py`

`apply_hires_fix(workflow, request)` を新設し、`build_workflow()` 内で **`apply_catalog_loras` の後・`apply_image_to_image` の前**に呼ぶ(`is_lora_sample_mode` 時と `hires_fix.enabled` でない時は何もしない)。

ノード構成(`next_node_id(workflow, 9200)` で採番。KSampler 19 の `model/positive/negative/cfg/sampler_name/scheduler/seed` の**参照値をそのままコピー**して使う):

- 共通: `size = compute_hires_size(request)`。`workflow["1"]` の出力画像入力を最終Decodeへ差し替え。`request["hires_fix"]` に `{applied: true, mode, final_width, final_height, factor}` をマージ(メタデータ用)。
- **latent mode**:
  - `U = LatentUpscaleBy {samples: ["19",0], upscale_method: hires.latent_upscale_method or "nearest-exact", scale_by: size.factor}`
  - `K2 = KSampler {model/positive/negative/cfg/sampler_name/scheduler: 19と同じ参照, seed: 19と同じ, steps: hires.steps or 15, denoise: hires.denoise or 0.45, latent_image: [U,0]}`
  - `D2 = VAEDecode {samples: [K2,0], vae: ["15",0]}` → `workflow["1"]["inputs"]["images"] = [D2,0]`
- **model mode**:
  - `L = UpscaleModelLoader {model_name: hires.upscale_model}`(空ならValueError)
  - `IU = ImageUpscaleWithModel {upscale_model: [L,0], image: ["8",0]}`
  - `SC = ImageScale {image: [IU,0], width: size.final_width, height: size.final_height, upscale_method: "lanczos", crop: "disabled"}`
  - `EN = VAEEncode {pixels: [SC,0], vae: ["15",0]}` → `K2(latent_image:[EN,0], 他はlatentと同じ)` → `D2` → `images=[D2,0]`
- face detailer との順序: build_workflow の既存呼び出し順では `apply_face_detailer` が最後で、`workflow["1"]["inputs"]["images"]` を入力に取るため、hires適用後のD2出力に自動で繋がる(=順序変更不要)。i2i併用は既存validatorが既定で拒否するので考慮不要。

## 2. backend: バリデーション

`app/main.py` の generate/preview は既に `validate_hires_fix` を呼んでいる(SAA由来のまま生きている)ので**変更不要**。`LATENT_UPSCALE_METHODS` 検査・サイズ検査がそのまま機能することを確認のこと(validators.pyを読む)。

## 3. テスト追加(実行はしない)

`tests/test_payload_golden.py` に2ケース追加: `test_build_prompt_payload_hires_latent`(factor1.5/bicubic/denoise0.45/steps15)と `test_build_prompt_payload_hires_model`(upscale_model "RealESRGAN_x4.pth"/target 1344x2016)。既存の `base_request()` を上書きする形。goldenファイルの生成はClaude側で行うので、テストメソッドだけ書く。

## 4. frontend: `app/static/app.js`

- `collectRequest()` の `hires_fix` を `{enabled, mode, upscale_factor, denoise, steps, latent_upscale_method(#hiresMethod), upscale_model(#hiresModel), target_width(#hiresTargetW), target_height(#hiresTargetH)}` に。enabled時は `workflow_mode: "anima_mobile_extended"` を設定(通常は "anima")。
- `/api/models` 応答の `upscale_methods`→#hiresMethod、`upscale_models`→#hiresModel に充填(既存のselect充填処理に追加)。
- `#hiresSummary`: `OFF` / `ON · ×1.5 · latent` 形式。
- frame-reuse / レシピ適用 / ガチャの写像に hires_fix を含める(item側に保存されていれば復元)。

## 5. 完了条件(Claude側で検証)

hires OFFの回帰全一致 / 新goldenの内容レビュー / unittest green / node --check。
