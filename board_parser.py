"""
フェーズ2: MotionBoardのボード定義ファイル群を解析し、
「物理カラム名 → 表示名（エイリアス）→ ボード名/アイテムID」の
レコード一覧を作る。

■ 自動検出モード（--auto、デフォルト）
  タグ名・キー名を事前に手動設定しなくても動くように、
  dr_sum_metadata.py で取得済みの「実在する物理カラム名一覧」を
  手がかりにして、ファイルの中から「既知のカラム名がどこかの
  属性値・キー値として出現している箇所」を総当たりで探す。
  見つかった場所の「近くにある、カラム名とは違う文字列」を
  表示名（エイリアス）の候補として拾う。

  → これにより、事前にタグ構造を調べなくても
    「定義ファイルを渡すだけ」で動作する。
    ただしヒューリスティック（経験則）なので100%の精度は保証されない。
    誤検出・検出漏れが多い場合は --manual モードで
    TAG_CONFIG を実物に合わせて調整する方式に切り替える。

■ 手動モード（--manual）
  以前からある、TAG_CONFIGでタグ名を明示的に指定する方式。
  自動検出の精度が低い場合のフォールバックとして残してある。

使い方:
    # 自動検出モード（推奨・デフォルト）
    python board_parser.py <ボード定義フォルダ> --columns dr_sum_columns.json --out board_aliases.json

    # 手動モード
    python board_parser.py <ボード定義フォルダ> --manual --out board_aliases.json

    # ダミーデータで動作確認
    python board_parser.py --stub --out board_aliases.json
"""
import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

JAPANESE_RE = re.compile(r"[぀-ヿ㐀-鿿]")  # ひらがな・カタカナ・漢字を含むか
LABEL_KEY_HINTS = ("label", "disp", "name", "alias", "title", "caption", "表示", "名称")
ID_KEY_HINTS = ("id", "no", "seq", "key", "index", "番号", "コード")
NAME_KEY_HINTS = ("name", "title", "caption", "名称", "ボード")


@dataclass
class AliasRecord:
    table_name: str
    column_name: str
    display_name: str
    board_name: str
    item_id: str


# ============================================================
# 手動モード用の設定（自動検出の精度が低い場合のフォールバック）
# ============================================================
TAG_CONFIG = {
    "board_name_attr": "name",
    "item_tag": "Item",
    "item_id_attr": "id",
    "field_tag": "Field",
    "field_column_attr": "column",
    "field_label_attr": "label",
    "field_table_attr": "table",
}


def _contains_japanese(s: str) -> bool:
    return bool(JAPANESE_RE.search(s))


def _looks_like_label_key(key: str) -> bool:
    key_lower = key.lower()
    return any(hint in key_lower for hint in LABEL_KEY_HINTS)


def _looks_like_name_key(key: str) -> bool:
    key_lower = key.lower()
    return any(hint in key_lower for hint in NAME_KEY_HINTS)


def _looks_like_id_key(key: str) -> bool:
    key_lower = key.lower()
    return any(hint in key_lower for hint in ID_KEY_HINTS)


def _local_tag(tag: str) -> str:
    """XML名前空間のClark記法(`{uri}tag`)からローカル名だけを取り出す。"""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


class ColumnIndex:
    """dr_sum_columns.json から作る「カラム名 → 候補テーブル一覧」の索引。"""

    def __init__(self, columns: List[dict]):
        self.by_column: Dict[str, List[str]] = {}
        self.table_names_upper = set()
        for c in columns:
            col_upper = c["column_name"].strip().upper()
            self.by_column.setdefault(col_upper, []).append(c["table_name"])
            self.table_names_upper.add(c["table_name"].strip().upper())

    def match(self, value: str) -> Optional[str]:
        return value.strip().upper() if value.strip().upper() in self.by_column else None

    def resolve_table(self, column_upper: str, context_values: List[str],
                       preferred_table: Optional[str] = None) -> str:
        candidates = self.by_column.get(column_upper, [])
        if preferred_table:
            pref_upper = preferred_table.strip().upper()
            for cand in candidates:
                if cand.strip().upper() == pref_upper:
                    return cand
        if len(candidates) == 1:
            return candidates[0]
        # 複数テーブルに同名カラムがある場合、周辺の値からテーブル名っぽいものを探して絞り込む
        for v in context_values:
            v_upper = v.strip().upper()
            if v_upper in self.table_names_upper:
                for cand in candidates:
                    if cand.strip().upper() == v_upper:
                        return cand
        return candidates[0] if candidates else "(不明・複数候補あり)"


