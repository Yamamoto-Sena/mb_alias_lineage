"""
dummygen_jp_gui(C:\\dev_2\\dummygen_jp_gui)で設計したスキーマを、
mb_alias_lineage が期待する dr_sum_columns.json 形式に変換する。

このファイルの SCHEMA は、GUIの複数テーブル編集画面で実際に設定した内容と
同じもの(隣にある dummygen_schema.yaml は、そのときGUIの
POST /api/export_schema_yaml から取得した実際の出力)。

dummygen_jp_guiの/api/export_schema_yamlは、GUIの「データの型(省略可)」欄で
手動指定した型(data_type)を出力に含めない(2026年時点の仕様)。そのため、
GUIで実際に指定した型をこのスクリプト側で明示的に補っている。
テーブル種別(TABLE/VIEW)もDr.Sum側の一覧特有の情報なのでここで明示する。

使い方:
    python build_dr_sum_columns.py
"""
import json
from pathlib import Path

OUT_PATH = Path(__file__).parent / "dr_sum_columns.json"

# GUIで設定した内容(dummygen_schema.yaml と同じ)。
# 各列の data_type は、GUIの「データの型(省略可)」欄で手動指定したもの
# (未指定の列は integer→INTEGER 等、型からそのまま採用)
SCHEMA = [
    ("T_売上明細", "TABLE", [
        ("URIAGE_KIN", "DECIMAL"),
        ("CHIIKI_KBN", "VARCHAR"),
        ("URIAGE_DATE", "DATE"),
        ("SHOHIN_CD", "VARCHAR"),
    ]),
    ("T_顧客M", "TABLE", [
        ("KOKYAKU_CD", "VARCHAR"),
        ("KOKYAKU_NAME", "VARCHAR"),
        ("GYOSHU_CD", "VARCHAR"),
    ]),
    ("T_在庫", "TABLE", [
        ("ZAIKO_SU", "INTEGER"),
        ("SOKO_CD", "VARCHAR"),
    ]),
    ("T_商品M", "TABLE", [
        ("SHOHIN_CD", "VARCHAR"),
        ("SHOHIN_NAME", "VARCHAR"),
        ("TANKA", "DECIMAL"),
    ]),
    ("V_売上_月次集計", "VIEW", [
        ("GETSUJI_URIAGE", "DECIMAL"),
    ]),
]


def main() -> None:
    columns_out = []
    for table_name, table_type, columns in SCHEMA:
        for ordinal, (column_name, data_type) in enumerate(columns, start=1):
            columns_out.append({
                "table_name": table_name,
                "table_type": table_type,
                "column_name": column_name,
                "data_type": data_type,
                "ordinal": ordinal,
            })

    OUT_PATH.write_text(
        json.dumps(columns_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(columns_out)}件のカラム情報を {OUT_PATH} に出力しました")


if __name__ == "__main__":
    main()
