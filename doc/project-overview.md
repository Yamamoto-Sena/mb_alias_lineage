# プロジェクト概要: mb_alias_lineage

> 新規参加者がまず読む入口。スコープ・環境・方針のみを扱う。使い方は
> [`doc/guide/user-guide.md`](guide/user-guide.md)、コマンド仕様は[`README.md`](../README.md)、
> 画面仕様は[`doc/spec/V001_カラムエイリアス使用状況ビューア.md`](spec/V001_カラムエイリアス使用状況ビューア.md)、
> 変更の経緯は[`doc/DD/`](DD/)・[`doc/archived/DD/`](archived/DD/)、長寿命の決定・落とし穴は
> [`doc/decisions.md`](decisions.md)・[`doc/engineering-patterns.md`](engineering-patterns.md)を参照。

## スコープ

**やること**: Dr.Sum上の物理カラムが、MotionBoard上でどんな表示名（エイリアス）で
どのボードに使われているかを突き合わせ、表記ゆれ（1対多・多対1・物理名直接使用・
孤立項目・類似度候補の5パターン）を自動検出してブラウザで一覧確認できるようにする。

**やらないこと**:
- Dr.Sum/MotionBoardのデータそのものの修正・移行（本ツールは可視化のみ。表示名の
  修正はDr.Sum/MotionBoard側で人が行う）
- 認証・アクセス制御（D-005参照。localhost限定の単一ユーザー想定ツール）
- 検出結果の永続的な履歴管理（`lineage.db`はスナップショット。D-001参照）
- 通知連携（Slack/メール等）。送信先未確定のため見送り中（DD-002-5）

## 対象ユーザー

- データ基盤担当者・MotionBoard運用者（検出結果の確認・ホワイトリスト管理）
- 社内の確認者（Pythonを実行できない人。`export_static.py`が生成する静的HTMLを受け取って閲覧するだけ）

## 技術スタック・実行環境

| 項目 | 内容 |
|------|------|
| 言語 | Python 3（標準ライブラリ中心。追加依存は最小限に抑える方針。D-003参照） |
| DB | SQLite（`lineage.db`、スキーマは`db_schema.sql`） |
| フロントエンド | 静的HTML/CSS/素のJavaScript（フレームワーク不使用）。`web_viewer.py`が`http.server`ベースの軽量サーバーで配信 |
| Dr.Sum接続 | JDBC（`JayDeBeApi`/`JPype1`。要Java/JDBCドライバー。D-004参照） |
| ブラウザ内評価モード | sql.js（SQLiteのWebAssembly版。CDN: cdnjs.cloudflare.com。DD-006） |
| テスト | pytest（`pytest.ini`で`tests/`配下を対象化。141件 + JS移植の回帰テスト1件[Node要・CI限定]） |
| CI | GitHub Actions（`.github/workflows/ci.yml`。push/PR時に`pytest`を自動実行） |
| 実行場所 | ローカル実行のみ。`web_viewer.py`はlocalhost限定で待受け、外部公開しない（D-005） |

## 全体構成（パイプライン）

```
① dr_sum_metadata.py  … Dr.SumからJDBC経由でテーブル・カラム一覧を取得
② board_parser.py     … MotionBoardボード定義ファイルを自動検出パース
③ match_aliases.py    … ①②を突き合わせ、表記ゆれを判定してlineage.dbに保存
④ web_viewer.py / export_static.py … ブラウザで確認 / 静的HTMLに書き出し
```

`main.py`が①〜③を1コマンドで実行するオーケストレーター。詳細な操作手順は
[利用ガイド](guide/user-guide.md)を参照。

## 方針（詳細はdecisions.mdの各決定を参照）

- **データの正典**: `lineage.db`は実行のたびに作り直すスナップショット（D-001）。ホワイトリストは
  DBでなく`naming_whitelist.json`で管理（D-002）。
- **依存を増やさない**: 標準ライブラリで完結させる方針（類似度判定はD-003）。`requirements.txt`は
  Dr.Sum接続用の2ライブラリ（JayDeBeApi/JPype1）のみ。
- **セキュリティ**: 認証なし・localhost限定・外部非公開が既定（D-005）。Dr.Sum接続パスワードは
  環境変数経由で渡し、コマンドライン引数やログに残さない（D-006）。
- **二重実装の回避**: ブラウザ内評価モードのJSロジックはPython版と一字一句同じになるよう移植する（D-007）。

## 運用

実行責任者・アクセス権限・定期実行・障害時対応・変更管理は
[`doc/operation/operations.md`](operation/operations.md)を参照。

## 開発の進め方

コード・仕様の変更は必ず`doc/DD/`にDDを起票してから行う（`AGENTS.md`「DD設定」節）。
DDの作成・一覧・検索は`/dd`スキルを使う。
