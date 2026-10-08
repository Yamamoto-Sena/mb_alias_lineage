# DD-027 検証ドキュメント

検証日: 2026-10-08

## コード修正

`board_parser.py`の`SEARCH_CONDITION_TAGS`/`_in_search_condition()`を汎用化し、`NON_ALIAS_CONTEXT_TAGS`/`_in_non_alias_context()`にリネーム。既存4タグ(`Condition`/`SearchCondition`/`PreCondition`/`Expression`)に加えて`ItemOrderChange`を除外対象に追加した。ロジック自体は変更なし(名前の一般化+タグの追加のみ)。

## 機械検証

- `pytest tests/test_board_parser.py` → 61 passed
- `pytest`(全体回帰) → 199 passed, 1 skipped(修正前と同じ内訳。既存エイリアス抽出ロジックへの影響なし)

新規テストクラス`TestItemOrderChangeNotTreatedAsAlias`(3件)を追加:
- `<ItemOrderChange category="TANKA" series="年度" summary="売上額">`で`年度`が抽出されないこと(Bug#001相当)
- `<CategoryDisp><Item label="TANKA" data="TANKA" selected="true" fid="6">`(ItemOrderChange配下)で`true`が抽出されないこと(Bug#002相当)
- `ItemOrderChange`配下外の通常の`Field label=...`は従来どおり検出される(過剰除外の回帰防止)

## 実データ検証

実機`C:\MotionBoard64`の`[My Boards]`配下全体(`real_columns.json`使用)を`board_parser.py`→`match_aliases.py`で再実行し、`lineage.db`を再生成した。修正前の`lineage.db`(2026-10-07生成)とエイリアス全件を突き合わせた結果:

### 除去されたレコード(修正前のみに存在)

| テーブル | 物理カラム | 誤エイリアス | ボード | item_id |
|---|---|---|---|---|
| 販売実績_練習用 | 支店 | 年度 | 地域別売上 | 9 |
| 販売実績_練習用 | 支店 | true | 地域別売上 | 6 |
| 販売実績_練習用 | 売上額 | true | 地域別売上 | 10 |
| 販売実績_練習用 | 地域 | true | 地域ブロック別売上 | 2 |
| 販売実績_練習用 | 売上額 | true | 地域ブロック別売上 | 10 |
| 販売実績_練習用 | 売上額 | 地域ブロック,地域 | 地域ブロック別売上 | 1 |

DD-027本体のBug#001/002(`支店`→`年度`/`true`、`地域別売上`)に加えて、同じ`ItemOrderChange`の欠陥クラスを持つ`地域ブロック別売上`ボードでも同種の誤抽出(`<ItemOrderChange category="地域ブロック,地域" series="" summary="売上額">`)が解消されたことを確認した。横展開調査(Explore agent)で判明した「`ItemOrderChange`は実機に9ボード・28箇所存在する」という事前調査と整合する結果。

### 正規のエイリアス抽出への影響

上記以外に削除・追加されたレコードはない(`達成率ダッシュボード`を除く。下記参照)。`支店`→`支店`、`受注日`→`年度`(計算項目)等、既存の正規エイリアス・計算項目の検出結果は変化なし。

### 補足: `達成率ダッシュボード`ボードについて

このボードの全エイリアスレコード(14件、`会社名`/`価格`/`地域`/`受注日`等ほぼ全列に対する`true`誤抽出)は、修正前・修正後いずれの結果にも現れなかった。原因を切り分けたところ、修正前のコード(`git stash`で一時的に復元して検証)でも同ボードの現在のスナップショットは0件(パースエラー)となり、**本修正とは無関係に、`C:\MotionBoard64`側でこのボードの定義が更新されて現在のスナップショットが解析不能な状態になっている**ことを確認した(詳細: [bug-report.md](bug-report.md)の横展開調査結論を参照)。

この件(`価格`列等の`disp="true"`属性キーの誤マッチ)はDD-027のスコープ外であり、別バグとして新規DD起票予定(本DDの完了条件には含めない)。

### 組み込みブラウザでの確認

`web_viewer.py --db lineage.db`で再生成後の`lineage.db`を開き、`支店`列(`販売実績_練習用`、`DB不一致の可能性`表示)の「使用ボード」欄が`地域ブロック別売上`/`地域別売上`ともに「支店 (物理名のまま)」のみになっており、`年度`・`true`が表示されないことを目視確認した。

## 受け入れ基準との対応

| # | 基準 | 結果 |
|---|------|------|
| 1 | 構造の特定 | 完了済み(Phase 0) |
| 2 | `auto_parse_xml`で`支店`に`年度`/`true`が記録されない | 新規テスト3件で確認(pytest全パス) |
| 3 | 既存の正規エイリアス抽出に変化なし | 全体回帰199 passed/1 skipped。DB差分突き合わせでも対象外の変化なしを確認 |
| 4 | 実データで`支店`の使用ボード欄から`年度`・`true`が消える | `lineage.db`再生成+組み込みブラウザで確認 |
