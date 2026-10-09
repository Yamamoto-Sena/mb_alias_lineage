# DD-033: テーブル定義パネルに精度・スケール・NULL許可・ユニークを追加

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-08 | 2026-10-08 | 完了 | 2件の受け入れ基準をE2E確認。実機Dr.Sum取得は別DDへ |

> アプローチ: 標準（既存のテーブル定義パネルへの列追加・既存画面の小規模改善で、新規画面や大幅な見た目変更を伴わないためモック先行は不要。guides.md §1）
> リスク: あり（DBスキーマ — `lineage.db`の`columns`テーブルに列追加。ただしD-001によりlineage.dbは実行毎に作り直す使い捨てスナップショットのため、既存データの移行は不要）

## 目的

テーブル定義パネル（物理カラム名クリックで開く`table-def-panel`）で、データ型に加えて精度・スケール・NULL許可・ユニークまで確認できるようにする。既定表示はデータ型までの簡潔な表示を維持し、ボタン操作で詳細列を展開できるようにする。

## 背景・課題

現状`table-def-panel`は「物理カラム名」「データ型」の2列のみ表示しており(`web_viewer.py`の`openTableDefPanel`/`fetch_data`)、精度・スケール・NULL許可・ユニーク制約の情報は`columns`テーブル(`db_schema.sql`)にも取得元のJSON(`dr_sum_columns.json`)にも存在しない。

ユーザーからの要望: 「テーブル定義の表示は精度、スケール、null、ユニークまで表記してほしい。基本はデータ型で折り畳みですべて表示まで」。

実機Dr.Sumの`__all_tables__`カタログがこれらの属性を実際に公開しているかは未確認（`doc/decisions.md` D-004参照）。ユーザー確認の結果、今回はデモデータ(`demo_data/dr_sum_type_schema/テーブル定義.md`に精度/スケール/NULL可否の定義が既にある)のみで画面を先行実装し、実機Dr.Sumからの取得対応は別DDとする。

## 検討内容

- 情報源: デモデータのみで先行実装（ユーザー確認済み。実機カタログ調査は別DD）
- 折りたたみ方式: 列を増やし既定は非表示、ボタンで展開（ユーザー確認済み。行のグループ化は不採用）
- スキーマ命名: 将来の実機JDBC対応(`dr_sum_metadata.py`)で標準的なJDBC `DatabaseMetaData.getColumns()`の列名(`COLUMN_SIZE`/`DECIMAL_DIGITS`/`IS_NULLABLE`)に寄せた`column_size`/`decimal_digits`/`is_nullable`を採用し、将来の実機対応時に意味が分かりやすいようにする。「ユニーク」はJDBC標準に対応列が無く独自項目のため`is_unique`とする
- 欠損値の扱い: 既存5テーブル(`SCHEMA`)は精度/スケール/NULL/ユニーク情報が無いため`NULL`のまま。パネル上は「-」表示とし、「情報なし」が自然に見えることを確認する(実機でこれらの値が取れない場合の表示にもそのまま使える)

## 決定事項

- `columns`テーブルに`column_size`/`decimal_digits`/`is_nullable`/`is_unique`(すべてNULL許容)を追加する
- `demo_data/dr_sum_type_schema/テーブル定義.md`に既にある精度/スケール/NULL可否を`build_dr_sum_columns.py`の`SCHEMA_TYPE_COVERAGE`に反映する。ユニークは同フォルダの README記載(コード列は5,000行で重複なしを確認済み)に基づき、コード/番号列のみ`is_unique="YES"`とする
- 既存`SCHEMA`(5テーブル)はこれらの値を追加しない(NULLのまま。欠損時の表示確認を兼ねる)
- `table-def-panel`に「すべて表示」トグルボタンを追加し、既定非表示→押下で精度・スケール・NULL許可・ユニーク列を表示する(他N件表示などの既存トグルUIパターンを踏襲)

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | デモデータ読み込み後、物理カラム名をクリックしてテーブル定義パネルを開く → 既定では「物理カラム名」「データ型」の2列のみ表示される | Phase 2 E2Eシナリオ#1 |
| 2 | パネル内の「すべて表示」ボタンを押す → 精度・スケール・NULL許可・ユニークの列が追加表示され、値が無いカラムは「-」になる(`T_配送案件.運賃`は`(10,2)`/NULL可、`T_配送案件.配送案件コード`はユニーク) → 再度押すと元の2列表示に戻る | Phase 2 E2Eシナリオ#2 |
| 3 | `pytest`が全件パスする | Phase 1/2 🔬機械検証 |

## タスク一覧

