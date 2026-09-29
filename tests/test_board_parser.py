import json
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
