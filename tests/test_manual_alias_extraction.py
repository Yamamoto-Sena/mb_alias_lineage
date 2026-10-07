"""エイリアスを付けた定義ファイル(tests/fixtures/manual_alias_check/)を
自動検出モードで正しく抽出できるかを確認する単発テスト。

既存の sample_data/motionboard_backup/ とは別フォルダに置くことで、
tests/test_board_parser.py の件数系アサーション(41件/38alias等)に影響しない。
"""
from pathlib import Path

import board_parser as bp

FIXTURES = Path(__file__).parent / "fixtures" / "manual_alias_check"
COLUMNS_PATH = Path(__file__).parent / "fixtures" / "manual_alias_check_columns.json"


def all_records():
    return bp.auto_parse_all(FIXTURES, str(COLUMNS_PATH))


def find(records, board_name, item_id, column_name, usage_type="alias"):
    matches = [r for r in records
               if r.board_name == board_name and r.item_id == item_id
               and r.column_name == column_name and r.usage_type == usage_type]
    assert matches, f"レコードが見つからない: board={board_name} item={item_id} col={column_name} type={usage_type}"
    return matches[0]


class TestAliasExtraction:
    """同じ物理カラムがボードごとに異なるエイリアスで使われているケース。"""

    def test_kansai_board_aliases(self):
        records = all_records()
        r1 = find(records, "関西エリア売上", "kansai-001", "URIAGE_KIN")
        assert r1.display_name == "関西売上金額"
        assert r1.table_name == "T_売上明細"

        r2 = find(records, "関西エリア売上", "kansai-001", "CHIIKI_KBN")
        assert r2.display_name == "地区区分"

    def test_kanto_board_uses_different_alias_for_same_column(self):
        r = find(all_records(), "関東エリア売上", "kanto-001", "URIAGE_KIN")
        assert r.display_name == "関東売上金額"

    def test_same_column_has_two_distinct_aliases_across_boards(self):
        records = all_records()
        uriage_kin_aliases = {r.display_name for r in records
                               if r.column_name == "URIAGE_KIN" and r.usage_type == "alias"}
        assert uriage_kin_aliases == {"関西売上金額", "関東売上金額"}


class TestUnaliasedColumnNotExtracted:
    """ラベルの手がかりが無い(物理名そのまま使用)場合はエイリアスとして抽出されないこと。"""

    def test_tanka_without_label_produces_no_alias_record(self):
        records = all_records()
        matches = [r for r in records
                   if r.board_name == "関西エリア売上" and r.item_id == "kansai-001"
                   and r.column_name == "TANKA"]
        assert matches == []


class TestCalcFieldDetection:
    """計算式(formula)の中で使われている物理カラムは usage_type='calc' で区別されること。"""

    def test_formula_columns_detected_as_calc(self):
        records = all_records()
        matches = [r for r in records
                   if r.board_name == "関東エリア売上" and r.item_id == "kanto-calc-001"]
        columns_found = {r.column_name for r in matches}
        assert columns_found == {"URIAGE_KIN", "TANKA"}
        for r in matches:
            assert r.usage_type == "calc"
            assert r.display_name == "単価換算売上高"
            assert r.source_file == "board_kanto_sales.xml"


class TestJsonFormatAlias:
    """XMLだけでなくJSON形式の定義ファイルからも正しくエイリアスを抽出できること。"""

    def test_product_name_alias_from_json(self):
        r = find(all_records(), "関西商品一覧", "panel-kansai-1", "SHOHIN_NAME")
        assert r.display_name == "商品名称"
        assert r.table_name == "T_商品M"
        assert r.source_file == "board_kansai_product.json"


class TestTotalRecordCount:
    def test_total_alias_and_calc_record_count(self):
        records = all_records()
        alias_records = [r for r in records if r.usage_type == "alias"]
        calc_records = [r for r in records if r.usage_type == "calc"]
        assert len(alias_records) == 4  # URIAGE_KIN x2 + CHIIKI_KBN + SHOHIN_NAME
        assert len(calc_records) == 2   # URIAGE_KIN, TANKA (formula内)
