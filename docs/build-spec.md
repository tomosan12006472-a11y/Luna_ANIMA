# ANIMA_claude build spec(Codex実装用)

新アプリ「ANIMA 暗室(ANIMA Claude)」のビルド仕様。デザインと操作レイヤーは作成済み。あなた(Codex)の仕事は **(A) 実績あるANIMA_MobilePanelバックエンドの移植** と **(B) app.js(データ配線)の実装**、**(C) 検証**。

## 絶対条件

- 作業ディレクトリは `D:\AI\ANIMA_claude` のみ。**`D:\AI\ANIMA_MobilePanel` ほか既存repoは読み取り専用**(1バイトも変更しない)。
- **`app/static/index.html` / `app/static/styles.css` / `app/static/ui.js` は変更禁止**(デザイナー所有)。配線上の不整合を見つけたら、変更せず停止して報告。
- 新規Python依存の追加禁止(`fastapi` / `uvicorn[standard]` / `pillow` のみ)。フロントはvanilla JSのみ。
- ポート **51031**、PIN 既定 **2197**(env `ANIMA_CLAUDE_PIN`)、cookie名 **`anima_claude_session`**。
- フェーズごとに1コミット。コミット前に各フェーズの検証を通す。

## Phase A: バックエンド移植

1. `git init`(まだの場合)。
2. `D:\AI\ANIMA_MobilePanel` から以下をコピー:
   - `app/*.py` 全部(`app/static/` は**コピーしない**。既にこのrepoの新ファイルがある)
   - `config/` 一式、`tools/` 一式、`tests/` 一式(golden含む)、`requirements.txt`、`.gitignore`
   - コピーしないもの: `.git` `.venv` `user_data` `logs` `docs` `README.md` `run_anima_mobile.bat`
3. identity変更(コピー後のファイルに対して):
   - `app/config.py`: `APP_PIN = os.environ.get("ANIMA_CLAUDE_PIN", "2197")`
   - `app/main.py`: `FastAPI(title="ANIMA Claude")`、cookieパラメータ名 `saa_mobile_session` を **全箇所** `anima_claude_session` へ(関数引数名=cookie名。`set_cookie` も)。ログprefixの `[anima-mobile]` は `[anima-claude]` へ。
   - `/health` の `"app"` を `"ANIMA Claude"` に。
4. `run_anima_claude.bat` を作成(ANIMA版のbatを雛形に、port 51031)。
5. `README.md` を新規作成(起動方法・port・PIN env・参照元(SAA CSV / ComfyUI 8188 / ANIMA workflow)・「ANIMA_MobilePanelと並行稼働できる別アプリ」である旨を簡潔に)。
6. `.venv` を作成し `pip install -r requirements.txt`。
7. 検証: `compileall -q app tools` / `unittest discover -s tests` 全green / サーバ起動して `/health` 200(`{"app":"ANIMA Claude"}`)。
8. コミット1: `chore: scaffold ANIMA Claude (backend transplant + darkroom shell)`(デザイン済みstaticファイル+docs含む全部)。
9. 以後 `tools/payload_regression_check.py --base <コミット1のhash>` が回帰チェックとして使える。

## Phase B: `app/static/app.js` の実装

vanilla JS、IIFE、`window.UI`(ui.js)のプリミティブを使う。`UI.$ / UI.$$ / UI.toast / UI.safelight / UI.openSheet / UI.closeSheets / UI.bindSeg / UI.segValue / UI.setSegValue / UI.markDeveloping / UI.enterDarkroom / UI.onTab / UI.switchTab` が利用可能。

実装ロジックは `D:\AI\ANIMA_MobilePanel/app/static/app.js` から**読み取って移植**してよい(リクエストの組み立て・共有フロー等の実績ある形を踏襲)。コピーではなく必要部分の移植。

### B-1. api基盤
- `api(path, options)`: fetch+JSON。401なら loginView へ戻す。エラーenvelope(`{ok:false, stage, message}`)は呼び出し側でtoast表示。

### B-2. ログイン/起動
- `data-action="login"`: POST `/api/login` `{pin}`。成功→`UI.enterDarkroom()`→`bootstrap()`。失敗→`#loginStatus`に表示。Enterキー対応。
- 起動時に GET `/api/bootstrap` を試し、200ならログイン省略で入室(cookie生存時)。
- `bootstrap()`: `/api/bootstrap` のdefaults(`width/height/steps/cfg/shift/sampler/scheduler/model/negative_prompt_mode` 等)をフォームへ反映、`#catalogCount`に件数、`state.appSettings` 保持(透かし欄へ反映)、`/api/models` でselect群(sampler/scheduler/model)を充填、`/api/loras/catalog` のselectableを保持、お気に入りロード、履歴の先読み(背景)。

