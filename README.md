# カラム・エイリアス使用状況マップ - たたき台

Dr.Sum上の物理カラムが、MotionBoard上でどんな別名（エイリアス）で
どのボードに使われているかを可視化するためのプロジェクトの骨格です。

**タグ構造を事前に調べなくても、基本は「定義ファイルを渡すだけ」で
動くように、自動検出モードをデフォルトにしてあります。**
（Dr.Sumの実カラム名一覧を手がかりに、ファイルの中から既知のカラム名が
出現する場所を総当たりで探すヒューリスティック方式）

## 構成

```
mb_alias_lineage/
├── README.md
├── requirements.txt
├── inspect_file.py     # 調査ツール: 自動検出がうまくいかない時の目視確認用
├── dr_sum_metadata.py  # Dr.Sumからテーブル/カラム一覧を取得
├── board_parser.py     # MotionBoardボード定義ファイルの自動検出パーサー
├── match_aliases.py    # 突き合わせ・表記ゆれ検出・SQLiteへの保存
├── db_schema.sql       # 中間データを保存するSQLiteのスキーマ
├── web_viewer.py       # lineage.dbをブラウザで見るための軽量ビューア(localhost限定)
├── export_static.py    # lineage.dbを単一の静的HTMLに書き出す(社内配布用)
└── main.py             # 全体を通しで実行するオーケストレーター
```

## 仮データで一気通貫に試す(実物のファイルがまだ無い場合)

`sample_data/` フォルダに、実物に近い「仮のDr.Sumカラム一覧」と
「タグ構造がバラバラな5種類のボード定義サンプル」(XML4種+JSON1種)を
用意してあります。`--stub`より多様な構造でパイプラインの動きを
確認したい場合はこちらを使ってください。

```bash
python board_parser.py sample_data/motionboard_backup --columns sample_data/dr_sum_columns.json --out board_aliases.json
python match_aliases.py --columns sample_data/dr_sum_columns.json --aliases board_aliases.json
```

`label`属性、`caption`属性、深い階層の`Series`要素、`colName`/`alias`属性、
JSON形式、というように、あえてタグ名も属性名も全て違う書き方にしてあり、
自動検出モードがどんな構造でも同じように動くことを確認できます。

実行すると32件のエイリアスが検出され、表記ゆれ候補が4件
（例: `URIAGE_KIN`が「売上金額」「Revenue」「売上」の3通りで
使われている、など）見つかるはずです。

`sample_data/motionboard_backup/`内のXML/JSONファイルを開いて中身を
見てもらうと、実際のボード定義がどんな見た目になり得るかのイメージにも
なります（もちろん実物とは異なりますが、構造のバリエーションの参考には
なります）。

このうち以下の7ファイルは、自動検出ロジックが元々苦手としていた構造
（検出漏れ、または`board_name`/`item_id`が誤った値になる不具合）を
再現した回帰テスト用サンプルです（`TANKA`/`SHOHIN_NAME`列を使用。
表記ゆれ検出には影響しません）。現在は`board_parser.py`側の対応により
すべて正しく検出できていますが、今後ロジックを変更する際にデグレしていないか
確認する目的で残してあります。

- `board_returns_analysis.xml` … ラベルが同じ要素の属性ではなく子要素`<DisplayName>`のテキストにある
- `board_text_content_columns.xml` … カラム名が属性値ではなく要素のテキスト内容にある
- `board_qualified_column_ref.xml` … カラム名が`T_商品M.TANKA`のようにテーブル名で修飾されている
- `board_name_as_child_element.xml` … ボード名が属性ではなく子要素`<Title>`のテキストにある
- `board_item_id_alt_key.xml` … アイテムIDのキー名が`seq`/`itemNo`など"id"を含まない
- `board_purchase_lookup.json` … カラムとラベルが`fieldDefs`/`fieldLabels`のように別々の対応表に分かれ、IDで紐付く構造
- `board_parallel_arrays.json` … カラム名配列と表示名配列が同じインデックスで対応する構造

## 使い方（実物のファイルが手に入ったら）

### ステップ1: Dr.Sum側のメタデータを取得する

```bash
python dr_sum_metadata.py --host <server> --db <dbname> --user <user> --jdbc-jar <jarのパス>
```

