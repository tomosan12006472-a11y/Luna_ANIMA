# build-spec v3 — レシピ / バリエーション / キュー管理

共通厳守: 検証コマンド・git操作禁止(node --check/構文確認のみ可)。repo直下に一時ファイル禁止。JSON書式は `ensure_ascii=False, indent=2`。store実装は commit 2b4afea のロックパターン(module Lock / _unlocked分割 / parse失敗0.05s再試行 / write_json_atomic)に必ず従う。

## v3-② バリエーション(フロントのみ、app/static/app.js)

シェル: フレームシートに `#variationCount`(2/4/8)と `data-action="frame-variations"`。

- 押下で、表示中の履歴itemから生成リクエストを構築(`frame-reuse` の項目→フォーム反映ロジックを関数化して再利用し、フォームには反映**せず**リクエストdictだけ作る、または一時的にフォーム反映→collectRequest→元に戻すのではなく前者の純関数化を推奨)。
- 上書き: `seed_mode:"random"`, `seed:-1`, `count: Number(#variationCount)`, `wait:false`。
- POST `/api/generate` → 成功で `UI.closeSheets()` + toast「🎲 N枚キューに入れました」+ セーフライトdeveloping + 履歴ポーリング開始(既存の生成成功処理を再利用)。
- 失敗はmessageをtoast(error)。

## v3-① レシピ(バックエンド新store + ルート + フロント)

### backend: `app/recipes_store.py`(新規)
`positive_prompt_favorites_store.py` を雛形に: PATH=`user_data/recipes_anima.json`、`{"version":1, "app_scope":"anima", "items":[...]}`。
item = `{id: "recipe_<stamp>_<hex>", name: str(<=60字), request: dict(collectRequest相当の生成リクエスト全体), summary: str(<=120字), created_at, updated_at, use_count, last_used_at}`。`request` は無検証で保存してよい(適用時にフロントが解釈)が、dict以外は拒否。
公開関数: `list_recipes()`(last_used_at/created_at降順) / `add_recipe(name, summary, request)` / `delete_recipe(recipe_id)` / `mark_recipe_used(recipe_id)`。全mutationはロック内RMW。

### backend: `app/main.py` ルート追加(既存の認証付きルートの形式に厳密に合わせる)
- GET `/api/recipes` → `{ok, items, count}`
- POST `/api/recipes` body `{name, summary, request}` → 201 `{ok, item, ...}`(nameが空ならsummaryから自動生成)
- DELETE `/api/recipes/{recipe_id}` → `{ok, removed}`
- POST `/api/recipes/{recipe_id}/used` → `{ok, item}`
Pydanticモデルは既存スタイル(`RecipeRequest`)で。

### frontend(app.js)
- `data-action="save-recipe"`: `collectRequest()` を取り、name=自動(`C1表示名 / 品質 / WxH / HH:MM` 形式、C1未選択なら"Random")、summary=`rating·quality·サイズ·steps` 程度 → POST。成功toast。
- `data-action="open-recipes"`: GET → `#recipeList` に行(name+summaryの2行表示、右に削除ghostボタン)。行タップ→ `request` をフォームへ全反映(`frame-reuse` と同じ反映関数を共用。スロット名・rating/quality seg・シーン各欄・negative・技術設定・公式LoRA・LoRAスロット・i2i/参照固定/FDのenabled類まで反映できる範囲で)+ `/used` 通知 + `UI.closeSheets()` + toast「レシピを適用しました」。
- 適用関数はitem.request内に無いキーを既定値に戻すこと(古いレシピでも安全)。

## v3-③ キュー管理(backend小+フロント)

### backend
- `app/comfy_client.py` に追加: `queue_delete(addr, prompt_ids: list[str])` = POST `http://{addr}/queue` body `{"delete": prompt_ids}`、`interrupt(addr)` = POST `http://{addr}/interrupt`。既存 `queue_prompt` のurllib形式に合わせ、`{ok, status, text}` を返す。
- `app/main.py` ルート追加(要認証):
  - GET `/api/queue`: `comfy_client.queue_info(addr)` を整形 → `{ok, running:[{prompt_id, ours, history_id?}], pending:[{position, prompt_id, ours, history_id?}]}`。`ours` 判定は、pending状態の履歴item(`list_all_history_with_warnings` から status queued/running)の `prompt_id` 集合との一致で行う(client_id文字列には依存しない)。
  - POST `/api/queue/cancel` body `{prompt_id}` → queue_delete。対応する自アプリのpending履歴があれば `update_pending_history_status(history_id, "failed", "Cancelled by user")` を呼ぶ。
  - POST `/api/queue/interrupt` → interrupt(実行中1件の中断。履歴側はポーリングの既存stale/failed処理に任せる)。
- ComfyUI不達時は `{ok:false, message}`(500にしない)。

### frontend(app.js)
- `data-action="open-queue"`(セーフライトstatusタップ): `UI.openSheet("#queueSheet")` + 取得描画。シートが開いている間は3秒毎に自動更新、閉じたら停止。
- `#queueList` 行: `queue-dot`(running=`is-running`)+ `#位置` + prompt_id先頭8字 + `ours` なら「このアプリ」ラベル + 右に「取消」ghostボタン(pendingのみ。POST cancel→再描画+履歴リフレッシュ)。
- `data-action="queue-interrupt"`: confirm的な二度押し不要、即POST → toast。`data-action="queue-refresh"`: 手動更新。
- `#queueCountLbl` に `実行中N · 待機N`。空なら `#queueStatus` に「キューは空です」。

## 実装順序と納品

②→①→③ の順に、**1機能ずつ別タスクで依頼される**。各タスクでは指定された機能のみ実装し、保存→変更要約→終了。
