# redesign 2026-07 — S1: 露光タブの平坦化(引き出し6段+ドロワーレール)

背景: 機能追加で露光タブが「Workbench(fold)>タブ>fold」の3階層になり、状態がタブに隠れて「目的の設定を探す」「ごちゃつき」が発生。ユーザー承認済みの方針=**大胆に再構成OK・段階適用**。本書はS1(情報アーキテクチャ)のみ。S2(質感統一)は別タスク。

設計原則: **タブは状態を隠すので、設定には使わない**。設定は「引き出し(details 1階層)」に置き、取っ手(summary)に現在値を常時表示する。タブ的切替は「一時的な道具」にだけ許す。

## 完成形: 露光タブの構造(上から)

```
[safelightStatus 既存]
[#drawerRail 新設・sticky]  被写体|構図|道具|現像|増感|修整
[セッション行(旧heroの置換)]  レシピchip列 + payload確認ボタン
[#sec-subject 被写体]  ← 既存キャラクターtray(常時展開のまま)
[#sec-prompt  構図]    ← rating/quality/positive/library行/ネガティブ/prompt_ban を1つのtrayに平置き
[#sec-tools   道具]    ← 変換・Random・AutoInsert・辞書(fold内、slimチップ切替、パネルは平坦)
[#sec-develop 現像]    ← サイズ/steps/cfg/shift/sampler/scheduler/model/seed(+旧Output/Quickの中身)
[#sec-boost   増感]    ← 公式LoRA+LoRAスロット+Hires(平置き、hr区切り)
[#sec-retouch 修整]    ← i2i / 参照固定 / Detailer / Dynamic Prompt(平置き、hr区切り)
[確認/既定値 fold=defaults 既存のまま最下段]
```

## ブロック移設マップ(既存identifierで指定。**中身のinput/button/idは一切変更禁止**、移動のみ)

| 現在地 | 行先 |
|---|---|
| `.studio-hero` 全体 | **削除**。代替=セッション行: `quick-actions` 行を拡張し「レシピ / レシピ保存 / payload確認」の1行+`#heroTechSummary`/`#heroAssistSummary` は削除(レールと取っ手summaryが代替。参照JSも除去) |
| fold `prompt-workbench` + そのタブ機構 | **解体** |
| panel `write` の中身(rating/quality/positive/library行) | `#sec-prompt` tray 前半 |
| fold `negative`(More内) | `#sec-prompt` tray 後半に**平置き**(foldのまま置くのではなく、中身を展開して配置。ネガティブは核心設定のため常時可視) |
| fold `prompt-converter`(Convert内) | `#sec-tools` の「変換」パネル |
| fold `prompt-random`(Random内) | `#sec-tools` の「Random」パネル |
| fold `auto-insert`(More内) | `#sec-tools` の「Auto Insert」パネル |
| fold `dictionary`(More内) | `#sec-tools` の「辞書」パネル |
| fold `tuning-workbench` + タブ機構 | **解体** |
| panel `official` / panel `lora` / fold `hires` | `#sec-boost` に上から順に平置き(区切りは `<hr class="drawer-rule">`) |
| panel `output` の中身(サイズ等があれば) | `#sec-develop` へ統合(重複入力があれば既存idの方を残す) |
| panel `quick` / fold `quick-controls-bulk` | 中身を精査し、生成条件系は `#sec-develop`、一括操作系は `#sec-tools` 末尾へ。判断に迷う要素は**捨てずに** `#sec-develop` 末尾 |
| fold `advanced-assist` + タブ機構 | **解体** |
| fold `i2i` / fold `refmod` / panel `finish` の中身 / fold `dynamic` | `#sec-retouch` に i2i→参照固定→Finish(Krita/署名)→Detailer系→Dynamic の順で平置き+hr区切り |
| fold `defaults` | 最下段に現状のまま |

- 解体後、`data-workbench-tab`/`data-workbench-panel`/`assist-hub-tabs` の露光タブ内での使用は `#sec-tools` の道具切替**のみ**(クラス名を `tool-switch` に改名可)。
- `#sec-*` は `<details class="tray drawer" id="sec-x" data-fold="sec-x" open>`。summaryは「日本語名+`<span class="lbl">EN</span>`+現在値`<span class="lbl drawer-value" id="secXValue">`」の3点構成。被写体のみ`<div class="tray">`(常時展開)に `id="sec-subject"`。
- 各drawer summaryの現在値はapp.jsが既存のsummary更新関数を流用して書く(例: 現像=`1024×1536 · 32 · 4.5 · shift4`、増感=`Official 1 · Slots 2 · Hires ON`、修整=`i2i OFF · Ref OFF · Detailer ON`)。ON状態のdrawerには `UI.railMark("sec-boost", true)` を呼ぶ(実装済みプリミティブ)。

## ドロワーレール(新設)

- HTML(exposeView先頭、セッション行の前):
```html
<nav id="drawerRail" aria-label="sections">
  <button type="button" data-rail="sec-subject" class="is-active">被写体</button>
  <button type="button" data-rail="sec-prompt">構図</button>
  <button type="button" data-rail="sec-tools">道具</button>
  <button type="button" data-rail="sec-develop">現像</button>
  <button type="button" data-rail="sec-boost">増感</button>
  <button type="button" data-rail="sec-retouch">修整</button>
</nav>
```
- JSは実装済み(`UI.initRail()` を `enterDarkroom` 後に1回呼ぶ / `UI.railMark(id,on)`)。app.jsから呼び出しを追加。
- CSS(styles.cssに追加): `#drawerRail{position:sticky; top:26px; z-index:40; display:flex; gap:4px; overflow-x:auto; background:var(--bg); padding:6px 0; border-bottom:1px solid var(--line); -webkit-overflow-scrolling:touch}` / ボタン=mono 12px・min-height 36px・borderなし・`color:var(--ink-faint)`、`.is-active{color:var(--safelight)}`、`.has-on::after{content:"";display:inline-block;width:5px;height:5px;margin-left:4px;background:var(--safelight);vertical-align:2px}`。スクロールバー非表示。各`#sec-*`に `scroll-margin-top: 92px`。

## 制約(絶対)

- 既存の全 input/select/textarea/button の **id と data-action を1つも消さない・変えない**(移動のみ)。削除対象で参照が残るのは `heroTechSummary`/`heroAssistSummary` のみ(参照JSごと除去)。
- backend変更禁止。`app/static/` 以外変更禁止。
- fold記憶キー(`data-fold`)は新drawerに新名を与え、旧名(prompt-workbench等)の掃除はlocalStorage側では不要。
- cache buster を全3箇所更新(例: `?v=v2.0-drawers-<date>`)。
- 検証: `node --check`(全 app/static/js/*.js と ui.js)+「旧HTMLに存在した `id="` と `data-action="` の集合が新HTMLでも同一(hero2件を除く)」をスクリプトで確認し、結果を報告に含める。unittest/サーバ起動/gitはClaude側。
- repo直下に一時ファイルを作らない。

## S2(次タスク・今回やらない)予告

語彙統一(Workbench/Hub/Studio用語の全廃、drawer名で統一)、summary/ラベル/ボタン階層のスタイル統一、間隔トークン整備。
