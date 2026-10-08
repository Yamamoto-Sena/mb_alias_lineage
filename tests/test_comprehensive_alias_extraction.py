"""架空の定義ファイル群(tests/fixtures/comprehensive_check/)を使って、
自動検出モードが「想定しうる内容(正しくエイリアス抽出すべきパターン)」と
「想定外の内容(過去の実機バグでエイリアスと誤認された、抽出してはいけない
パターン)」の両方を一度に正しく扱えることを確認する統合テスト。

含まれるファイル:
- board_comprehensive_sales.xml: 通常Field/計算式/クロス集計(ItemOrderChange)/
  検索条件(SearchCondition)/フラグ属性(DsDef disp)/ラベル無し物理名、を1ボードに同居させた
  (実機のボード定義ファイルは複数の要素が混在しているため、それを模している)
- board_comprehensive_product.json: JSON形式の定義ファイルからの抽出
- board_comprehensive_drsum.xml: MotionBoardの実データソース定義(<DataSource type="drsum">)
  形式。aliasTitle空(物理名そのまま)/aliasTitleあり/ExField計算項目、を含む

各パターンの個別の回帰テストは tests/test_board_parser.py 側に断片XML単位で
既に存在する。本テストはそれらを「1つの架空の定義ファイル一式」としてまとめ、
auto_parse_all()でエンドツーエンドに抽出できることを確認する点が異なる。
既存の tests/fixtures/manual_alias_check/ や tests/fixtures/crosstab_check/ とは
別フォルダ・別カラムインデックスに置き、互いの件数系アサーションに影響しない。
"""
from pathlib import Path

import board_parser as bp

FIXTURES = Path(__file__).parent / "fixtures" / "comprehensive_check"
COLUMNS_PATH = Path(__file__).parent / "fixtures" / "comprehensive_check_columns.json"


def all_records():
    return bp.auto_parse_all(FIXTURES, str(COLUMNS_PATH))


def find(records, column_name, usage_type="alias"):
    matches = [r for r in records if r.column_name == column_name and r.usage_type == usage_type]
    assert matches, f"レコードが見つからない: column={column_name} type={usage_type}"
    return matches


class TestExpectedPatternsAreExtracted:
    """想定しうる内容: 正しくエイリアス/計算項目として抽出されるべきパターン。"""

    def test_normal_field_alias(self):
        r = find(all_records(), "SHIIRE_SU")[0]
        assert r.display_name == "仕入数量"
        assert r.table_name == "T_売上明細"
        assert r.board_name == "総合テスト売上ダッシュボード"
        assert r.item_id == "item-001"

    def test_formula_calc_fields(self):
        records = all_records()
        calc_cols = {r.column_name for r in records
                     if r.item_id == "item-002" and r.usage_type == "calc"}
        assert calc_cols == {"URIAGE_KIN", "TANKA"}
        for r in records:
            if r.item_id == "item-002":
                assert r.display_name == "単価換算売上高"

    def test_sibling_field_alongside_crosstab_is_extracted(self):
        r = find(all_records(), "URIAGE_KIN")
        matches = [x for x in r if x.item_id == "item-003"]
        assert len(matches) == 1
        assert matches[0].display_name == "売上金額(集計表併設)"

    def test_json_format_alias(self):
        r = find(all_records(), "SHOHIN_CODE")[0]
        assert r.display_name == "商品コード"
        assert r.table_name == "T_商品M"
        assert r.source_file == "board_comprehensive_product.json"

    def test_drsum_alias_title_is_used_when_present(self):
        r = find(all_records(), "SHUKKA_SU")[0]
        assert r.display_name == "出荷数量"
        assert r.table_name == "T_出荷実績"

    def test_drsum_empty_alias_title_falls_back_to_physical_name(self):
        # aliasTitleが空の場合は物理名そのものが表示名になる(DD-002-1/DD-022の前提)
        records = {r.column_name: r for r in all_records()
                   if r.usage_type == "alias" and r.table_name == "T_出荷実績"}
        assert records["DENPYO_NO"].display_name == "denpyo_no"
        assert records["NOUHIN_DATE"].display_name == "nouhin_date"

    def test_drsum_exfield_calc_resolves_target_fid(self):
        r = find(all_records(), "NOUHIN_DATE", usage_type="calc")[0]
        assert r.display_name == "納品年月"


class TestUnexpectedPatternsAreNotExtracted:
    """想定外の内容: 過去の実機バグで誤ってエイリアス化されていたパターンが、
    今も正しく抽出対象から除外され続けていること。"""

    def test_crosstab_only_item_produces_no_records(self):
        records = [r for r in all_records() if r.item_id == "item-004"]
        assert records == []

    def test_crosstab_axis_values_never_leak_as_records(self):
        # CHIIKI_KBN/NENDOはitem-003/item-004のクロス集計軸にしか登場しないので、
        # ファイル全体のどこにもレコードとして現れないはず
        leaked = [r for r in all_records() if r.column_name in ("CHIIKI_KBN", "NENDO")]
        assert leaked == []

    def test_search_condition_disp_title_produces_no_record(self):
        records = [r for r in all_records() if r.item_id == "item-005"]
        assert records == []

    def test_dsdef_boolean_flag_with_empty_alias_produces_no_record(self):
        # DsDef配下のItem(fid=9)はTANKAが物理名のまま・aliasTitle空・disp="true"のため
        # 誤ってエイリアス化されない。item-002のformula由来のTANKA(calc)だけが残ること
        records = [r for r in all_records() if r.column_name == "TANKA"]
        assert len(records) == 1
        assert records[0].usage_type == "calc"
        assert records[0].item_id == "item-002"

    def test_unlabeled_field_produces_no_record(self):
        records = [r for r in all_records() if r.column_name == "ZAIKO_SU"]
        assert records == []


class TestTotalRecordCount:
    def test_expected_and_unexpected_patterns_net_out_correctly(self):
        records = all_records()
        alias_records = [r for r in records if r.usage_type == "alias"]
        calc_records = [r for r in records if r.usage_type == "calc"]
        # alias: SHIIRE_SU, URIAGE_KIN(item-003), SHOHIN_CODE, DENPYO_NO, NOUHIN_DATE, SHUKKA_SU
        assert len(alias_records) == 6
        # calc: URIAGE_KIN+TANKA(item-002のformula), NOUHIN_DATE(drsum ExField)
        assert len(calc_records) == 3
        assert len(records) == 9
