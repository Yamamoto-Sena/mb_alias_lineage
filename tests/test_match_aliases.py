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


def test_build_db_rerun_is_idempotent(tmp_path):
    # 同じ入力で2回実行しても、aliases/columnsの行数が増殖しないこと(重複追記バグの回帰テスト)
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.build_db(str(db_path), COLUMNS, aliases)

    conn = sqlite3.connect(db_path)
    alias_count = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    column_count = conn.execute("SELECT COUNT(*) FROM columns").fetchone()[0]
    conn.close()
    assert alias_count == 1
    assert column_count == 1


def test_build_db_stores_usage_type_and_source_file(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "利益率", "board_name": "board1",
         "item_id": "i1", "usage_type": "calc", "source_file": "board1.xml"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT usage_type, source_file FROM aliases").fetchone()
    conn.close()
    assert row == ("calc", "board1.xml")


def test_build_db_defaults_usage_type_to_alias_when_absent(tmp_path):
    # 既存呼び出し(usage_type/source_fileキー無し)との後方互換性
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT usage_type FROM aliases").fetchone()
    conn.close()
    assert row == ("alias",)


def test_report_naming_inconsistencies_ignores_calc_usage(tmp_path, capsys):
    # 同じカラムが複数の計算式で使われていても、それは「表記ゆれ」ではないので
    # 通常のエイリアス(usage_type='alias')だけで判定する
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_A", "column_name": "COL1", "display_name": "利益率", "board_name": "board2",
         "item_id": "i2", "usage_type": "calc"},
        {"table_name": "T_A", "column_name": "COL1", "display_name": "税込金額", "board_name": "board3",
         "item_id": "i3", "usage_type": "calc"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.report_naming_inconsistencies(str(db_path))
    out = capsys.readouterr().out
    assert "表記ゆれ候補は見つかりませんでした" in out
    assert "計算式内で使用されている項目: 2件" in out


def test_build_db_normalizes_fullwidth_and_case(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        # 全角+小文字での参照でも、正規化キーでDr.Sum側の"T_A"."COL1"と一致するはず
        {"table_name": "ｔ_ａ", "column_name": "ｃｏｌ１", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT table_name, column_name FROM columns").fetchall()
    conn.close()
    assert rows == [("T_A", "COL1")]  # "(不明)"として仮登録されていない
    assert "正規化により追加で一致した" in capsys.readouterr().out