JDBC経由でテーブル/ビュー/カラムの一覧を取得し、`dr_sum_columns.json`
に出力します。自動検出の「手がかり」として使うので、必ず先に実行してください。

### ステップ2: ボード定義を解析してエイリアスを抽出する（自動検出モード）

```bash
python board_parser.py path/to/backup/data/ --columns dr_sum_columns.json --out board_aliases.json
```

指定フォルダ以下のXML/JSONファイルを再帰的に読み、既知のカラム名が
属性値やキー値としてどこかに出現していないか総当たりで探します。
見つかったら、その近くにある「カラム名とは違う文字列」を表示名
（エイリアス）候補として拾い、ボード名・アイテムIDも周辺のタグ・キーから
推測します。実行結果に「検出: xxx.xml → N件」と出れば成功です。

検証として、タグ名も属性名もまったく違う2種類のサンプル
（`label`属性を使うものと`caption`属性を使うもの）で試したところ、
どちらも正しく検出できることを確認済みです。

### ステップ3: 突き合わせて表記ゆれを検出する

```bash
python match_aliases.py --columns dr_sum_columns.json --aliases board_aliases.json
```

`lineage.db`（SQLite）にまとめて保存し、同じ物理カラムに
複数の表示名が使われているケース（表記ゆれ候補）をコンソールに一覧出力します。

### 結果をブラウザで見る

```bash
python web_viewer.py
```

`lineage.db`をもとに、検索・表記ゆれのハイライト付きの一覧をブラウザで
表示します。**`localhost`のみで待ち受ける設計であり、実行したPC上からしか
閲覧できません。複数人が使う共有サーバーに常時起動して使う用途には
対応していません**（そのような使い方をしたい場合は認証機構の追加が別途必要です）。

社内にメールやファイル共有で結果を配布したい場合は、代わりに以下でサーバー
不要の単一HTMLファイルを生成できます（受け取った側はPython不要、ブラウザで
開くだけで閲覧できます）。

```bash
python export_static.py
```

どちらも、カラム数が多い（目安として3000件超）場合はブラウザでの表示が
重くなる可能性がある旨の警告が表示されます（現時点ではページネーション未対応）。

### まとめて実行

```bash
python main.py --backup-dir path/to/backup/data/ --host <server> --db <dbname> --user <user> --jdbc-jar <jarのパス>
```

### 動作確認だけしたい場合（ダミーデータ）

```bash
python main.py --stub
```

## テスト

```bash
pip install -r requirements-dev.txt
pytest
```

`board_parser.py`の自動検出ロジック(`sample_data/`の12ファイル全件を使った
回帰テスト。特に直近修正した7パターンはファイル単位でピンポイントに検証)、
`match_aliases.py`の突き合わせ・表記ゆれ検出、`web_viewer.py`/`export_static.py`
のデータ整形、`main.py`のオーケストレーションを中心にカバーしています。
ロジックを変更した際は、まず `pytest` を実行して既存の挙動を壊していないか
確認してください。

## うまく検出できない場合（フォールバック）

自動検出はヒューリスティック（経験則）なので、ファイル構造によっては
誤検出・検出漏れが起きることがあります。検出件数が明らかに少ない・
おかしい場合は、まず `inspect_file.py` で中身を目視確認してください。

```bash
python inspect_file.py path/to/backup/data/some_board_definition.xml
```

XML/JSONであれば構造をツリー表示します。実際のタグ・属性名が
分かったら、`board_parser.py` 内の `TAG_CONFIG` を書き換えたうえで
`--manual` オプションを付けて実行してください（従来の手動指定モード）。

```bash
python board_parser.py path/to/backup/data/ --manual --out board_aliases.json
```

## 現時点で調整が必要な箇所（TODOコメントで明示）

- `dr_sum_metadata.py` 内の接続文字列（JDBC URL書式）・ドライバークラス名・
  システムカタログのクエリ: 実環境に合わせて要調整
- `board_parser.py` の自動検出精度: 実ファイルで試して、誤検出が多ければ
  `_looks_like_label_key` 等のヒント文字列(`LABEL_KEY_HINTS`など)を
  実際のキー名の傾向に合わせて調整するとさらに精度が上がる
- `db_schema.sql`: 実データを見て型やインデックスを調整
