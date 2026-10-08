import io
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import board_parser as bp

FIXTURES = Path(__file__).parent.parent / "sample_data"
BACKUP_DIR = FIXTURES / "motionboard_backup"
COLUMNS_PATH = FIXTURES / "dr_sum_columns.json"


def load_index() -> bp.ColumnIndex:
    columns = json.loads(COLUMNS_PATH.read_text(encoding="utf-8"))
    return bp.ColumnIndex(columns)


def all_records():
    return bp.auto_parse_all(BACKUP_DIR, str(COLUMNS_PATH))


def find(records, board_name, item_id, column_name):
    matches = [r for r in records
               if r.board_name == board_name and r.item_id == item_id and r.column_name == column_name]
    assert matches, f"レコードが見つからない: board={board_name} item={item_id} col={column_name}"
    return matches[0]


class TestAutoParseAllTotals:
    def test_total_record_count(self):
        assert len(all_records()) == 41

    def test_sample_data_file_count(self):
        assert len(list(BACKUP_DIR.glob("*.xml"))) == 12
        assert len(list(BACKUP_DIR.glob("*.json"))) == 4
        assert len(list(BACKUP_DIR.glob("*.zip"))) == 1


class TestRegressionPatterns:
    """直近セッションで修正した7パターンが、今後も正しく検出され続けることを固定する回帰テスト。"""

    def test_label_in_child_element(self):
        r = find(all_records(), "返品分析", "ret-001", "TANKA")
        assert r.display_name == "単価"
        assert r.table_name == "T_商品M"

    def test_column_name_in_element_text(self):
        r = find(all_records(), "単価確認一覧", "txt-001", "TANKA")
        assert r.display_name == "単価"

    def test_qualified_column_reference(self):
        r = find(all_records(), "仕入先別分析", "qual-001", "TANKA")
        assert r.display_name == "単価"
        assert r.table_name == "T_商品M"

    def test_board_name_in_child_element(self):
        r = find(all_records(), "単価マスタ確認", "title-001", "TANKA")
        assert r.display_name == "単価"

    def test_item_id_alt_key(self):
        records = all_records()
        r1 = find(records, "仕入分析", "1", "TANKA")
        r2 = find(records, "仕入分析", "2", "SHOHIN_NAME")
        assert r1.display_name == "単価"
        assert r2.display_name == "商品名"

    def test_linked_lookup_tables_json(self):
        r = find(all_records(), "仕入先分析", "f1", "TANKA")
        assert r.display_name == "単価"

    def test_parallel_arrays_json(self):
        r = find(all_records(), "在庫単価一覧", "arr-001", "TANKA")
        assert r.display_name == "単価"


class TestAdditionalRobustnessPatterns:
    """ZIP圧縮・XML名前空間・Shift-JIS宣言への対応を固定する回帰テスト。"""

    def test_xml_namespace_prefix(self):
        # <mb:Field mb:column="..." mb:label="..."/> のような名前空間プレフィックス付き属性
        r = find(all_records(), "名前空間テスト", "ns-001", "TANKA")
        assert r.display_name == "単価"

    def test_shift_jis_declared_xml(self):
        # <?xml version="1.0" encoding="Shift_JIS"?>
        # 修正前はexpatが直接デコードできず"multi-byte encodings are not
        # supported"で例外になり、auto_parse_all全体がクラッシュしていた。
        r = find(all_records(), "文字コード確認", "sjis-001", "TANKA")
        assert r.display_name == "単価"

    def test_zip_compressed_backup(self):
        # ZIP内のXML/JSONエントリを展開せずメモリ上で解析できる
        r = find(all_records(), "ZIP内ボード", "zip-001", "TANKA")
        assert r.display_name == "単価"


class TestPreExistingBugFix:
    def test_customer_segment_board_name_from_sibling_meta(self):
        # <Meta name="..."/> が兄弟要素にある構造。修正前はファイル名にフォールバックしていた。
        r = find(all_records(), "顧客セグメント", "seg-item-01", "KOKYAKU_CD")
        assert r.display_name == "顧客コード"


