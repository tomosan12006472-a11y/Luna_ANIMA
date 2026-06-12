# build-spec v2-① — Dynamic Prompt + Positiveお気に入り/テンプレート 配線

前提: build-spec.md の厳守事項をすべて引き継ぐ(app/static/{index.html,styles.css,ui.js} 変更禁止 / venv禁止 / lock残骸は削除して続行 / 変更は app/static/app.js のみ)。HTML側のUIシェルは追加済み(commit参照)。

## 1. Dynamic Prompt(fold `data-fold="dynamic"`)

- `#dynamicEnabled`(checkbox): ONで `collectRequest()` の `dynamic_prompt` を `{enabled:true}` に(`wildcard_seed` は送らない=seed連動)。`#dynamicSummary` に ON/OFF を反映。
- `data-action="dynamic-wildcards"`: GET `/api/dynamic-prompts/wildcards` → `#wildcardChips` に各wildcard名のchip(`__name__`形式表示)。chipタップで `#positivePrompt` のカーソル位置(なければ末尾)に `__name__, ` を挿入。
- `data-action="dynamic-preview"`: POST `/api/dynamic-prompts/preview` `{positive_prompt: 現在のpositive全文(collectRequestのprompt組み立てではなく#positivePromptの生値でよい), negative_prompt:"", seed: 現在のseed値(数値), enabled:true}` → `expanded_positive_prompt` を `#dynamicPreview` に表示+hidden解除。warningsがあればtoast。

## 2. Positiveお気に入り / テンプレート(共用シート `#promptSheet`)

- `data-action="save-positive-fav"`: POST `/api/prompts/positive-favorites` `{title: 先頭40文字, prompt: #positivePromptの値, tags: [], note: ""}` → toast「保存しました」。空なら toast(error)。
- `data-action="open-positive-favs"`: `#promptSheetTitle`=「Positiveお気に入り」、GET `/api/prompts/positive-favorites` → `#promptSheetList` に行(タイトル+prompt先頭60字)。行タップ→ `#positivePrompt` に **append**(空なら置換)+ POST `/api/prompts/positive-favorites/{id}/used` + `UI.closeSheets()` + toast。行内に削除ボタン(ghost、`削除`)→ DELETE `/api/prompts/positive-favorites/{id}` → リスト再描画。`#promptSheetQuery` でクライアント側絞り込み。`UI.openSheet("#promptSheet")`。
- `data-action="open-templates"`: `#promptSheetTitle`=「テンプレート」、GET `/api/prompts/positive-templates?query=&limit=50` → 同形式で表示(削除ボタンなし)。タップでappend+閉じる。`#promptSheetQuery` 変更時はAPIの `query=` で再取得(250msデバウンス)。
- 表示は既存class(`.resultlist`の`<button>`行+`.tag`)を流用。新規CSS不要。

## 3. 検証とコミット

- `node --check app/static/app.js` / `.venv\Scripts\python.exe -m unittest discover -s tests` green / 51031起動→PIN 2197→bootstrap 200→停止。
- 動作確認(curlで可): positive-favorites POST→GET→DELETE 往復、dynamic-prompts/wildcards 200。
- コミット: `feat: add dynamic prompt and prompt library wiring`
