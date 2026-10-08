# DD-030 原因分析

## Bug#001: 結合データソースの構造的属性値が計算式の表示名として誤表示される

**ファイル**: `board_parser.py` L226-227 `_looks_like_formula_value()` / L443-459 `auto_parse_xml()` 内 `walk()`

**現象**: `DATALIZER_PRACTICE`接続時、ボード別ドリルダウンで`09_結合データソース`を選択すると、
`T_STORE_KPI.store_name`の表示名が`1/store_name/true//2//true//3//true/true`という意味不明な
文字列になり、種別は「計算式」と表示される。

**原因**:

1. `auto_parse_xml()`の汎用ヒューリスティック(`walk()`)は、属性値がカラム名と完全一致しない場合でも、
   `_looks_like_formula_value()`(L226-227)が`True`を返す値(`+`・`*`・`/`・`[`・`]`・`(`・`)`のいずれかを
   含む文字列)を「計算式らしい値」とみなし、`_find_columns_in_formula()`でトークン単位の部分一致を試みる。
2. 「結合データソース」(複数データソースを統合するMotionBoardの機能)のXML要素は、`<DataSource type="drsum">`
   専用形式(`_parse_drsum_datasource`)ではなく汎用ヒューリスティックの対象になる構造らしく、各データソースの
   対応カラム・有効フラグを`/`区切りでシリアライズした構造的な属性値（例:
   `1/store_name/true//2//true//3//true/true` = データソース1は`store_name`列が対応・有効、
   データソース2・3は対応列なし・有効、を表すとみられる値）を持つ。
3. この値はたまたま物理カラム名`store_name`を部分文字列として含むため、手順1の判定に引っかかり
   `cols_in_formula = ["STORE_NAME"]`が検出される。
4. 同一要素内にラベルらしい手がかり(`LABEL_KEY_HINTS`一致・日本語)が無いため、
   `calc_name = find_label_on_element(el, attr_key, attr_val) or attr_val`(L448)の`or attr_val`が
   発動し、構造的な生の属性値がそのまま`display_name`として採用される。

[DD-027](../archived/DD/DD-027_支店カラムのエイリアスに無関係な年度が誤検出される不具合.md)・
[DD-028](../archived/DD/DD-028_データソース定義のdisp属性キーをカラムのエイリアスと誤認する不具合.md)と
同じ欠陥クラス(物理カラム名と一致した値の周辺に意味的検証がない)だが、今回は「計算式らしさ」の判定自体
(`_looks_like_formula_value`)が、実際には計算式ではない構造的シリアライズ値(インデックス・真偽値を
`/`区切りで並べたもの)まで拾ってしまう点が異なる。`auto_parse_json()`側の同等ロジック(L585-602)も
同じ欠陥を持つため、JSON形式の結合データソース定義が将来現れた場合に備えて併せて対象とする。

**再現手順**:
1. `DATALIZER_PRACTICE`接続のMotionBoardコンテンツストアに含まれる`09_結合データソース.fs-file`を
   `board_parser.py --auto`で解析する
2. 生成された`board_aliases.json`から`board_name`が`09_結合データソース`のレコードを確認する
3. `table_name=T_STORE_KPI`, `column_name=STORE_NAME`, `usage_type=calc`のレコードの
   `display_name`が`1/store_name/true//2//true//3//true/true`になっていることを確認する

**実機データ**(`board_aliases.json`より抜粋):
```json
{
  "table_name": "T_STORE_KPI",
  "column_name": "STORE_NAME",
  "display_name": "1/store_name/true//2//true//3//true/true",
  "board_name": "09_結合データソース",
  "item_id": "6",
  "usage_type": "calc",
  "source_db": ""
}
```

**次のアクション**: マッチした物理カラム名トークン以外の全トークンが数字または真偽値リテラル
(`true`/`false`)のみで構成される値は、計算式ではなく構造的なシリアライズ値とみなし、
計算式としての抽出対象から除外する汎用ガードを`auto_parse_xml`・`auto_parse_json`双方の
`walk()`に追加する(DD本体「修正方針」参照)。