class TestCalcFieldDetection:
    """カスタム項目・事後計算項目の計算式の中で使われている物理カラムの検出。
    エイリアスとして完全一致するわけではないので、usage_type='calc'で区別される。"""

    def test_custom_field_formula_xml(self):
        records = all_records()
        matches = [r for r in records
                   if r.board_name == "利益率分析" and r.item_id == "calc-001"
                   and r.usage_type == "calc"]
        columns_found = {r.column_name for r in matches}
        assert columns_found == {"URIAGE_KIN", "TANKA"}
        for r in matches:
            assert r.display_name == "単価換算売上"
            assert r.source_file == "board_custom_calc_field.xml"

    def test_post_calc_item_expression_json(self):
        r = find(all_records(), "地域別構成比", "postcalc-001", "URIAGE_KIN")
        assert r.usage_type == "calc"
        assert r.display_name == "売上構成比"
        assert r.source_file == "board_post_calc_item.json"

    def test_calc_records_do_not_pollute_ordinary_aliases(self):
        # 通常のエイリアス(usage_type='alias')の件数は今回の追加で変化しないはず
        alias_records = [r for r in all_records() if r.usage_type == "alias"]
        assert len(alias_records) == 38


class TestFormulaHeuristicHelpers:
    def test_looks_like_formula_key(self):
        assert bp._looks_like_formula_key("formula") is True
        assert bp._looks_like_formula_key("expression") is True
        assert bp._looks_like_formula_key("calcType") is True
        assert bp._looks_like_formula_key("name") is False
        assert bp._looks_like_formula_key(None) is False

    def test_looks_like_formula_value(self):
        assert bp._looks_like_formula_value("[URIAGE_KIN]/[TANKA]") is True
        assert bp._looks_like_formula_value("URIAGE_KIN * 1.1") is True
        assert bp._looks_like_formula_value("SUM(URIAGE_KIN)") is True
        # ハイフンだけ(IDや日付でありがち)では計算式とは判定しない
        assert bp._looks_like_formula_value("item-001") is False
        assert bp._looks_like_formula_value("単価換算売上") is False

    def test_find_columns_in_formula(self):
        index = load_index()
        found = bp._find_columns_in_formula(index, "[URIAGE_KIN]/[TANKA]")
        assert found == ["URIAGE_KIN", "TANKA"]

    def test_find_columns_in_formula_dedupes(self):
        index = load_index()
        found = bp._find_columns_in_formula(index, "URIAGE_KIN / SUM(URIAGE_KIN) * 100")
        assert found == ["URIAGE_KIN"]

    def test_find_columns_in_formula_no_match(self):
        index = load_index()
        assert bp._find_columns_in_formula(index, "1 + 1") == []

    def test_record_root_file_strips_zip_entry(self):
        assert bp._record_root_file("backup.zip:entry.xml") == "backup.zip"
        assert bp._record_root_file("plain.xml") == "plain.xml"
        assert bp._record_root_file(None) == ""