def _extract_match(index: ColumnIndex, value: str) -> Optional[Tuple[str, Optional[str]]]:
    """値そのもの、または`テーブル名.カラム名`のように修飾された値の右側がカラム名と
    一致するか調べる。一致すれば (カラム名, 修飾子として使われていたテーブル名らしき文字列) を返す。"""
    value = value.strip()
    if not value:
        return None
    direct = index.match(value)
    if direct:
        return direct, None
    if "." in value:
        qualifier, _, tail = value.rpartition(".")
        tail_match = index.match(tail)
        if tail_match:
            return tail_match, qualifier.strip()
    return None


# ============================================================
# 自動検出モード: XML
# ============================================================
def auto_parse_xml(path: Path, index: ColumnIndex) -> List[AliasRecord]:
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return []

    root = tree.getroot()
    records: List[AliasRecord] = []

    def find_label_on_element(el: ET.Element, matched_key: Optional[str], matched_val: str) -> Optional[str]:
        matched_val = matched_val.strip()
        candidates = [(k, v) for k, v in el.attrib.items()
                      if k != matched_key and v.strip() != matched_val and v.strip()]
        for k, v in candidates:
            if _looks_like_label_key(k):
                return v
        for k, v in candidates:
            if _contains_japanese(v):
                return v
        if candidates:
            return candidates[0][1]
        # 同じ要素に手がかりが無ければ、子要素(タグ名がラベルっぽい/日本語テキストを持つ)を見る
        for child in el:
            child_text = (child.text or "").strip()
            if child_text and child_text != matched_val:
                if _looks_like_label_key(_local_tag(child.tag)) or _contains_japanese(child_text):
                    return child_text
        text = (el.text or "").strip()
        return text if text and text != matched_val else None

    def find_ancestor_name(stack: List[ET.Element]) -> str:
        for el in stack:  # ルートに近い方から探す(ボード名は上位にあることが多い)
            for k, v in el.attrib.items():
                if _looks_like_name_key(k) and v.strip():
                    return v.strip()
            # 自身に無ければ、直下の子要素(属性/タグ名+テキスト)も手がかりとして見る
            # (例: <Meta name="..."/> という兄弟要素、<Title>...</Title> という子要素)
            for child in el:
                for k, v in child.attrib.items():
                    if _looks_like_name_key(k) and v.strip():
                        return v.strip()
                child_text = (child.text or "").strip()
                if child_text and _looks_like_name_key(_local_tag(child.tag)):
                    return child_text
        return path.stem  # 見つからなければファイル名で代用

    def find_ancestor_id(stack: List[ET.Element]) -> str:
        for el in reversed(stack):  # 現在位置に近い方から探す
            for k, v in el.attrib.items():
                if _looks_like_id_key(k) and v.strip():
                    return v.strip()
        return ""

    def walk(el: ET.Element, stack: List[ET.Element]) -> None:
        stack.append(el)
        # マッチ元候補: 属性値、および(属性で見つからない場合の)要素のテキスト内容
        match_sources: List[Tuple[Optional[str], str]] = list(el.attrib.items())
        own_text = (el.text or "").strip()
        if own_text:
            match_sources.append((None, own_text))

        for attr_key, attr_val in match_sources:
            extracted = _extract_match(index, attr_val)
            if not extracted:
                continue
            col_upper, qualifier = extracted
            label = find_label_on_element(el, attr_key, attr_val)
            if label and not index.match(label):  # ラベル候補自体がカラム名そのものなら除外
                table_name = index.resolve_table(col_upper, list(el.attrib.values()), preferred_table=qualifier)
                records.append(AliasRecord(
                    table_name=table_name,
                    column_name=col_upper,
                    display_name=label,
                    board_name=find_ancestor_name(stack),
                    item_id=find_ancestor_id(stack),
                ))
        for child in el:
            walk(child, stack)
        stack.pop()

    walk(root, [])
    return records


