# DD-028 バグ再現レポート

確認日: 2026-10-08
環境: 最小XMLフィクスチャ（実機再現は未実施。[cause-analysis.md](cause-analysis.md)の「未確認事項」参照 — `達成率ダッシュボード.fs-file`の現スナップショットが解析不能のため、同じ`disp="true"`構造を模したフィクスチャで代替）

---

## Bug#001: dsDef内`Item`要素の`disp`属性が、同一要素の物理カラム名属性のエイリアスとして誤抽出される

**現象**: `達成率ダッシュボード`(dsDef`月次売上明細`)で、`価格`・`会社名`・`地域`等ほぼ全列に`true`という無関係な値がエイリアスとして記録される([cause-analysis.md](cause-analysis.md)参照)。

### フィクスチャでの再現

実機で確認された構造（推定復元）を模した最小XMLを`auto_parse_xml()`に渡す:

```xml
<?xml version="1.0" ?><BoardDefinition name="達成率ダッシュボード">
<DsDef name="月次売上明細">
<Item id="9" fid="9" title="TANKA" aliasTitle="" type="NUMBER" disp="true" orderNum="9"/>
</DsDef>
</BoardDefinition>
```

（`title`の値は、サンプル定義ファイル(`sample_data/dr_sum_columns.json`)に実在する物理カラム名`TANKA`を使用。実機の`価格`相当。）

結果:

```json
[
  {
    "column_name": "TANKA",
    "display_name": "true",
    "board_name": "達成率ダッシュボード"
  }
]
```

`display_name`に本来無関係な表示フラグ値`"true"`が記録され、[cause-analysis.md](cause-analysis.md)で分析した原因（`aliasTitle`が空のため候補除外→属性キー`disp`が`LABEL_KEY_HINTS`の`"disp"`に完全一致→属性値`"true"`がラベルとして採用）と一致する再現結果が得られた。

## 確認結果サマリー

| Bug# | 概要 | 再現 | エビデンス手段 | 備考 |
|------|------|------|--------------|------|
| 001 | dsDef`Item`要素の`disp="true"` → カラムのエイリアスとして`true`が誤抽出 | OK | 最小XMLフィクスチャ(`auto_parse_xml`直接呼び出し) | 実機再現は未実施（スナップショット解析不能のためブロック中。[cause-analysis.md](cause-analysis.md)の「未確認事項」参照） |

## 次のステップ

Phase 0の残タスクはユーザーレビュー（修正方針A/B/Cの合意）。