class TestIncrementalParse:
    """--watch (差分取り込み)の挙動。ファイルの追加/変更/削除に応じて
    board_aliases.json をマージ更新し、変わっていないファイルは再処理しない。"""

    def _write(self, path, content):
        path.write_text(content, encoding="utf-8")

    def test_first_run_parses_everything(self, tmp_path):
        root = tmp_path / "backup"
        root.mkdir()
        self._write(root / "a.xml", '<Board name="A"><Item id="1">'
                                     '<Field column="URIAGE_KIN" label="売上"/></Item></Board>')
        columns_path = tmp_path / "columns.json"
        columns_path.write_text(json.dumps([{"table_name": "T_売上明細", "table_type": "TABLE",
                                              "column_name": "URIAGE_KIN", "data_type": "DECIMAL", "ordinal": 1}]),
                                 encoding="utf-8")
        out_path = tmp_path / "board_aliases.json"

        merged, summary = bp.incremental_parse(root, str(columns_path), out_path)

        assert summary == {"changed": 1, "removed": 0, "unchanged": 0, "total_records": 1}
        assert merged[0]["column_name"] == "URIAGE_KIN"
        assert (tmp_path / "board_aliases.json.watch_state.json").exists()

    def test_second_run_skips_unchanged_file(self, tmp_path, capsys):
        root = tmp_path / "backup"
        root.mkdir()
        self._write(root / "a.xml", '<Board name="A"><Item id="1">'
                                     '<Field column="URIAGE_KIN" label="売上"/></Item></Board>')
        columns_path = tmp_path / "columns.json"
        columns_path.write_text(json.dumps([{"table_name": "T_売上明細", "table_type": "TABLE",
                                              "column_name": "URIAGE_KIN", "data_type": "DECIMAL", "ordinal": 1}]),
                                 encoding="utf-8")
        out_path = tmp_path / "board_aliases.json"

        merged1, _ = bp.incremental_parse(root, str(columns_path), out_path)
        out_path.write_text(json.dumps(merged1, ensure_ascii=False), encoding="utf-8")

        capsys.readouterr()
        merged2, summary2 = bp.incremental_parse(root, str(columns_path), out_path)
        assert summary2 == {"changed": 0, "removed": 0, "unchanged": 1, "total_records": 1}
        assert merged2 == merged1
        assert "検出:" not in capsys.readouterr().out

    def test_changed_file_is_reparsed_and_old_records_replaced(self, tmp_path):
        root = tmp_path / "backup"
        root.mkdir()
        file_a = root / "a.xml"
        self._write(file_a, '<Board name="A"><Item id="1">'
                             '<Field column="URIAGE_KIN" label="売上"/></Item></Board>')
        columns_path = tmp_path / "columns.json"
        columns_path.write_text(json.dumps([{"table_name": "T_売上明細", "table_type": "TABLE",
                                              "column_name": "URIAGE_KIN", "data_type": "DECIMAL", "ordinal": 1}]),
                                 encoding="utf-8")
        out_path = tmp_path / "board_aliases.json"

        merged1, _ = bp.incremental_parse(root, str(columns_path), out_path)
        out_path.write_text(json.dumps(merged1, ensure_ascii=False), encoding="utf-8")

        # 表示名を変更し、mtimeも確実に更新されるようずらす
        import os
        import time
        time.sleep(0.01)
        self._write(file_a, '<Board name="A"><Item id="1">'
                             '<Field column="URIAGE_KIN" label="売上高"/></Item></Board>')
        os.utime(file_a, None)

        merged2, summary2 = bp.incremental_parse(root, str(columns_path), out_path)
        assert summary2["changed"] == 1
        assert len(merged2) == 1
        assert merged2[0]["display_name"] == "売上高"

    def test_removed_file_drops_its_records(self, tmp_path):
        root = tmp_path / "backup"
        root.mkdir()
        file_a = root / "a.xml"
        self._write(file_a, '<Board name="A"><Item id="1">'
                             '<Field column="URIAGE_KIN" label="売上"/></Item></Board>')
        columns_path = tmp_path / "columns.json"
        columns_path.write_text(json.dumps([{"table_name": "T_売上明細", "table_type": "TABLE",
                                              "column_name": "URIAGE_KIN", "data_type": "DECIMAL", "ordinal": 1}]),
                                 encoding="utf-8")
        out_path = tmp_path / "board_aliases.json"

        merged1, _ = bp.incremental_parse(root, str(columns_path), out_path)
        out_path.write_text(json.dumps(merged1, ensure_ascii=False), encoding="utf-8")

        file_a.unlink()
        merged2, summary2 = bp.incremental_parse(root, str(columns_path), out_path)
        assert summary2["removed"] == 1
        assert merged2 == []


class TestColumnIndex:
    def test_match_exact(self):
        index = load_index()
        assert index.match("URIAGE_KIN") == "URIAGE_KIN"
        assert index.match(" urIAGE_kin ") == "URIAGE_KIN"

    def test_match_none_for_unknown(self):
        assert load_index().match("NOT_A_COLUMN") is None

    def test_resolve_table_single_candidate(self):
        assert load_index().resolve_table("ZAIKO_SU", []) == "T_在庫"

    def test_resolve_table_multiple_candidates_uses_preferred(self):
        # SHOHIN_CD は T_売上明細 と T_商品M の両方に存在する
        index = load_index()
        assert index.resolve_table("SHOHIN_CD", [], preferred_table="T_商品M") == "T_商品M"


class TestExtractMatch:
    def test_direct_match(self):
        assert bp._extract_match(load_index(), "TANKA") == ("TANKA", None)

    def test_qualified_match(self):
        assert bp._extract_match(load_index(), "T_商品M.TANKA") == ("TANKA", "T_商品M")

    def test_no_match(self):
        assert bp._extract_match(load_index(), "NOT_A_COLUMN") is None


class TestHeuristicHelpers:
    def test_contains_japanese(self):
        assert bp._contains_japanese("売上金額") is True
        assert bp._contains_japanese("Revenue") is False

    def test_looks_like_label_key(self):
        assert bp._looks_like_label_key("dispName") is True
        assert bp._looks_like_label_key("column") is False

    def test_looks_like_id_key(self):
        assert bp._looks_like_id_key("itemNo") is True
        assert bp._looks_like_id_key("seq") is True
        assert bp._looks_like_id_key("column") is False

    def test_local_tag_strips_namespace(self):
        assert bp._local_tag("{http://example.com/ns}Title") == "Title"
        assert bp._local_tag("Title") == "Title"


