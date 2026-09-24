import sqlite3

import web_viewer as wv


def _make_db(tmp_path, rows):
    db_path = tmp_path / "lineage.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE columns (id INTEGER PRIMARY KEY, table_name TEXT, table_type TEXT, column_name TEXT, data_type TEXT);
        CREATE TABLE aliases (id INTEGER PRIMARY KEY, column_id INTEGER, display_name TEXT, board_name TEXT, item_id TEXT);
    """)
    for col_id, table_name, column_name, aliases in rows:
        conn.execute(
            "INSERT INTO columns (id, table_name, table_type, column_name, data_type) VALUES (?,?,?,?,?)",
            (col_id, table_name, "TABLE", column_name, "VARCHAR"),
        )
        for display_name, board_name in aliases:
            conn.execute(
                "INSERT INTO aliases (column_id, display_name, board_name, item_id) VALUES (?,?,?,?)",
                (col_id, display_name, board_name, "item1"),
            )
    conn.commit()
    conn.close()
    return str(db_path)


def test_fetch_data_single_alias(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("表示A", "board1")])])
    result = wv.fetch_data(db_path)
    assert len(result) == 1
    row = result[0]
    assert row["table_name"] == "T_A"
    assert row["column_name"] == "COL1"
    assert row["display_names"] == ["表示A"]
    assert row["alias_count"] == 1
    assert row["usage_count"] == 1
    assert row["boards"] == ["board1"]


def test_fetch_data_naming_variants(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("表示A", "board1"), ("表示B", "board2")])])
    result = wv.fetch_data(db_path)
    assert result[0]["alias_count"] == 2
    assert set(result[0]["display_names"]) == {"表示A", "表示B"}


def test_fetch_data_no_aliases(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [])])
    result = wv.fetch_data(db_path)
    assert result[0]["display_names"] == []
    assert result[0]["alias_count"] == 0
    assert result[0]["usage_count"] == 0
