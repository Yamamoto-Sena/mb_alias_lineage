# DD-026: 所属DB判定による他DBボードの除外とサマリ表示

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-06 | 2026-10-06 | 完了 | 実装・pytest・デモ環境に加え、実際の環境（複数DB混在のバックアップ）でも動作確認済み |

> アプローチ: 標準（既存の`DataSource`解析・SQLite書き込みロジックの拡張のため）
> リスク: あり（DBスキーマ変更 — `lineage.db`に新規テーブル追加。ただし`match_aliases.py`
  実行のたびに`DROP→CREATE`で作り直す設計のため、既存データへの移行は発生しない）

## 目的

DD-025で追加した「DB不一致の可能性」バッジが、`--backup-dir`に複数DB分のボードが
混在する運用では常に大量にヒットし、意味をなさなくなる問題を解消する。ボード定義に
既に書かれている「所属DB名」を使い、接続中のDBと違うことが**確定している**ものは
一覧から完全に除外し、残った「不一致」を本当に調べる価値があるものだけに絞り込む。

## 背景・課題

DD-019の調査過程で判明した事実:
- `<DataSource type="drsum">`の`src`属性は`{DB名}/{テーブル名}`形式（例:
  `src="DATALIZER_PRACTICE/販売実績_練習用"`）で、**所属DB名を含んでいる**
  （[board_parser.py:234](../../board_parser.py:234)の`_parse_drsum_datasource`は
  現在`srcName`〈テーブル名部分〉しか読んでおらず、`src`のDB名部分は未使用）
- ユーザーの実際の運用では、`--backup-dir`に`Test`用ボードと`DATALIZER_PRACTICE`用
  ボードが混在しており、どちらのDBに接続しても「接続していない方のDB用ボード」が
  大量に「DB不一致の可能性」として表示され、ユーザーから「意味をなしていない」との指摘

## 検討内容

- 所属DBが「分かっているのに接続中DBと違う」ケースと、「所属DB不明、または接続中DBのはず
  なのに物理カラムと一致しない」ケースを区別する必要がある。前者は確定的に無関係なので
  除外してよいが、後者はDD-025が本来捉えたかった「ボード参照切れ」等の兆候なので残す
- 除外しても情報を完全に捨てると「本当に除外されただけか、見えなくなっただけか」が
  分からなくなるため、件数と内容を画面下部にサマリ表示する（ユーザー合意）
- `lineage.db`は`match_aliases.py`実行のたびに`DROP→CREATE`で作り直す設計（既存の
  `db_schema.sql`冒頭コメント参照）のため、新規テーブル追加でも過去データとの
  整合性問題は発生しない

## 決定事項

- `board_parser.py`の`AliasRecord`に`source_db`フィールドを追加。`_parse_drsum_datasource`で
  `src`属性を`{DB名}/{テーブル名}`としてパースし、DB名部分を格納する（他の抽出経路
  〈汎用ヒューリスティック・手動モード〉は所属DB情報を持たないため空文字のまま）
- `main.py`は接続先DB名（既存の`args.db`）を`match_aliases.py`に新規オプション
  `--connected-db`で渡す（`match_aliases.py`の既存`--db`はSQLite出力パスの意味で
  使用中のため、別名にする）
- `match_aliases.py`の`build_db()`: エイリアスの`source_db`が非空かつ`--connected-db`と
  一致しない場合、`columns`/`aliases`への登録を完全にスキップし、代わりに
  `excluded_aliases`テーブル（新規）に記録する。`source_db`が空、または`--connected-db`と
  一致する場合は、現行どおり一致判定→不一致なら`table_type='(不明)'`で仮登録
- `db_schema.sql`に`excluded_aliases`テーブルを追加（他テーブルと同様、実行のたびに
  `DROP→CREATE`）
- `web_viewer.py`に除外一覧を返す`/api/excluded_aliases`（サーバーモード）を追加し、
  JS版（アップロードモード）・`export_static.py`（埋め込みデータ）にも同じデータを渡す
- ビューア画面の最下部に「他DBのボードのため除外（N件）」セクションを追加し、
  所属DB名・テーブル名・物理カラム名・表示名・ボード名の一覧を表示する

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | 所属DBが分かっていて接続中DBと異なるエイリアスがある状態で`match_aliases.py`を実行 → メイン一覧（`columns`/`aliases`）には登録されず、`excluded_aliases`に記録される | `pytest tests/test_match_aliases.py` |
| 2 | 所属DB不明、または接続中DBのはずなのに物理カラムと一致しないエイリアス → 従来どおり`table_type='(不明)'`で登録され、「DB不一致の可能性」バッジが付く | `pytest tests/test_match_aliases.py` / `pytest tests/test_web_viewer.py` |
| 3 | ビューア画面の最下部に「他DBのボードのため除外」セクションが表示され、件数と一覧が確認できる | ブラウザ実機確認 |
| 4 | `--connected-db`未指定（`--demo`等、既存の呼び出し）時は、除外ロジックが働かず従来どおりの挙動になる | `pytest`（全回帰） |

## タスク一覧

### Phase 1: データ抽出・書き込み層
- [x] `board_parser.py`: `AliasRecord`に`source_db: str = ""`を追加し、
      `_parse_drsum_datasource`で`src`属性からDB名部分を抽出して格納
