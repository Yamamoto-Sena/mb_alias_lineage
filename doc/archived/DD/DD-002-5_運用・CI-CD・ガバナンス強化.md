# DD-002-5: 運用・CI/CD・ガバナンス強化

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-09-30 | 2026-09-30 | 完了 | CI導入・定期実行強化・ガバナンス文書整備完了。通知連携は送信先未確定のため見送り。pytest 131件パス |

> アプローチ: 標準（探索的実装。画面変更を伴わず、CI設定・スクリプト追加・文書整備が中心のため）
> リスク: あり（外部I/F — GitHub Actions。送信先確定後に追加する通知連携も対象だが、本DDでは送信は実施しない）

## 目的

DD-002の最終工程として、①CI導入（pytest自動実行）②定期実行の強化（実行履歴保存・新規/増減検知）
③通知連携の方針整理④ガバナンス文書整備を行い、mb_alias_lineageツールを安定運用フェーズに移行させる。

## 背景・課題

DD-002-1〜4が完了し前提条件が整った。現状はCI未導入（push/PR時の自動テストなし）、定期実行は
README記載のタスクスケジューラ手動運用のみで実行履歴が残らず、通知連携も未実装。ガバナンス文書
（運用ルール・アクセス権限・変更管理）も存在しない。

## 検討内容

- **CI導入の前提調査**: `dr_sum_metadata.py`はjaydebeapi/JPype1を実行時に遅延importし、テストは
  `monkeypatch`でモック化している（`tests/test_dr_sum_metadata.py`）。実際に`requirements-dev.txt`
  （pytestのみ）だけで`pytest`が127件パスすることを確認済み。→ CI環境にJava/JDBCドライバーは不要。
- **通知先の比較**（送信先は保留、参考情報として記載）:

  | 選択肢 | 長所 | 短所 |
  |--------|------|------|
  | Slack Webhook | 実装が単純（HTTP POST 1回） | slack.comへの外部接続が必要。Dr.Sum/MotionBoardと同じオンプレ想定環境では接続不可の可能性 |
  | SMTPメール | 外部接続不要。README記載の既存の社内配布（メール配布）と一貫 | 宛先リストの管理が別途必要 |

  ユーザーに確認したところ「いったん保留」。運用担当者・Slack利用状況が確認できた時点で再検討する。
- **新規検出・増減の検知方法**: `db_schema.sql`のコメントにある通り、lineage.dbは「その時点のスナップ
  ショット」であり過去実行を積み上げない設計（DROP→CREATE運用）。この設計は変更せず、DBの外側で
  各カテゴリの件数（表記ゆれ候補/多対1/物理名直接使用/孤立項目/類似度候補）を`run_history.json`に
  前回分と一緒に保存し、差分を検知する。送信先が決まればこの差分をそのまま通知本文に使える。

## 決定事項

- CI: `.github/workflows/ci.yml`を追加し、push/pull_request時に`requirements-dev.txt`のみをインストール
  して`pytest`を実行する（`requirements.txt`のJDBC関連はインストールしない）。
- 定期実行の強化: `match_aliases.py`に各カテゴリ件数を集計し、`<db>.history.json`
  （`--history-file`で上書き可）へ前回分と比較した新規/増減を記録・標準出力に表示する機能を追加する。
  `--db`に紐づけた既定値にすることで、`--demo`実行と本番実行の履歴が混在しないようにする。
  lineage.dbのスキーマ・DROP→CREATE設計は変更しない。
- 通知連携: 送信先未確定のため本DDでは送信実装を**見送る**。差分検知結果（上記）は送信先確定後に
  別DDで送信部分のみ追加できる形（JSON構造）まで用意しておく。
- ガバナンス文書: `doc/operation/operations.md`を新設し、実行責任者・アクセス権限・定期実行の運用
  手順・障害時対応・変更管理ルールを記載する。`doc/DOC-MAP.md`に運用セクションを追加する。

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | `.github/workflows/ci.yml`が存在し、YAML構文が正しい | Phase 1 🔬機械検証 |
| 2 | `python match_aliases.py`を2回連続実行 → 2回目の標準出力に前回との差分件数が表示される | Phase 2 🔬機械検証・新規テスト |
| 3 | `doc/operation/operations.md`が存在し、DOC-MAPから参照される | Phase 4 🔬機械検証（`doc-check.sh`） |
| 4 | 通知連携が送信先未確定のため見送りであることがログに明記されている | 本DDのログ参照 |

