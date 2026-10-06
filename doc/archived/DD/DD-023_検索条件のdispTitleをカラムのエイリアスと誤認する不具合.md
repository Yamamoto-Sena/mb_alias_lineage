# DD-023: 検索条件のdispTitleをカラムのエイリアスと誤認する不具合

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-10-06 | 2026-10-06 | 完了 | walk()にSearchCondition配下除外判定を追加。実機再生成で架空エイリアス消滅を確認 |

> アプローチ: バグ修正・ライトパス（原因箇所・実機での再現を特定済み。単一バグで画面の構造変更を伴わず、既存の抽出ロジックの対象範囲を絞るだけの修正のため）
> エビデンス: テスト出力（pytest。実機XMLの構造を模したフィクスチャを追加）
> リスク: なし（認可・認証／DBスキーマ／外部I/F／機密情報・決済のいずれにも該当しない）

## 概要

| Bug# | 概要 | 重要度 |
|------|------|--------|
| 1 | MotionBoardの検索条件(事前設定フィルタ)のキャプション(`dispTitle`)が、物理カラムのエイリアス(表示名)として誤抽出され、実際には設定されていないエイリアスが「使用ボード」欄・「表示名(エイリアス)」欄に表示される |

## 原因分析

[DD-022](DD-022_使用ボード欄の物理名そのまま表示をエイリアスと誤認させない対応.md)のエビデンス確認中、ユーザーから「`名古屋店`等のエイリアスを命名した覚えがない」との指摘を受け、実機(`C:\MotionBoard64`)の該当ボード(`KPI・棒グラフ・ランキングパーツ・折れ線グラフ`)のスナップショットXMLを直接確認した結果、該当箇所は以下の構造だった:

```xml
<Condition><SearchCondition><PreCondition>
  <Expression enable="true" dsid="0" fid="3" title="store_name" dispTitle="大阪店"
              dispType="INPUT" operatorType="EQUAL" valType="INPUT" .../>
</PreCondition></SearchCondition></Condition>
```

これは「店舗別タブ」のための**事前設定フィルタ条件**であり、`dispTitle`はその検索条件(フィルタ)自体のキャプションで、`title`(＝物理カラム名)の**エイリアス(aliasTitle)ではない**。

