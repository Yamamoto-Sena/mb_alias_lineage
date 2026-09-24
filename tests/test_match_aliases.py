import sqlite3

import match_aliases as ma

COLUMNS = [
    {"table_name": "T_A", "table_type": "TABLE", "column_name": "COL1", "data_type": "VARCHAR"},
]


def test_build_db_matches_known_column(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT table_name, column_name FROM columns").fetchall()
    conn.close()
    assert rows == [("T_A", "COL1")]


def test_build_db_unmatched_alias_falls_back_to_fumei(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_UNKNOWN", "column_name": "GHOST", "display_name": "幽霊", "board_name": "board1", "item_id": None},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT table_name, column_name FROM columns WHERE column_name='GHOST'").fetchall()
    conn.close()
    assert rows == [("T_UNKNOWN", "GHOST")]
    assert "見つからないエイリアス" in capsys.readouterr().out


def test_report_naming_inconsistencies_detects_variants(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示B", "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.report_naming_inconsistencies(str(db_path))
    out = capsys.readouterr().out
    assert "表記ゆれ候補: 1件" in out


def test_report_naming_inconsistencies_no_variants(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.report_naming_inconsistencies(str(db_path))
    out = capsys.readouterr().out
    assert "表記ゆれ候補は見つかりませんでした" in out
