"""board_parser.py が対応する「考えられる限りのデータパターン」を網羅的に検証する。

tests/test_manual_alias_extraction.py がフォルダ一括読み込み(auto_parse_all)での
「一種類の業務シナリオ」の動作確認だったのに対し、こちらは個々のヒューリスティック
経路(XML属性/テキスト/子要素ラベル、名前空間、文字コード、検索条件除外、JSON各形状、
実データソース形式、ZIP/入れ子ZIP、複数テーブル同名カラムの曖昧性解決、--watch差分、
.fs-file内部ストア)を1パターン1テストで独立に確認する(多くはinメモリのbytesで完結し、
ディスクに新規ファイルを置かない)。
"""
import io
import json
import os
import time
import zipfile

import board_parser as bp

COLUMNS = [
    {"table_name": "T_売上明細", "table_type": "TABLE", "column_name": "URIAGE_KIN", "data_type": "DECIMAL", "ordinal": 1},
    {"table_name": "T_売上明細", "table_type": "TABLE", "column_name": "CHIIKI_KBN", "data_type": "VARCHAR", "ordinal": 2},
    {"table_name": "T_商品M", "table_type": "TABLE", "column_name": "TANKA", "data_type": "DECIMAL", "ordinal": 1},
    {"table_name": "T_商品M", "table_type": "TABLE", "column_name": "SHOHIN_NAME", "data_type": "VARCHAR", "ordinal": 2},
    {"table_name": "T_在庫", "table_type": "TABLE", "column_name": "ZAIKO_SU", "data_type": "INTEGER", "ordinal": 1},
    {"table_name": "T_店舗在庫", "table_type": "TABLE", "column_name": "ZAIKO_SU", "data_type": "INTEGER", "ordinal": 1},
]


def make_index() -> bp.ColumnIndex:
    return bp.ColumnIndex(COLUMNS)


