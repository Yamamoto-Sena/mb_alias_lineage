# デモ用データセット

社内説明・デモ用の**架空データ**です。実際のDr.Sum/MotionBoardのデータは一切含みません。

## 構成

```
demo_data/
├── dummygen_jp_gui(C:\dev_2\dummygen_jp_gui)で設計したスキーマ
│   ├── dummygen_schema.yaml      # GUIのエクスポート機能で取得した実際の出力(業務テーマ13カラム分)
│   └── build_dr_sum_columns.py   # 上記+型カバレッジスキーマ→dr_sum_columns.json形式への変換スクリプト
├── dr_sum_type_schema/            # Dr.Sumの8型を網羅するために別途設計したスキーマの参考資料
│   ├── README.md                  # 作成経緯・データの作り方
│   └── テーブル定義.md             # テーブル・カラム定義書(型カバレッジ確認表つき)
├── dr_sum_columns.json           # Dr.Sum風のカラム一覧(業務テーマ13カラム+型カバレッジ30カラム=43カラム)
└── motionboard_backup/           # MotionBoard風のボード定義5件
    (sample_data/motionboard_backup/ の「実物に近い」サンプルと同じものを流用)
```

`dr_sum_columns.json`は、[dummygen_jp_gui](../../../dev_2/dummygen_jp_gui)(和風ダミーデータ生成ツールのGUI)を実際に操作して設計したテーブル・カラム構成をもとに作成しました。GUIの`/api/export_schema_yaml`エンドポイントで取得したYAMLが`dummygen_schema.yaml`です(ただし2026年現在、このエンドポイントは列ごとに手動指定した「データの型」を出力に含めない仕様のため、`build_dr_sum_columns.py`側で実際にGUIで指定した型を明示的に補っています)。

`dr_sum_type_schema/`は、DD-021（テーブル定義パネルの「データ型」欄改善）に伴い、Dr.Sumがサポートする8種類の型(REAL/NUMERIC/VARCHAR/INTERVAL/DATE/TIME/TIMESTAMP/OBJECT)がビューア上で一通り確認できるよう、同じdummygen_jp_guiで別途設計したスキーマです。実データ(各テーブル5,000行)はリポジトリサイズの都合で含めず、テーブル・カラム定義のみ`build_dr_sum_columns.py`の`SCHEMA_TYPE_COVERAGE`に転記しています。これらの物理カラムはMotionBoard側のエイリアス定義が無いため、ビューア上では「未使用」として表示されます(型表示の確認が目的のため、意図的な状態です)。

## 再現方法

```bash
python build_dr_sum_columns.py   # dr_sum_columns.json を作り直す(通常は再実行不要)
cd ..
python main.py --demo             # board_parser.py → match_aliases.py を一気通貫で実行
python web_viewer.py --db demo_data/lineage.db   # ブラウザで結果を見る
python export_static.py --db demo_data/lineage.db --out demo_data/column_alias_map_demo.html
```

`demo_data/board_aliases.json`・`demo_data/lineage.db`・`demo_data/column_alias_map_demo.html`は
実行のたびに作り直される生成物のため、`.gitignore`で追跡対象から除外しています。

## 想定している見せ方

`URIAGE_KIN`(売上金額/Revenue/売上)、`CHIIKI_KBN`(地域区分/エリア/Region)など、
同じ物理カラムがボードごとに異なる表示名で使われている「表記ゆれ」が4件見つかる
ように意図的に構成してあります。`python main.py --demo`実行後、`web_viewer.py`の
画面でこの表記ゆれがハイライト表示される様子がそのままデモになります。

`naming_whitelist.json`も用意してあり、`CHIIKI_KBN`を「英語ダッシュボード向けの
意図的な別名」として表記ゆれ候補から除外するサンプルになっています。
`python main.py --demo`はこのファイルが存在すれば自動的に読み込むため、実行前後で
`CHIIKI_KBN`が表記ゆれ候補から消えることを確認できます。
