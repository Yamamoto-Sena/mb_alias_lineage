# カラム・エイリアス使用状況マップ - たたき台

Dr.Sum上の物理カラムが、MotionBoard上でどんな別名（エイリアス）で
どのボードに使われているかを可視化するためのプロジェクトの骨格です。

**タグ構造を事前に調べなくても、基本は「定義ファイルを渡すだけ」で
動くように、自動検出モードをデフォルトにしてあります。**
（Dr.Sumの実カラム名一覧を手がかりに、ファイルの中から既知のカラム名が
出現する場所を総当たりで探すヒューリスティック方式）
渡すフォルダは、エクスポート済みのXML/JSON一式でも、MotionBoardサーバーの内部データ
フォルダ（`<ボード名>.fs-file/`を含むフォルダ。`data/mb/mbds_def/mbDef/`配下等）を
そのまま指定してもよい（DD-002-3で対応。実データソース定義`<DataSource type="drsum">`
は専用ロジックで解析する）。

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
├── main.py             # 全体を通しで実行するオーケストレーター
└── demo_data/          # 社内説明・デモ用の合成データ(詳細はdemo_data/README.md)
```

## 社内デモを見る

実際のDr.Sum/MotionBoardへの接続がまだなくても、このツールが何をするものかを
説明できるよう、[dummygen_jp_gui](../../dev_2/dummygen_jp_gui)(和風ダミーデータ
生成ツール)で作成した架空データ一式を`demo_data/`に用意してあります。

```bash
python main.py --demo
python web_viewer.py --db demo_data/lineage.db
```

`URIAGE_KIN`(売上金額/Revenue/売上)など、意図的に作り込んだ4件の表記ゆれが
ブラウザ上でハイライト表示されます。詳細は`demo_data/README.md`を参照してください。

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

実行すると41件のレコード(表示名としてのエイリアス38件＋カスタム項目・事後計算項目の
計算式内での使用3件)が検出され、表記ゆれ候補が4件（例: `URIAGE_KIN`が「売上金額」
「Revenue」「売上」の3通りで使われている、など）見つかるはずです。計算式内での
使用はエイリアスの表記ゆれ集計には含まれません。

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

さらに以下の3ファイルは、実物のバックアップでありがちな「ZIP圧縮」
「XML名前空間」「Shift-JIS文字コード」への対応を確認するための
回帰テスト用サンプルです。

- `board_zipped_backup.zip` … ZIP圧縮されたボード定義(中に`board_in_zip.xml`を含む)。展開せずメモリ上で直接解析する
- `board_namespaced.xml` … `<mb:Field mb:column="..." mb:label="..."/>`のようなXML名前空間プレフィックス付き
- `board_sjis_encoded.xml` … `<?xml version="1.0" encoding="Shift_JIS"?>`宣言のファイル。**修正前はPython標準のXMLパーサーがこの宣言を直接デコードできず例外で処理全体が止まっていた**(`board_parser.py`の`_parse_xml_bytes`で回避)

さらに以下の2ファイルは、カスタム項目・事後計算項目の計算式の中で使われている
物理カラムの検出（表示名としての完全一致ではなく、計算式の一部として部分文字列で
出現するケース）を確認するためのサンプルです。

- `board_custom_calc_field.xml` … `<CustomField formula="[URIAGE_KIN]/[TANKA]"/>`のように、計算式の中に複数の物理カラムが角括弧付きで埋め込まれている
- `board_post_calc_item.json` … `{"expression": "URIAGE_KIN / SUM(URIAGE_KIN) * 100"}`のように、事後計算項目(集計後の構成比計算等)の計算式に物理カラムが埋め込まれている

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

指定フォルダ以下のXML/JSON/ZIPファイルを再帰的に読み、既知のカラム名が
属性値やキー値としてどこかに出現していないか総当たりで探します。
見つかったら、その近くにある「カラム名とは違う文字列」を表示名
（エイリアス）候補として拾い、ボード名・アイテムIDも周辺のタグ・キーから
推測します。実行結果に「検出: xxx.xml → N件」と出れば成功です。

ZIPファイルは展開せずメモリ上で中のXML/JSONエントリを直接解析します
（実行結果には「検出: xxx.zip:entry.xml → N件」のように表示されます）。
また、XML名前空間プレフィックス付き（`<mb:Field mb:column="..."/>`）や
Shift-JIS文字コード宣言のファイルにも対応しています。

検証として、タグ名も属性名もまったく違う2種類のサンプル
（`label`属性を使うものと`caption`属性を使うもの）で試したところ、
どちらも正しく検出できることを確認済みです。

**表示名（エイリアス）だけでなく、カスタム項目・事後計算項目の計算式の中で
使われている物理カラムも検知します。** `formula`/`expression`など計算式らしい
キー名を持つ値や、`[URIAGE_KIN]/[TANKA]`のように演算子・角括弧を含む値の中から、
既知の物理カラム名をトークン単位（部分文字列として）で拾います。この使われ方は
表記ゆれの候補には数えず（`usage_type`が`alias`ではなく`calc`として区別され）、
ビューア上では別バッジで「カスタム項目/計算式で使用」として表示されます。
検出精度を調整したい場合は`board_parser.py`内の`FORMULA_KEY_HINTS`
（計算式らしいキー名のヒント）を実際のキー名の傾向に合わせて調整してください。

### ステップ3: 突き合わせて表記ゆれを検出する

```bash
python match_aliases.py --columns dr_sum_columns.json --aliases board_aliases.json
```

`lineage.db`（SQLite）にまとめて保存したうえで、以下5パターンの表記ゆれ・ズレ候補を
コンソールに一覧出力します。

- **1対多**: 同じ物理カラムに複数の表示名が使われているケース
- **多対1**: 異なる物理カラムに同じ表示名が付与されているケース（例: `T_売上.AMOUNT`と`T_受注.AMOUNT`がどちらも「金額」）
- **物理名直接使用**: エイリアスが設定されず、物理カラム名がそのまま表示名になっているケース
- **孤立項目（未使用カラム）**: Dr.Sum側に存在するが、MotionBoard定義で一度も使われていないカラム（計算式内での使用は「使用済み」とみなす）
- **類似度候補**: 標準ライブラリ`difflib`による類似度判定で見つかった、表記ゆれの可能性がある表示名の組み合わせ（要目視確認。文字種が全く異なる表記〔例:「コード」と「CD」〕は検出できません）

英語ダッシュボード向けの表記など、意図的な別名を候補から除外したい場合は
`naming_whitelist.json`（物理カラム単位で除外指定）を用意し、`--whitelist`で指定します。

```json
{
  "excluded_columns": [
    {"table_name": "T_売上明細", "column_name": "CHIIKI_KBN", "reason": "英語版ボード向けのRegion表記"}
  ]
}
```

```bash
python match_aliases.py --columns dr_sum_columns.json --aliases board_aliases.json \
    --whitelist naming_whitelist.json --similarity-threshold 0.8
