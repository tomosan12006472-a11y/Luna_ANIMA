# 潜在バグ監査: store 同時アクセス / フロントエラー処理

監査日: 2026-06-12

## 前提

今日発生した `positive_prompt_favorites_store` の事故型は、同時読み書き中の一時的な JSON parse 失敗を「壊れたファイル」と誤判定し、`.broken` 退避や空データ扱いに進むことで、ユーザーからはデータ消失に見えるものだった。

本監査では次を重点確認した。

- ロック無しの read-modify-write
- transient な parse 失敗で `.broken` 退避、空データ、デフォルトに戻る箇所
- `write_json_atomic` を使わない JSON 直接書込
- `app/static/app.js` の fetch 失敗、401、非 JSON 応答時の扱い
- ANIMA_MobilePanel / SAA / claude が同じ外部ファイルを共有しうる箇所

## 指摘一覧

| ID | ファイル:行 | 発生条件 | 実害 | 推奨修正 |
| --- | --- | --- | --- | --- |
| A1 | `app/reference_store.py:38-55`, `app/reference_store.py:119-121`, `app/reference_store.py:125-154` | reference manifest に対して、アップロード、ComfyUI upload 結果反映、削除が同時に走る。`load_manifest()` -> mutate -> `save_manifest()` がロックされていない。さらに読込 parse 失敗時は空 manifest を返す。 | 高: 片方の登録や更新が消える。parse transient 後の保存で manifest 全体が空扱いになり、参照画像ファイルだけ残る orphan 状態になりうる。 | module lock を追加し、RMW 全体を同一 lock 内に入れる。parse 失敗時は短時間 sleep 後に 1 回 retry し、失敗時は空で上書きせずエラー扱いにする。 |
| A2 | `app/i2i_store.py:50-66`, `app/i2i_store.py:142-144`, `app/i2i_store.py:154-197`, `app/i2i_store.py:212-253` | i2i manifest に対して、upload、prepare、prepared upload 反映、削除が同時に走る。RMW 全体の lock がなく、parse 失敗時は空 manifest を返す。 | 高: 下絵登録、prepared 情報、ComfyUI upload 情報、削除結果が相互に上書きされる。空 manifest 保存で下絵一覧が消えたように見える。 | `_I2I_LOCK` などを追加し、manifest の load/mutate/save を一体で保護する。parse 失敗は 50ms retry 後も失敗なら保存系処理を止める。 |
| A3 | `app/settings_store.py:153-158`, `app/settings_store.py:221-243` | `settings.json` 読込中に transient parse 失敗が起きると即 `settings.broken_*.json` へ移動する。`save_app_settings()` / `reset_app_settings()` にも lock がない。 | 高: 設定がデフォルトへ戻ったように見える。保存と読込が重なると `.broken` 退避が誤爆する可能性がある。 | `_SETTINGS_LOCK` を追加し、load/save/reset を保護する。parse 失敗時は sleep + 1 retry 後にのみ broken 退避し、非 dict も同じ扱いにするか明示エラーにする。 |
| A4 | `app/favorites_store.py:32-37`, `app/favorites_store.py:78-90`, `app/favorites_store.py:136-172` | mutation 系は `_FAVORITES_LOCK` 内で呼ばれるが、`load_favorites()` 自体は lock/retry を持たず、parse 失敗で即 `.broken` 退避する。公開 read と mutation read が並行しうる。 | 中: キャラお気に入りが空に見える、または `.broken` へ退避される。write は atomic なので発生頻度は下がるが、外部プロセスや非 atomic writer が混ざると事故型に近い。 | `_load_favorites_unlocked()` と lock 付き wrapper に分割する。mutation 側は lock 内で unlocked を使い、parse 失敗は 1 retry 後にだけ退避する。 |
| A5 | `app/history_flags_store.py:26-45`, `app/history_flags_store.py:104-120` | flags 更新は lock 内だが、`load_history_flags()` が parse 失敗時に空 flags を返す。update 中に一時的な読込失敗が起きると、その空 payload に 1 件だけ追加して保存する。 | 高: 既存の favorite / post_candidate / hidden / tags がまとめて消えたように見える。 | `_FLAGS_LOCK` 配下で load/mutate/save を続ける点は維持しつつ、load を unlocked 化して retry を入れる。parse 失敗時は空保存へ進まずエラーにする。 |
| A6 | `app/lora_catalog.py:163-185`, `app/lora_catalog.py:252-281` | LoRA favorites の toggle が `load_lora_favorites()` -> mutate -> `write_lora_favorites()` だが lock がなく、保存も `write_text()` 直接。 | 中: 同時にお気に入り ON/OFF すると片方の変更が失われる。直接書込中に読まれると parse 失敗し、favorites が空に見える。 | `write_json_atomic` を使い、LoRA favorites 専用 lock で RMW 全体を保護する。読込 parse 失敗時は retry し、空 favorites として保存しない。 |
| A7 | `app/lora_catalog.py:123-148` | catalog refresh が `CATALOG_PATH.write_text()` 直接で、読込側は parse 失敗時に `default_catalog()` を返す。 | 中: refresh 中の部分書込を別 request が読むと、catalog が一時的にローカルスキャン結果へ戻る。UI 上は登録済み catalog が消えたように見える。 | catalog も `write_json_atomic` に統一する。parse 失敗時は retry し、それでも失敗なら default 返却ではなく warning 付きエラーに寄せる。 |
| A8 | `app/lora_catalog.py:430-457` | discovery review queue が `read_text()` -> mutate -> `path.write_text()` 直接で lock なし。複数 candidate review が同時に走る。 | 中: review_status / note の片方が失われる。直接書込中の読込で queue が空から再生成され、既存 review が消えたように見える。 | discovery review 専用 lock を追加し、`write_json_atomic` で保存する。既存 JSON parse 失敗時に空 queue へ進む前に retry する。 |
| A9 | `app/history_store.py:47-76`, `app/history_store.py:520-555`, `app/history_store.py:589-639` | 同じ history_id に対し、complete/status 更新/public save が近いタイミングで走る。個別 history JSON の `load_history_item()` -> mutate -> `save_history_item()` に per-item lock がない。 | 中: public_save メタデータ、queue status、完了時の image path などが stale item の保存で上書きされる。`write_json_atomic` は部分書込対策にはなるが lost update は防げない。 | history_id 単位の lock、または history store 全体 lock を導入し、同一 item の RMW を直列化する。保存前に現在値を再読込して merge する方式も可。 |
| A10 | `app/history_store.py:51-54`, `app/history_store.py:103-108`, `app/history_store.py:543-555` | history JSON 読込中の transient parse 失敗で `None` または skipped warning になり、status 更新が何もせず終了する。 | 中: queued/running が完了・失敗に更新されず、履歴が stale/missing に見える。データ削除ではないが、状態不整合が残る。 | `load_history_item()` と一覧読込に短時間 retry を入れる。更新系では parse 失敗を `None` と同じ扱いにせず、呼び出し側へエラーを返す。 |
| A11 | `app/prompt_dictionary_store.py:14`, `app/prompt_dictionary_store.py:127-184` | `D:\AI\PromptDictionaryData\sd-webui-prompt-dictionary\data` を複数アプリや生成ツールが共有する。TSV 更新中に検索 request が読むと、部分行や欠落行を cache する可能性がある。`_CACHE` に lock もない。 | 低-中: Prompt辞書の検索結果が欠ける、または一時的に例外で検索不能になる。JSON 退避事故ではないが、共有外部ファイル競合の入口。 | cache lock を追加する。TSV reader は mtime/size 安定確認または 1 retry を入れ、更新側にも tmp -> replace の atomic publish を徹底する。 |
| A12 | `app/positive_prompt_favorites_store.py:95-128`, `app/positive_prompt_favorites_store.py:155-157`, `app/positive_prompt_favorites_store.py:162-174`, `app/positive_prompt_favorites_store.py:180-185`, `app/positive_prompt_favorites_store.py:190-201` | 直近の対策で read と write は個別に lock されたが、add/update/delete/used の RMW 全体は同一 lock ではない。2 request が同時に同じ payload を読んで別々に保存する。 | 中: parse 失敗による `.broken` 誤爆は軽減済みだが、同時追加や use_count 更新の片方が lost update する。 | public mutation 関数で `_FAVORITES_LOCK` を取り、内部では `_load_payload_unlocked()` と write を同じ lock 内で実行する。Lock 再入を避けるため wrapper を使い分ける。 |
| F1 | `app/static/app.js:153-168` | 共通 `api()` は 401 と非 JSON を扱っているが、非 JSON 応答では raw body / content-type / status の情報を捨てて `"Response was not JSON"` だけになる。 | 低: デバッグ時にバックエンド HTML エラーや proxy エラーの原因が UI から追いにくい。 | 非 JSON の場合、status と raw 先頭 200-500 文字程度を error.data に残す。ユーザー表示は短く、console/debug 用に詳細を保持する。 |
| F2 | `app/static/app.js:1392-1395` | 履歴 polling の `loadContact()` 失敗を `console.warn()` のみで握りつぶす。連続失敗や 401 後の状態表示が残らない。 | 低-中: ネットワーク断やサーバ再起動中にユーザーは stale な履歴を見続ける。401 は `api()` が login view を出すが、polling 側の説明はない。 | 連続失敗回数を持ち、数回連続したら polling を止めて UI toast/status を出す。401 の場合は polling timer も止める。 |
| F3 | `app/static/app.js:1626-1627` | `shareFrame()` だけ画像取得に直接 `fetch()` を使い、401 を `exitToLogin()` に流さず汎用エラーにする。 | 中: セッション切れ時に「共有用画像を取得できませんでした」だけになり、ログイン切れだと分からない。 | blob/image 用の `fetchWithAuthHandling()` を作り、401 なら `exitToLogin()` し、status 別のエラーを投げる。 |
| F4 | `app/static/app.js:1827-1839`, `app/static/app.js:1843-1850` | bootstrap 中の `loadFavorites()` / `searchCharacters()` / `loadContact()` は `Promise.allSettled()` で失敗を表示しない。初回 bootstrap 失敗も `exitToLogin()` のみで理由を表示しない。 | 中: 起動直後に favorites/history が空に見えても、API 失敗・401・非 JSON のどれか判別しづらい。 | bootstrap の optional failure は status/toast に出す。401 は処理を中断し、loginStatus に理由を表示する。 |
| F5 | `app/static/app.js:1997-2000` | favorite 使用回数更新 API の失敗を完全に握りつぶす。 | 低: use_count / last_used_at が更新されず、並び順や利用履歴がずれる。 | ユーザー操作自体は成功扱いでよいが、少なくとも console/debug と軽い retry を入れる。 |