class TestParseXmlBytes:
    def test_utf8_bytes(self):
        root = bp._parse_xml_bytes('<Board name="テスト"/>'.encode("utf-8"))
        assert root.tag == "Board"

    def test_shift_jis_declared_bytes(self):
        content = '<?xml version="1.0" encoding="Shift_JIS"?><Board name="テスト"/>'.encode("shift_jis")
        root = bp._parse_xml_bytes(content)
        assert root.attrib["name"] == "テスト"

    def test_malformed_xml_raises(self):
        import pytest
        with pytest.raises(ET.ParseError):
            bp._parse_xml_bytes(b"<Board><Unclosed>")


class TestAutoParseXmlDoesNotCrashOnBadFiles:
    def test_malformed_xml_returns_empty_list_not_exception(self):
        assert bp.auto_parse_xml("broken.xml", b"<Board><Unclosed>", load_index()) == []

    def test_undecodable_declared_encoding_returns_empty_list(self):
        content = b'<?xml version="1.0" encoding="not-a-real-encoding"?><Board name="x"/>'
        assert bp.auto_parse_xml("broken.xml", content, load_index()) == []


# ============================================================
# DD-002-3: MotionBoardの実データソース定義(<DataSource type="drsum">)専用ロジック
# ============================================================
# 実機確認で得た構造を模した合成XML(実ファイルはコミットしない)。列名・ボード名は
# 架空のものに置き換えてある。
DRSUM_DATASOURCE_XML = """<?xml version="1.0" ?>
<DataSource name="テストデータソース" type="drsum" comId="Dr.Sum"
            src="Test/T_SAMPLE" dispSrc="Dr.Sum/Test/T_SAMPLE" srcName="T_SAMPLE" version="4.0.1">
  <Layout>
    <Field>
      <Item id="1" fid="1" title="product_code" aliasTitle="" type="VARCHAR" disp="true"/>
      <Item id="2" fid="2" title="sale_date" aliasTitle="" type="DATE" disp="true"/>
      <Item id="3" fid="3" title="amount" aliasTitle="売上金額" type="NUMBER" disp="true"/>
    </Field>
    <ExField>
      <Item id="1" fid="10000" title="販売年月" aliasTitle="" type="VARCHAR" exType="DATE_GROUPING" disp="false">
        <DateGroups dateType="DATE" targetItemFid="2" format="yyyy/MM"/>
      </Item>
      <Item id="2" fid="10001" title="未解決の計算項目" aliasTitle="" type="VARCHAR" exType="DATE_GROUPING" disp="false">
        <DateGroups dateType="DATE" targetItemFid="0" format="yyyy/MM"/>
      </Item>
    </ExField>
  </Layout>
</DataSource>
"""


class TestDrSumDataSourceFormat:
    def _parse(self):
        return bp.auto_parse_xml("ds.xml", DRSUM_DATASOURCE_XML.encode("utf-8"), load_index())

    def test_table_name_from_src_name_attribute(self):
        records = self._parse()
        assert all(r.table_name == "T_SAMPLE" for r in records)

    def test_source_db_extracted_from_src_attribute(self):
        # DD-026: src="Test/T_SAMPLE"の"/"より前がDB名
        records = self._parse()
        assert all(r.source_db == "Test" for r in records)

    def test_source_db_empty_when_src_has_no_slash(self):
        content = ('<?xml version="1.0" ?><DataSource name="x" type="drsum" '
                   'src="NoSlashHere" srcName="T_SAMPLE" version="4.0.1">'
                   '<Layout><Field><Item id="1" fid="1" title="COL1" aliasTitle=""/></Field></Layout>'
                   '</DataSource>')
        records = bp.auto_parse_xml("ds.xml", content.encode("utf-8"), load_index())
        assert all(r.source_db == "" for r in records)

    def test_empty_alias_title_uses_physical_name_as_display_name(self):
        r = find(self._parse(), "テストデータソース", "1", "PRODUCT_CODE")
        assert r.display_name == "product_code"
        assert r.usage_type == "alias"

    def test_non_empty_alias_title_is_used_as_display_name(self):
        r = find(self._parse(), "テストデータソース", "3", "AMOUNT")
        assert r.display_name == "売上金額"

    def test_exfield_resolves_target_fid_to_source_column(self):
        records = self._parse()
        matches = [r for r in records if r.column_name == "SALE_DATE" and r.usage_type == "calc"]
        assert len(matches) == 1
        assert matches[0].display_name == "販売年月"

    def test_exfield_with_unresolvable_target_fid_is_skipped(self):
        records = self._parse()
        assert not any(r.display_name == "未解決の計算項目" for r in records)

    def test_root_without_srcname_returns_empty(self):
        content = ('<?xml version="1.0" ?><DataSource name="x" type="drsum" '
                   'src="" srcName="" version="4.0.1"><Layout></Layout></DataSource>')
        assert bp.auto_parse_xml("ds.xml", content.encode("utf-8"), load_index()) == []

    def test_non_drsum_datasource_falls_back_to_generic_logic(self):
        # type="drsum"以外は専用パスに分岐させない(専用パスなら<Layout>が無く空リストになるはず)。
        # 汎用ロジックが働けば、属性値の完全一致+同一要素内ラベル探索で1件検出される。
        content = ('<?xml version="1.0" ?><DataSource name="x" type="other" srcName="T_SAMPLE">'
                   '<Field column="TANKA" label="単価"/></DataSource>')
        records = bp.auto_parse_xml("ds.xml", content.encode("utf-8"), load_index())
        assert len(records) == 1
        assert records[0].display_name == "単価"


