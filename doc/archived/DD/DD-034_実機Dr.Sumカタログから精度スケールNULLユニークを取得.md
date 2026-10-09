# DD-034: 実機Dr.Sumカタログから精度・スケール・NULL許可・ユニークを取得

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-09 | 2026-10-09 | 完了 | 実機`__all_tables__`に4列がそのまま存在すると判明。実機確認済み |

> アプローチ: 標準（`dr_sum_metadata.py`の既存クエリ拡張が中心で、新規画面や大幅な設計変更を伴わないためモック先行は不要。guides.md §1）
> リスク: あり（外部I/F — Dr.Sum JDBC接続のクエリ拡張。Phase 1に実機確認タスクを置く）

## 目的

[DD-033](../archived/DD/DD-033_テーブル定義パネルに精度スケールNULLユニークを追加.md)で画面側(テーブル定義パネル)とDBスキーマ(`columns.column_size`/`decimal_digits`/`is_nullable`/`is_unique`)は対応済みだが、値は現状デモデータのみ。実機Dr.Sumから`dr_sum_metadata.py`経由でこれらの値を取得できるようにし、実機接続時もテーブル定義パネルの「すべて表示」で実データが見られるようにする。

## 背景・課題

`dr_sum_metadata.py`の`fetch_columns()`は現在、以下のクエリで`table_name`/`column_name`/`column_type`のみ取得している(D-004で確認済みの仕様)。

```sql
SELECT table_name, column_name, column_type
FROM __all_tables__
WHERE assortment = 'column'
```

精度・スケール・NULL許可・ユニーク制約に相当する列が`__all_tables__`自体に存在するか（単に今は`SELECT`していないだけか）、あるいは別のシステムカタログ／JDBC標準API（`DatabaseMetaData.getColumns()`等）を使う必要があるかは未確認。これはDr.Sumの実機環境でしか検証できず、Claude側に実機接続手段が無いため、**Phase 1はユーザーによる実機調査が前提**になる（DD-002-2・DD-024と同じ進め方）。

「ユニーク」はJDBC標準の`getColumns()`には対応列が無く、`getIndexInfo()`（非ユニークインデックス情報）や主キー情報から別途判定する必要がある点も未確認要素。

## 検討内容

### 調査方針

1. `__all_tables__`（`assortment='column'`）を`SELECT *`で取得し、現在選択していない列に精度・スケール・NULL許可相当の情報が無いか確認する（最小変更で済む可能性が最も高い案）
2. 1で見つからない場合、JDBC標準の`DatabaseMetaData.getColumns()`（`jaydebeapi`経由で`conn.jconn.getMetaData()`を呼ぶ）を試す。`COLUMN_SIZE`/`DECIMAL_DIGITS`/`IS_NULLABLE`が返るかはDr.SumのJDBCドライバ実装依存で未確認
3. 「ユニーク」は1・2のいずれでも取得できない可能性が高い。取得できなければ本DDのスコープからユニークのみ除外し、別途見送りとする判断もあり得る（DD-024が型コード一部のみ対応したのと同じ「確認できた範囲だけ実装する」方針を踏襲）

### 誤った値を出すリスクへの対応

DD-021/DD-024の「対応表が未確認の値は誤変換せず、そのまま/未確認表示にする」という方針（D-004）を踏襲する。精度等が取得できない列は`NULL`のまま（画面側は既にDD-033で「-」表示に対応済み）とし、誤った値を表示しない。

### 調査結果（実機Dr.Sum、host=localhost、db=Test）

調査方針1（`__all_tables__`を`SELECT *`で取得）で解決した。ユーザーが実機に対して`--dump-raw`を実行した結果、`assortment='column'`の全列は以下の15列で、精度・スケール・NULL許可・ユニークに相当する列がそのまま存在することが判明した（JDBC標準APIへのフォールバックは不要だった）。

```
assortment, table_name, column_name, column_type, column_null, column_unique,
column_precision, column_scale, comments, view_select, view_connect,
update_time, update_user, dataupdate_time, dataupdate_user
```

実データ(26カラム)を突き合わせたところ、各テーブルの主キー的な列（`T_EC_CUSTOMER.order_id`等）だけが`column_null=1`かつ`column_unique=1`で、他の列はいずれも`column_null=0`・`column_unique=0`だった。`column_null`は列名だけ見ると「NULLを許可するか」に読めるが、主キー的な列がNULL許容になるのは通常のDB設計と矛盾するため、ユーザーに実際の意味を確認した結果「`column_null=1`はNOT NULL制約ありを意味する（0がNULL許容）」と判明した（D-004に反映）。

## 決定事項

