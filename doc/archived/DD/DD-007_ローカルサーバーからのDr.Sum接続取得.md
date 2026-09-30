# DD-007: ローカルサーバーからのDr.Sum接続取得

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-09-30 | 2026-09-30 | 完了 | --connectフラグとフォームを実装。ユーザーの実機Dr.Sum環境でシナリオ1〜4すべて確認済み |

> アプローチ: E2E駆動（フォーム入力→取得ボタン→結果表示という「操作→結果」の検証が中心。guides.md §1 優先順3）
> リスク: あり（外部I/F・機密情報 — Dr.Sum実サーバーへの接続、接続パスワードを扱う）

## 目的

`main.py`をコマンドラインで手動実行する手間をなくし、`web_viewer.py`の画面から「Dr.Sumに接続」
ボタン一つで接続情報を入力するだけで`lineage.db`を作成・表示できるようにする。

## 背景・課題

DD-006で「実データをアップロードして見る」機能を追加したが、そもそも`lineage.db`を作るには
`python main.py --backup-dir ... --host ... --db ... --user ... --jdbc-jar ...`という
コマンドライン引数の多いコマンドを手動実行する必要があり、ユーザーから「面倒」との指摘があった。
なお、ブラウザから直接Dr.SumにJDBC接続することはブラウザの技術的制約上不可能（JDBCはJavaベースの
DB接続方式で、ブラウザのJavaScriptからは呼び出せない）であるため、ローカルで動くPythonサーバー
（`web_viewer.py`自身）が仲介する方式とすることをユーザーに説明し合意を得た。

## 検討内容

- **有効化方法**: 誤って本番Dr.Sumへの接続機能を有効化しないよう、新しい`--connect`フラグを
  明示的に指定した場合のみ機能を有効にする（`python web_viewer.py --connect`）。
- **フォーム項目**: `dr_sum_metadata.py`/`board_parser.py`が要求する既存パラメータそのまま
  （ホスト名・ポート・DB名・ユーザー名・パスワード・JDBCドライバーのパス・MotionBoardバックアップ
  フォルダのパス。ホワイトリストパス・類似度閾値は任意）。新しい接続方式を発明せず、既存の
  `main.py`引数と1対1対応させる。
- **実装方式**: `web_viewer.py`に`POST /api/connect`を追加し、`subprocess`で`main.py`を
  そのまま呼び出す（既存のパイプライン処理・エラーメッセージをそのまま再利用し、ロジックの
  二重実装を避ける）。
- **パスワードの扱い**: `main.py`には現状`--password`引数が無い（`dr_sum_metadata.py`は
  `DR_SUM_PASSWORD`環境変数をフォールバックとして読む設計）。`main.py`自体は変更せず、
  `/api/connect`ハンドラがsubprocess起動時の環境変数に`DR_SUM_PASSWORD`をセットする形で渡す
  （コマンドライン引数に平文で乗せない。プロセス一覧に表示されるリスクを避ける）。
- **実行時間**: JDBC接続・MotionBoard解析には時間がかかりうるため、`ThreadingHTTPServer`が
  リクエストごとにスレッドを立てる既存の仕組みを利用し、同期的に`subprocess.run`で待つ
  （非同期ジョブ化は本DDのスコープ外。プロトタイプとして許容する）。
- **エラー表示**: `main.py`の標準出力・標準エラー出力をそのまま画面に表示し、
  `dr_sum_metadata.py`が既に持っている分かりやすいエラーメッセージ（JDBCドライバー未検出等）を
  そのまま活かす。
- **STATIC_EXPORT・実データアップロードモードとの関係**: 静的エクスポート
  （`export_static.py`、`STATIC_EXPORT`）ではサーバーが存在しないため、この機能のボタン自体を
  非表示にする（`whitelistAddButton`と同じ理由）。DD-006の「実データをアップロードして見る」
  機能とは独立した別機能として共存させる。

## 決定事項

