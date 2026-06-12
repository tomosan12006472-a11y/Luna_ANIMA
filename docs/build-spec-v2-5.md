# build-spec v2-⑤ — Face Detailer 配線

前提: 既存spec系列の厳守事項を引き継ぐ。変更可は `app/static/app.js` のみ。
**検証コマンド(unittest/サーバ起動/curl/git commit)実行禁止。`node --check` のみ可。実装→保存→要約して終了。** repo直下に一時ファイル禁止。

UIシェル実装済み: fold `data-fold="facedetailer"`(#fdEnabled/#fdDenoise/#fdSteps/#fdCfg/#fdBbox/#fdSummary/#fdStatus)、フレームシートに `data-action="frame-face-detail"`(「顔を補正」)。

## 配線内容

1. **生成時FD**: `collectRequest()` の `face_detailer` を更新。キー名は `app/face_detailer.py` の `sanitize_face_detailer_settings` 実装を読んで正確に合わせる(目安: `{enabled, denoise, steps, cfg, bbox_threshold}` だが必ず実装を確認)。`#fdSummary` に `ON · 0.30` / `OFF`。
2. **後処理FD**(`frame-face-detail`): 表示中フレームに対し POST `/api/face-detailer/postprocess` `{history_id, settings: {denoise/steps/cfg/bbox_threshold(現在のfold値)}}` → 成功で `UI.closeSheets()` → toast「顔補正をキューに入れました」→ 安全灯をdevelopingに(既存の生成後ポーリング起動処理を再利用し、pending監視を開始)。失敗(`face_detailer` 未サポート等)はレスポンスのmessageをtoast(error)。
3. ComfyUI側にFaceDetailerノードが無い環境では postprocess が400を返す — そのままmessage表示でよい(機能検出UIは作らない)。
