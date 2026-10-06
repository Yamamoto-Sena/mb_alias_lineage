# DD-019 原因分析

## Bug#001: DATALIZER_PRACTICEのカラム数が合わない（足りない/多い）

**ファイル**: `dr_sum_metadata.py` L85-127 `DrSumConnector.fetch_columns()`

**現象**: Dr.SumのDB名`Test`に接続し`DATALIZER_PRACTICE`テーブルのカラム一覧を取得すると、
実際のテーブル定義と比べてカラム数が一致しない（足りない、または多い）。

**現在のクエリ**（L98-102）:
```sql
SELECT table_name, column_name, column_type
FROM __all_tables__
WHERE assortment = 'column'
```

**疑わしい点（実機確認が必要・未確定）**:

1. **テーブル種別を区別していない**: [DD-002-2](../../archived/DD/DD-002-2_Dr.Sum実環境対応.md)
   の決定事項で「ビュー・マルチビュー・ディストリビューターを区別する専用値は
   本環境では確認されなかったため、それらの除外は現時点でスコープ外」とされている。
   `DATALIZER_PRACTICE`がこれらの特殊種別だった場合、`__all_tables__`上での
   `assortment='column'`行の意味（実列か、参照元の列が重複して載るか等）が
   通常テーブルと異なる可能性がある。
2. **`ORDER BY`無しの返却順への依存**: `ordinal_by_table`（L115-126）は
   DBが返す行の順序をそのまま列定義順として採番している。DD-002-2で確認済みなのは
   `T_EC_CUSTOMER`等の3テーブルのみで、`DATALIZER_PRACTICE`では未確認。
   SQL標準上`ORDER BY`無しの順序保証は無いため、テーブル・データ量によって
   順序が変わる可能性がある。
3. **`assortment`の値がテーブルによって異なる可能性**: DD-002-2のPhase 1確認は
   `'table'`と`'column'`の2値のみだったが、確認対象は限定的な環境であり、
   `DATALIZER_PRACTICE`固有の値（例: 計算列・隠し列等）が存在する可能性を排除できない。

**再現手順**:
1. Dr.SumサーバーにDB名`Test`、ユーザー`Administrator`等で接続
2. `python dr_sum_metadata.py --host <host> --db Test --user <user> --jdbc-jar <jar> --out dr_sum_columns.json`を実行
3. 出力された`dr_sum_columns.json`内の`DATALIZER_PRACTICE`のカラム一覧と、
   Dr.Sum管理画面上の実際の列定義を比較する

**次のアクション**: Phase 0の実機診断SQL（DD本体参照）の結果を待って、上記1〜3のどれが
原因かを特定し、修正方針を決定する。