- [x] `db_schema.sql`: `excluded_aliases`テーブルを追加（`DROP→CREATE`に含める）
- [x] `match_aliases.py`: `--connected-db`オプションを追加し、`build_db()`に
      所属DB判定による除外ロジックを実装（`excluded_aliases`への記録を含む）
- [x] `main.py`: `match_cmd`に`--connected-db args.db`を追加（`--stub`では
      接続先DBが無いため渡さない。`--demo`は早期returnのためそもそも対象外）
- [x] `tests/test_match_aliases.py`・`tests/test_board_parser.py`・`tests/test_main.py`に
      テスト追加
- [x] 🔬 機械検証: `pytest tests/test_match_aliases.py tests/test_board_parser.py
      tests/test_main.py` → 全件パス（117 passed）

### Phase 2: 表示層・エビデンス
- [x] `web_viewer.py`: `fetch_excluded_aliases()`（Python）・`jsFetchExcludedAliases()`
      （JS、アップロードモード）・`/api/excluded_aliases`エンドポイントを追加
- [x] `export_static.py`: 除外一覧も埋め込みデータとして渡す（`load()`文字列置換も
      5引数版に追従させ、既存テストで置換失敗がないことを確認）
- [x] ビューア画面最下部に除外一覧セクションを追加（件数・DB名・テーブル名・物理カラム名・
      表示名・ボード名）
- [x] `demo_data`に他DB向けボード（`<DataSource type="drsum" src="OtherDB/...">`）を
      一時的に追加し、`board_parser.py`→`match_aliases.py --connected-db Test`→
      ブラウザ実機確認を実施。「他DBのボードのため除外（1件）」セクションに正しく
      表示され、メイン一覧には含まれないことを確認（確認後、注入データは
      `python main.py --demo`で元に戻し、スクラッチファイルも削除済み）
- [x] `tests/test_web_viewer.py`・`tests/test_export_static.py`にテスト追加
- [x] 🔬 機械検証: `pytest tests/test_web_viewer.py tests/test_export_static.py` →
      全件パス（37 passed）

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合 — 1〜4とも上記の実機確認・pytestで達成
- [x] 😈 セルフレビュー1巡 — `fetch_excluded_aliases`/`jsFetchExcludedAliases`で
      `excluded_aliases`テーブル不在時に例外を握りつぶして空配列を返す実装にしたため、
      DD-026より前に生成された`lineage.db`でも画面が壊れないことを確認済み（テストにも
      反映）。`db_schema.sql`はDROP→CREATE方式のため、過去データの移行は元々発生しない設計
- [x] 🔬 全回帰1回: `pytest` → 159 passed, 1 skipped

## ログ

### 2026-10-06
- DD作成。DD-019の調査過程で`<DataSource>`の`src`属性に所属DB名が含まれることが判明し、
  ユーザーから「所属DBが分かっているのに不一致として表示するメリットがない」との指摘を
  受け、所属DB判定による除外＋画面下部サマリ表示として起票。ユーザーの要望により、
  除外時も件数と内容を画面下部にまとめて表示する方針で合意
- Phase 1実装: `board_parser.py`の`AliasRecord`に`source_db`を追加し`src`属性
  （`{DB名}/{テーブル名}`形式）からDB名部分を抽出。`db_schema.sql`に`excluded_aliases`
  テーブルを追加。`match_aliases.py`に`--connected-db`オプションと除外ロジックを実装
  （`_normalize_text`で全角半角/大小文字を正規化して比較、既存の表記ゆれ対策と同じ方式に
  揃えた）。`main.py`の実接続時フローから`--connected-db`を渡すよう変更
  （`--stub`は接続先DBが無いため対象外）
- Phase 2実装: `web_viewer.py`にサーバーモード用`fetch_excluded_aliases()`・
  アップロードモード用`jsFetchExcludedAliases()`・`/api/excluded_aliases`エンドポイントを
  追加。画面最下部に「他DBのボードのため除外（N件）」セクションを追加。`export_static.py`
  は`renderAll()`呼び出しの引数が5個に増えたため、文字列置換対象のJSコードも合わせて
  更新（既存テスト`assert "fetch(...)" not in html`が置換失敗の検知ネットとして機能）
- `demo_data`に他DB向けのダミーボード（`<DataSource type="drsum"
  src="OtherDB/T_OTHER_SALES">`）を一時的に追加し、`board_parser.py`→
  `match_aliases.py --connected-db Test`→ブラウザ実機（`web-viewer-demo`プレビュー）で
  一連の動作を確認。「他DBのボードのため除外（1件）」セクションに所属DB・テーブル名・
  物理カラム名・表示名・ボード名が正しく表示され、メイン一覧には含まれないことを確認。
  確認後、`demo_data/lineage.db`は`python main.py --demo`で元の状態に復元し、注入に使った
  スクラッチファイルも削除済み
- `pytest`（全件）→ 159 passed, 1 skipped。既存機能への回帰なしを確認
- `doc/spec/V001_カラムエイリアス使用状況ビューア.md`に新UI要素・API・DBテーブルを反映
- ステータスを「確認待ち」に更新。ユーザーの実際の環境（複数DB混在のバックアップ
  フォルダ）での最終確認を待って「完了」とする

### 2026-10-06（続き）
- ユーザーが実際の環境で動作確認し、問題なしとの報告を受けた。ステータスを「完了」に更新
