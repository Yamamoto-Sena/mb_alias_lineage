import sqlite3

import export_static as es


def _make_db(tmp_path):
    db_path = tmp_path / "lineage.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE columns (id INTEGER PRIMARY KEY, table_name TEXT, table_type TEXT, column_name TEXT, data_type TEXT);
        CREATE TABLE aliases (id INTEGER PRIMARY KEY, column_id INTEGER, display_name TEXT, board_name TEXT, item_id TEXT);
    """)
    conn.execute(
        "INSERT INTO columns (id, table_name, table_type, column_name, data_type) VALUES (1,'T_A','TABLE','COL1','VARCHAR')"
    )
    conn.execute(
        "INSERT INTO aliases (column_id, display_name, board_name, item_id) VALUES (1,'表示A','board1','item1')"
    )
    conn.commit()
    conn.close()
    return str(db_path)


def test_build_static_html_embeds_data_and_removes_fetch_call(tmp_path):
    html = es.build_static_html(_make_db(tmp_path))
    assert "EMBEDDED_DATA" in html
    assert "fetch('/api/columns')" not in html
    assert "表示A" in html


def test_build_static_html_includes_generated_timestamp(tmp_path):
    html = es.build_static_html(_make_db(tmp_path))
    assert "時点のスナップショット" in html
