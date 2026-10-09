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


def test_build_db_stores_column_size_decimal_digits_nullable_unique(tmp_path):
    # DD-033: 精度・スケール・NULL許可・ユニークをcolumnsテーブルに保存する
    db_path = tmp_path / "lineage.db"
    columns = [
        {"table_name": "T_A", "table_type": "TABLE", "column_name": "COL1", "data_type": "NUMERIC",
         "column_size": 10, "decimal_digits": 2, "is_nullable": "NO", "is_unique": "YES"},
    ]
    ma.build_db(str(db_path), columns, [])

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT column_size, decimal_digits, is_nullable, is_unique FROM columns WHERE table_name='T_A'"
    ).fetchone()
    conn.close()
    assert row == (10, 2, "NO", "YES")


def test_build_db_defaults_column_size_decimal_digits_nullable_unique_to_null(tmp_path):
    # DD-033: 未指定の場合はNULLのまま保存される(実機で取得できない場合の挙動と同じ)
    db_path = tmp_path / "lineage.db"
    ma.build_db(str(db_path), COLUMNS, [])

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT column_size, decimal_digits, is_nullable, is_unique FROM columns WHERE table_name='T_A'"
    ).fetchone()
    conn.close()
    assert row == (None, None, None, None)


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


def test_build_db_excludes_alias_from_different_known_db(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_OTHER", "column_name": "COL1", "display_name": "他DB項目",
         "board_name": "board1", "item_id": "i1", "source_db": "OtherDB"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases, connected_db="Test")

    conn = sqlite3.connect(db_path)
    columns_rows = conn.execute("SELECT table_name, column_name FROM columns WHERE table_name='T_OTHER'").fetchall()
    excluded_rows = conn.execute(
        "SELECT source_db, table_name, column_name, display_name, board_name FROM excluded_aliases"
    ).fetchall()
    conn.close()
    assert columns_rows == []
    assert excluded_rows == [("OtherDB", "T_OTHER", "COL1", "他DB項目", "board1")]
    assert "別のDB用と分かったエイリアスが1件" in capsys.readouterr().out


def test_build_db_does_not_exclude_when_source_db_matches_connected_db(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A",
         "board_name": "board1", "item_id": "i1", "source_db": "Test"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases, connected_db="Test")

    conn = sqlite3.connect(db_path)
    alias_rows = conn.execute("SELECT display_name FROM aliases").fetchall()
    excluded_rows = conn.execute("SELECT * FROM excluded_aliases").fetchall()
    conn.close()
    assert alias_rows == [("表示A",)]
    assert excluded_rows == []


def test_build_db_does_not_exclude_when_source_db_unknown(tmp_path):
    # source_db未設定(汎用ヒューリスティック・手動モード等、所属DBを特定できない経路)の
    # エイリアスは、接続中DBと違う保証がないため除外せず、従来どおり不一致判定の対象にする
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_UNKNOWN", "column_name": "GHOST", "display_name": "幽霊",
         "board_name": "board1", "item_id": None},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases, connected_db="Test")

    conn = sqlite3.connect(db_path)
    columns_rows = conn.execute("SELECT table_name, column_name FROM columns WHERE column_name='GHOST'").fetchall()
    excluded_rows = conn.execute("SELECT * FROM excluded_aliases").fetchall()
    conn.close()
    assert columns_rows == [("T_UNKNOWN", "GHOST")]
    assert excluded_rows == []


def test_build_db_does_not_exclude_when_connected_db_not_given(tmp_path):
    # --connected-db未指定(--stub/--demo等)では除外ロジック自体を無効化し、従来どおりの挙動にする
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_OTHER", "column_name": "COL1", "display_name": "他DB項目",
         "board_name": "board1", "item_id": "i1", "source_db": "OtherDB"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases, connected_db=None)

    conn = sqlite3.connect(db_path)
    columns_rows = conn.execute("SELECT table_name, column_name FROM columns WHERE table_name='T_OTHER'").fetchall()
    excluded_rows = conn.execute("SELECT * FROM excluded_aliases").fetchall()
    conn.close()
    assert columns_rows == [("T_OTHER", "COL1")]
    assert excluded_rows == []


