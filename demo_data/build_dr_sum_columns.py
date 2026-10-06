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
SCHEMA_TYPE_COVERAGE = [
    ("T_配送案件", "TABLE", [
        ("配送案件コード", "VARCHAR"),
        ("受付日時", "TIMESTAMP"),
        ("出荷予定日", "DATE"),
        ("配送所要時間", "INTERVAL"),
        ("運賃", "NUMERIC"),
    ]),
    ("T_設備保守履歴", "TABLE", [
        ("保守履歴番号", "VARCHAR"),
        ("点検実施日", "DATE"),
        ("点検開始時刻", "TIME"),
        ("点検所要時間", "INTERVAL"),
        ("温度測定値", "REAL"),
        ("点検報告書添付ファイル", "OBJECT"),
    ]),
    ("T_契約情報", "TABLE", [
        ("契約番号", "VARCHAR"),
        ("契約開始日", "DATE"),
        ("契約締結日時", "TIMESTAMP"),
        ("契約更新猶予期間", "INTERVAL"),
        ("契約金額", "NUMERIC"),
        ("契約書スキャンファイル", "OBJECT"),
    ]),
    ("T_問い合わせ対応記録", "TABLE", [
        ("対応履歴番号", "VARCHAR"),
        ("受付日時", "TIMESTAMP"),
        ("対応開始時刻", "TIME"),
        ("対応所要時間", "INTERVAL"),
        ("満足度評価スコア", "REAL"),
        ("対応記録添付ファイル", "OBJECT"),
    ]),
    ("T_勤怠記録", "TABLE", [
        ("勤怠記録番号", "VARCHAR"),
        ("勤務日", "DATE"),
        ("出勤時刻", "TIME"),
        ("退勤時刻", "TIME"),
        ("休憩時間", "INTERVAL"),
        ("残業手当", "NUMERIC"),
        ("体温測定値", "REAL"),
    ]),
]


def main() -> None:
    columns_out = []
    for table_name, table_type, columns in SCHEMA + SCHEMA_TYPE_COVERAGE:
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
