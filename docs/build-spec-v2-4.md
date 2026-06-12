# build-spec v2-④ — 参照固定(Outfit / Pose)配線

前提: 既存spec系列の厳守事項を引き継ぐ。変更してよいのは `app/static/app.js` のみ。
**検証コマンド(unittest/サーバ起動/curl/git commit)は実行禁止。`node --check` のみ可。実装→保存→要約して終了。** repo直下に一時ファイル禁止。

UIシェル実装済み(fold `data-fold="refmod"`): #outfitEnabled/#outfitStrength/#outfitStart/#outfitEnd/#outfitFile/#outfitPreview、#poseEnabled/#poseMode/#poseStrength/#poseStart/#poseEnd/#poseFile/#posePreview、#refModSummary/#refModStatus。actions: outfit-upload/outfit-clear/pose-upload/pose-clear。

## 配線内容

1. state追加: `refmod = { outfit: {imageId:"", thumb:"", name:""}, pose: {imageId:"", thumb:"", name:""} }`。
2. `outfit-upload` / `pose-upload`: 各fileを FormData(`file`)で POST `/api/reference-modules/upload?module=outfit|pose` → 返却 `item.image_id` を保存、プレビューにサムネ(`item.thumbnail_url`)+名前、該当Enabledを自動ON。失敗toast(error)。
3. `outfit-clear` / `pose-clear`: state空・プレビュー初期化・EnabledをOFF。
4. `collectRequest()` の `reference_modules` を更新(フィールド名は移植元 `D:\AI\ANIMA_MobilePanel\app\static\app.js` の組み立てと、バックエンド `app/reference_modules.py` の `sanitize_reference_modules` が読むキーに正確に合わせる):
   `{ enabled: true, outfit: { enabled, image_id, strength, start_percent, end_percent }, pose: { enabled, image_id, mode, strength, start_percent, end_percent } }`
   ※キー名(`start_percent`等)は必ず sanitize_reference_modules の実装を読んで確定させること。
5. クライアントガード: Enabled ONかつimage_id空で生成しようとしたら toast(error)で中断(i2iと同様)。
6. `#refModSummary`: OFF / `OUTFIT` / `POSE` / `OUTFIT+POSE` を反映。
7. 生成・プレビューのエラーenvelope(`stage:"validate_reference_modules"`)はmessageをtoast(error)表示(既存エラーハンドラで足りるなら追加不要)。
