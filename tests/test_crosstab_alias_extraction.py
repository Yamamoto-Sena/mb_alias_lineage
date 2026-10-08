"""クロス集計(集計表)パーツを含む架空の定義ファイル(tests/fixtures/crosstab_check/)を
自動検出モードで正しく抽出できるかを確認する単発テスト。

DD-027で対応した「ItemOrderChange配下(category/series/summary軸設定、および
CategoryDisp/SeriesDisp/SummaryDispの表示設定)はカラムのエイリアスではない」という
除外ロジックが、ボード定義ファイル全体を通した自動検出モード(auto_parse_all)でも
機能し続けることの回帰テスト。

tests/test_board_parser.py の TestItemOrderChangeNotTreatedAsAlias は
auto_parse_xml への断片XML直接投入でこの挙動を検証しているが、本テストは
実際のフォルダ構成・列インデックス(dr_sum_columns.json相当)を使った架空の
定義ファイルでエンドツーエンドに確認する。既存の
tests/fixtures/manual_alias_check/ とは別フォルダ・別カラムインデックスに
置くことで、そちらの件数系アサーションに影響しない。
"""
from pathlib import Path

import board_parser as bp

FIXTURES = Path(__file__).parent / "fixtures" / "crosstab_check"
COLUMNS_PATH = Path(__file__).parent / "fixtures" / "crosstab_check_columns.json"


def all_records():
    return bp.auto_parse_all(FIXTURES, str(COLUMNS_PATH))


class TestCrosstabAxisNotTreatedAsAlias:
    """集計表(クロス集計)パーツの軸設定(category/series/summary)や
    CategoryDisp/SeriesDisp/SummaryDisp配下の表示設定が、
    カラムのエイリアスとして誤抽出されないこと。"""

    def test_crosstab_only_item_produces_no_records(self):
        # chubu-crosstab-002はItemOrderChangeのみで通常のFieldを持たないため、
        # 1件もレコードが作られないこと
        records = [r for r in all_records() if r.item_id == "chubu-crosstab-002"]
        assert records == []

    def test_axis_columns_are_not_extracted_anywhere_in_file(self):
        # category/series/summaryで参照されている3カラムは、ファイル中のどこにも
        # エイリアス/calcレコードとして現れないこと
        axis_columns = {"CHIIKI_KBN", "NENDO", "URIAGE_KIN"}
        leaked = [r for r in all_records() if r.column_name in axis_columns]
        assert leaked == []


class TestSiblingFieldStillExtractedAlongsideCrosstab:
    """同じアイテム内にクロス集計パーツがあっても、通常のFieldラベルは
    従来どおり検出され続けること(過剰除外の回帰防止)。"""

    def test_sibling_alias_is_extracted(self):
        records = all_records()
        matches = [r for r in records
                   if r.board_name == "中部エリア売上集計" and r.item_id == "chubu-crosstab-001"
                   and r.column_name == "SHIIRE_SU"]
        assert len(matches) == 1
        assert matches[0].display_name == "仕入数量"
        assert matches[0].table_name == "T_売上明細"
        assert matches[0].usage_type == "alias"


class TestTotalRecordCount:
    def test_only_the_sibling_alias_is_extracted(self):
        # クロス集計の軸設定からは何も抽出されず、通常Fieldの1件のみが残ること
        assert len(all_records()) == 1