- `dr_sum_metadata.py`の`fetch_columns()`クエリに`column_precision`/`column_scale`/`column_null`/`column_unique`を追加する
- `ColumnMeta`に`column_size`(←`column_precision`)/`decimal_digits`(←`column_scale`)/`is_nullable`(←`column_null`。0→`"YES"`、1→`"NO"`)/`is_unique`(←`column_unique`。1→`"YES"`、0→`"NO"`)を追加する。既存コードとの互換のため新4フィールドはデフォルト`None`
- JDBC標準`DatabaseMetaData.getColumns()`へのフォールバックは不要（調査方針1で解決したため）。「ユニーク」も`column_unique`列でそのまま取得できたため、見送りにはしない

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | `__all_tables__`(`assortment='column'`)の全列、またはJDBC `getColumns()`の結果から、精度・スケール・NULL許可に相当する列が特定できる(取得不可と判明した場合もその事実が記録される) | Phase 1 調査結果 |
| 2 | `python dr_sum_metadata.py --host ... --out dr_sum_columns.json`を実機に対して実行 → 出力JSONの各カラムに(取得できた範囲で)`column_size`/`decimal_digits`/`is_nullable`/`is_unique`が入る | Phase 2 動作確認 |
| 3 | 実機データで`main.py`→`web_viewer.py`を実行し、テーブル定義パネルの「すべて表示」で実機の値(取得できたもののみ)が表示される。取得できない項目は引き続き「-」表示になる(誤表示が無い) | Phase 2 動作確認(ユーザー実機確認) |
| 4 | `pytest`が全件パスする | Phase 2 🔬機械検証 |

## タスク一覧

### Phase 1: 実機カタログ調査（ユーザー作業）
- [x] `dr_sum_metadata.py`に調査用の一時モード`--dump-raw`を追加。`DrSumConnector.dump_raw_columns()`が`SELECT * FROM __all_tables__ WHERE assortment='column'`(列を絞らない)を実行し、`cursor.description`から列名一覧を取得、`{columns, total_rows, rows}`を`--raw-out`(既定`dr_sum_catalog_raw.json`)に出力する。Dr.SumのSQL方言でLIMIT構文が使えるか未確認なため、行数の絞り込みはPython側(`fetchall()`後)で行う(`--dump-raw-limit`、既定50)
- [x] ユーザーに実機Dr.Sum(host=localhost, db=Test)での実行を依頼し、結果を共有してもらった。`column_null`/`column_unique`/`column_precision`/`column_scale`の4列が存在することを確認
- [x] 調査結果を基に「検討内容」「決定事項」セクションを更新（`column_null`の意味はユーザーに別途確認: 1=NOT NULL制約あり、0=NULL許容）
- [x] 🔬 機械検証: `pytest tests/test_dr_sum_metadata.py` 全パス（12 passed。`dump_raw_columns`の新規テスト4件含む）

### Phase 2: 実装
- [x] `dr_sum_metadata.py`: `ColumnMeta`に`column_size`/`decimal_digits`/`is_nullable`/`is_unique`を追加(デフォルト`None`)。`fetch_columns()`のクエリに`column_precision`/`column_scale`/`column_null`/`column_unique`を追加し、`is_nullable`/`is_unique`へのマッピング(`column_null`は0→"YES"/1→"NO"、`column_unique`は1→"YES"/0→"NO")を実装
- [x] `tests/test_dr_sum_metadata.py`: 新フィールドのマッピングを確認するテストを2件追加(`column_null=1`→NOT NULL、`column_null=0`→NULL許容)。既存の`test_fetch_columns_assigns_ordinal_per_table_in_return_order`も新しい7列クエリ形式に更新
- [x] `doc/decisions.md` D-004を更新（実機確認済みの列名・`column_null`の解釈を追記）
- [x] `doc/spec/V001_カラムエイリアス使用状況ビューア.md`の「実機Dr.Sumからの取得は未対応」という記述(DD-033で追加)を実態に合わせて更新、変更ログにDD-034を追記
- [x] 🔬 機械検証: `pytest` 全パス（236 passed, 1 skipped）
- [x] ユーザー実機確認: 受け入れ基準#2・#3（下記エビデンス参照）

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（全4件達成。詳細は下記）
- [x] 😈 セルフレビュー1巡（ログ参照）
- [x] 🔬 全回帰1回（`pytest && bash scripts/doc-check.sh` → 236 passed, 1 skipped / doc-check OK）

## 受け入れ基準の確認結果