[board_parser.py](../../board_parser.py) の汎用ヒューリスティック経路(`auto_parse_xml`内`walk()`、[board_parser.py:386-400](../../board_parser.py#L386-L400))は、属性値`title="store_name"`が物理カラム名と一致した時点で`find_label_on_element`([board_parser.py:334-353](../../board_parser.py#L334-L353))を呼び、同一要素の他の属性から`_looks_like_label_key`([board_parser.py:88-90](../../board_parser.py#L88-L90))に一致するものを探す。`LABEL_KEY_HINTS = ("label", "disp", "name", "alias", "title", "caption", "表示", "名称")`に`"disp"`が含まれるため、`dispTitle`属性名はこの判定にヒットしてしまい、フィルタ条件のキャプション("大阪店"等)がそのままカラムのエイリアスとして記録される。

この経路は`.fs-file`のボード本体XML(`<DataSource type="drsum">`を持たないファイル。DD-002-3で判明した専用パーサー`_parse_drsum_datasource`の対象外)に対して適用されるため、データソース定義ファイル自体([board_parser.py:224-280](../../board_parser.py#L224-L280))は影響を受けない。

**実例**: `T_STORE_KPI.STORE_NAME`列は、全6データソース定義(`_parse_drsum_datasource`経由、item_id="3")で`aliasTitle`が空(＝物理名そのまま使用)であることを確認済み。にも関わらず、ボード本体XML由来の誤抽出(item_id="0"、`dsid`属性を拾ったもの)により「名古屋店/大阪店/札幌店/東京店/福岡店」という5つの架空エイリアスが「KPI・棒グラフ・ランキングパーツ・折れ線グラフ」ボードの使用ボード欄・表示名欄に表示されている。

## 修正方針

`walk()`が`<Condition>`/`<SearchCondition>`/`<PreCondition>`/`<Expression>`配下を辿っている間は、エイリアス抽出(`find_label_on_element`によるラベル探索)の対象外とする。検索条件は「ボードがそのカラムをどう表示しているか」の定義ではなく「どう絞り込むか」の定義であるため、本ツールの対象外として構造的に除外する。

## 対象ファイル

| ファイル | 変更内容 |
|---------|---------|
| `board_parser.py` | `walk()`(XML)に、祖先要素のタグ名が`SearchCondition`/`PreCondition`/`Condition`/`Expression`のいずれかの場合はエイリアス抽出をスキップする判定を追加。`auto_parse_json`側の`walk()`にも同根パターンがないか確認し、あれば同様に対応 |
| `tests/test_board_parser.py` | 実機で確認した`<Condition><SearchCondition><PreCondition><Expression title="..." dispTitle="...">`構造を模したフィクスチャで、`dispTitle`がエイリアスとして抽出されないことを確認するテストを追加 |

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | `<Condition><SearchCondition><PreCondition><Expression title="<物理カラム名>" dispTitle="<任意の文字列>">`を含むボード本体XMLを`auto_parse_xml`で解析する → `dispTitle`の値が`AliasRecord.display_name`として記録されない | `pytest tests/test_board_parser.py` |
| 2 | 既存の正規のエイリアス抽出(aliasTitle・ExField計算項目・汎用ヒューリスティックの他パターン)の検出結果に変化がない | `pytest`全体 → 既存件数のまま全パス |
| 3 | 実データ(`lineage.db`再生成)で`T_STORE_KPI.STORE_NAME`の「使用ボード」欄から「名古屋店/大阪店/札幌店/東京店/福岡店」が消え、物理名そのまま使用(DD-022案A適用後は「(物理名のまま)」付記)のみになる | 実機確認（組み込みブラウザ） |

## タスク一覧

### Phase 0: 調査・再現確認・修正前エビデンス

- [x] コードベース調査 — 原因箇所の特定（本DD起票時に完了。上記「原因分析」参照）
- [x] 実機確認 — `C:\MotionBoard64`上の実スナップショットXMLで`dispTitle`誤抽出を確認済み（上記「実例」参照）
- [x] 📸 修正前エビデンス — [DD-022](DD-022_使用ボード欄の物理名そのまま表示をエイリアスと誤認させない対応.md)の`DD-022/bug022-before-boards-column-unaliased.jpg`を流用（同一現象が写っている）
- [x] 👀 **ユーザーレビュー** — 原因分析・修正方針の合意（ゲート）→ 合意（DD-022と合わせて両方進める指示）

### Phase 1: コード修正・テスト
- [x] `board_parser.py`の`walk()`にCondition/SearchCondition/PreCondition/Expression配下を除外する判定を追加（`SEARCH_CONDITION_TAGS`定数+`_in_search_condition()`ヘルパーを新設し、`walk()`内のマッチ処理をガード）
- [x] 同根パターンの横展開確認（`sample_data/`配下のJSONフィクスチャに`dispTitle`/`SearchCondition`相当のキーが存在しないことをgrepで確認。MotionBoard内部ストアはXML形式のみでJSON側はこのパターン対象外と判断。`auto_parse_json`の`walk()`は変更不要）
- [x] `tests/test_board_parser.py`にテスト追加（`TestSearchConditionNotTreatedAsAlias`。実機確認した構造を模したフィクスチャで、SearchCondition配下の`dispTitle`が抽出されないこと・配下外の通常`Field/label`は従来どおり検出されることの2点を検証）
- [x] 🔬 機械検証: `pytest` → 145 passed, 1 skipped、全パス

### Phase 2: 修正後エビデンス・ドキュメント整備
- [x] `lineage.db`を実データ(`C:\MotionBoard64`)で再生成し、`T_STORE_KPI.STORE_NAME`の`board_aliases.json`上のレコードが20件→10件に減少、「名古屋店/大阪店/札幌店/東京店/福岡店」が完全に消えたことを確認
- [x] 📸 修正後エビデンス取得 → `DD-023/bug023-after-fabricated-aliases-removed.jpg`
- [x] 🔬 機械検証: `bash scripts/doc-check.sh` → OK

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合（#1・#2: `pytest`全件パスで達成。#3: 実機データ再生成+組み込みブラウザで達成）
- [x] 😈 セルフレビュー1巡（所見: `_in_search_condition`はstack全体を毎回線形走査するため、極端に深いXMLではわずかに遅くなるが、実機データで3069〜95507バイト程度のXMLに対し体感影響なし。性能上の懸念なしと判断）
- [x] 🔬 全回帰1回: `pytest && bash scripts/doc-check.sh` → 全パス

## ログ

### 2026-10-06
- [DD-022](DD-022_使用ボード欄の物理名そのまま表示をエイリアスと誤認させない対応.md)のエビデンス確認中、ユーザーから「`名古屋店`等のエイリアス名を命名した覚えがない。どこに存在しているのか」との質問を受けて調査。実機(`C:\MotionBoard64`)の該当ボードのスナップショットXMLを直接確認し、`<SearchCondition><PreCondition><Expression title="store_name" dispTitle="大阪店" .../>`という事前設定フィルタ条件のキャプションが、汎用ヒューリスティックの`LABEL_KEY_HINTS`に含まれる`"disp"`文字列にマッチして誤ってエイリアス抽出されていたことを特定。DD-022とは原因箇所・修正箇所が異なる別バグのため、DD-023として分離して起票
- ユーザーから「両方とも進めてください」との指示を受け、DD-022と合わせて実装。`board_parser.py`に`SEARCH_CONDITION_TAGS`定数と`_in_search_condition()`ヘルパーを追加し、`auto_parse_xml`内`walk()`のマッチ処理をCondition/SearchCondition/PreCondition/Expression配下で無効化
- `tests/test_board_parser.py`に`TestSearchConditionNotTreatedAsAlias`を追加。`pytest` → 145 passed, 1 skipped(全パス)
- 実データで`board_parser.py`→`match_aliases.py`を再実行して`lineage.db`を再生成。`T_STORE_KPI.STORE_NAME`の架空エイリアス5種(名古屋店/大阪店/札幌店/東京店/福岡店、計10レコード)が消え、物理名そのまま使用の10レコードのみに正しく絞られたことを実データで確認。組み込みブラウザでも「使用ボード」欄から該当エイリアスが消えたことを目視確認
- 受け入れ基準#1〜3すべて達成。アーカイブはユーザー確認後に実施する
