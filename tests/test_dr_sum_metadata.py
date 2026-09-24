import dr_sum_metadata as dsm


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
