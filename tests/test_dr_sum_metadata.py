import sys

import pytest

import dr_sum_metadata as dsm


class _FailingCursor:
    def execute(self, query):
        raise RuntimeError("system catalog not found")

    def fetchall(self):
        return []

    def close(self):
        pass


class _FakeConnection:
    def cursor(self):
        return _FailingCursor()


class _RecordingCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed_query = None

    def execute(self, query):
        self.executed_query = query

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _RecordingConnection:
    def __init__(self, rows):
        self.cursor_obj = _RecordingCursor(rows)

    def cursor(self):
        return self.cursor_obj


def test_connect_raises_friendly_error_for_missing_jar(tmp_path):
    connector = dsm.DrSumConnector(
        host="h", database="d", user="u", password="p",
        jdbc_jar=str(tmp_path / "does_not_exist.jar"),
    )
    with pytest.raises(dsm.DrSumConnectionError, match="jarファイルが見つかりません"):
        connector.connect()


def test_connect_raises_friendly_error_when_library_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "jaydebeapi", None)  # importが必ずImportErrorになるようにする
    jar = tmp_path / "fake.jar"
    jar.write_bytes(b"")
    connector = dsm.DrSumConnector(host="h", database="d", user="u", password="p", jdbc_jar=str(jar))
    with pytest.raises(dsm.DrSumConnectionError, match="jaydebeapi"):
        connector.connect()


def test_fetch_columns_wraps_query_error():
    connector = dsm.DrSumConnector(host="h", database="d", user="u", password="p", jdbc_jar="whatever.jar")
    connector._conn = _FakeConnection()
    with pytest.raises(dsm.DrSumConnectionError, match="システムカタログ"):
        connector.fetch_columns()


def test_fetch_columns_stub_shape():
    columns = dsm.fetch_columns_stub()
    assert len(columns) == 4
    assert all(isinstance(c, dsm.ColumnMeta) for c in columns)
    assert columns[0].table_name == "T_売上明細"
    assert columns[0].column_name == "URIAGE_KIN"


def test_build_jdbc_url_dwods_format():
    # DD-002-2で確定したシンプル形式(jdbc:dwods:<host>:<port>:<database>)を検証する。
    connector = dsm.DrSumConnector(
        host="myhost", database="mydb", user="u", password="p",
        jdbc_jar="dummy.jar", port=6001,
    )
    assert connector._build_jdbc_url() == "jdbc:dwods:myhost:6001:mydb"


def test_connect_uses_confirmed_driver_class_and_url(tmp_path, monkeypatch):
    jar = tmp_path / "fake.jar"
    jar.write_bytes(b"")
    captured = {}

    class _FakeJaydebeapi:
        @staticmethod
        def connect(driver_class, url, credentials, jar_path):
            captured["driver_class"] = driver_class
            captured["url"] = url
            return "connection"

    monkeypatch.setitem(sys.modules, "jaydebeapi", _FakeJaydebeapi)
    connector = dsm.DrSumConnector(
        host="myhost", database="mydb", user="u", password="p",
        jdbc_jar=str(jar), port=6001,
    )
    connector.connect()
    assert captured["driver_class"] == "jp.co.dw_sapporo.JDBC.JDBCDriver"
    assert captured["url"] == "jdbc:dwods:myhost:6001:mydb"


def test_fetch_columns_filters_by_assortment_column():
    conn = _RecordingConnection(rows=[])
    connector = dsm.DrSumConnector(host="h", database="d", user="u", password="p", jdbc_jar="whatever.jar")
    connector._conn = conn
    connector.fetch_columns()
    query = conn.cursor_obj.executed_query
    assert "__all_tables__" in query
    assert "assortment" in query
    assert "'column'" in query


def test_fetch_columns_assigns_ordinal_per_table_in_return_order():
    rows = [
        ("T_売上明細", "URIAGE_KIN", "DECIMAL"),
        ("T_売上明細", "CHIIKI_KBN", "VARCHAR"),
        ("T_顧客M", "KOKYAKU_CD", "VARCHAR"),
    ]
    conn = _RecordingConnection(rows)
    connector = dsm.DrSumConnector(host="h", database="d", user="u", password="p", jdbc_jar="whatever.jar")
    connector._conn = conn
    columns = connector.fetch_columns()
    assert columns == [
        dsm.ColumnMeta(table_name="T_売上明細", table_type="TABLE", column_name="URIAGE_KIN", data_type="DECIMAL", ordinal=1),
        dsm.ColumnMeta(table_name="T_売上明細", table_type="TABLE", column_name="CHIIKI_KBN", data_type="VARCHAR", ordinal=2),
        dsm.ColumnMeta(table_name="T_顧客M", table_type="TABLE", column_name="KOKYAKU_CD", data_type="VARCHAR", ordinal=1),
    ]
