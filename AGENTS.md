# AGENTS.md

> 全エージェント共通の正本（Codex は直接、Claude Code は CLAUDE.md の `@AGENTS.md` インポート経由で読む）

## プロジェクト概要

Dr.Sum上の物理カラムがMotionBoard上でどんなエイリアスでどのボードに使われているかを可視化するツール。定義ファイルを渡すだけで動く自動検出モードがデフォルト。

- **技術スタック**: なし(HTML静的ビューア) / Python 3 / SQLite / ローカル実行（`web_viewer.py`はlocalhost限定）
- **ドキュメント一覧**: `doc/DOC-MAP.md`（全ドキュメントの場所と目的。迷ったらまずここ）

## コマンド

| コマンド | 用途 |
|---------|------|
| `python main.py` | 全体オーケストレーター実行（`--demo`でデモデータ使用） |
| `python web_viewer.py --db lineage.db` | lineage.dbをブラウザで確認（軽量ビューア） |
| `python export_static.py` | lineage.dbを単一の静的HTMLに書き出す（社内配布用） |
| `pytest` | テスト実行（`pytest.ini`で`tests/`配下を対象化） |
| `bash scripts/doc-check.sh` | ドキュメント整合性チェック（DOC-MAP孤児・リンク切れ） |
| `pytest && bash scripts/doc-check.sh` | DD完了前の集約チェック |

## DD設定

- **DDフォルダ**: `doc/DD/` / **アーカイブ**: `doc/archived/DD/` / **テンプレート**: `doc/templates/dd_template.md`
- **パス設定**: ルート直下の `.dd-config`（スクリプト・フックはここを読む。上の実パスと常に一致させる）
- **ステータス**: 固定6種（検討中/進行中/確認待ち/保留/見送り/完了）+ 補足列。語彙ルール: `doc/templates/guides.md` §3
- **スキル**: `/dd new|list|log|archive|search|rebuild-index|health`（Claude Code: `.claude/skills/` / Codex: `.agents/skills/` — 同一内容のミラー）
- **開発フロー**: DD作成 → 仕様確認 → 実装 → 検証 → 完了（いきなりコードを書かない）
- **レビュー**: DDタスクに組み込まない — 完了報告を見た人間が別モデルへ都度指示（`doc/templates/guides.md` §10）
- **コミット**: `DD-{番号}: 概要` 形式。stage は対象ファイルを明示する — `git add -A` は並行セッションの作業や秘匿ファイルを巻き込むため使わない

## コーディング規約

- 基準書: `doc/templates/coding-standards.md`（コードレビューはこの基準で評価する）

## ドキュメント更新義務

- `doc/` にドキュメントを追加・移動したら `doc/DOC-MAP.md` も更新する
- 画面・API・DBを変更したら、対応する仕様書も同じ変更で更新する

## エージェント別の注意

- 編集ガード等の hooks は Claude Code 固有。Codex 等ではガードが効かないがルールは同じ: DD-INDEX.md は直接編集せず `bash scripts/dd-index-gen.sh` で再生成する
