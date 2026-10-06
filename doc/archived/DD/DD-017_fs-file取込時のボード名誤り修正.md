# DD-017: fs-file取込時のボード名誤り修正

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-05 | 2026-10-05 | 完了 | board_name_overrideで.fs-fileフォルダ名を優先するよう修正。pytest 142件パス |

> アプローチ: バグ修正・ライトパス（原因箇所特定済み・単一バグ・`board_parser.py`のみの修正で画面コードは触らない・既存pytestで検証完結するため）
> エビデンス: テスト出力（`pytest`。既存`TestNestedZipAndFsFileDiscovery`にboard_nameのアサーションを追加）
> リスク: なし（認可・認証／DBスキーマ／外部I/F／機密情報・決済のいずれにも該当しない。`lineage.db`はスキーマ変更なしで毎回再生成されるため移行作業も不要）

## 概要

| Bug# | 概要 | 重要度 |
|------|------|--------|
| 1 | MotionBoard内部ストア(`<ボード名>.fs-file/fs-snap/snap_*`)を自動検出モードで取り込むと、ビューアの「使用ボード」欄に実際の画面名ではなく、そのデータソース自体の名前（`<DataSource name="...">`の`name`属性）が入ってしまう |

## 原因分析

`auto_parse_all`は`.fs-file`フォルダ名(例: `受注一覧.fs-file`)を見つけて中のスナップショットを解析するが、本来のボード名である`fs_file_dir.name`はコンソール出力のラベルとしてしか使われず、`_parse_zip_bytes`→`auto_parse_xml`→`_parse_drsum_datasource`のどこにも渡されない([board_parser.py:663-670](../../board_parser.py#L663-L670))。

`_parse_drsum_datasource`は`board_name = root.attrib.get("name", "").strip() or table_name`([board_parser.py:228](../../board_parser.py#L228))で`board_name`を決めており、これは`<DataSource>`要素の`name`属性＝**データソース自体の名前**で、画面(ボード)名とは別物。DD-002-3の実機確認記録にも同じズレが残っている([doc/archived/DD/DD-002-3_MotionBoard解析精度向上.md:56](../archived/DD/DD-002-3_MotionBoard解析精度向上.md#L56)): 実際のボード名`Test1_EC_SALES`に対し、データソース名は未命名の既定値「新規データソース」。データソースが未命名のまま複数ボードで使われていると、ビューア上で別々のボードが同じ「新規データソース」に潰れて区別できなくなる。

汎用ヒューリスティック経路(`auto_parse_xml`の`find_ancestor_name`、`auto_parse_json`の同名関数)も同様に、`.fs-file`内のXML/JSON自身の属性から`board_name`を推測しており、正しい保証がない。

## 修正方針

`auto_parse_all`が`.fs-file`フォルダを解析する際、そのフォルダ名(拡張子`.fs-file`を除いた部分)を「確定済みの本当のボード名」として`_parse_zip_bytes`→`auto_parse_xml`/`auto_parse_json`に伝播させ、各関数が返すレコードの`board_name`を問答無用で上書きする。ファイル内部のヒューリスティックな推測(データソース名・属性探索)より、フォルダ構造から確実に分かる情報を優先する。

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `board_parser.py` | `auto_parse_xml`/`auto_parse_json`/`_parse_zip_bytes`に`board_name_override`引数を追加し、指定時は返却レコードの`board_name`を上書きする。`auto_parse_all`の`fs_file_dirs`ループで`fs_file_dir.stem`(`.fs-file`を除いたボード名)を`board_name_override`として渡す |
| `tests/test_board_parser.py` | `TestNestedZipAndFsFileDiscovery`に、`.fs-file`経由で取り込んだレコードの`board_name`がフォルダ名と一致することを確認するテストを追加 |

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | `<本当のボード名>.fs-file/fs-snap/`配下に、`name`属性が別の値(データソース名)の`<DataSource type="drsum">`を含むスナップショットを置いて`auto_parse_all`を実行する → 返却される`AliasRecord.board_name`がフォルダ名(`<本当のボード名>`)と一致し、データソースの`name`属性の値にはならない | `pytest tests/test_board_parser.py::TestNestedZipAndFsFileDiscovery` |
| 2 | 既存の`.fs-file`以外の経路(標準XML/JSON/ZIP単体ファイル)の取り込み結果に変化がない | `pytest`全体 → 既存件数のまま全パス |

## タスク一覧

### Phase 1: コード修正・テスト
- [x] `board_parser.py`: `_parse_zip_bytes`/`auto_parse_xml`/`auto_parse_json`に`board_name_override`引数を追加し、戻り値の`board_name`を上書きする共通処理(`_apply_board_name_override`)を入れる
- [x] `board_parser.py`: `auto_parse_all`の`fs_file_dirs`ループで`fs_file_dir.stem`を`board_name_override`として渡す
- [x] 同根パターンの横展開確認: `_auto_parse_zip`(標準ZIP単体ファイル向け)・`_parse_one_file`(`--watch`差分取り込み向け)に`.fs-file`参照が無いことをgrepで確認。対象外で問題ないことを確認した
- [x] `tests/test_board_parser.py`: `TestNestedZipAndFsFileDiscovery`に`test_fs_file_board_name_uses_folder_name_not_datasource_name`を追加(データソース名「テストデータソース」ではなくフォルダ名「MyBoard」になることを確認)
- [x] 🔬 機械検証: `pytest` → 142 passed, 1 skipped(新規テスト1件追加・全パス)

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（#1・#2とも達成）
- [x] 😈 セルフレビュー1巡
- [x] 🔬 全回帰1回: `pytest && bash scripts/doc-check.sh` → 全パス

## ログ

### 2026-10-05
- ユーザーから「使用ボードの欄がデータソース名になっているのか」という実機での疑問を受けて調査。`.fs-file`取込経路で本当のボード名(フォルダ名)が一切使われず、データソース定義XMLの`name`属性(データソース自身の名前)がそのまま`board_name`になっていることを特定。ユーザーの「使用データソース」実機確認時の報告とDD-002-3の記録(`Test1_EC_SALES`対「新規データソース」)で裏付けを取り、DD-017として起票
- ユーザーが「はい、進めてください」と合意したため、ライトパスでPhase 0(再現キャプチャ等)を省略しPhase 1から直接着手
- `_apply_board_name_override`ヘルパーを追加し、`auto_parse_xml`/`auto_parse_json`/`_parse_zip_bytes`に`board_name_override`引数を伝播。`auto_parse_all`の`fs_file_dirs`ループで`fs_file_dir.stem`(`.fs-file`を除いたフォルダ名)を渡すよう変更
- 同根パターン確認: `_auto_parse_zip`(標準ZIP単体ファイル)・`_parse_one_file`(`--watch`差分取り込み)はどちらも`.fs-file`を扱わない独立経路であり、今回のバグの対象外であることをgrepで確認(修正不要)
- `tests/test_board_parser.py`に新規テストを追加し、`.fs-file`フォルダ名("MyBoard")が`board_name`になり、データソース定義の`name`属性("テストデータソース")にはならないことを確認
- 🔬 全回帰: `pytest` → 142 passed, 1 skipped(新規テスト含め全パス)、`bash scripts/doc-check.sh` → OK
- 受け入れ基準#1・#2とも達成。画面側(`web_viewer.py`)・V001仕様書はデータの中身が変わるだけで項目追加等は無いため更新不要と判断(影響はデータ取り込みロジックのみ)