## タスク一覧

### Phase 1: CI導入
- [x] `.github/workflows/ci.yml`を新規作成: `actions/checkout` → `actions/setup-python@v5`(3.12) →
      `pip install -r requirements-dev.txt` → `pytest`
- [x] 🔬 機械検証: ローカルで`py -m pytest`が127件パス済みであることを確認（実施済み）。CI上での
      実行結果はpush後にActionsタブで確認する

### Phase 2: 定期実行の強化（実行履歴・差分検知）
- [x] `match_aliases.py`: 5カテゴリ（表記ゆれ候補/多対1/物理名直接使用/孤立項目/類似度候補）の件数を
      集計し、`--history-file`（既定値`<db>.history.json`）に前回分と比較した新規/増減を記録・表示する
      関数を追加
- [x] `tests/test_match_aliases.py`: 初回実行（履歴なし）・2回目実行（差分検知・変化なし）のテストケースを追加
- [x] 🔬 機械検証: `py -m pytest tests/test_match_aliases.py` が全件パス（実施済み）

### Phase 3: 通知連携（方針整理のみ、送信は見送り）
- [x] 送信先確定後に着手できるよう、Phase 2の差分JSON構造をこのDDの検討内容に記録済みであることを確認
- [x] 🔬 機械検証: 対象外（コード変更なし）

### Phase 4: ガバナンス文書整備
- [x] `doc/operation/operations.md`を新設: 実行責任者・アクセス権限・定期実行の運用手順・障害時対応・
      変更管理ルールを記載
- [x] `doc/DOC-MAP.md`に運用セクション（`doc/operation/`）を追加
- [x] 🔬 機械検証: `bash scripts/doc-check.sh` → OK（実施済み）

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（未達成があれば理由をログへ）
- [x] 😈 セルフレビュー1巡
- [x] 🔬 全回帰1回: `py -m pytest && bash scripts/doc-check.sh` → 全パス

## ログ

### 2026-09-30
- DD作成。ユーザーにスコープを確認し、CI導入・通知連携・定期実行強化・ガバナンス文書整備の4点を対象とする方針で合意
- 通知連携の送信先（Slack Webhook / SMTPメール）をユーザーに確認 → 「いったん保留」。送信実装は見送り、
  差分検知ロジックのみ先行実装する方針に変更（Phase 3として明記）
- Phase 1（CI導入）完了: `.github/workflows/ci.yml`を追加。ローカルで`py -m pytest`が127件パス
  済みであることを確認（YAML構文は`yaml.safe_load`でパース確認）。実際のActions実行はpush後に確認が必要
- Phase 2（定期実行の強化）完了: `match_aliases.py`に`collect_category_counts`/`report_history_diff`を
  追加し、`main.py --stub`を2回連続実行して差分表示（1回目「前回実行なし」→2回目「変化なし」）を確認。
  セルフレビューで、履歴ファイルの既定値が固定名だと`--demo`実行と本番実行の履歴が混在する問題に気づき、
  既定値を`<db>.history.json`（`--db`に紐づく）に変更して解消
- Phase 4（ガバナンス文書整備）完了: `doc/operation/operations.md`を新設、`doc/DOC-MAP.md`を更新
- 全回帰実施: `pytest`131件パス、`doc-check.sh` OK。受け入れ基準1〜4すべて達成
- DD完了。子DD一覧（DD-002本体）を更新し、DD-INDEX.mdを再生成
- （アーカイブ後の追補）push後にActionsで実行を確認したところ、`actions/checkout@v4`/
  `actions/setup-python@v5`がNode.js 20非推奨警告を出していたため、`v7`（Node 24ネイティブ）に
  更新（コミット`2b104f2`）。再実行でpytest 131件パス・警告解消を確認。ステータスは軽微な
  設定変更のため「完了」のまま維持
