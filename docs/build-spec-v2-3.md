# build-spec v2-③ — Image to Image 配線

前提: build-spec.md系列の厳守事項を引き継ぐ。変更してよいのは `app/static/app.js` のみ。UIシェル実装済み: fold `data-fold="i2i"`(#i2iEnabled / #i2iDenoise / #i2iResize / #i2iUseSource / #i2iFile / #i2iPreview / #i2iStatus、actions: `i2i-upload` / `i2i-clear`)、フレームシートに `frame-to-i2i`。

**重要(新ルール): 検証コマンド(unittest / サーバ起動 / curl / git commit)は実行しない。実装してファイル保存したら終了。検証とコミットはClaude側で行う。** `node --check` のみ実行可。

## 配線内容

1. state に `i2i = { imageId: "", thumb: "", name: "" }` を追加。
2. `i2i-upload`: `#i2iFile` のファイルを `FormData`(フィールド名 `file`)で POST `/api/i2i/upload` → 返却itemの `image_id` を保存し、`#i2iPreview` にサムネ(`item.thumbnail_url`)+ファイル名を表示(`is-empty`解除)。`#i2iEnabled` を自動ONにし `#i2iSummary` を ON に。失敗はtoast(error)。
3. `i2i-clear`: stateを空にし、プレビューを初期文言に戻し、`#i2iEnabled` をOFF。
4. `frame-to-i2i`(フレームシート内): POST `/api/i2i/from-history` `{history_id}` → 2.と同様にstate/プレビュー反映+自動ON → `UI.closeSheets()` → `UI.switchTab("expose")` → toast「下絵に設定しました」→ i2i foldを `open=true`。
5. `collectRequest()` の `image_to_image` を更新:
   `{ enabled: checked("#i2iEnabled") && !!state.i2i.imageId, image_id: state.i2i.imageId, denoise: number(#i2iDenoise), resize_mode: #i2iResize, use_source_size: checked("#i2iUseSource"), allow_with_hires_fix: false, allow_with_reference_assist: false }`
   imageId が空のままONの場合は、生成時にtoast(error)「下絵が未選択です」を出して送信中断(クライアント側ガード)。
6. `#i2iSummary` は ON/OFF + denoise値(例: `ON · 0.45`)を反映。

## Claude側で行う検証(参考)

node --check / unittest / 起動スモーク(upload往復はユーザー実機) / コミット `feat: add image-to-image wiring`