### B-3. キャラクター
- スロット選択状態: `.slot` タップで `is-armed` 移動。
- 検索: `#charSearch` 250msデバウンス→ GET `/api/catalog?q=&kind=all&limit=60` → `#charResults` に `<button>`(左=display_name、右=`<span class="tag">prompt_tag`)。
- 結果タップ→armedスロットへ割当。値の規則:
  - C1〜C3スロット: kindが`original`の項目は `original:{id または display_name}` を値に、それ以外はdisplay_nameを値に。
  - ORIGINALスロット: idまたはdisplay_name(`original_character` フィールドへ)。
  - 空スロットの送信値: C1=`"Random"`、C2/C3/ORIGINAL=`"None"`。C1の空表示名は「Random」とする。
- `data-action="clear-slot"`: armedスロットを空に。
- お気に入り: GET `/api/favorites` → `#favRow` にchip(タップでarmedスロットへ)。`data-action="toggle-favorite-slot"`: armedスロットのキャラを POST `/api/favorites` / DELETE で登録解除(旧app.jsのpayload形を踏襲: source は `wai_characters` / `original_character`)。

### B-4. リクエスト組み立て `collectRequest()`
GenerateRequest(バックエンドのPydanticモデル)へ**正確なキー名**で:
`workflow_mode:"anima"`, `character1..3`, `original_character`, 各`*_weight:1.0`, `character1_role:"main"`,`character2_role:"left"`,`character3_role:"right"`, `rating`(=`UI.segValue("#ratingSeg","rating")`), `quality_preset`, `meta_prompt`, `year_prompt`, `outfit_prompt`, `expression_prompt`, `pose_prompt`, `background_prompt`, `lighting_prompt`, `camera_prompt`, `natural_description`, `positive_prompt`, `negative_prompt` と `negative_prompt_raw`(同値=#negativePrompt), `negative_prompt_mode`, `negative_preset`, `prompt_ban`, `common_prompt:""`, `model`, `text_encoder`/`vae`(bootstrap defaultsの値をそのまま通す。UIなし), `width/height/steps/cfg`(number), `shift`(number), `sampler/scheduler`, `seed`(number)/`seed_mode`, `official_loras: {highres:{enabled,strength}, turbo:{enabled, version:"auto", strength}, colorfix:{enabled,strength}}`, `official_lora_preset`(任意メタ), `loras`(B-5), `count`(#queueCount), `wait:false`, そして `dynamic_prompt/hires_fix/reference_assist/image_to_image/face_detailer: {enabled:false}`, `reference_modules: {enabled:false, outfit:{enabled:false}, pose:{enabled:false}}`。

### B-5. LoRAスロット
- `data-action="add-lora"` で `#loraSlots` に行を追加: LoRA選択select(catalogのselectable: 表示=display_name、値=name/relative_path)+ model強度 + clip強度(0〜1 step0.05)+ application select(`model_clip`/`model_only`)+ 削除ボタン。行のDOMは `.tray` 流儀・既存class(`grid2`/`ghost`等)で構築。
- `collectRequest()` の `loras` へ `{enabled:true, name, application, strength_model, strength_clip}`。

### B-6. 露光(生成)
- `data-action="preview"`: POST `/api/payload/preview` → `#payloadPreview` にJSON整形表示+`hidden`解除。エラーはtoast(message)。
- `data-action="generate"`(#exposeBtn): POST `/api/generate`。成功(`status:"queued"`)→ toast「◯枚 露光しました」、`UI.safelight("developing", "N FRAMES DEVELOPING")`、ポーリング開始。失敗→ toast(message,"error") + `UI.safelight("error")`(次の成功でidleへ)。送信中はボタンdisabled。
- `#techSummary` / `#sceneSummary` / `#negativeSummary` をフォーム変更時に更新(例: `1024×1536 · 32 · 4.5 · shift4`)。

### B-7. 密着(履歴)
- `loadContact(reset)`: GET `/api/history?view=list&limit=24&offset=N&filter=F`。filterは `#contactFilters` のchip(`all`→`all`、`favorite`→`favorite`、`active`→`all`+クライアント側で `queued/running` のみ表示)。filter名は `app/history_flags_store.py` の `filter_items_by_flags` 実装を確認して合わせる。
- レンダリング: `#contactGrid` に `.frame` ボタン。completed→`<img src=thumbnail_small_url loading="lazy" decoding="async">`+`.no`にフレーム番号(`#` + (filtered_total−絶対index) を4桁ゼロ詰め)。pending(queued/running)→`.frame.is-pending`+`<span class="dev-dot">`。failed→`.is-failed`。
- ポーリング: 実行中アイテムがある間、3秒ごとに `known_revision` 付き再取得(`unchanged`なら何もしない)。pending→completedに変わった画像には `UI.markDeveloping(img)`。実行中が0になったら `UI.safelight("idle")` + toast「現像完了」。
- `#contactCount` に `表示数 / filtered_total`。`#loadMoreBtn` でoffset追加。

### B-8. フレーム詳細シート
- `.frame` タップ→ GET `/api/history/{id}` → `#frameImage` に `image_url`、`#frameMeta` に `<tr><td>ラベル<td>値` 行: FRAME(id) / TIME(created_at) / SEED / SIZE(出力w×h) / STEPS·CFG·SHIFT / SAMPLER·SCHEDULER / MODEL(ファイル名のみ) / RATING / CHARACTERS(characters配列) / LORA(あれば) / POSITIVE / NEGATIVE(全文、selectable)。→ `UI.openSheet("#frameSheet")`。
- `data-action="frame-favorite"`: POST `/api/history/{id}/flags` `{favorite: !現在}` → ボタン表示を ★/☆ 切替。
- `data-action="frame-public-save"`: POST `/api/history/{id}/public-save` `{apply_watermark, watermark:{enabled,text,position,opacity,size}}`(設定シートの値)→ `#frameActionStatus` に結果。
- `data-action="frame-share"`: 旧app.jsの共有フローを移植(public-save→画像fetch→`navigator.canShare({files})`→share。不可なら public-image URLを新タブで開く案内)。iPhone Safari前提。
- `data-action="frame-reuse"`: itemの値をフォームへ逆反映(スロット名・rating・quality・シーン各欄・negative・サイズ/steps/cfg/shift/sampler/scheduler/model・official_loras・loras行)→ toast→`UI.switchTab("expose")`。

### B-9. 設定シート
- 開いたとき: `/api/diagnostics`(要cookie)→ `#connMeta` に API_ADDR / WORKFLOW(found) / MODELS_CACHE 等の主要値、`#diagBadge` に api_addr。
- 透かし欄は `state.appSettings.watermark` と双方向。
- `data-action="save-defaults"`: `state.appSettings` に現フォームの主要値(model/width/height/steps/cfg/shift/sampler/scheduler/seed_mode/負プリセット/negative_prompt_mode/watermark/official系を既存キー名に合わせて)をマージし、**全量を** POST `/api/settings`(部分送信禁止。settings_storeはdeep_merge(DEFAULT, 受信)のため)。→ `#settingsStatus`。
- `data-action="reset-defaults"`: POST `/api/settings/reset` → フォームへ再反映。
- `data-action="reload-models"`: `/api/models?refresh=true` → select再充填。

### B-10. コミット
コミット2: `feat: wire darkroom frontend to ANIMA backend`

## Phase C: 検証と報告

1. `node --check app/static/app.js`(nodeが無ければskipと明記)
2. 契約チェック: app.js が参照する全id(`#xxx`)が index.html に存在することをスクリプトで確認(逆方向: index.htmlの全 `data-action` がapp.js/ui.jsで処理されること)。
3. `compileall` / `unittest discover -s tests` / `tools/payload_regression_check.py --base <コミット1>` → 全green。
4. ポート51031で起動: `/health` 200、PIN 2197ログイン200、`/api/bootstrap` 200、`POST /api/payload/preview`(`collectRequest()`相当の最小JSON)200。
5. 報告: 実行コマンドと結果、コミット一覧、**ユーザー実機チェックリスト**(iPhoneでの確認項目: 入室→キャラ検索→スロット割当→露光→セーフライト脈動→密着で現像リビール→詳細→透かし保存→共有→再利用→既定値保存)。

## Out of scope(v2予定。実装しない)

i2i / Outfit・Pose参照固定 / FaceDetailer / Dynamic Prompt / Prompt辞書 / Positiveテンプレ・お気に入り(プロンプト側)/ LoRA discovery UI。バックエンドAPIはそのまま生きているので、UIだけ後日追加する。
