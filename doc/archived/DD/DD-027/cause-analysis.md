# DD-027 原因分析

## Bug#001/002: `支店`列に`年度`/`true`という無関係なエイリアスが記録される

**ファイル**: `board_parser.py` L354-424 `auto_parse_xml()`内`walk()`/`find_label_on_element()`

**現象**:

`lineage.db`で`支店`列(`販売実績_練習用`テーブル、ボード`地域別売上`)を調べると、次の4件のエイリアスレコードが存在する。

| id | column_name | display_name | item_id | usage_type |
|----|-------------|---------------|---------|------------|
| 29 | 支店 | 支店（正規） | 6 | alias |
| 20 | 支店 | **true**（不審） | 6 | alias |
| 32 | 受注日 | 受注日（正規） | 9 | alias |
| 19 | 支店 | **年度**（不審） | 9 | alias |

正規のエイリアス(id=29)とは別に、`支店`列へ`true`・`年度`という業務上あり得ない値がエイリアスとして記録されている。いずれも`usage_type='alias'`であり、計算式参照(`usage_type='calc'`)経由ではない。

参考: 同ボードには`受注日`から`年度`を計算する正規の計算項目(id=60: `受注日`→`年度`, item_id=1, `usage_type='calc'`)が別途存在する。`年度`という文字列自体はこのボードの業務用語として実在するため、どこかで取り違えが起きていると考えられる。

**原因（推定、コードレベル）**:

`_parse_drsum_datasource()`（データソース定義本体の専用パーサー、L238-300）は`<Field>`の`title`/`aliasTitle`属性を厳密に1:1でペアにするため、このような取り違えは原理的に起こらない。一方、同じ`.fs-file`内にはボード本体（ウィジェット定義）のXMLも同梱されており、これは`<DataSource type="drsum">`を持たないため、汎用ヒューリスティック経路（L331-447）で解析される。

この経路の`walk()`は、ある要素の属性値が既知の物理カラム名(`支店`)と完全一致すると、`find_label_on_element()`を呼び**同一要素内の他の属性**からラベル候補を探す(L354-373)。優先順は:

1. キー名が`LABEL_KEY_HINTS = ("label", "disp", "name", "alias", "title", "caption", "表示", "名称")`のいずれかを含む属性
2. （1が無ければ）日本語を含む最初の属性値
3. （2も無ければ）属性リストの先頭
4. （属性に無ければ）子要素

`true`というアルファベット値は(1)(2)に該当しないため、一致する属性が他に無い（＝候補が`true`しか無い）状況で(3)にフォールバックしたものと推測される。`年度`は日本語なので(2)で拾われた可能性が高い。

いずれにせよ共通するのは、**「物理カラム名と一致した属性」と「ラベル候補として拾った属性」の間に意味的な関連性を一切検証していない**という設計上の弱点であり、[DD-023](../archived/DD/DD-023_検索条件のdispTitleをカラムのエイリアスと誤認する不具合.md)で修正された`SearchCondition`配下の`dispTitle`誤抽出と同じ欠陥クラスである。DD-023の修正(`_in_search_condition`)は`Condition`/`SearchCondition`/`PreCondition`/`Expression`配下のみを除外しており、今回の誤抽出がこれらのタグ配下で起きているかは未確認（恐らく別のタグ、例えばクロス集計/ピボット系ウィジェットの軸設定のように、行軸=`支店`・列軸=`年度`といった関連のない複数のフィールド参照が同一要素の属性として同居する箇所が疑わしい）。

**確定（実機XML確認済み、2026-10-07）**:

実機`C:\MotionBoard64`の`地域別売上.fs-file`最新スナップショットを展開し、ボード本体(mcDef)のXML(ルート直下`地域別売上`エントリ)に以下の構造を確認した。

```xml
<ItemOrderChange category="支店" series="年度" summary="売上額">
  <CategoryDisp><Item label="支店" data="支店" selected="true" fid="6"></Item></CategoryDisp>
  <SeriesDisp><Item label="年度" data="年度" selected="true" fid="10000"></Item></SeriesDisp>
  <SummaryDisp invisibleSelectedItems=""><Item label="売上額" data="売上額" selected="true" fid="10" visible="true"></Item></SummaryDisp>
</ItemOrderChange>
```

`<ItemOrderChange>`は集計表(クロス集計)パーツの軸設定要素で、`category`(行軸)/`series`(列軸)/`summary`(集計値)という3つの無関係なフィールド参照を同一要素の属性として持つ。`支店`との完全一致判定後、`find_label_on_element()`が同一要素の他属性(`series="年度"`)を日本語フォールバックで拾ってしまう(Bug#001)。

同じ`<CategoryDisp><Item label="支店" data="支店" selected="true" fid="6">`では、`label`/`data`が一致するため除外され、残る`selected="true"`が最終フォールバックで採用される(Bug#002)。

いずれも[DD-023](../../archived/DD/DD-023_検索条件のdispTitleをカラムのエイリアスと誤認する不具合.md)と同じ欠陥クラス（物理カラム名と一致した属性と、ラベル候補として拾う属性の間に意味的関連性の検証が無い）。DD-023のガード(`_in_search_condition`、`Condition`/`SearchCondition`/`PreCondition`/`Expression`配下除外)は`ItemOrderChange`配下をカバーしていない。

詳細な再現手順・実機エビデンスは[bug-report.md](bug-report.md)を参照。

**再現手順**:
1. `python board_parser.py <MotionBoardバックアップフォルダ> --columns dr_sum_columns.json --out board_aliases.json` を実行（または実機を直接走査）
2. `地域別売上`ボードの`支店`列のエイリアス一覧に`年度`・`true`が含まれることを確認