def _build_zip_bytes(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ============================================================
# XML: 値の表現パターン
# ============================================================
class TestQualifiedColumnReferenceXml:
    def test_table_dot_column_value_resolves_both(self):
        content = ('<Board name="仕入先別分析"><Item id="qual-001">'
                   '<Field source="T_商品M.TANKA" label="単価"/>'
                   '</Item></Board>')
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert len(records) == 1
        r = records[0]
        assert (r.column_name, r.table_name, r.display_name) == ("TANKA", "T_商品M", "単価")


class TestColumnNameAsElementText:
    def test_label_attribute_with_column_name_in_text_content(self):
        content = ('<Board name="単価確認一覧"><Item id="txt-001">'
                   '<Field label="単価">TANKA</Field>'
                   '</Item></Board>')
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert len(records) == 1
        assert records[0].column_name == "TANKA"
        assert records[0].display_name == "単価"


class TestLabelInChildElement:
    def test_display_name_child_element_used_as_label(self):
        content = ('<Board name="返品分析"><Item id="ret-001">'
                   '<Field column="TANKA"><DisplayName>単価</DisplayName></Field>'
                   '</Item></Board>')
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert len(records) == 1
        assert records[0].display_name == "単価"


class TestItemIdAlternateKeys:
    def test_seq_attribute_used_as_item_id(self):
        content = '<Board name="仕入分析"><Item seq="1"><Field column="TANKA" label="単価"/></Item></Board>'
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert records[0].item_id == "1"

    def test_itemNo_attribute_used_as_item_id(self):
        content = '<Board name="仕入分析"><Item itemNo="2"><Field column="SHOHIN_NAME" label="商品名"/></Item></Board>'
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert records[0].item_id == "2"


class TestBoardNameFromSiblingMetaElement:
    def test_meta_name_sibling_used_as_board_name(self):
        content = ('<Board><Meta name="顧客セグメント"/>'
                   '<Item id="seg-01"><Field column="SHOHIN_NAME" label="商品名"/></Item></Board>')
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert records[0].board_name == "顧客セグメント"


class TestNamespacePrefixedAttributes:
    def test_mb_prefixed_attributes_are_matched(self):
        content = ('<?xml version="1.0" encoding="UTF-8"?>'
                   '<mb:Board xmlns:mb="http://example.com/motionboard" mb:name="名前空間テスト">'
                   '<mb:Item mb:id="ns-001">'
                   '<mb:Field mb:column="TANKA" mb:label="単価"/>'
                   '</mb:Item></mb:Board>')
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert len(records) == 1
        r = records[0]
        assert r.display_name == "単価"
        assert r.board_name == "名前空間テスト"
        assert r.item_id == "ns-001"


class TestShiftJisEncodedXml:
    def test_shift_jis_declared_board_is_decoded_and_parsed(self):
        content = ('<?xml version="1.0" encoding="Shift_JIS"?>'
                   '<Board name="文字コード確認"><Item id="sjis-001">'
                   '<Field column="TANKA" label="単価"/>'
                   '</Item></Board>').encode("shift_jis")
        records = bp.auto_parse_xml("b.xml", content, make_index())
        assert len(records) == 1
        assert records[0].display_name == "単価"
        assert records[0].board_name == "文字コード確認"


class TestSearchConditionExcluded:
    """DD-023: 検索条件(事前設定フィルタ)のdispTitleはエイリアスではないので除外される。"""

    def test_disp_title_inside_search_condition_not_extracted(self):
        content = ('<?xml version="1.0" ?><BoardDefinition>'
                   '<Condition><SearchCondition><PreCondition>'
                   '<Expression title="TANKA" dispTitle="絞り込みキャプション"/>'
                   '</PreCondition></SearchCondition></Condition>'
                   '</BoardDefinition>')
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert records == []

    def test_sibling_field_outside_search_condition_still_extracted(self):
        content = ('<?xml version="1.0" ?><BoardDefinition>'
                   '<Field column="TANKA" label="単価"/>'
                   '<Condition><SearchCondition><PreCondition>'
                   '<Expression title="TANKA" dispTitle="絞り込みキャプション"/>'
                   '</PreCondition></SearchCondition></Condition>'
                   '</BoardDefinition>')
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert len(records) == 1
        assert records[0].display_name == "単価"


# ============================================================
# JSON: 値の表現パターン
# ============================================================
class TestQualifiedColumnReferenceJson:
    def test_qualified_value_in_json_resolves_table(self):
        content = json.dumps({"board": {"name": "商品単価JSON",
                                         "items": [{"itemId": "jq-1", "source": "T_商品M.TANKA", "label": "単価"}]}})
        records = bp.auto_parse_json("b.json", content.encode("utf-8"), make_index())
        assert len(records) == 1
        r = records[0]
        assert (r.column_name, r.table_name, r.display_name) == ("TANKA", "T_商品M", "単価")


class TestParallelArraysJson:
    def test_columns_and_display_names_arrays_zip_by_index(self):
        content = json.dumps({
            "board": {"name": "在庫単価一覧", "panels": [
                {"panelId": "arr-001", "columns": ["TANKA", "SHOHIN_NAME"],
                 "displayNames": ["単価", "商品名"]}
            ]}
        })
        records = bp.auto_parse_json("b.json", content.encode("utf-8"), make_index())
        by_col = {r.column_name: r.display_name for r in records}
        assert by_col == {"TANKA": "単価", "SHOHIN_NAME": "商品名"}


class TestLinkedLookupTablesJson:
    def test_field_defs_and_field_labels_joined_by_shared_id(self):
        content = json.dumps({
            "board": {"name": "仕入先分析", "fieldDefs": {"f1": {"col": "TANKA"}},
                      "fieldLabels": {"f1": "単価"}}
        })
        records = bp.auto_parse_json("b.json", content.encode("utf-8"), make_index())
        assert len(records) == 1
        assert records[0].column_name == "TANKA"
        assert records[0].display_name == "単価"
        assert records[0].item_id == "f1"


# ============================================================
# MotionBoardの実データソース定義(<DataSource type="drsum">)
# ============================================================
DRSUM_XML = """<?xml version="1.0" ?>
<DataSource name="手動検証用データソース" type="drsum" src="TESTDB/T_MANUAL_CHECK" srcName="T_MANUAL_CHECK" version="4.0.1">
  <Layout>
    <Field>
      <Item id="1" fid="1" title="order_no" aliasTitle="" type="VARCHAR"/>
      <Item id="2" fid="2" title="amount" aliasTitle="注文金額" type="NUMBER"/>
    </Field>
    <ExField>
      <Item id="1" fid="100" title="金額換算" type="VARCHAR">
        <DateGroups targetItemFid="2" format="yyyy/MM"/>
      </Item>
    </ExField>
  </Layout>
</DataSource>
"""


class TestDrSumDataSourceFormat:
    def _parse(self):
        return bp.auto_parse_xml("ds.xml", DRSUM_XML.encode("utf-8"), make_index())

    def test_unaliased_field_falls_back_to_physical_name(self):
        r = next(r for r in self._parse() if r.column_name == "ORDER_NO")
        assert r.display_name == "order_no"
        assert r.usage_type == "alias"

    def test_aliased_field_uses_alias_title(self):
        r = next(r for r in self._parse() if r.column_name == "AMOUNT" and r.usage_type == "alias")
        assert r.display_name == "注文金額"

    def test_table_name_from_src_name_attribute(self):
        assert all(r.table_name == "T_MANUAL_CHECK" for r in self._parse())

    def test_source_db_extracted_from_src_attribute(self):
        assert all(r.source_db == "TESTDB" for r in self._parse())

    def test_exfield_resolves_calc_via_fid_reference(self):
        r = next(r for r in self._parse() if r.usage_type == "calc")
        assert r.column_name == "AMOUNT"
        assert r.display_name == "金額換算"


# ============================================================
# ZIP圧縮・入れ子ZIP
# ============================================================
class TestZipCompressedBackup:
    def test_xml_entry_inside_zip_is_parsed(self):
        xml_bytes = ('<Board name="ZIP内ボード"><Item id="zip-001">'
                     '<Field column="TANKA" label="単価"/></Item></Board>').encode("utf-8")
        zip_bytes = _build_zip_bytes({"board1.xml": xml_bytes})
        records = bp._parse_zip_bytes(zip_bytes, make_index(), "z.zip", "z.zip")
        assert len(records) == 1
        assert records[0].display_name == "単価"
        assert records[0].source_file == "z.zip:board1.xml"

    def test_nested_zip_entry_is_parsed_recursively(self):
        inner = _build_zip_bytes({"inner_board": DRSUM_XML.encode("utf-8")})
        outer = _build_zip_bytes({"fs-xcabinets/0": inner})
        records = bp._parse_zip_bytes(outer, make_index(), "outer.zip", "outer.zip")
        assert any(r.table_name == "T_MANUAL_CHECK" for r in records)


# ============================================================
# 複数テーブルに同名カラムがある場合のテーブル曖昧性解決
# ============================================================
class TestAmbiguousColumnAcrossTables:
    def test_preferred_table_wins(self):
        index = make_index()
        assert index.resolve_table("ZAIKO_SU", [], preferred_table="T_店舗在庫") == "T_店舗在庫"
        assert index.resolve_table("ZAIKO_SU", [], preferred_table="T_在庫") == "T_在庫"

    def test_context_values_disambiguate_without_preferred_table(self):
        index = make_index()
        assert index.resolve_table("ZAIKO_SU", ["T_店舗在庫", "在庫数"]) == "T_店舗在庫"

    def test_falls_back_to_first_candidate_when_truly_ambiguous(self):
        index = make_index()
        assert index.resolve_table("ZAIKO_SU", []) in ("T_在庫", "T_店舗在庫")

    def test_end_to_end_xml_table_attribute_disambiguates(self):
        content = ('<Board name="店舗在庫一覧"><Item id="shop-001">'
                   '<Field column="ZAIKO_SU" label="在庫数" table="T_店舗在庫"/>'
                   '</Item></Board>')
        records = bp.auto_parse_xml("b.xml", content.encode("utf-8"), make_index())
        assert len(records) == 1
        assert records[0].table_name == "T_店舗在庫"


# ============================================================
# --watch 差分取り込み
# ============================================================
class TestIncrementalWatchParsing:
    def _columns_path(self, tmp_path):
        p = tmp_path / "columns.json"
        p.write_text(json.dumps(COLUMNS, ensure_ascii=False), encoding="utf-8")
        return p

    def test_new_file_parsed_on_first_run(self, tmp_path):
        root = tmp_path / "backup"
        root.mkdir()
        (root / "a.xml").write_text(
            '<Board name="A"><Item id="1"><Field column="TANKA" label="単価"/></Item></Board>', encoding="utf-8")
        out_path = tmp_path / "board_aliases.json"
        merged, summary = bp.incremental_parse(root, str(self._columns_path(tmp_path)), out_path)
        assert summary["changed"] == 1
        assert merged[0]["column_name"] == "TANKA"

    def test_unchanged_file_is_skipped_on_second_run(self, tmp_path, capsys):
        root = tmp_path / "backup"
        root.mkdir()
        (root / "a.xml").write_text(
            '<Board name="A"><Item id="1"><Field column="TANKA" label="単価"/></Item></Board>', encoding="utf-8")
        columns_path = self._columns_path(tmp_path)
        out_path = tmp_path / "board_aliases.json"
        merged1, _ = bp.incremental_parse(root, str(columns_path), out_path)
        out_path.write_text(json.dumps(merged1, ensure_ascii=False), encoding="utf-8")

        capsys.readouterr()
        merged2, summary2 = bp.incremental_parse(root, str(columns_path), out_path)
        assert summary2 == {"changed": 0, "removed": 0, "unchanged": 1, "total_records": 1}
        assert "検出:" not in capsys.readouterr().out

    def test_updated_file_replaces_old_records_other_files_untouched(self, tmp_path):
        root = tmp_path / "backup"
        root.mkdir()
        file_a = root / "a.xml"
        file_a.write_text('<Board name="A"><Item id="1"><Field column="TANKA" label="単価"/></Item></Board>',
                           encoding="utf-8")
        (root / "b.xml").write_text(
            '<Board name="B"><Item id="2"><Field column="SHOHIN_NAME" label="商品名"/></Item></Board>',
            encoding="utf-8")
        columns_path = self._columns_path(tmp_path)
        out_path = tmp_path / "board_aliases.json"
        merged1, _ = bp.incremental_parse(root, str(columns_path), out_path)
        out_path.write_text(json.dumps(merged1, ensure_ascii=False), encoding="utf-8")

        time.sleep(0.01)
        file_a.write_text('<Board name="A"><Item id="1"><Field column="TANKA" label="単価(改)"/></Item></Board>',
                           encoding="utf-8")
        os.utime(file_a, None)

        merged2, summary2 = bp.incremental_parse(root, str(columns_path), out_path)
        assert summary2["changed"] == 1
        assert summary2["unchanged"] == 1
        by_col = {r["column_name"]: r["display_name"] for r in merged2}
        assert by_col == {"TANKA": "単価(改)", "SHOHIN_NAME": "商品名"}

    def test_removed_file_drops_its_records_only(self, tmp_path):
        root = tmp_path / "backup"
        root.mkdir()
        file_a = root / "a.xml"
        file_a.write_text('<Board name="A"><Item id="1"><Field column="TANKA" label="単価"/></Item></Board>',
                           encoding="utf-8")
        (root / "b.xml").write_text(
            '<Board name="B"><Item id="2"><Field column="SHOHIN_NAME" label="商品名"/></Item></Board>',
            encoding="utf-8")
        columns_path = self._columns_path(tmp_path)
        out_path = tmp_path / "board_aliases.json"
        merged1, _ = bp.incremental_parse(root, str(columns_path), out_path)
        out_path.write_text(json.dumps(merged1, ensure_ascii=False), encoding="utf-8")

        file_a.unlink()
        merged2, summary2 = bp.incremental_parse(root, str(columns_path), out_path)
        assert summary2["removed"] == 1
        assert len(merged2) == 1
        assert merged2[0]["column_name"] == "SHOHIN_NAME"


# ============================================================
# .fs-file 内部ストア(fs-snap最新スナップショット走査)
# ============================================================
class TestFsFileInternalStore:
    def test_latest_snapshot_is_used_and_folder_name_overrides_board_name(self, tmp_path):
        root = tmp_path / "backup"
        board_dir = root / "手動検証ボード.fs-file"
        snap_dir = board_dir / "fs-snap"
        snap_dir.mkdir(parents=True)
        old_zip = _build_zip_bytes({"body": b'<?xml version="1.0" ?><Old/>'})
        new_zip = _build_zip_bytes({"body": DRSUM_XML.encode("utf-8")})
        (snap_dir / "snap_00000001_1000").write_bytes(old_zip)
        (snap_dir / "snap_00000002_2000").write_bytes(new_zip)

        columns_path = tmp_path / "columns.json"  # rootの外に置き、rglob("*.json")に巻き込まれないようにする
        columns_path.write_text(json.dumps(COLUMNS, ensure_ascii=False), encoding="utf-8")

        records = bp.auto_parse_all(root, str(columns_path))
        assert any(r.table_name == "T_MANUAL_CHECK" for r in records)
        # .fs-fileフォルダ名が、データソース定義自身のname属性より優先されてboard_nameになる(DD-017)
        assert all(r.board_name == "手動検証ボード" for r in records)
        assert not any(r.board_name == "手動検証用データソース" for r in records)

    def test_fs_file_without_snapshot_does_not_crash(self, tmp_path):
        root = tmp_path / "backup"
        (root / "空.fs-file" / "fs-snap").mkdir(parents=True)
        columns_path = tmp_path / "columns.json"
        columns_path.write_text(json.dumps(COLUMNS, ensure_ascii=False), encoding="utf-8")
        assert bp.auto_parse_all(root, str(columns_path)) == []