class TestSearchConditionNotTreatedAsAlias:
    """DD-023: 検索条件(事前設定フィルタ)のdispTitleがエイリアスと誤認されないことの回帰テスト。
    実機(C:\\MotionBoard64)確認で判明した
    <Condition><SearchCondition><PreCondition><Expression title="..." dispTitle="..."/>
    の実構造を模したフィクスチャを使う。"""

    def test_dispTitle_inside_search_condition_is_not_extracted(self):
        content = (
            '<?xml version="1.0" ?><BoardDefinition>'
            '<Condition><SearchCondition><PreCondition>'
            '<Expression enable="true" dsid="0" fid="3" title="TANKA" dispTitle="絞り込みキャプション" '
            'dispType="INPUT" operatorType="EQUAL"/>'
            '</PreCondition></SearchCondition></Condition>'
            '</BoardDefinition>'
        )
        records = bp.auto_parse_xml("board.xml", content.encode("utf-8"), load_index())
        assert records == []

    def test_sibling_field_outside_search_condition_is_still_extracted(self):
        # SearchCondition配下を除外しても、同じファイル内の通常のField/labelは
        # 従来どおり検出され続けることを確認する(過剰除外の回帰防止)
        content = (
            '<?xml version="1.0" ?><BoardDefinition>'
            '<Field column="TANKA" label="単価"/>'
            '<Condition><SearchCondition><PreCondition>'
            '<Expression title="TANKA" dispTitle="絞り込みキャプション"/>'
            '</PreCondition></SearchCondition></Condition>'
            '</BoardDefinition>'
        )
        records = bp.auto_parse_xml("board.xml", content.encode("utf-8"), load_index())
        assert len(records) == 1
        assert records[0].display_name == "単価"


class TestItemOrderChangeNotTreatedAsAlias:
    """DD-027: 集計表(クロス集計)パーツの軸設定(ItemOrderChange)配下の他軸属性・
    selected属性がエイリアスと誤認されないことの回帰テスト。実機(C:\\MotionBoard64、
    地域別売上.fs-file)確認で判明した
    <ItemOrderChange category="支店" series="年度" summary="売上額">
      <CategoryDisp><Item label="支店" data="支店" selected="true" fid="6"></Item></CategoryDisp>
    の実構造を模したフィクスチャを使う。"""

    def test_other_axis_attribute_inside_item_order_change_is_not_extracted(self):
        # Bug#001: category(行軸)="TANKA"と同一要素のseries(列軸)="年度"が
        # TANKAのエイリアスとして誤って拾われないこと
        content = (
            '<?xml version="1.0" ?><BoardDefinition>'
            '<ItemOrderChange category="TANKA" series="年度" summary="売上額">'
            '</ItemOrderChange>'
            '</BoardDefinition>'
        )
        records = bp.auto_parse_xml("board.xml", content.encode("utf-8"), load_index())
        assert records == []

    def test_selected_attribute_inside_item_order_change_is_not_extracted(self):
        # Bug#002: label/dataが物理カラム名と値一致して候補から除外された後、
        # 残る selected="true" が最終フォールバックで誤って拾われないこと。
        # 外側のItemOrderChange自身の属性はどの物理カラムとも一致しない値にして、
        # 検証対象(CategoryDisp配下のItem)の挙動だけを切り出す
        content = (
            '<?xml version="1.0" ?><BoardDefinition>'
            '<ItemOrderChange category="X" series="Y" summary="Z">'
            '<CategoryDisp><Item label="TANKA" data="TANKA" selected="true" fid="6"></Item></CategoryDisp>'
            '</ItemOrderChange>'
            '</BoardDefinition>'
        )
        records = bp.auto_parse_xml("board.xml", content.encode("utf-8"), load_index())
        assert records == []

    def test_sibling_field_outside_item_order_change_is_still_extracted(self):
        # ItemOrderChange配下を除外しても、同じファイル内の通常のField/labelは
        # 従来どおり検出され続けることを確認する(過剰除外の回帰防止)
        content = (
            '<?xml version="1.0" ?><BoardDefinition>'
            '<Field column="TANKA" label="単価"/>'
            '<ItemOrderChange category="TANKA" series="年度" summary="売上額">'
            '</ItemOrderChange>'
            '</BoardDefinition>'
        )
        records = bp.auto_parse_xml("board.xml", content.encode("utf-8"), load_index())
        assert len(records) == 1
        assert records[0].display_name == "単価"