def test_build_db_exclusion_normalizes_fullwidth_and_case(tmp_path):
    # 全角/半角・大文字小文字の違いだけで誤って除外(または除外漏れ)しないことを確認
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A",
         "board_name": "board1", "item_id": "i1", "source_db": "ｔｅｓｔ"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases, connected_db="TEST")

    conn = sqlite3.connect(db_path)
    alias_rows = conn.execute("SELECT display_name FROM aliases").fetchall()
    excluded_rows = conn.execute("SELECT * FROM excluded_aliases").fetchall()
    conn.close()
    assert alias_rows == [("表示A",)]
    assert excluded_rows == []


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


def test_load_whitelist_returns_normalized_set(tmp_path):
    whitelist_path = tmp_path / "naming_whitelist.json"
    whitelist_path.write_text(
        '{"excluded_columns": [{"table_name": "T_A", "column_name": "col1", "reason": "意図的"}]}',
        encoding="utf-8",
    )
    result = ma.load_whitelist(str(whitelist_path))
    assert result == {("T_A", "COL1")}


def test_load_whitelist_empty_when_key_missing(tmp_path):
    whitelist_path = tmp_path / "naming_whitelist.json"
    whitelist_path.write_text('{}', encoding="utf-8")
    assert ma.load_whitelist(str(whitelist_path)) == set()


