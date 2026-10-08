# DD-028: データソース定義(dsDef)のdisp属性キーをカラムのエイリアスと誤認する不具合

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-08 | 2026-10-08 | 完了 | 実ファイル・正式な`lineage.db`再生成の両方で修正を確認。受け入れ基準#1〜3すべて達成 |

> アプローチ: バグ修正・フルパス（画面表示(使用ボード欄)に影響するため。かつ対応方針が未確定でユーザー合意が必要なため）
> リスク: なし（外部I/F読み取り専用のパーサー・抽出ロジックの修正のみ。書き込み・認証には触れない）
> エビデンス: テスト出力（抽出ロジックの単体テスト。実機XML構造を模したフィクスチャを追加）

## 概要

| Bug# | 概要 | 重要度 |
|------|------|--------|
| 001 | `達成率ダッシュボード`ボード(dsDef`月次売上明細`)で、`価格`・`会社名`・`地域`・`受注日`・`品名`・`数量`・`氏名`・`売上額`・`支店`等ほぼ全列に、`true`という無関係な値がエイリアスとして記録される | MEDIUM |

## 原因分析

[DD-027](DD-027_支店カラムのエイリアスに無関係な年度が誤検出される不具合.md)の横展開調査で、Explore agentが実機`C:\MotionBoard64`の`達成率ダッシュボード.fs-file`内`dsDef/月次売上明細`のXMLを直接確認して特定した（DD-027の対応ではないため、別バグとして本DDに切り出す）。

`board_parser.py`の汎用ヒューリスティック(`walk()`→`find_label_on_element()`)は、物理カラム名と一致した属性と同一要素内の別属性を、`LABEL_KEY_HINTS = ("label", "disp", "name", "alias", "title", "caption", "表示", "名称")`への部分一致でラベル候補として拾う。

dsDef内の`<Item id="9" fid="9" title="価格" aliasTitle="" type="NUMBER" disp="true" orderNum="9" ...>`のような要素では、`aliasTitle`が空のため候補から除外された後、**属性キー`disp`自体**が`LABEL_KEY_HINTS`の`"disp"`に(部分一致どころか完全一致で)ヒットしてしまい、本来は「表示するかどうかのON/OFFフラグ」である属性値`"true"`がラベルとして採用される。

[DD-023](../archived/DD/DD-023_検索条件のdispTitleをカラムのエイリアスと誤認する不具合.md)・[DD-027](DD-027_支店カラムのエイリアスに無関係な年度が誤検出される不具合.md)と同じ欠陥クラス（物理カラム名と一致した属性と、ラベル候補として拾う属性の間に意味的関連性の検証が無い）だが、発生箇所(dsDef内`Item`要素自身の属性キー名)・ガードの当て方が異なる。DD-023/DD-027のガード(祖先タグ名での配下除外)では塞げない — `disp`は除外したい`Item`要素自身の属性キーであり、タグ名ではなく「`LABEL_KEY_HINTS`の`"disp"`という文字列が、表示フラグの属性キー名とも衝突する」という属性名ヒューリスティック自体の弱点。

> 詳細・引き継ぎ情報: [DD-027/bug-report.md](DD-027/bug-report.md)の「横展開調査の結論」節を参照

### 未確認事項(解消済み)

- 本DD起票時点(2026-10-08)では、`達成率ダッシュボード.fs-file`の実機スナップショットを`board_parser.py`で再解析すると0件(パースエラー)になるという過去の調査記録があった。Phase 2で改めて確認したところ**これは古い情報**で、現在のスナップショットは正常にパースできる状態だった(詳細: [verification.md](DD-028/verification.md)「実データ検証」節)
- `disp`属性による誤抽出が`達成率ダッシュボード`以外のボード・dsDefにも存在するかは、Phase 1で横展開確認済み(真偽値リテラル除外は属性名に依存しない汎用ガードのため個別対応不要と判断)

## 修正方針

**案B拡張版**（2026-10-08、ユーザー合意済み。実装時に当初の案Bから1段階拡張）:

1. `find_label_on_element()`の候補リスト生成時点で、値が`true`/`false`等の真偽値リテラルである属性を候補から除外する（属性名が`disp`かどうかに関わらず効く汎用ガード。当初合意の案B）
2. 上記だけでは、`aliasTitle`が空の`Item`要素に残る他の構造的属性(`id`/`fid`/`orderNum`等の連番、`type`等の型名)が、ラベルらしい手がかり(属性名一致・日本語)が無いまま最終フォールバック（残った候補の先頭を無条件採用）で次々に誤ったエイリアスとして拾われることが実装中の検証で判明したため、**この最終フォールバック自体を撤廃**した。ラベルらしい手がかりが本当に無い場合は`None`を返し、その列はエイリアスとして記録されない

