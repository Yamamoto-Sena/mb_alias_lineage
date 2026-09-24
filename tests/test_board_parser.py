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
        assert len(all_records()) == 38

    def test_sample_data_file_count(self):
        assert len(list(BACKUP_DIR.glob("*.xml"))) == 11
        assert len(list(BACKUP_DIR.glob("*.json"))) == 3
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
