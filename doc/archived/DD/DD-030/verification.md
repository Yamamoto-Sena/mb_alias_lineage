# DD-030 修正検証レポート

確認日: 2026-10-08
環境: `DATALIZER_PRACTICE`接続。実機MotionBoardコンテンツストア
(`C:\MotionBoard64\data\mb\mbds_def\mbDef\[My Boards]\Dr.SumDomain\Administrator\演習課題`)

---

## Bug#001: 結合データソースの構造的属性値が計算式の表示名として誤表示される

### テスト出力:
```
$ pytest -q（全回帰）
226 passed, 1 skipped in 4.91s
```

新規追加したユニットテスト(`tests/test_board_parser.py`):
- `TestFormulaHeuristicHelpers::test_looks_like_structural_value_rejects_index_flag_serialization` /
  `test_looks_like_structural_value_accepts_real_formula` /
  `test_looks_like_structural_value_accepts_formula_with_numeric_constant` — ガード関数単体の
  判定ロジック確認。自己レビューで「マッチしたカラム名以外が数字のみ」だけを条件にすると
  `TANKA * 2`のような数値定数を使う正当な計算式まで誤って除外してしまうことに気づき、
  `true`/`false`という真偽値リテラルの存在を必須条件に追加して過剰除外を防いだ
- `TestUnionDataSourceMappingNotTreatedAsCalc` — 実機で判明した
  `1/store_name/true//2//true//3//true/true` 相当の構造的属性値が計算式として誤抽出されない
  こと、通常のField/labelは従来どおり検出され続けること、実際の計算式(`/`を含む本物の
  カラム参照式)は引き続き検出されることを回帰テストで確認

### 実機データでの確認（予定外だが実機バックアップが本環境で参照可能だったため実施）:

修正前に取得済みの`board_aliases.json`(リポジトリ直下、実機接続時に生成)では、ボード
`09_結合データソース`配下に計15件のレコード(エイリアス14件＋バグの計算式1件)が記録されていた。

修正後の`board_parser.py`を実機コンテンツストア
(`09_結合データソース.fs-file`を含む`演習課題`フォルダ)に対して直接再実行
(`python board_parser.py "<演習課題フォルダ>" --columns real_columns.json --out <一時出力>`)した結果、
同ボードのレコードは14件(エイリアスのみ)となり、`T_STORE_KPI.store_name`の計算式レコード
(`display_name="1/store_name/true//2//true//3//true/true"`)が除去され、他の14件の正規エイリアスは
1件も欠落せず従来どおり検出されることを確認した。

| 項目 | 修正前 | 修正後 | 期待値 | 判定 |
|------|--------|--------|--------|------|
| `09_結合データソース`のレコード総数 | 15件(エイリアス14＋計算式(誤)1) | 14件(エイリアス14) | エイリアス14件のみ | OK |
| `T_STORE_KPI.store_name`の誤った計算式レコード | 存在する(`display_name`が構造的な生値) | 存在しない | 存在しない | OK |
| 他14件の正規エイリアス(`jisseki_nenji`/`branch_annual`の支店・年・累計実績額等) | 14件すべて検出 | 14件すべて検出(欠落なし) | 14件すべて検出 | OK |

**修正内容**: `board_parser.py`に`_looks_like_structural_value()`を追加。計算式検出で
マッチした物理カラム名トークン以外の全トークンが数字または真偽値リテラル(`true`/`false`)
のみで構成される値は、計算式ではなく構造的なシリアライズ値とみなして抽出対象から除外する
ようにした(`auto_parse_xml`・`auto_parse_json`の両方に適用)。

---

## 確認結果サマリー

| Bug# | 概要 | Before | After | エビデンス手段 | 判定 |
|------|------|--------|-------|--------------|------|
| 001 | 結合データソースの構造的シリアライズ値が計算式の表示名として誤表示される | `1/store_name/true//2//true//3//true/true`が表示名になる | 当該レコードが生成されなくなる(他のエイリアスは欠落なし) | テスト出力＋実機再実行 | PASS |