# ============================================================
# DD-002-3: MotionBoardサーバー内部コンテンツストア(.fs-file/fs-snap)の走査
# ============================================================
def _build_zip_bytes(entries: dict) -> bytes:
    """{エントリ名: 中身(bytes)} からZIPバイト列を作る。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestNestedZipAndFsFileDiscovery:
    def test_nested_zip_entry_is_parsed_recursively(self):
        index = load_index()
        inner_zip = _build_zip_bytes({
            "mbds_def/dsDef/日本語データソース": DRSUM_DATASOURCE_XML.encode("utf-8"),
        })
        outer_zip = _build_zip_bytes({
            "board_body": b"<?xml version=\"1.0\" ?><BoardDefinition/>",
            "fs-xcabinets/0": inner_zip,
        })
        records = bp._parse_zip_bytes(outer_zip, index, "outer.zip", "outer.zip")
        assert any(r.table_name == "T_SAMPLE" for r in records)

    def test_extensionless_xml_entry_is_sniffed_by_content(self):
        index = load_index()
        zip_bytes = _build_zip_bytes({"Test1_BOARD": DRSUM_DATASOURCE_XML.encode("utf-8")})
        records = bp._parse_zip_bytes(zip_bytes, index, "b.zip", "b.zip")
        assert any(r.table_name == "T_SAMPLE" for r in records)

    def test_fs_file_snapshot_is_discovered_and_parsed(self, tmp_path):
        board_dir = tmp_path / "MyBoard.fs-file"
        snap_dir = board_dir / "fs-snap"
        snap_dir.mkdir(parents=True)
        zip_bytes = _build_zip_bytes({"MyBoard": DRSUM_DATASOURCE_XML.encode("utf-8")})
        (snap_dir / "snap_00000001_1000").write_bytes(_build_zip_bytes({"MyBoard": b"<?xml version=\"1.0\" ?><Old/>"}))
        (snap_dir / "snap_00000002_2000").write_bytes(zip_bytes)

        records = bp.auto_parse_all(tmp_path, str(COLUMNS_PATH))
        assert any(r.table_name == "T_SAMPLE" for r in records)

    def test_fs_file_board_name_uses_folder_name_not_datasource_name(self, tmp_path):
        # DD-017: データソース定義XML自身のname属性("テストデータソース")ではなく、
        # .fs-fileフォルダ名("MyBoard")が本当のボード名としてboard_nameに入ることを確認
        board_dir = tmp_path / "MyBoard.fs-file"
        snap_dir = board_dir / "fs-snap"
        snap_dir.mkdir(parents=True)
        zip_bytes = _build_zip_bytes({"MyBoard": DRSUM_DATASOURCE_XML.encode("utf-8")})
        (snap_dir / "snap_00000001_1000").write_bytes(zip_bytes)

        records = bp.auto_parse_all(tmp_path, str(COLUMNS_PATH))
        assert records
        assert all(r.board_name == "MyBoard" for r in records)
        assert not any(r.board_name == "テストデータソース" for r in records)

    def test_fs_file_without_snapshot_does_not_crash(self, tmp_path):
        board_dir = tmp_path / "Empty.fs-file"
        (board_dir / "fs-snap").mkdir(parents=True)
        assert bp.auto_parse_all(tmp_path, str(COLUMNS_PATH)) == []