- `web_viewer.py`に`--connect`フラグを追加。指定時のみ`server.connect_enabled = True`。
- `POST /api/connect`: `connect_enabled`が`False`なら403で「--connectオプション付きで起動して
  ください」を返す。`True`なら、受け取ったJSONの各項目を`main.py`の対応引数に変換し、
  `subprocess.run([sys.executable, "main.py", ...], env={**os.environ, "DR_SUM_PASSWORD": password},
  capture_output=True, text=True)`を実行する。
- 成功時（returncode 0）: `{"ok": true}`を返す。フロントは`lineage.db`（既定パス、`main.py`の
  出力先と一致）を`load()`で再読み込みする。
- 失敗時: `main.py`の標準出力+標準エラー出力をそのまま`{"error": "..."}`で返し、画面に表示する。
- フロントに「Dr.Sumに接続」ボタンとフォーム（ホスト名・DB名・ユーザー名・パスワード
  [type=password]・JDBCドライバーパス・MotionBoardバックアップフォルダパス・ホワイトリストパス
  [任意]・類似度閾値[任意]）を追加する（ポートは`main.py`が現状受け取らないため対象外）。
  `STATIC_EXPORT`時は非表示にする。

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | `--connect`未指定でボタン操作 → 分かりやすいエラーが表示される | シナリオ1 |
| 2 | `--connect`指定でボタンをクリック → 接続情報フォームが表示される | シナリオ2 |
| 3 | 存在しないJDBCドライバーパスで取得 → `dr_sum_metadata.py`本来のエラーメッセージが表示される | シナリオ3 |
| 4 | （実機Dr.Sum環境がある場合）取得成功 → `lineage.db`が更新され画面に反映される | シナリオ4（アーカイブ後、ユーザーの実機Dr.Sum環境で確認済み。下記ログ参照） |

## タスク一覧

### Phase 1: E2Eシナリオ設計
- [x] 🎭 E2Eシナリオ設計: `DD-007/e2e-scenarios.md`に4シナリオを記載
- [x] 👀 ユーザーレビュー・合意（ゲート。合意後にPhase 2へ進む）

### Phase 2: `--connect`機能の実装
- [x] `web_viewer.py`: `--connect`フラグ・`POST /api/connect`ハンドラを実装
      （`connect_enabled`チェック、`main.py`のsubprocess呼び出し、`DR_SUM_PASSWORD`環境変数渡し、
      標準出力/エラーの返却）。`--db`未存在でも`--connect`時は起動を許可するよう`main()`を調整し、
      `load()`側もAPIがエラーレスポンスを返した場合に空配列/空オブジェクトへフォールバックするよう修正
- [x] `web_viewer.py`: 「Dr.Sumに接続」ボタン・フォームをフロントに実装（`STATIC_EXPORT`時は非表示）
- [x] 🔬 機械検証: `py -m pytest` 全件パス（141件、回帰なし確認。`export_static.py`の`load()`
      置換対象文字列も新実装に合わせて更新）
- [x] 🔬 機械検証: Claudeの組み込みブラウザでシナリオ1〜3を操作し確認
      （シナリオ4は実機Dr.Sum環境がないためコードレビューのみ）

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（基準4は実機未検証である旨を明記）
- [x] 😈 セルフレビュー1巡（特にパスワードの取り扱いを重点的に確認。`--password`引数には含めず
      環境変数のみで渡していること、`main.py`が印字するコマンドログにパスワードが出ないことを
      実機ログで確認。`subprocess.run`はリスト引数[shell=False]のためコマンドインジェクションなし）
- [x] 🔬 全回帰1回: `py -m pytest && bash scripts/doc-check.sh` → 全パス

## ログ

### 2026-09-30
- DD作成。ユーザーから「実データ取得のコマンド入力が面倒。ボタンから取得できるようにしたい」
  との要望。ブラウザから直接Dr.SumにJDBC接続することは技術的に不可能である旨を説明し、
  ローカルサーバー（`web_viewer.py`自身）経由での接続方式でユーザーの合意を得た
- E2Eシナリオ4件を作成。シナリオ4（実接続成功パス）は本DD作業環境に実際のDr.Sumサーバーが
  ないため実機検証できないことをシナリオに明記