# ============================================================
# 自動検出モード: JSON
# ============================================================
def auto_parse_json(path: Path, index: ColumnIndex) -> List[AliasRecord]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []

    records: List[AliasRecord] = []

    def find_label_in_dict(node: dict, matched_key, matched_val: str) -> Optional[str]:
        candidates = [(k, v) for k, v in node.items()
                      if k != matched_key and isinstance(v, str) and v.strip() != matched_val.strip() and v.strip()]
        for k, v in candidates:
            if _looks_like_label_key(str(k)):
                return v
        for k, v in candidates:
            if _contains_japanese(v):
                return v
        return candidates[0][1] if candidates else None

    def find_ancestor_name(dict_stack: List[dict]) -> str:
        for node in dict_stack:
            for k, v in node.items():
                if isinstance(v, str) and _looks_like_name_key(str(k)) and v.strip():
                    return v.strip()
        return path.stem

    def find_ancestor_id(dict_stack: List[dict]) -> str:
        for node in reversed(dict_stack):
            for k, v in node.items():
                if isinstance(v, (str, int)) and _looks_like_id_key(str(k)):
                    return str(v)
        return ""

    def _try_parallel_arrays(node: dict, dict_stack: List[dict]) -> None:
        """カラム名配列と表示名配列が同じインデックスで対応している構造を拾う
        (例: {"columns": ["A","B"], "displayNames": ["名称A","名称B"]})。"""
        string_list_items = [(k, v) for k, v in node.items()
                              if isinstance(v, list) and v and all(isinstance(x, str) for x in v)]
        if len(string_list_items) < 2:
            return
        for cols_key, cols in string_list_items:
            if not all(index.match(x) for x in cols):
                continue  # 全要素がカラム名と一致する配列だけを「カラム名配列」とみなす
            for labels_key, labels in string_list_items:
                if labels_key == cols_key or len(labels) != len(cols):
                    continue
                if any(index.match(x) for x in labels):
                    continue  # ラベル側にもカラム名が混ざるなら対応関係として扱わない
                for col_val, label_val in zip(cols, labels):
                    col_upper = index.match(col_val)
                    table_name = index.resolve_table(col_upper, cols)
                    records.append(AliasRecord(
                        table_name=table_name,
                        column_name=col_upper,
                        display_name=label_val,
                        board_name=find_ancestor_name(dict_stack),
                        item_id=find_ancestor_id(dict_stack),
                    ))

    def _try_linked_lookup_tables(node: dict, dict_stack: List[dict]) -> None:
        """カラム定義とラベルが別々の対応表(同じIDをキーに持つ2つの辞書)に
        分かれている構造を拾う(例: fieldDefs={"f1": {"col": "A"}}, fieldLabels={"f1": "名称A"})。"""
        dict_of_dicts = [(k, v) for k, v in node.items()
                          if isinstance(v, dict) and v and all(isinstance(iv, dict) for iv in v.values())]
        dict_of_strings = [(k, v) for k, v in node.items()
                            if isinstance(v, dict) and v and all(isinstance(iv, str) for iv in v.values())]
        for _, defs in dict_of_dicts:
            for _, labels in dict_of_strings:
                shared_ids = set(defs.keys()) & set(labels.keys())
                for item_key in shared_ids:
                    label_val = labels[item_key]
                    if index.match(label_val):
                        continue
                    inner_values = [v for v in defs[item_key].values() if isinstance(v, str)]
                    for v in inner_values:
                        col_upper = index.match(v)
                        if col_upper:
                            table_name = index.resolve_table(col_upper, inner_values)
                            records.append(AliasRecord(
                                table_name=table_name,
                                column_name=col_upper,
                                display_name=label_val,
                                board_name=find_ancestor_name(dict_stack),
                                item_id=str(item_key),
                            ))

    def walk(node, dict_stack: List[dict]) -> None:
        if isinstance(node, dict):
            new_stack = dict_stack + [node]
            for k, v in node.items():
                if isinstance(v, str):
                    extracted = _extract_match(index, v)
                    if extracted:
                        col_upper, qualifier = extracted
                        label = find_label_in_dict(node, k, v)
                        if label and not index.match(label):
                            context_values = [x for x in node.values() if isinstance(x, str)]
                            table_name = index.resolve_table(col_upper, context_values, preferred_table=qualifier)
                            records.append(AliasRecord(
                                table_name=table_name,
                                column_name=col_upper,
                                display_name=label,
                                board_name=find_ancestor_name(new_stack),
                                item_id=find_ancestor_id(new_stack),
                            ))
            _try_parallel_arrays(node, new_stack)
            _try_linked_lookup_tables(node, new_stack)
            for v in node.values():
                walk(v, new_stack)
        elif isinstance(node, list):
            for item in node:
                walk(item, dict_stack)

    walk(data, [])
    return records


