# build-spec v2-② — Prompt辞書 配線

前提: build-spec.md / build-spec-v2-1.md の厳守事項を全部引き継ぐ。変更してよいのは `app/static/app.js` のみ。HTMLシェル(fold `data-fold="dictionary"`: #dictTarget / #dictQuery / #dictResults / #dictStatus)は実装済み。

## 配線内容

1. `#dictQuery` 入力を250msデバウンスして GET `/api/prompt-dictionary/search?q=<query>&limit=50`。クエリ空なら `#dictResults` を空にしてreturn。応答が古いクエリ分なら破棄(検索UXと同じstaleガード方式)。
2. 結果行は `.resultlist` の `<button>` 行で、左=日本語/表示名、右=`<span class="tag">` に英語タグ。行タップで `#dictTarget` の値に応じて挿入:
   - `positive` → `#positivePrompt` のカーソル位置(なければ末尾)に `タグ, ` を挿入
   - `negative` → `#negativePrompt` 末尾に `, タグ`(空なら裸で)
   挿入後は結果リストを**消さない**(連続挿入できるように)。toastで「追加: タグ」。
3. fold初回オープン時(toggleイベント or 初回検索時)に GET `/api/prompt-dictionary/status` を1回呼び、`ok`でなければ `#dictStatus` に warning文言を表示(辞書データ未配置の案内)。
4. 挿入ヘルパーはv2-①で作ったカーソル挿入関数を再利用(重複実装しない)。

## 検証とコミット

- `node --check app/static/app.js` / `.venv\Scripts\python.exe -m unittest discover -s tests` green。
- HTTPスモークは**読み取りのみ**: 51031起動→PIN 2197→ GET `/api/prompt-dictionary/status` と `search?q=hair` が200→サーバ停止。書き込み系APIは叩かない。
- コミット: `feat: add prompt dictionary wiring`(`git add app/static/app.js` のみ。`git add -A`禁止)
- repo直下に一時ファイルを作らない(必要ならOSのTEMP)。