```

`--whitelist`は1対多・多対1・類似度候補の3パターンにのみ適用されます（物理名直接使用・
孤立項目は事実の指摘であり除外対象ではありません）。`--similarity-threshold`は類似度候補の
判定しきい値（0〜1、デフォルト0.8）です。

### 結果をブラウザで見る

```bash
python web_viewer.py
```

`lineage.db`をもとに、検索・表記ゆれのハイライト付きの一覧をブラウザで
表示します。**`localhost`のみで待ち受ける設計であり、実行したPC上からしか
閲覧できません。複数人が使う共有サーバーに常時起動して使う用途には
対応していません**（そのような使い方をしたい場合は認証機構の追加が別途必要です）。

多対1マッピング候補・類似度候補は専用セクションで、物理名直接使用・未使用カラムは
一覧テーブル上のバッジ・ミュート表示で確認できます。`web_viewer.py`/`export_static.py`
も`match_aliases.py`と同じ`--whitelist`/`--similarity-threshold`オプションに対応しています。

検索ボックスは物理カラム名・テーブル名・表示名に加えボード名でも絞り込めます。統計
カード（表記ゆれ候補／物理名そのまま／未使用カラム）はクリックすると該当する行に
絞り込まれ（再クリックで解除）、ページ下部の「ボード別ドリルダウン」でボードを1つ
選ぶと、そのボードが使用している物理カラム→表示名の対応（エイリアス/計算式の種別・
アイテムIDつき）を一覧できます（DD-002-4）。

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

### 定義ファイルの取得・取り込みを自動化する（手動取得をやめたい場合）

- **Dr.Sum側**: `dr_sum_metadata.py`はJDBC経由でサーバーから直接カラム一覧を取得するので、
  そもそも手動でのファイルエクスポートは不要です。あとはこのコマンドをタスクスケジューラ等で
  定期実行するだけで、常に最新のカラム一覧が使われます。
- **MotionBoard側**: バックアップフォルダに`--watch`を付けて実行すると、前回実行からの
  新規/更新/削除ファイルだけを差分処理し、既存の`board_aliases.json`とマージします。
  MotionBoardのバッチ機能などが定義ファイルを随時吐き出すフォルダをそのまま指定し、
  このコマンドをタスクスケジューラ等で定期実行することで、都度のファイル取得・実行を
  手動で行う必要がなくなります。

```bash
python main.py --backup-dir path/to/backup/data/ --watch \
    --host <server> --db <dbname> --user <user> --jdbc-jar <jarのパス>
```

差分検出はファイルパス＋更新日時＋サイズによる簡易的な指紋比較です（内容のハッシュまでは
見ません）。差分検出用の状態は`board_aliases.json.watch_state.json`のような名前で
保存されます（`board_parser.py --watch-state`で明示的に指定することも可能です）。
`board_parser.py`単体で使う場合は以下のようになります。

```bash
python board_parser.py path/to/backup/data/ --columns dr_sum_columns.json \
    --out board_aliases.json --watch
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

- `board_parser.py` の自動検出精度: MotionBoardの実データソース定義
  （`<DataSource type="drsum">`、Dr.Sum接続ボード）は専用の抽出ロジック
  （`_parse_drsum_datasource`）で対応済み（DD-002-3、実機確認済み）。それ以外の
  形式（手動エクスポート・他製品連携等）で誤検出が多い場合は、引き続き
  `_looks_like_label_key` 等のヒント文字列(`LABEL_KEY_HINTS`など)を実際のキー名の
  傾向に合わせて調整する
- `board_parser.py` のカスタム項目・事後計算項目の計算式検出精度: Dr.Sum接続ボードの
  計算項目（`<ExField>`、`fid`による構造参照）はDD-002-3で対応済み。計算式が文字列
  として埋め込まれる形式（`FORMULA_KEY_HINTS`/`_FORMULA_OPERATOR_RE`が対象とする形式）
  で誤検出が多い場合は、実際のキー名・演算子の書き方に合わせて調整する
- `db_schema.sql`: 実データを見て型やインデックスを調整