def auto_parse_all(root_dir: Path, columns_path: str) -> List[AliasRecord]:
    columns = json.loads(Path(columns_path).read_text(encoding="utf-8"))
    index = ColumnIndex(columns)

    all_records: List[AliasRecord] = []
    xml_files = list(root_dir.rglob("*.xml"))
    json_files = list(root_dir.rglob("*.json"))
    print(f"XML {len(xml_files)}件 / JSON {len(json_files)}件を自動検出モードで走査します")

    for path in xml_files:
        recs = auto_parse_xml(path, index)
        if recs:
            print(f"  検出: {path.name} → {len(recs)}件")
        all_records.extend(recs)

    for path in json_files:
        recs = auto_parse_json(path, index)
        if recs:
            print(f"  検出: {path.name} → {len(recs)}件")
        all_records.extend(recs)

    if not all_records:
        print("  ※1件も検出できませんでした。ファイル形式がZIP圧縮/暗号化/独自バイナリの")
        print("    可能性があります。inspect_file.py で中身を確認し、必要なら --manual を検討してください")

    return all_records


# ============================================================
# 手動モード（従来方式・フォールバック）
# ============================================================
def manual_parse_file(path: Path) -> List[AliasRecord]:
    records: List[AliasRecord] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return records

    root = tree.getroot()
    board_name = root.attrib.get(TAG_CONFIG["board_name_attr"], path.stem)

    for item in root.iter(TAG_CONFIG["item_tag"]):
        item_id = item.attrib.get(TAG_CONFIG["item_id_attr"], "")
        for field in item.iter(TAG_CONFIG["field_tag"]):
            column = field.attrib.get(TAG_CONFIG["field_column_attr"])
            label = field.attrib.get(TAG_CONFIG["field_label_attr"])
            table = field.attrib.get(TAG_CONFIG["field_table_attr"], "")
            if column and label:
                records.append(AliasRecord(
                    table_name=table, column_name=column,
                    display_name=label, board_name=board_name, item_id=item_id,
                ))
    return records


def manual_parse_all(root_dir: Path) -> List[AliasRecord]:
    all_records: List[AliasRecord] = []
    for path in list(root_dir.rglob("*.xml")):
        all_records.extend(manual_parse_file(path))
    return all_records


def stub_records() -> List[AliasRecord]:
    sample = [
        ("T_売上明細", "URIAGE_KIN", "売上金額", "月次売上", "item001"),
        ("T_売上明細", "URIAGE_KIN", "Revenue", "海外向けサマリー", "item045"),
        ("T_顧客M", "KOKYAKU_CD", "顧客コード", "顧客一覧", "item010"),
        ("T_売上明細", "CHIIKI_KBN", "地域区分", "地域別実績", "item022"),
        ("T_売上明細", "CHIIKI_KBN", "エリア", "支社別KPI", "item031"),
        ("T_売上明細", "CHIIKI_KBN", "Region", "海外向けサマリー", "item045"),
        ("T_在庫", "ZAIKO_SU", "在庫数", "在庫アラート", "item050"),
    ]
    return [AliasRecord(table_name=t, column_name=c, display_name=d, board_name=b, item_id=i)
            for t, c, d, b, i in sample]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root_dir", nargs="?", help="ボード定義が入ったフォルダ")
    parser.add_argument("--columns", help="dr_sum_metadata.pyの出力(dr_sum_columns.json)。自動検出モードで必須")
    parser.add_argument("--manual", action="store_true", help="TAG_CONFIGによる手動モードを使う")
    parser.add_argument("--out", default="board_aliases.json")
    parser.add_argument("--stub", action="store_true", help="ダミーデータで動作確認する")
    args = parser.parse_args()

    if args.stub:
        records = stub_records()
        print("※ --stub モード: ダミーデータを使用しています")
    elif args.manual:
        if not args.root_dir:
            parser.error("フォルダパスが必須です")
        records = manual_parse_all(Path(args.root_dir))
    else:
        if not (args.root_dir and args.columns):
            parser.error("自動検出モードには フォルダパス と --columns dr_sum_columns.json が必須です")
        records = auto_parse_all(Path(args.root_dir), args.columns)

    out_path = Path(args.out)
    out_path.write_text(
        json.dumps([asdict(r) for r in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n{len(records)}件のエイリアスレコードを {out_path} に出力しました")


if __name__ == "__main__":
    main()
