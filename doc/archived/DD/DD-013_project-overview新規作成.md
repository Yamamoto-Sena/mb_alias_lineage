# DD-013: project-overview.mdの新規作成

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-02 | 2026-10-02 | 完了 | doc/project-overview.md を新規作成。pytest 141件パス |

> アプローチ: 標準（新規ドキュメント作成。コード変更を伴わないため差分テンプレートなし。guides.md §1）
> リスク: なし（ドキュメント追加のみ。既存コード・DBへの変更なし）

## 目的

`doc/DOC-MAP.md`に「未作成。最初に書くことを推奨」と記載されたまま12件のDDが進んでいた`doc/project-overview.md`を新規作成し、新規参加者がプロジェクトのスコープ・環境・方針を最初に把握できる入口を用意する。

## 背景・課題

DD・利用ガイド（DD-010）・画面仕様書（DD-011）・意思決定記録とパターン集（DD-012）は揃ったが、それらへの導線となる「プロジェクト概要」が存在しなかった。README.mdはコマンド仕様の正本、利用ガイドは操作手順の案内であり、いずれも「このツールは何をしない（スコープ外）か」「技術スタックは何か」「運用方針はどこに書いてあるか」を一望できる文書ではない。

## 検討内容

- 既存文書（README.md・utilsガイド・operations.md・decisions.md）との重複を避け、project-overview.mdは「スコープ・環境・方針」のみに絞り、詳細は各文書へのリンクに留める方針とした（DOC-MAPの説明文と一致させる）。
- 「やらないこと」を明記することで、認証機構や通知連携等がなぜ無いのか（既存のD-005等の決定）を新規参加者が誤解しないようにした。

## 決定事項

- `doc/project-overview.md`を新規作成。スコープ（やること/やらないこと）・対象ユーザー・技術スタック・全体構成（パイプライン図）・方針（decisions.mdの該当決定への参照）・運用（operations.mdへの参照）・開発の進め方（DD起票の原則）を記載。
- `doc/DOC-MAP.md`の該当行から「（未作成。最初に書くことを推奨）」の注記を削除。

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | `doc/project-overview.md`を開く → スコープ・環境・方針が記載され、関連文書（README/guide/spec/decisions/operations）へのリンクが揃っている | 目視確認 |
| 2 | `doc/DOC-MAP.md`の該当行が更新されている | `bash scripts/doc-check.sh` |
| 3 | 既存ドキュメント・テストに回帰がない | `pytest` / `bash scripts/doc-check.sh` |

## タスク一覧

### Phase 1: project-overview.mdの作成
- [x] README.md・requirements.txt・operations.md・decisions.mdを確認し、スコープ・環境・方針の記載内容を洗い出す
- [x] `doc/project-overview.md`を作成
- [x] `doc/DOC-MAP.md`の注記を削除
- [x] 🔬 機械検証: `bash scripts/doc-check.sh` → OK

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（全項目達成）
- [x] 😈 セルフレビュー1巡: README.md/利用ガイドとの内容重複がないか確認 → スコープ・方針の要約とリンクのみに留め、手順の重複記載はしていないことを確認
- [x] 🔬 全回帰1回: `pytest` → 141 passed, 1 skipped / `bash scripts/doc-check.sh` → OK

## ログ

### 2026-10-02
- DD作成
- `doc/project-overview.md`を作成し、`doc/DOC-MAP.md`の注記を更新
- `pytest`（141 passed, 1 skipped）・`doc-check.sh`（OK）で回帰なしを確認
