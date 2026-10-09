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

SCHEMA_TYPE_COVERAGE(DD-021関連。テーブル定義パネルの「データ型」欄の改善に伴い、
Dr.Sumがサポートする8種類の型を一通り画面上で確認できるようにするため追加)は、
同じdummygen_jp_guiで別途設計したスキーマ(demo_data/dr_sum_type_schema/を参照。
TIME/TIMESTAMP/INTERVAL/OBJECTはdummygen_jp_guiにネイティブ対応する型が無いため
後処理で追加したもので、実データ(5,000行/テーブル)はリポジトリに含めず定義のみ転記)。

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

# Dr.Sumがサポートする8種類の型(REAL/NUMERIC/VARCHAR/INTERVAL/DATE/TIME/TIMESTAMP/OBJECT)を
# 偏りなくカバーするための追加スキーマ。詳細はdemo_data/dr_sum_type_schema/テーブル定義.md参照。
# 既存SCHEMAとテーブル名・カラム名の重複が無いことを確認済み。MotionBoard側のエイリアス定義は
# 無いため、これらの物理カラムはビューア上で「未使用」として表示される(型表示の確認が目的のため)
#
# DD-033: 各列は (column_name, data_type, column_size, decimal_digits, is_nullable, is_unique)。
# 精度・スケール・NULL可否は同フォルダのテーブル定義.mdの記載を転記。is_unique="YES"は
# README記載の「各コード列(配送案件コード等)は5,000行すべてでユニーク」を確認済みの列のみ
# (それ以外は未確認のためNoneのまま=テーブル定義パネルでは「-」表示になる)
SCHEMA_TYPE_COVERAGE = [
    ("T_配送案件", "TABLE", [
        ("配送案件コード", "VARCHAR", 20, None, "NO", "YES"),
        ("受付日時", "TIMESTAMP", None, None, "NO", None),
        ("出荷予定日", "DATE", None, None, "YES", None),
        ("配送所要時間", "INTERVAL", None, None, "YES", None),
        ("運賃", "NUMERIC", 10, 2, "YES", None),
    ]),
    ("T_設備保守履歴", "TABLE", [
        ("保守履歴番号", "VARCHAR", 20, None, "NO", "YES"),
        ("点検実施日", "DATE", None, None, "NO", None),
        ("点検開始時刻", "TIME", None, None, "YES", None),
        ("点検所要時間", "INTERVAL", None, None, "YES", None),
        ("温度測定値", "REAL", None, None, "YES", None),
        ("点検報告書添付ファイル", "OBJECT", None, None, "YES", None),
    ]),
    ("T_契約情報", "TABLE", [
        ("契約番号", "VARCHAR", 20, None, "NO", "YES"),
        ("契約開始日", "DATE", None, None, "NO", None),
        ("契約締結日時", "TIMESTAMP", None, None, "YES", None),
        ("契約更新猶予期間", "INTERVAL", None, None, "YES", None),
        ("契約金額", "NUMERIC", 12, 2, "YES", None),
        ("契約書スキャンファイル", "OBJECT", None, None, "YES", None),
    ]),
    ("T_問い合わせ対応記録", "TABLE", [
        ("対応履歴番号", "VARCHAR", 20, None, "NO", "YES"),
        ("受付日時", "TIMESTAMP", None, None, "NO", None),
        ("対応開始時刻", "TIME", None, None, "YES", None),
        ("対応所要時間", "INTERVAL", None, None, "YES", None),
        ("満足度評価スコア", "REAL", None, None, "YES", None),
        ("対応記録添付ファイル", "OBJECT", None, None, "YES", None),
    ]),
    ("T_勤怠記録", "TABLE", [
        ("勤怠記録番号", "VARCHAR", 20, None, "NO", "YES"),
        ("勤務日", "DATE", None, None, "NO", None),
        ("出勤時刻", "TIME", None, None, "YES", None),
        ("退勤時刻", "TIME", None, None, "YES", None),
        ("休憩時間", "INTERVAL", None, None, "YES", None),
        ("残業手当", "NUMERIC", 10, 2, "YES", None),
        ("体温測定値", "REAL", None, None, "YES", None),
    ]),
]


def main() -> None:
    columns_out = []
    for table_name, table_type, columns in SCHEMA + SCHEMA_TYPE_COVERAGE:
        for ordinal, col in enumerate(columns, start=1):
            # DD-033: SCHEMA(精度等の情報なし)は(column_name, data_type)の2要素のまま、
            # SCHEMA_TYPE_COVERAGEは(column_name, data_type, column_size, decimal_digits,
            # is_nullable, is_unique)の6要素。どちらの形式でも動くよう後ろをNoneで埋める
            column_name, data_type, column_size, decimal_digits, is_nullable, is_unique = (
                tuple(col) + (None,) * (6 - len(col))
            )
            columns_out.append({
                "table_name": table_name,
                "table_type": table_type,
                "column_name": column_name,
                "data_type": data_type,
                "ordinal": ordinal,
                "column_size": column_size,
                "decimal_digits": decimal_digits,
                "is_nullable": is_nullable,
                "is_unique": is_unique,
            })

    OUT_PATH.write_text(
        json.dumps(columns_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(columns_out)}件のカラム情報を {OUT_PATH} に出力しました")


if __name__ == "__main__":
    main()
