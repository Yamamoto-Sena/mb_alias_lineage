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


def test_build_jdbc_url_current_placeholder_format():
    # 実環境向けにURL書式(dr_sum_metadata.pyのTODO)を変更したら、このテストは
    # 意図的に落ちる。そのときはテストとTODOコメントの両方を実環境の値に更新すること。
    connector = dsm.DrSumConnector(
        host="myhost", database="mydb", user="u", password="p",
        jdbc_jar="dummy.jar", port=6001,
    )
    assert connector._build_jdbc_url() == "jdbc:dsjdbc://myhost:6001/mydb"
