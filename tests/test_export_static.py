import sqlite3

import export_static as es


def _make_db(tmp_path):
    db_path = tmp_path / "lineage.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE columns (id INTEGER PRIMARY KEY, table_name TEXT, table_type TEXT, column_name TEXT, data_type TEXT);
        CREATE TABLE aliases (id INTEGER PRIMARY KEY, column_id INTEGER, display_name TEXT, board_name TEXT, item_id TEXT, usage_type TEXT DEFAULT 'alias');
    """)
    conn.execute(
        "INSERT INTO columns (id, table_name, table_type, column_name, data_type) VALUES (1,'T_A','TABLE','COL1','VARCHAR')"
    )
    conn.execute(
        "INSERT INTO aliases (column_id, display_name, board_name, item_id, usage_type) VALUES (1,'表示A','board1','item1','alias')"
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


def test_build_static_html_escapes_script_close_tag_in_display_name(tmp_path):
    # display_nameに"</script>"のような文字列が混入していても、埋め込み用の
    # <script>タグが途中で終了してHTMLが壊れないことを確認する
    db_path = tmp_path / "lineage.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE columns (id INTEGER PRIMARY KEY, table_name TEXT, table_type TEXT, column_name TEXT, data_type TEXT);
        CREATE TABLE aliases (id INTEGER PRIMARY KEY, column_id INTEGER, display_name TEXT, board_name TEXT, item_id TEXT, usage_type TEXT DEFAULT 'alias');
    """)
    conn.execute(
        "INSERT INTO columns (id, table_name, table_type, column_name, data_type) VALUES (1,'T_A','TABLE','COL1','VARCHAR')"
    )
    conn.execute(
        "INSERT INTO aliases (column_id, display_name, board_name, item_id, usage_type) VALUES "
        "(1,'</script><script>alert(1)</script>','board1','item1','alias')"
    )
    conn.commit()
    conn.close()

    html = es.build_static_html(str(db_path))
    # 悪意あるdisplay_name由来の"</script>"はエスケープされ、ページ本来の
    # </script>(スクリプトブロックの終了タグ、1箇所だけ)しか残らないはず
    assert html.count("</script>") == 1
    assert "<\\/script>" in html


def test_build_static_html_warns_on_large_dataset(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(es, "warn_if_large", lambda n: print(f"warned:{n}"))
    es.build_static_html(_make_db(tmp_path))
    assert "warned:1" in capsys.readouterr().out


def test_build_static_html_embeds_patterns(tmp_path):
    html = es.build_static_html(_make_db(tmp_path))
    assert "EMBEDDED_PATTERNS" in html
    assert "fetch('/api/patterns')" not in html


def test_build_static_html_disables_whitelist_editing(tmp_path):
    # 静的エクスポートはサーバーを持たないため、追加・削除ボタンは無効化する(DD-003)
    html = es.build_static_html(_make_db(tmp_path))
    assert "let STATIC_EXPORT = true;" in html
    assert "fetch('/api/whitelist')" not in html


def test_build_static_html_embeds_whitelist_entries(tmp_path):
    html = es.build_static_html(
        _make_db(tmp_path),
        whitelist_entries=[{"table_name": "T_A", "column_name": "COL1", "reason": "テスト用"}],
    )
    assert "EMBEDDED_WHITELIST" in html
    assert "テスト用" in html