def test_report_naming_inconsistencies_excludes_whitelisted_column(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示B", "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.report_naming_inconsistencies(str(db_path), whitelist={("T_A", "COL1")})
    out = capsys.readouterr().out
    assert "表記ゆれ候補は見つかりませんでした" in out


def test_find_many_to_one_mappings_detects_shared_display_name_across_columns(tmp_path):
    db_path = tmp_path / "lineage.db"
    columns = [
        {"table_name": "T_URIAGE", "table_type": "TABLE", "column_name": "AMOUNT", "data_type": "DECIMAL"},
        {"table_name": "T_ORDER", "table_type": "TABLE", "column_name": "AMOUNT", "data_type": "DECIMAL"},
    ]
    aliases = [
        {"table_name": "T_URIAGE", "column_name": "AMOUNT", "display_name": "金額", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_ORDER", "column_name": "AMOUNT", "display_name": "金額", "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), columns, aliases)
    results = ma.find_many_to_one_mappings(str(db_path))
    assert len(results) == 1
    assert results[0]["display_name"] == "金額"
    assert len(results[0]["columns"]) == 2


def test_find_many_to_one_mappings_excludes_whitelisted_column(tmp_path):
    db_path = tmp_path / "lineage.db"
    columns = [
        {"table_name": "T_URIAGE", "table_type": "TABLE", "column_name": "AMOUNT", "data_type": "DECIMAL"},
        {"table_name": "T_ORDER", "table_type": "TABLE", "column_name": "AMOUNT", "data_type": "DECIMAL"},
    ]
    aliases = [
        {"table_name": "T_URIAGE", "column_name": "AMOUNT", "display_name": "金額", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_ORDER", "column_name": "AMOUNT", "display_name": "金額", "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), columns, aliases)
    # 片方だけホワイトリストに入れると、残り1カラムだけでは「多対1」にならないため候補から消える
    results = ma.find_many_to_one_mappings(str(db_path), whitelist={("T_URIAGE", "AMOUNT")})
    assert results == []


def test_find_many_to_one_mappings_ignores_same_column_multiple_display_names(tmp_path):
    # 同一カラム内の複数表示名(既存1対多検出の対象)は多対1の対象に含めない
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示B", "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    assert ma.find_many_to_one_mappings(str(db_path)) == []


def test_find_unaliased_columns_detects_raw_column_name_as_display_name(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "COL1", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    results = ma.find_unaliased_columns(str(db_path))
    assert results == [{"table_name": "T_A", "column_name": "COL1"}]


def test_find_unaliased_columns_normalizes_fullwidth_and_case(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "ｃｏｌ１", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    results = ma.find_unaliased_columns(str(db_path))
    assert results == [{"table_name": "T_A", "column_name": "COL1"}]


def test_find_unaliased_columns_ignores_when_alias_set(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    assert ma.find_unaliased_columns(str(db_path)) == []


def test_find_orphan_columns_detects_columns_with_no_alias_rows(tmp_path):
    db_path = tmp_path / "lineage.db"
    columns = [
        {"table_name": "T_A", "table_type": "TABLE", "column_name": "COL1", "data_type": "VARCHAR"},
        {"table_name": "T_A", "table_type": "TABLE", "column_name": "COL2", "data_type": "VARCHAR"},
    ]
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), columns, aliases)
    results = ma.find_orphan_columns(str(db_path))
    assert results == [{"table_name": "T_A", "column_name": "COL2"}]


def test_find_orphan_columns_treats_calc_only_usage_as_used(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "利益率", "board_name": "board1",
         "item_id": "i1", "usage_type": "calc"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    assert ma.find_orphan_columns(str(db_path)) == []


def test_find_orphan_columns_empty_when_all_used(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    assert ma.find_orphan_columns(str(db_path)) == []


def test_find_similar_display_name_pairs_detects_pair_above_threshold(tmp_path):
    # difflib.SequenceMatcherは文字ベースの類似度計算のため、送り仮名の有無のような
    # 表記ゆれは高いratioになる(「コード」/「CD」のような文字種が全く異なる表記ゆれは
    # 検出できない。これはdifflib採用時に許容した既知の精度限界)
    db_path = tmp_path / "lineage.db"
    columns = [
        {"table_name": "T_UKETSUKE", "table_type": "TABLE", "column_name": "UKETSUKE_BI", "data_type": "DATE"},
        {"table_name": "T_UKETSUKE", "table_type": "TABLE", "column_name": "UKETSUKE_YMD", "data_type": "DATE"},
    ]
    aliases = [
        {"table_name": "T_UKETSUKE", "column_name": "UKETSUKE_BI", "display_name": "受付日",
         "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_UKETSUKE", "column_name": "UKETSUKE_YMD", "display_name": "受付け日",
         "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), columns, aliases)
    results = ma.find_similar_display_name_pairs(str(db_path), threshold=0.8)
    assert len(results) == 1
    assert results[0]["ratio"] >= 0.8


def test_find_similar_display_name_pairs_excludes_below_threshold(tmp_path):
    db_path = tmp_path / "lineage.db"
    columns = [
        {"table_name": "T_A", "table_type": "TABLE", "column_name": "COL1", "data_type": "VARCHAR"},
        {"table_name": "T_A", "table_type": "TABLE", "column_name": "COL2", "data_type": "VARCHAR"},
    ]
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "顧客コード", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_A", "column_name": "COL2", "display_name": "在庫数", "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), columns, aliases)
    results = ma.find_similar_display_name_pairs(str(db_path), threshold=0.9)
    assert results == []


def test_find_similar_display_name_pairs_ignores_same_column_pairs(tmp_path):
    # 同一カラム内の複数表示名同士は比較対象に含めない(既存1対多検出の対象のため)
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "顧客コード", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_A", "column_name": "COL1", "display_name": "顧客ＣＤ", "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    results = ma.find_similar_display_name_pairs(str(db_path), threshold=0.5)
    assert results == []


def test_find_similar_display_name_pairs_excludes_whitelisted_column(tmp_path):
    db_path = tmp_path / "lineage.db"
    columns = [
        {"table_name": "T_UKETSUKE", "table_type": "TABLE", "column_name": "UKETSUKE_BI", "data_type": "DATE"},
        {"table_name": "T_UKETSUKE", "table_type": "TABLE", "column_name": "UKETSUKE_YMD", "data_type": "DATE"},
    ]
    aliases = [
        {"table_name": "T_UKETSUKE", "column_name": "UKETSUKE_BI", "display_name": "受付日",
         "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_UKETSUKE", "column_name": "UKETSUKE_YMD", "display_name": "受付け日",
         "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), columns, aliases)
    results = ma.find_similar_display_name_pairs(
        str(db_path), threshold=0.8, whitelist={("T_UKETSUKE", "UKETSUKE_BI")}
    )
    assert results == []


def test_report_many_to_one_mapping_no_candidates(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.report_many_to_one_mapping(str(db_path))
    assert "多対1マッピング候補は見つかりませんでした" in capsys.readouterr().out


def test_report_unaliased_columns_no_candidates(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.report_unaliased_columns(str(db_path))
    assert "物理名直接使用の候補は見つかりませんでした" in capsys.readouterr().out


def test_report_orphan_columns_no_candidates(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.report_orphan_columns(str(db_path))
    assert "孤立項目(未使用カラム)は見つかりませんでした" in capsys.readouterr().out


def test_report_similar_display_name_pairs_no_candidates(tmp_path, capsys):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    ma.report_similar_display_name_pairs(str(db_path))
    assert "類似度による表記ゆれ候補は見つかりませんでした" in capsys.readouterr().out


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


def test_collect_category_counts_matches_find_functions(tmp_path):
    db_path = tmp_path / "lineage.db"
    aliases = [
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示A", "board_name": "board1", "item_id": "i1"},
        {"table_name": "T_A", "column_name": "COL1", "display_name": "表示B", "board_name": "board2", "item_id": "i2"},
    ]
    ma.build_db(str(db_path), COLUMNS, aliases)
    counts = ma.collect_category_counts(str(db_path))
    assert counts["naming_inconsistencies"] == len(ma.find_naming_inconsistencies(str(db_path)))
    assert counts["many_to_one"] == len(ma.find_many_to_one_mappings(str(db_path)))
    assert counts["unaliased_columns"] == len(ma.find_unaliased_columns(str(db_path)))
    assert counts["orphan_columns"] == len(ma.find_orphan_columns(str(db_path)))
    assert counts["similar_display_name_pairs"] == len(ma.find_similar_display_name_pairs(str(db_path)))


def test_report_history_diff_first_run_has_no_previous(tmp_path, capsys):
    history_path = tmp_path / "run_history.json"
    ma.report_history_diff(str(history_path), {"naming_inconsistencies": 3})
    out = capsys.readouterr().out
    assert "前回実行なし" in out
    assert history_path.exists()


def test_report_history_diff_second_run_shows_delta(tmp_path, capsys):
    history_path = tmp_path / "run_history.json"
    ma.report_history_diff(str(history_path), {"naming_inconsistencies": 3})
    capsys.readouterr()

    ma.report_history_diff(str(history_path), {"naming_inconsistencies": 5})
    out = capsys.readouterr().out
    assert "前回3件から+2" in out


def test_report_history_diff_no_change(tmp_path, capsys):
    history_path = tmp_path / "run_history.json"
    ma.report_history_diff(str(history_path), {"naming_inconsistencies": 3})
    capsys.readouterr()

    ma.report_history_diff(str(history_path), {"naming_inconsistencies": 3})
    out = capsys.readouterr().out
    assert "変化なし" in out


def test_load_whitelist_entries_missing_file_returns_empty_list(tmp_path):
    path = tmp_path / "naming_whitelist.json"
    assert ma.load_whitelist_entries(str(path)) == []


def test_add_whitelist_entry_creates_file_when_missing(tmp_path):
    path = tmp_path / "naming_whitelist.json"
    entries = ma.add_whitelist_entry(str(path), "T_A", "COL1", reason="テスト用")
    assert entries == [{"table_name": "T_A", "column_name": "COL1", "reason": "テスト用"}]
    assert path.exists()
    assert ma.load_whitelist_entries(str(path)) == entries


def test_add_whitelist_entry_reason_defaults_to_empty_string(tmp_path):
    path = tmp_path / "naming_whitelist.json"
    entries = ma.add_whitelist_entry(str(path), "T_A", "COL1")
    assert entries[0]["reason"] == ""


def test_add_whitelist_entry_is_idempotent_for_same_column(tmp_path):
    path = tmp_path / "naming_whitelist.json"
    ma.add_whitelist_entry(str(path), "T_A", "COL1", reason="1回目")
    entries = ma.add_whitelist_entry(str(path), "T_A", "COL1", reason="2回目")
    assert len(entries) == 1
    assert entries[0]["reason"] == "1回目"  # 既存エントリは上書きしない


def test_add_whitelist_entry_matches_existing_entry_by_normalized_key(tmp_path):
    path = tmp_path / "naming_whitelist.json"
    ma.add_whitelist_entry(str(path), "T_A", "COL1")
    entries = ma.add_whitelist_entry(str(path), "ｔ_ａ", "ｃｏｌ１")  # 全角/大小文字違い
    assert len(entries) == 1


def test_remove_whitelist_entry_removes_matching_entry(tmp_path):
    path = tmp_path / "naming_whitelist.json"
    ma.add_whitelist_entry(str(path), "T_A", "COL1")
    ma.add_whitelist_entry(str(path), "T_B", "COL2")
    entries = ma.remove_whitelist_entry(str(path), "T_A", "COL1")
    assert entries == [{"table_name": "T_B", "column_name": "COL2", "reason": ""}]
    assert ma.load_whitelist_entries(str(path)) == entries


def test_remove_whitelist_entry_missing_entry_is_noop(tmp_path):
    path = tmp_path / "naming_whitelist.json"
    ma.add_whitelist_entry(str(path), "T_A", "COL1")
    entries = ma.remove_whitelist_entry(str(path), "T_X", "COL_X")
    assert len(entries) == 1