## 共有ファイルの競合可能性

- `app/config.py:7-17` を見る限り、settings / favorites / history / images / thumbnails / public は `ROOT_DIR / "user_data"` 配下で、デフォルトでは ANIMA_claude repo ローカル。ANIMA_MobilePanel / SAA / claude が別 checkout なら、これらの JSON は直接共有されない。
- `app/prompt_dictionary_store.py:14` の `D:\AI\PromptDictionaryData\sd-webui-prompt-dictionary\data` は外部共有パス。ANIMA_MobilePanel / SAA / claude が同じ辞書データを読む構成になりやすく、辞書更新プロセスが非 atomic に TSV を書くと全アプリへ影響する。
- `app/config.py:24-27` の ComfyUI LoRA directories は外部共有だが、この repo からは基本的に scan/read 用。JSON 状態は `user_data/lora_*.json` に保存されるため、LoRA ファイル自体の読込競合より、catalog/favorites JSON の非 atomic 書込の方が実害が出やすい。
- `app/config.py:19` の `SAA_ROOT` は SAA 側データ参照の入口だが、今回の対象 store では書込は確認できない。読み取り中に SAA 側がファイルを更新する場合は、同じく retry/snapshot 対策があると安全。

## 優先度順の修正案

1. `settings_store.py`, `reference_store.py`, `i2i_store.py`, `history_flags_store.py` に lock + read retry + RMW 直列化を入れる。
2. `lora_catalog.py` の `write_text()` を `write_json_atomic()` に置き換え、favorites/review queue の RMW を lock する。
3. `history_store.py` は history_id 単位の更新 lock を入れ、complete/status/public_save の lost update を防ぐ。
4. `favorites_store.py` と `positive_prompt_favorites_store.py` は load/save 個別 lock ではなく、mutation 全体を lock する形に揃える。
5. `app/static/app.js` は直接 fetch と bootstrap/polling の握りつぶしを減らし、401 と非 JSON の診断情報を UI/console に残す。
