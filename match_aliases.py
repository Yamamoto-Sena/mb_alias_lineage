"""
フェーズ3: dr_sum_metadata.py の出力(dr_sum_columns.json)と
board_parser.py の出力(board_aliases.json)を突き合わせ、
SQLite(lineage.db)に保存したうえで、表記ゆれ候補を一覧表示する。

使い方:
    python match_aliases.py --columns dr_sum_columns.json --aliases board_aliases.json
"""
import argparse
import json
import sqlite3
from pathlib import Path


def load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_db(db_path: str, columns: list, aliases: list) -> None:
    schema_path = Path(__file__).parent / "db_schema.sql"
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    cur = conn.cursor()

    # カラムを登録し、table_name+column_name -> id の対応表を作る
    column_id_map = {}
    for col in columns:
        cur.execute(
            """
            INSERT OR IGNORE INTO columns (table_name, table_type, column_name, data_type)
            VALUES (?, ?, ?, ?)
            """,
            (col["table_name"], col.get("table_type"), col["column_name"], col.get("data_type")),
        )
        cur.execute(
            "SELECT id FROM columns WHERE table_name=? AND column_name=?",
            (col["table_name"], col["column_name"]),
        )
        row = cur.fetchone()
        if row:
            column_id_map[(col["table_name"], col["column_name"])] = row[0]

    # エイリアスを登録。Dr.Sum側にカラムが見つからない場合は警告して table_name="(不明)" で仮登録
    unmatched = 0
    for alias in aliases:
        key = (alias["table_name"], alias["column_name"])
        column_id = column_id_map.get(key)
        if column_id is None:
            unmatched += 1
            cur.execute(
                """
                INSERT OR IGNORE INTO columns (table_name, table_type, column_name, data_type)
                VALUES (?, '(不明)', ?, NULL)
                """,
                (alias["table_name"] or "(不明)", alias["column_name"]),
            )
            cur.execute(
                "SELECT id FROM columns WHERE table_name=? AND column_name=?",
                (alias["table_name"] or "(不明)", alias["column_name"]),
            )
            column_id = cur.fetchone()[0]
            column_id_map[key] = column_id

        cur.execute(
            """
            INSERT INTO aliases (column_id, display_name, board_name, item_id)
            VALUES (?, ?, ?, ?)
            """,
            (column_id, alias["display_name"], alias["board_name"], alias.get("item_id")),
        )

    conn.commit()
    conn.close()

    if unmatched:
        print(f"※ Dr.Sum側のカラム一覧に見つからないエイリアスが{unmatched}件ありました"
              f"（テーブル名の表記ゆれや、取得漏れの可能性があります）")


def report_naming_inconsistencies(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.table_name, c.column_name,
               COUNT(DISTINCT a.display_name) AS alias_count,
               GROUP_CONCAT(DISTINCT a.display_name) AS display_names,
               COUNT(*) AS usage_count
        FROM aliases a
        JOIN columns c ON c.id = a.column_id
        GROUP BY c.id
        HAVING alias_count > 1
        ORDER BY alias_count DESC, usage_count DESC
        """
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("表記ゆれ候補は見つかりませんでした")
        return

    print(f"\n表記ゆれ候補: {len(rows)}件\n" + "-" * 60)
    for table_name, column_name, alias_count, display_names, usage_count in rows:
        print(f"[{table_name}].{column_name}")
        print(f"  表示名({alias_count}種): {display_names}")
        print(f"  使用ボード数(延べ): {usage_count}件\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--columns", required=True, help="dr_sum_metadata.pyの出力ファイル")
    parser.add_argument("--aliases", required=True, help="board_parser.pyの出力ファイル")
    parser.add_argument("--db", default="lineage.db")
    args = parser.parse_args()

    columns = load_json(args.columns)
    aliases = load_json(args.aliases)

    build_db(args.db, columns, aliases)
    print(f"{args.db} にデータを保存しました\n")
    report_naming_inconsistencies(args.db)


if __name__ == "__main__":
    main()