既存テスト(19件の`display_name`アサーション)はすべて属性名一致か日本語一致のいずれかで解決しており、撤廃した最終フォールバックに依存しているケースは無かった(実装後の全回帰`pytest`で確認済み)。

検討した他案（不採用）:
- 案A: `LABEL_KEY_HINTS`から`"disp"`を外す。シンプルだが`disp`という単語名に限定されたパッチで、将来別の表示フラグ属性名で同種バグが起きた場合には効かない
- 案C: `disp`等の「表示フラグ」系属性名をブラックリスト化。ピンポイントで安全だが、同様の属性名が増えるたびに追記が必要な運用になる
- 真偽値リテラル除外のみ(当初の案Bそのまま): 残存する`id`/`fid`/`orderNum`/`type`等の構造的属性が次々に誤って拾われることが判明したため、最終フォールバック撤廃まで踏み込んだ（詳細は[DD-028/cause-analysis.md](DD-028/cause-analysis.md)および本DDのログ参照）

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `board_parser.py` | `_looks_like_boolean_literal()`を追加。`find_label_on_element()`の候補リストから真偽値リテラルを除外し、最終フォールバック(残った候補の先頭を無条件採用)を撤廃 |
| `tests/test_board_parser.py` | `TestDsDefItemDispFlagNotTreatedAsAlias`クラスを追加（`disp="true"`/`disp="false"`の誤抽出防止、aliasTitle設定時の正規検出維持、dsDef外のField/labelの検出維持を検証） |

## エビデンス配置

```
doc/DD/DD-028/
  cause-analysis.md      # 原因分析（詳細・コードレベル）
  bug-report.md          # 修正前バグ再現ドキュメント(Phase 0で作成)
  verification.md        # 修正後検証ドキュメント(Phase 2で作成)
```

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | `disp="true"`属性パターンを含むdsDef XMLを`auto_parse_xml`で解析する → `true`がエイリアスとして記録されない | `pytest tests/test_board_parser.py` |
| 2 | 既存の正規のエイリアス抽出(dsDef由来・SearchCondition除外・ItemOrderChange除外・計算項目)の検出結果に変化がない | `pytest`全体 → 既存件数のまま全パス |
| 3 | 実データ(`lineage.db`再生成)で`達成率ダッシュボード`の各列から`true`という誤エイリアスが消える | 実機確認（Dr.Sum実接続→`lineage.db`再生成＋組み込みブラウザ） |

## タスク一覧

### Phase 0: 調査・再現確認・修正前エビデンス

**調査:**
- [x] コードベース調査・原因箇所の特定（DD-027の横展開調査で完了。上記「原因分析」参照）
- [x] 原因分析を添付ファイル（[DD-028/cause-analysis.md](DD-028/cause-analysis.md)）に記載

**再現確認・修正前エビデンス:**
- [x] 最小XMLフィクスチャ(`disp="true"`パターン)で`auto_parse_xml`を実行し、`true`が誤抽出されることを確認
- [x] 📝 バグレポート作成（[DD-028/bug-report.md](DD-028/bug-report.md)）— DD-027/bug-report.mdの横展開調査結論を引き継ぎ、再現結果を記載
- [x] 👀 **ユーザーレビュー** — バグ再現と修正方針(案B)の合意（ゲート）

### Phase 1: コード修正・テスト
- [x] 原因箇所のコード修正（`_looks_like_boolean_literal()`追加 + `find_label_on_element()`の候補除外 + 最終フォールバック撤廃。[board_parser.py](../../board_parser.py)）
- [x] 同根パターンの横展開確認 — 真偽値リテラル除外は属性名(`disp`)に依存しない汎用ガードのため、`LABEL_KEY_HINTS`の他の要素(`label`/`name`/`alias`/`title`/`caption`/`表示`/`名称`)が同様の表示フラグと衝突しても同じガードで塞がれる。個別のブラックリスト追加は不要と判断
- [x] `tests/test_board_parser.py`に`TestDsDefItemDispFlagNotTreatedAsAlias`クラス(4テスト)を追加 — disp="true"/disp="false"の誤抽出防止、aliasTitle設定時の正規検出維持、dsDef外のField/labelの検出維持
- [x] 🔬 機械検証: `pytest tests/test_board_parser.py` → 全件パス（新規4件含め203 passed, 1 skipped）

