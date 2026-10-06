import sqlite3

import web_viewer as wv


def _make_db(tmp_path, rows, calc_aliases=None):
    """rows: [(col_id, table_name, column_name, [(display_name, board_name), ...])]
    calc_aliases (省略可): [(col_id, display_name, board_name)] usage_type='calc'で登録する。"""
    db_path = tmp_path / "lineage.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE columns (id INTEGER PRIMARY KEY, table_name TEXT, table_type TEXT, column_name TEXT, data_type TEXT);
        CREATE TABLE aliases (id INTEGER PRIMARY KEY, column_id INTEGER, display_name TEXT, board_name TEXT, item_id TEXT, usage_type TEXT DEFAULT 'alias');
    """)
    for col_id, table_name, column_name, aliases in rows:
        conn.execute(
            "INSERT INTO columns (id, table_name, table_type, column_name, data_type) VALUES (?,?,?,?,?)",
            (col_id, table_name, "TABLE", column_name, "VARCHAR"),
        )
        for display_name, board_name in aliases:
            conn.execute(
                "INSERT INTO aliases (column_id, display_name, board_name, item_id, usage_type) VALUES (?,?,?,?,'alias')",
                (col_id, display_name, board_name, "item1"),
            )
    for col_id, display_name, board_name in (calc_aliases or []):
        conn.execute(
            "INSERT INTO aliases (column_id, display_name, board_name, item_id, usage_type) VALUES (?,?,?,?,'calc')",
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


def test_fetch_data_includes_data_type(tmp_path):
    # DD-020: 物理カラム名クリック時のテーブル定義パネルでデータ型を表示するため
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("表示A", "board1")])])
    result = wv.fetch_data(db_path)
    assert result[0]["data_type"] == "VARCHAR"


def test_fetch_data_naming_variants(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("表示A", "board1"), ("表示B", "board2")])])
    result = wv.fetch_data(db_path)
    assert result[0]["alias_count"] == 2
    assert set(result[0]["display_names"]) == {"表示A", "表示B"}


def test_fetch_data_no_aliases(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [])])
    result = wv.fetch_data(db_path)
    assert result[0]["display_names"] == []
    assert result[0]["calc_names"] == []
    assert result[0]["alias_count"] == 0
    assert result[0]["usage_count"] == 0


def test_fetch_data_calc_usage_is_separated_from_aliases(tmp_path):
    db_path = _make_db(
        tmp_path,
        [(1, "T_A", "COL1", [("表示A", "board1")])],
        calc_aliases=[(1, "利益率", "board3")],
    )
    result = wv.fetch_data(db_path)
    row = result[0]
    assert row["display_names"] == ["表示A"]
    assert row["calc_names"] == ["利益率"]
    assert row["alias_count"] == 1  # calc側は表記ゆれ集計に含めない
    assert row["usage_count"] == 2  # 使用件数(延べ)には両方カウントされる


def test_fetch_data_flags_unaliased_column(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("COL1", "board1")])])
    result = wv.fetch_data(db_path)
    assert result[0]["is_unaliased"] is True


def test_fetch_data_does_not_flag_when_alias_set(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("表示A", "board1")])])
    result = wv.fetch_data(db_path)
    assert result[0]["is_unaliased"] is False


def test_fetch_data_flags_orphan_column(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [])])
    result = wv.fetch_data(db_path)
    assert result[0]["is_orphan"] is True


def test_fetch_data_does_not_flag_orphan_when_used(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("表示A", "board1")])])
    result = wv.fetch_data(db_path)
    assert result[0]["is_orphan"] is False


def test_fetch_data_flags_naming_variant_when_alias_count_over_one(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("表示A", "board1"), ("表示B", "board2")])])
    result = wv.fetch_data(db_path)
    assert result[0]["is_naming_variant"] is True


def test_fetch_data_whitelist_suppresses_naming_variant_flag(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [("表示A", "board1"), ("表示B", "board2")])])
    result = wv.fetch_data(db_path, whitelist={("T_A", "COL1")})
    assert result[0]["is_naming_variant"] is False
    assert result[0]["alias_count"] == 2  # alias_count自体は保持する(表示件数として使うため)


def test_fetch_cross_column_patterns_detects_many_to_one(tmp_path):
    db_path = _make_db(tmp_path, [
        (1, "T_A", "COL1", [("金額", "board1")]),
        (2, "T_B", "COL1", [("金額", "board2")]),
    ])
    patterns = wv.fetch_cross_column_patterns(db_path)
    assert len(patterns["many_to_one"]) == 1
    assert patterns["many_to_one"][0]["display_name"] == "金額"


def test_fetch_cross_column_patterns_excludes_whitelisted_column(tmp_path):
    db_path = _make_db(tmp_path, [
        (1, "T_A", "COL1", [("金額", "board1")]),
        (2, "T_B", "COL1", [("金額", "board2")]),
    ])
    patterns = wv.fetch_cross_column_patterns(db_path, whitelist={("T_A", "COL1")})
    assert patterns["many_to_one"] == []


def test_fetch_board_details_returns_flat_alias_records(tmp_path):
    db_path = _make_db(tmp_path, [
        (1, "T_A", "COL1", [("表示A", "board1"), ("表示B", "board2")]),
    ])
    details = wv.fetch_board_details(db_path)
    assert len(details) == 2
    board1 = next(d for d in details if d["board_name"] == "board1")
    assert board1["table_name"] == "T_A"
    assert board1["column_name"] == "COL1"
    assert board1["display_name"] == "表示A"
    assert board1["usage_type"] == "alias"


def test_fetch_board_details_separates_calc_usage_type(tmp_path):
    db_path = _make_db(
        tmp_path,
        [(1, "T_A", "COL1", [("表示A", "board1")])],
        calc_aliases=[(1, "利益率", "board1")],
    )
    details = wv.fetch_board_details(db_path)
    usage_types = {d["display_name"]: d["usage_type"] for d in details}
    assert usage_types["表示A"] == "alias"
    assert usage_types["利益率"] == "calc"


def test_fetch_board_details_empty_db_returns_empty_list(tmp_path):
    db_path = _make_db(tmp_path, [(1, "T_A", "COL1", [])])
    assert wv.fetch_board_details(db_path) == []


def test_warn_if_large_below_threshold_is_silent(capsys):
    wv.warn_if_large(wv.LARGE_DATASET_WARNING_THRESHOLD)
    assert capsys.readouterr().out == ""


def test_warn_if_large_above_threshold_prints_warning(capsys):
    wv.warn_if_large(wv.LARGE_DATASET_WARNING_THRESHOLD + 1)
    assert "表示が重くなる可能性があります" in capsys.readouterr().out