### Phase 1: データ層（デモデータ・DB・ETL）
- [x] `db_schema.sql`: `columns`テーブルに`column_size INTEGER`, `decimal_digits INTEGER`, `is_nullable TEXT`, `is_unique TEXT`を追加(すべてNULL許容)
- [x] `match_aliases.py`: `build_db`内の2箇所の`INSERT INTO columns`を4列追加に対応(`col.get("column_size")`等、未指定はNULL)
- [x] `demo_data/build_dr_sum_columns.py`: `SCHEMA_TYPE_COVERAGE`の各列タプルに`column_size`/`decimal_digits`/`is_nullable`/`is_unique`を追加(`demo_data/dr_sum_type_schema/テーブル定義.md`の値を転記)。`SCHEMA`は変更なし(4フィールドとも未設定=NULL)。`main()`が両スキーマでフィールド数が異なっても動くようにする
- [x] `demo_data/build_dr_sum_columns.py`を実行して`demo_data/dr_sum_columns.json`を再生成
- [x] `tests/test_match_aliases.py`: `build_db`が4列を保存することを確認するテストを追加
- [x] 🔬 機械検証: `pytest tests/test_match_aliases.py` 全パス（47 passed）

### Phase 2: 画面表示
- [x] `web_viewer.py`: `fetch_data()`のSELECT文に`column_size`,`decimal_digits`,`is_nullable`,`is_unique`を追加し、返却dictにも追加（ブラウザ内評価モードの`jsFetchData`も同様に追加。D-007によりPython版と一致させる必要があるため）
- [x] `tests/test_web_viewer.py`: `_make_db`ヘルパーのCREATE TABLE/INSERT文に4列追加(既存呼び出しはNULLのままでテスト互換を維持)。新規テスト2件を追加
- [x] `web_viewer.py`(`table-def-panel`のHTML/CSS/JS): theadに「すべて表示」トグルボタンを追加。既定は「物理カラム名」「データ型」の2列のみ表示、押下で精度・スケール・NULL許可・ユニーク列を追加表示(値なしは「-」)。`export_static.py`は`fetch_data`/`INDEX_HTML`を再利用するため追加変更不要であることを確認した
- [x] 🔬 機械検証: `pytest tests/test_web_viewer.py` 全パス（24 passed）
- [x] 🔬 E2Eシナリオ(Playwright MCP): `.claude/skills/run`の`web-viewer-demo`設定でデモデータを開き、受け入れ基準#1・#2を操作して確認(下記エビデンス参照)

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（全3件達成。詳細は下記）
- [x] 😈 セルフレビュー1巡（ログ参照）
- [x] 🔬 全回帰1回（`pytest && bash scripts/doc-check.sh` → 230 passed, 1 skipped / doc-check OK）

## 受け入れ基準の確認結果

| # | 結果 |
|---|------|
| 1 | ✅ `T_配送案件`のパネルを開いた状態で確認。既定は「物理カラム名」「データ型」の2列のみ表示 |
| 2 | ✅ 「すべて表示」クリックで4列展開。`運賃`=`NUMERIC/10/2/NULL可/-`、`配送案件コード`=`VARCHAR/20/-/NOT NULL/○`を確認。再クリックで2列表示に復帰。別テーブル(`T_売上明細`、精度情報なし)では4列とも「-」表示を確認 |
| 3 | ✅ `pytest` 230 passed, 1 skipped |

## エビデンス

Playwright(Claude Browser)でのE2E確認（`get_page_text`によるテキスト抽出で検証。既定表示→展開→別テーブルへの切替→折りたたみの4操作を実施し、いずれも期待通り）。スクリーンショットは撮影不可(ヘッドレスpaneのタイムアウト)だったため、`get_page_text`の抽出結果をログに記録する形でエビデンスとした。

## ログ

### 2026-10-08
- DD作成。ユーザー確認: (1)情報源はデモデータのみで先行実装、実機Dr.Sumカタログ調査は別DD、(2)折りたたみはテーブル定義パネルの列追加+ボタン展開方式
- 実装完了。Phase1(DBスキーマ・ETL・デモデータ生成)→Phase2(fetch_data拡張・UI追加)の順で実装し、`python main.py --demo`で`demo_data/lineage.db`を再生成、Claude Browserで実画面確認
- セルフレビュー所見: (1) 既存の実機`lineage.db`(スキーマ変更前に生成されたもの)をそのまま使うと`fetch_data`が`no such column: c.column_size`で落ちる。D-001の設計(`match_aliases.py`実行毎にDROP→CREATEで作り直す使い捨てスナップショット)により通常は影響ないが、スキーマ変更後は一度`python main.py`(または`match_aliases.py`)の再実行が必要である旨を完了報告でユーザーに案内する。(2) `jsFetchData`(ブラウザ内評価モード用のJS版SQL)にも同じ列追加が必要なことに気づき対応済み(D-007)。(3) 実機Dr.Sumからの取得(`dr_sum_metadata.py`)は意図的にスコープ外のままで、`column_size`等は常にNULLになる(D-004の既知の制約として変更なし)
- 受け入れ基準3件すべて達成、全回帰パスを確認したためステータスを「完了」に変更
