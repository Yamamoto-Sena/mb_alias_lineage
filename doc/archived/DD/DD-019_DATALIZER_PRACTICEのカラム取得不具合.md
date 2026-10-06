# DD-019: DATALIZER_PRACTICEのカラム取得不具合

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-05 | 2026-10-06 | 見送り | DB名とテーブル名の混同による誤解と判明。`fetch_columns()`自体にバグなし。ユーザー了承済み |

> アプローチ: バグ修正・フルパス（原因が複雑/未確定で実機確認が必要なため）
> リスク: なし（外部I/F読み取りクエリの修正のみ。書き込み・認証には触れない）
> エビデンス: テスト出力（DBクエリ結果の不整合のため）

## 概要

| Bug# | 概要 | 重要度 |
|------|------|--------|
| 001 | Dr.SumのDB名`Test`に接続し`DATALIZER_PRACTICE`テーブルを取得すると、カラムが足りない/多い状態で表示される | HIGH |

## 原因分析

`dr_sum_metadata.py`の`fetch_columns()`（L98-113）は`__all_tables__`を
`assortment='column'`で絞り込むのみで、`ORDER BY`無しの返却順を列定義順と仮定している
（[DD-002-2](../archived/DD/DD-002-2_Dr.Sum実環境対応.md)で3テーブルのみ実機確認済み、
`DATALIZER_PRACTICE`は未確認）。また、テーブル種別（通常テーブル/ビュー/
ディストリビューター/マルチビュー）を区別していないため、`DATALIZER_PRACTICE`が
これらの特殊種別だった場合に想定外の行数で返る可能性がある。実機確認が無いと
確定できないため、Phase 0でユーザーに診断SQLの実行を依頼する。

> 詳細: [cause-analysis.md](DD-019/cause-analysis.md)

## 修正方針

Phase 0の実機確認結果を見てから決定する（現時点では未定）。

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `dr_sum_metadata.py` | Phase 0の結果に応じて`fetch_columns()`のクエリ/絞り込み条件を修正 |

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | 実機でDB名`Test`に接続し`DATALIZER_PRACTICE`を取得 → 実際のテーブル定義と一致するカラム数・順序・列名が返る | Phase 2 verification.md（実機再実行） |
| 2 | 既存3テーブル（`T_EC_CUSTOMER`等）の取得結果に回帰がない | `pytest tests/test_dr_sum_metadata.py` |

## タスク一覧

### Phase 0: 調査・再現確認・修正前エビデンス

**調査:**
- [ ] コードベース調査 — `dr_sum_metadata.py`の`fetch_columns()`と`__all_tables__`依存箇所の洗い出し（済・上記「原因分析」参照）
- [x] 原因分析を添付ファイル（`DD-019/cause-analysis.md`）に記載

**実機診断（ユーザー依頼）:**
- [ ] 実機のDr.Sum（DB名`Test`）で以下を実行し、結果をDDログに追記する:
  1. `SELECT COUNT(*) FROM __all_tables__ WHERE assortment='column' AND table_name='DATALIZER_PRACTICE'`
  2. `SELECT * FROM __all_tables__ WHERE table_name='DATALIZER_PRACTICE' ORDER BY assortment`（全件・全列を目視確認）
  3. `DATALIZER_PRACTICE`の実際の列定義（列数・列名・順序）をDr.Sum管理画面またはSQL Executorで確認
  4. 1〜3の結果と、実際にツールが出力した`dr_sum_columns.json`（または画面表示）の列一覧を比較し、どの列が余分/不足しているかを特定する
- [ ] 📝 バグレポート作成（`DD-019/bug-report.md`） — 3・4の比較結果を記載
- [ ] 👀 **ユーザーレビュー** — バグ再現と原因分析の合意（ゲート）

### Phase 1: コード修正・テスト
- [ ] 原因箇所のコード修正（Phase 0の結果に応じて具体化）
- [ ] 同根パターンの横展開確認（他の`assortment`/テーブル種別前提のコードがないかgrep確認）
- [ ] `tests/test_dr_sum_metadata.py` にテスト追加・更新
- [ ] 🔬 機械検証: `pytest tests/test_dr_sum_metadata.py` → 全件パス