### Phase 2: 修正後エビデンス・ドキュメント整備
- [x] 実ファイル(`達成率ダッシュボード.fs-file`の最新スナップショット)を直接取得し、`disp="true"`の実バグ構造が実在することを確認。`git stash`での修正前後比較で再現・解消を確認
- [x] 実データ(`C:\MotionBoard64`、Dr.Sum接続`DATALIZER_PRACTICE`)で`board_parser.py`→`match_aliases.py`を再実行し、`達成率ダッシュボード`のエイリアスが0件(誤エイリアスも含め一切記録されない)になったことを確認。組み込みブラウザでも目視確認
- [x] 📝 検証ドキュメント作成（[DD-028/verification.md](DD-028/verification.md)）
- [x] 🔬 機械検証（全回帰）: `pytest` → 203 passed, 1 skipped

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（[verification.md](DD-028/verification.md)の対応表参照。#1〜3すべて達成）
- [x] 😈 セルフレビュー1巡（所見: 真偽値リテラル除外のみでは`id`/`type`等が次々に誤って拾われる残存問題を実装中に発見し、最終フォールバック撤廃まで踏み込んだ。実ファイルでの修正前後比較と正式な`lineage.db`再生成の両方で実証済み。lineage.db再生成に伴う副作用(他スキーマのデータ混在)はユーザーに報告し、現状維持の了承を得た）
- [x] 🔬 全回帰1回: `pytest && bash scripts/doc-check.sh`

## ログ

### 2026-10-08
- DD-027の横展開調査(Explore agent)で、`達成率ダッシュボード`ボードの`価格`列→`true`等の誤エイリアスが、`ItemOrderChange`とは無関係の別原因(dsDef内`Item`要素の`disp`属性キーが`LABEL_KEY_HINTS`の`"disp"`に誤マッチ)と判明。DD-027のスコープ外としてユーザーと合意し、本DDとして新規起票
- Phase 0: 実機構造を模した最小XMLフィクスチャ(`<Item title="TANKA" aliasTitle="" disp="true">`)で`auto_parse_xml()`を実行し、`display_name='true'`の誤抽出を再現確認。[bug-report.md](DD-028/bug-report.md)に記録
- Phase 0完了: 修正方針を案B（値が真偽値リテラルならラベル候補から除外する汎用ガード）でユーザー合意。Phase 1着手
- Phase 1: 案Bを実装したところ、`disp="true"`は防げたが、同一要素に残る`id`/`fid`/`orderNum`(数字)や`type`(型名)が、ラベルらしい手がかりが無いまま最終フォールバック(残った候補の先頭を無条件採用)で次々に誤って拾われることが判明(`true`→`9`→`NUMBER`と変化)。ユーザーと相談し、最終フォールバック自体を撤廃する方針に拡張してユーザー合意
- Phase 1完了: `_looks_like_boolean_literal()`追加、`find_label_on_element()`の候補除外と最終フォールバック撤廃を実装。`tests/test_board_parser.py`に回帰テスト4件を追加し、全回帰`pytest`(203 passed, 1 skipped)で既存ケースへの影響なしを確認
- Phase 2: `C:\MotionBoard64`に直接アクセスできたため、`達成率ダッシュボード.fs-file`の最新スナップショットを取得。以前の「パースエラー」記録は古い情報で、実際には正常にパースできることが判明。入れ子ZIP内の実dsDef XMLを取り出すとcause-analysis.mdの推定構造が実在することを確認し、`git stash`での修正前後比較で再現(9件の`true`誤エイリアス)と解消(0件)を確認
- Phase 2: ユーザーからDr.Sum接続情報(ホスト`localhost`、DB`DATALIZER_PRACTICE`、ユーザー`Administrator`、パスワード無し)の提供を受け、正式な`dr_sum_metadata.py`→`board_parser.py`→`match_aliases.py`の手順で`lineage.db`を再生成。`達成率ダッシュボード`のエイリアス0件・DB全体で`true`誤エイリアス0件を確認し、組み込みブラウザでも目視確認。[verification.md](DD-028/verification.md)を作成
- `lineage.db`再生成に伴い、他スキーマのデータが混在する副作用が発生したためユーザーに報告。現状維持で了承を得た
- Phase 2完了。受け入れ基準#1〜3すべて達成と判断しDD完了