- ユーザーが合意し、Phase 2着手。フォーム項目からmain.pyが受け取らない「ポート」を削除し、
  既存引数と1対1対応させる方針を徹底
- `web_viewer.py`に`--connect`フラグ・`POST /api/connect`・接続フォームUIを実装。
  `main.py`をsubprocessで呼び出し、パスワードは環境変数`DR_SUM_PASSWORD`経由で渡す設計とした
- 実機検証: `--connect`なしでボタン操作→「--connectオプション付きで起動してください」エラーを
  確認（シナリオ1）。`--connect`ありでボタン操作→フォーム表示を確認（シナリオ2）。存在しない
  JDBCドライバーパスで取得→`dr_sum_metadata.py`本来のエラーメッセージ
  「JDBCドライバーのjarファイルが見つかりません」がそのまま画面に表示されることを確認
  （シナリオ3。パスワードがコマンドログに含まれないことも同時に確認）
- 静的エクスポート版で「Dr.Sumに接続」ボタンが正しく非表示になることも確認
- 全回帰実施: `pytest`141件パス・1件skip、`doc-check.sh` OK。受け入れ基準1〜3達成、
  基準4は実機Dr.Sum環境がないため未検証（コードレビューのみ、ユーザー実環境での最終確認が必要）
- DD完了。DD-INDEX.mdを再生成

### 2026-09-30（アーカイブ後の追補: 実機Dr.Sum環境での検証とバグ修正）
- ユーザーが実際のDr.Sum環境で`--connect`を試行し、以下2件の不具合・環境未整備を発見。
  いずれもコードのバグではなくJava/JDBC周りの実行環境要因だったが、1件は本ツール側の
  バグ（`web_viewer.py`起動時のクラッシュ）につながったため修正した
  1. `No JVM shared library file (jvm.dll) found`エラー → `JAVA_HOME`が未設定だったため。
     MotionBoard同梱のJRE（`C:\MotionBoard64\system\jre`）を`JAVA_HOME`に設定して解消。
     設定直後は実行中のターミナルに反映されないため、ターミナルを開き直す必要があった
  2. **本ツールのバグ**: JAVA_HOME未設定の状態で`--connect`起動→ページの初回読み込みで
     `/api/columns`等が`sqlite3.connect()`を呼び、まだ存在しない`lineage.db`を空ファイルとして
     自動生成してしまっていた。その空ファイルが残った状態で次回`--connect`起動すると、
     `main()`の起動時チェック（`SELECT COUNT(*) FROM columns`）が「no such table: columns」で
     未捕捉の例外を出し、サーバー自体がクラッシュして起動できなくなっていた
     → 修正: `main()`の起動時チェックを`try/except sqlite3.OperationalError`で保護し、
     `do_GET`に`_require_db()`ガードを追加して、`lineage.db`が存在しない間は
     `/api/columns`等がsqlite3.connect()を呼ばないようにした（空ファイルの自動生成自体を防止）
  3. `Class jp.co.dw_sapporo.JDBC.JDBCDriver is not found`エラー → `--jdbc-jar`にjarファイルの
     入っている**フォルダ**を指定していたため（`dwodsjd4.jar`自体を指定する必要があった）。
     コード側の問題ではなく入力値の問題だったため、README側にこの注意点を追記した
  4. 上記修正後、ユーザーの実機Dr.Sum環境で接続取得に成功。画面にDr.Sum実データが表示される
     ことを確認（受け入れ基準4、達成）
- 対応するドキュメント更新: `README.md`に「事前準備（Dr.Sumへの実接続に必要なもの）」節を新設し、
  JAVA_HOME設定・JDBCドライバーのパス（フォルダではなくjarファイル自体）を明記。「結果を
  ブラウザで見る」節にDD-003/004（ホワイトリストのボタン編集）・DD-006（実データアップロード）・
  DD-007（`--connect`）の使い方も追記した（DD-003〜007はいずれもREADME未反映のままだったため、
  まとめて追いついた）
- 全回帰再実施: `pytest`141件パス・1件skip、`doc-check.sh` OK