### Phase 2: 修正後エビデンス・ドキュメント整備
- [ ] 実機で`python dr_sum_metadata.py --host ... --db Test --user ... --jdbc-jar ...`を再実行し、`DATALIZER_PRACTICE`のカラムが正しく取得されることを確認
- [ ] 📝 検証ドキュメント作成（`DD-019/verification.md`）
- [ ] `doc/archived/DD/DD-002-2_Dr.Sum実環境対応.md`の既知の制約欄に、本件の訂正内容を反映（該当する場合）
- [ ] 🔬 機械検証（全回帰）: `pytest` → 全パス

### 完了前チェック
- [ ] 受け入れ基準を1項目ずつ照合
- [ ] 😈 セルフレビュー1巡
- [ ] 🔬 全回帰1回

## ログ

### 2026-10-05
- DD作成。ユーザーからDB名`Test`接続後の`DATALIZER_PRACTICE`取得でカラム数不一致（足りない/多い）の報告を受け起票
- AskUserQuestionで症状を確認: 「カラムが足りない/多い」（列順序の誤り・他テーブル混在・列名/型誤りは否定）

### 2026-10-06
- 別件[DD-025](../archived/DD/DD-025_DB名指定接続で無関係なDBのテーブルまで取得される不具合.md)
  （ビューアに「DB不一致の可能性」バッジを追加）の実機確認中、ユーザーからDB名
  `DATALIZER_PRACTICE`接続時に同バッジが大量に付く報告があった。AskUserQuestionで
  バッジが付いた行のテーブル名を確認したところ、`DATALIZER_PRACTICE`**自身**の名前に
  なっていることが判明。これは「`DATALIZER_PRACTICE`自身のエイリアスの多くが、取得された
  物理カラム一覧と一致していない」ことを意味し、本DDが追っている「カラムが足りない/多い」
  症状の規模が、当初の想定より大きい可能性を示す追加の間接的エビデンスと判断。
  Phase 0の実機診断（`__all_tables__`の直接クエリ）を進める方針で合意
- 実機診断の結果: DB名`Test`で接続した状態で`SELECT COUNT(*) FROM __all_tables__ WHERE
  assortment='column' AND table_name='DATALIZER_PRACTICE'` → **0**、`SELECT * FROM
  __all_tables__ WHERE table_name='DATALIZER_PRACTICE'`も**0行**。Dr.Sum管理画面の
  テーブルプロパティとして提示されたのは`DATALIZER_PRACTICE`ではなく`販売実績_練習用`
  だった
- ユーザーに確認したところ「`DATALIZER`はデータベース名」との回答。さらに
  `scripts/diag_find_datasource.py`（DD-019診断用に新規作成。`board_parser.py`の
  XML/ZIP/.fs-file走査ロジックを再利用し、バックアップフォルダ全体から`<DataSource>`
  要素を横断検索するスクリプト）でMotionBoardバックアップフォルダ全体を検索した結果、
  `srcName="DATALIZER_PRACTICE"`というボードは1件も存在せず、見つかった全ての
  `<DataSource>`は`srcName="販売実績_練習用"`で、`DATALIZER_PRACTICE`は`src`/`dispSrc`
  属性（`{DB名}/{テーブル名}`形式。例: `src="DATALIZER_PRACTICE/販売実績_練習用"`）の
  DB名部分としてのみ出現することを確認
- ビューアでDB名`DATALIZER_PRACTICE`に接続した実際の画面をユーザーに確認してもらったところ、
  「DB不一致の可能性」バッジが付いていたのは`T_STORE_KPI`・`T_EC_CUSTOMER`（いずれも
  DD-002-2で確認済みの`Test`DBのテーブル）で、`DATALIZER_PRACTICE`自身のテーブル
  `販売実績_練習用`にはバッジが付いていなかった
- **結論**: `DATALIZER_PRACTICE`という名前のテーブルは存在せず、DB名である。
  `--backup-dir`に`Test`用ボードと`DATALIZER_PRACTICE`用ボードが混在しているため、
  どちらのDBに接続しても「接続していない方のDB用ボード」がDD-025のバッジで
  正しく検出されていただけだった。元々の「カラムが足りない/多い」という報告は、
  DB名とテーブル名の混同、およびこの混在状態を見た際の誤認と判断する。
  `dr_sum_metadata.py`の`fetch_columns()`自体にバグはない
- ユーザーの了承を得て、本DDを「見送り」としてクローズする
