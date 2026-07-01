# redesign 2026-07 — S2: 質感統一パス(語彙・タイポ・ボタン階層・整理)

S1(引き出し6段+レール、e696cdb)完了・実機承認済み。S2は**構造を一切動かさず**、見た目と言葉の統一だけを行う。ID/data-actionの増減ゼロが合格条件。

## 1. 語彙統一(ユーザー可視文字列)

- 「Workbench」「Hub」「Studio」「MOONLIGHT」系の語をHTML/JSのユーザー可視文字列から全廃。引き出し名(被写体/構図/道具/現像/増感/修整)と暗室語彙(露光/現像/密着→は使わない・履歴のまま)で統一。
- toast/status/プレースホルダ文言も同トーンに(例:「Prompt Workbenchを開きました」的な残骸があれば「道具を開きました」等へ)。
- summary/ラベルの英語sublabelはmono大文字の短語1語(SUBJECT/PROMPT/TOOLS/DEVELOP/BOOST/RETOUCH)に統一。

## 2. 引き出しの取っ手(summary)統一

- 全drawerのsummaryを同一構造に: `日本語名 + <span class="lbl">EN</span> + <span class="lbl drawer-value">現在値</span>`(S1で導入済みの形へ未統一箇所を寄せる)。
- 現在値の表示規則: OFF系は `--ink-faint`、何かONなら `--safelight`。クラス `drawer-value.is-on` で切替(app.js側は既存summary更新関数にclass切替を1行追加)。

## 3. ボタン階層の再確認

- 琥珀フィル(`.primary`相当)は **露光する / 入室 / ask内is-primary** のみ。それ以外で琥珀フィルがあればghostへ。
- インラインstyle(`style="margin-top:10px"`等)をクラスへ回収: `.mt10`のようなユーティリティは作らず、該当要素の既存クラスにマージンを持たせる(drawer間隔は `.drawer { margin-bottom: 12px }` 系で一元化)。
- `<hr>` はS1の `drawer-rule` クラスに統一(インラインstyleのhrを置換)。

## 4. 死んだCSSの剪定

- 解体済み構造のセレクタ(`.studio-hero*`, `.assist-hub-*`, `.workbench-tabs*`, `.nested-workbench` 等)を削除。**削除する各セレクタについて、index.htmlとjs/*.jsに使用箇所ゼロであることをgrepで確認し、削除リスト(セレクタ名+確認結果)を報告に含める**。使用が残っているものは削除せず報告のみ。
- 逆に`.tool-switch`(道具の切替)のスタイルはworkbench-tabs流用でなく独立定義に整理。

## 5. 間隔と細部

- tray/drawer のpadding・margin・gapを 8/12/20px リズムに統一(現状の10px/14px混在を寄せる。ただし全面書き換えではなく、明らかな不揃いのみ)。
- seg・chip・ghostの min-height 44px / active時フィードバック(既存流儀 opacity/色)を欠けている箇所に補完。
- `:focus-visible` の琥珀アウトラインが新設要素(rail/drawer summary/tool-switch)にも効くことを確認。

## 制約と検証(絶対)

- 変更可: app/static/index.html(文字列とclass/インラインstyle整理のみ・**要素の移動禁止**)、app/static/styles.css、app/static/js/*(ユーザー可視文字列とsummary class切替のみ)。ui.js変更禁止。
- **ID/data-actionの増減ゼロ**(S1と同じ集合チェックを実行し報告)。
- cache buster更新(`?v=v2.1-polish-<date>`、3箇所)。
- node --check 全JS。unittest/サーバ/git操作はClaude側。repo直下に一時ファイル禁止。
- 報告: 変更要約 / 死CSS削除リスト(grep根拠付き) / ID検査結果。
