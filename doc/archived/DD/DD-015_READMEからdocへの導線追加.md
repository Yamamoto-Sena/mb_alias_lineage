# DD-015: READMEからdocへの導線追加

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-02 | 2026-10-02 | 完了 | README.mdに関連ドキュメント3件へのリンクを追加。pytest 141件パス |

> アプローチ: 標準（README冒頭への短い案内追加のみ。コード変更なし。guides.md §1）
> リスク: なし（ドキュメント追加のみ）

## 目的

`README.md`から`doc/project-overview.md`・`doc/guide/user-guide.md`・`doc/DOC-MAP.md`への導線を追加し、READMEを最初に開いた人がdoc/配下の整備済みドキュメントに気づけるようにする。

## 背景・課題

DD-010〜DD-013で`doc/project-overview.md`・`doc/guide/user-guide.md`・`doc/spec/`・`doc/decisions.md`等を整備したが、いずれも「README.mdを参照」という片方向のリンクのみを持ち、README.md側からdoc/への導線が1つもなかった。`README.md`は本プロジェクトで最初に開かれる前提のファイルであり、ここにdoc/への入口がないと、整備したドキュメント群が発見されない。

## 検討内容

- README.mdの性格（コマンド仕様の正本、技術者向け）を変えず、冒頭の概要文の直後・「## 構成」の手前に3行程度の案内リンクを追加するだけに留める方針とした。README本体の構成・既存内容は変更しない。
- 案内先は、役割が異なる3つの入口（スコープ・方針を知る: project-overview.md／使い方を知る: user-guide.md／全ドキュメントを探す: DOC-MAP.md）に絞った。

## 決定事項

- `README.md`の概要文（1〜13行目）の直後、「## 構成」見出しの手前に、3つの関連ドキュメントへのリンクを箇条書きで追加する。

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | `README.md`冒頭を開く → `doc/project-overview.md`・`doc/guide/user-guide.md`・`doc/DOC-MAP.md`へのリンクが見つかる | 目視確認 |
| 2 | 追加したリンクのリンク先ファイルが実在する | 目視突合（`ls`） |
| 3 | 既存ドキュメント・テストに回帰がない | `pytest` / `bash scripts/doc-check.sh` |

## タスク一覧

### Phase 1: README.mdへのリンク追加
- [x] `README.md`の概要文直後に関連ドキュメントへの案内を追加
- [x] 🔬 機械検証: リンク先3ファイルの実在を`ls`で確認、`bash scripts/doc-check.sh` → OK

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（全項目達成）
- [x] 😈 セルフレビュー1巡: README本体の既存構成・文体を変えていないか確認 → 追加のみで既存文言は無変更
- [x] 🔬 全回帰1回: `pytest` → 141 passed, 1 skipped / `bash scripts/doc-check.sh` → OK

## ログ

### 2026-10-02
- DD作成
- `README.md`冒頭に関連ドキュメントへの案内を追加
- `pytest`（141 passed, 1 skipped）・`doc-check.sh`（OK）で回帰なしを確認