| # | 結果 |
|---|------|
| 1 | ✅ `__all_tables__`(`assortment='column'`)の全列から`column_precision`/`column_scale`/`column_null`/`column_unique`を特定。精度・スケール・ユニークは列名の意味も自明。NULL許可は`column_null`の意味をユーザーに確認し「1=NOT NULL制約あり」と判明 |
| 2 | ✅ 実機(host=localhost, db=Test)に対して`python dr_sum_metadata.py ... --out dr_sum_columns.json`を実行し、26カラム全件に`column_size`/`decimal_digits`/`is_nullable`/`is_unique`が入ることを確認(例: `order_id`→`10`/`0`/`"NO"`/`"YES"`) |
| 3 | ✅ 実機データで`match_aliases.py`→`web_viewer.py`を実行し、テーブル定義パネルの「すべて表示」で`T_EC_CUSTOMER`の実機値(`order_id`=NUMERIC/10/0/NOT NULL/○、他はNULL可/-)が正しく表示されることをClaude Browserで確認 |
| 4 | ✅ `pytest` 236 passed, 1 skipped |

## エビデンス

Claude Browser(`web-viewer-root`設定)で実機データ(`lineage.db`、DB=Test)のテーブル定義パネルを開き、`get_page_text`で以下の表示を確認(スクリーンショットのタイムアウトのためテキスト抽出で代替):

```
テーブル定義: T_EC_CUSTOMER
物理カラム名	データ型	精度	スケール	NULL	ユニーク
customer_name	VARCHAR	100	0	NULL可	-
order_date	DATE	0	0	NULL可	-
order_id	NUMERIC	10	0	NOT NULL	○
payment_method	VARCHAR	30	0	NULL可	-
...(他5列もNULL可/-)
```

## ログ

### 2026-10-09
- DD作成。[DD-033](../archived/DD/DD-033_テーブル定義パネルに精度スケールNULLユニークを追加.md)で画面・DBスキーマ対応済みだった精度・スケール・NULL許可・ユニークについて、実機Dr.Sumからの取得対応を別DDとして起票。Phase 1はClaude側に実機接続手段が無いため、ユーザーによるカタログ調査が前提
- `--dump-raw`モードを実装。`DrSumConnector.dump_raw_columns()`を追加し、`main()`に`--dump-raw`/`--dump-raw-limit`/`--raw-out`を追加。出力ファイル(`dr_sum_catalog_raw.json`)は環境固有の実データを含むため`.gitignore`に追加(`real_columns.json`と同じ扱い)。テスト4件追加、`pytest` 234 passed/1 skipped、`doc-check.sh` OK
- ユーザーが実機Dr.Sum(host=localhost, db=Test)に対して`main.py`を実行(DB名を`Administrator`→`Test`に訂正後に成功)、続けて`--dump-raw`も実行。`__all_tables__`の全15列が判明し、`column_precision`/`column_scale`/`column_null`/`column_unique`が存在することを確認
- `column_null`の意味(列名からは「NULL許可」に読めるが、主キー的な列が`column_null=1`かつ`column_unique=1`だった)をユーザーに確認し、「1=NOT NULL制約あり、0=NULL許容」と判明(AskUserQuestionで確認。誤った解釈のまま実装するリスクを避けるため、確信が持てるまで実装を保留した)
- Phase 2実装: `dr_sum_metadata.py`の`ColumnMeta`/`fetch_columns()`を拡張。実機(host=localhost, db=Test)に対して再度`dr_sum_metadata.py`→`match_aliases.py`を実行し`lineage.db`を再生成、`web_viewer.py`(ポート8793)でテーブル定義パネルの実機値表示を確認(`order_id`がNOT NULL/ユニークと正しく表示)
- `doc/decisions.md` D-004・`doc/spec/V001...`を更新。`pytest` 236 passed/1 skipped、`doc-check.sh` OK。受け入れ基準4件すべて達成のためステータスを「完了」に変更
- セルフレビュー所見: (1) `column_null`の解釈はこの実機(1テーブルにつき主キー的な列1つのみNOT NULL)から帰納した推測であり、ユーザーに別途確認して裏付けを取った上で実装した。他のDr.Sum環境で業務カラムにもNOT NULL制約が付いているケースがあれば、この推測が引き続き正しいかは未検証(他環境での再確認が望ましいが、確認時点の情報としては妥当と判断)。(2) `column_precision`/`column_scale`はDATE型等「桁数の概念が無い型」でも`0`が返る(NULLではない)。画面側は`0`をそのまま「0」と表示する(DD-033の「-」表示はnull/undefined時のみ)。意味的には違和感が残りうるが、取得した値をそのまま見せる(誤った推測で上書きしない)というD-004の方針に沿っており、実機確認でも実害は無かった。(3) `ColumnMeta`の新4フィールドはデフォルト`None`にしたため、既存の`fetch_columns_stub()`など呼び出し元への影響は無い(回帰テストで確認済み)
