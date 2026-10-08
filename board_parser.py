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

■ MotionBoardの実データソース定義（<DataSource type="drsum">）
  実機確認（DD-002-3）で判明した、汎用ヒューリスティックとは異なる専用形式。
  srcName属性からテーブル名を直接取得し、<Field>（物理カラム）はaliasTitleの
  有無で表示名を決定、<ExField>（計算項目）はfidによる構造参照を解決してlineageを
  繋ぐ（_parse_drsum_datasource）。また、MotionBoardサーバーの内部コンテンツストア
  （<ボード名>.fs-file/fs-snap/snap_*、拡張子なしの入れ子ZIP構造）も直接走査できる。

使い方:
    # 自動検出モード（推奨・デフォルト）
    python board_parser.py <ボード定義フォルダ> --columns dr_sum_columns.json --out board_aliases.json

    # 手動モード
    python board_parser.py <ボード定義フォルダ> --manual --out board_aliases.json

    # ダミーデータで動作確認
    python board_parser.py --stub --out board_aliases.json
"""
import argparse
import io
import json
import re
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

JAPANESE_RE = re.compile(r"[぀-ヿ㐀-鿿]")  # ひらがな・カタカナ・漢字を含むか
LABEL_KEY_HINTS = ("label", "disp", "name", "alias", "title", "caption", "表示", "名称")
ID_KEY_HINTS = ("id", "no", "seq", "key", "index", "番号", "コード")
NAME_KEY_HINTS = ("name", "title", "caption", "名称", "ボード")
# 物理カラム名と無関係な複数のフィールド参照が同一要素の属性として同居するため、
# walk()の汎用ヒューリスティック(同一要素内の他属性をラベル候補として拾う)が
# 誤動作するタグ名。この配下はエイリアス抽出対象から除外する。
# - Condition/SearchCondition/PreCondition/Expression: 検索条件(事前設定フィルタ)。
#   dispTitle等はフィルタ条件自体のキャプションでカラムのエイリアスではない(DD-023)。
# - ItemOrderChange: 集計表(クロス集計)パーツの軸設定。category(行軸)/series(列軸)/
#   summary(集計値)という無関係な3つのフィールド参照が同居する(DD-027)。
NON_ALIAS_CONTEXT_TAGS = ("Condition", "SearchCondition", "PreCondition", "Expression",
                          "ItemOrderChange")


@dataclass
class AliasRecord:
    table_name: str
    column_name: str
    display_name: str
    board_name: str
    item_id: str
    source_file: str = ""
    # "alias"(表示名/エイリアスとして使用) or "calc"(カスタム項目・事後計算項目の
    # 計算式の中で物理カラムが参照されている)
    usage_type: str = "alias"
    # このエイリアスが実際に参照しているDr.SumのDB名(DD-026)。`<DataSource type="drsum">`の
    # `src`属性(`{DB名}/{テーブル名}`形式)から取得できた場合のみ設定し、取得元経路が
    # DB名を持たない場合(汎用ヒューリスティック・手動モード・スタブ)は空文字のままにする
    source_db: str = ""


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


def _in_non_alias_context(stack: List[ET.Element]) -> bool:
    """stack(現在位置を含む祖先要素列)が、カラムのエイリアス(表示名)とは無関係な
    概念が同居するタグ(NON_ALIAS_CONTEXT_TAGS)の配下にあるかを判定する(DD-023/DD-027)。"""
    return any(_local_tag(el.tag) in NON_ALIAS_CONTEXT_TAGS for el in stack)


_XML_ENCODING_DECL_RE = re.compile(rb'<\?xml[^>]*encoding=["\']([^"\']+)["\']', re.IGNORECASE)


def _parse_xml_bytes(content: bytes) -> ET.Element:
    """Shift_JIS等、Pythonの標準XMLパーサー(expat)が`encoding=`宣言だけでは
    直接デコードできない文字コードでも読めるようにする。
    (例: <?xml version="1.0" encoding="Shift_JIS"?> はexpatに直接渡すと
    "multi-byte encodings are not supported" で失敗するため、宣言を読み取って
    Python側で先にデコードしてから渡す。)"""
    try:
        return ET.fromstring(content)
    except ValueError:
        match = _XML_ENCODING_DECL_RE.search(content[:200])
        if not match:
            raise
        encoding = match.group(1).decode("ascii", errors="ignore")
        return ET.fromstring(content.decode(encoding))


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
# カスタム項目・事後計算項目の計算式の中で使われている物理カラムの検出
# ============================================================
# 値がカラム名と完全一致(または`テーブル名.カラム名`)する場合は上の_extract_matchで
# 拾えるが、MotionBoardの「カスタム項目」「事後計算項目」は計算式の中に物理カラム名が
# 部分文字列として埋め込まれる(例: "[URIAGE_KIN]/[TANKA]"、"URIAGE_KIN * 1.1")。
# これを拾うため、キー名が計算式らしい、または値に演算子・角括弧が含まれる場合に、
# トークン単位でカラム名を探す。
FORMULA_KEY_HINTS = ("formula", "expression", "expr", "calc", "算式", "計算式")
_FORMULA_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_FORMULA_OPERATOR_RE = re.compile(r"[+*/\[\]()]")  # "-"は日付・ID等の区切りにも多用されるため対象外


def _looks_like_formula_key(key: Optional[str]) -> bool:
    if not key:
        return False
    key_lower = key.lower()
    return any(hint in key_lower for hint in FORMULA_KEY_HINTS)


def _looks_like_formula_value(value: str) -> bool:
    return bool(_FORMULA_OPERATOR_RE.search(value))


def _find_columns_in_formula(index: ColumnIndex, value: str) -> List[str]:
    """計算式らしい文字列の中から、既知の物理カラム名をトークン単位(部分文字列として)で拾う。"""
    found: List[str] = []
    seen = set()
    for token in _FORMULA_TOKEN_RE.findall(value):
        col = index.match(token)
        if col and col not in seen:
            seen.add(col)
            found.append(col)
    return found


# ============================================================
# MotionBoardの実データソース定義(<DataSource type="drsum">)専用の抽出
# ============================================================
# 実機確認(DD-002-3、2026-09-30)で判明: MotionBoardの実際のデータソース定義ファイルは
# 「1要素=1フィールド、title(物理カラム名)/aliasTitle(表示名上書き。未設定なら空文字)/
# fid(フィールドID)等の属性がフラットに同居する」形式であり、下の汎用ロジック(属性値の
# 完全一致→同一要素内の別属性からラベル候補を探す)は前提が異なり機能しない
# (ラベルが見つからず無関係な属性値を誤ってラベルとして採用してしまう)。
# `srcName`属性がテーブル名そのものを正確に示すため、`ColumnIndex`によるテーブル名の
# 推測も不要。計算項目(ExField)は元カラムを計算式の文字列ではなく`fid`で構造的に参照する。
def _parse_drsum_datasource(root: ET.Element, source_file: str) -> List[AliasRecord]:
    table_name = root.attrib.get("srcName", "").strip()
    if not table_name:
        return []
    board_name = root.attrib.get("name", "").strip() or table_name
    # `src`属性は実機確認(DD-026)で`{DB名}/{テーブル名}`形式と判明。テーブル名側は
    # srcNameと重複するため使わず、DB名部分だけを所属DB判定用に取り出す
    src = root.attrib.get("src", "").strip()
    source_db = src.split("/", 1)[0].strip() if "/" in src else ""

    layout = root.find("Layout")
    if layout is None:
        return []

    records: List[AliasRecord] = []
    fid_to_title: Dict[str, str] = {}

    field_container = layout.find("Field")
    if field_container is not None:
        for item in field_container.findall("Item"):
            title = item.attrib.get("title", "").strip()
            if not title:
                continue
            fid = item.attrib.get("fid", "").strip()
            if fid:
                fid_to_title[fid] = title
            alias_title = item.attrib.get("aliasTitle", "").strip()
            # aliasTitleが空 = 物理名をそのまま表示に使っている状態
            # (DD-002-1の「物理名直接使用」パターン)。display_nameに物理名自身を入れて
            # おくことで、既存のfind_unaliased_columns側の正規化比較にそのまま乗る。
            records.append(AliasRecord(
                table_name=table_name,
                column_name=title.upper(),
                display_name=alias_title or title,
                board_name=board_name,
                item_id=item.attrib.get("id", ""),
                source_file=source_file,
                source_db=source_db,
            ))

    exfield_container = layout.find("ExField")
    if exfield_container is not None:
        for item in exfield_container.findall("Item"):
            calc_title = item.attrib.get("title", "").strip()
            if not calc_title:
                continue
            for target_fid in _exfield_target_fids(item):
                source_title = fid_to_title.get(target_fid)
                if source_title:
                    records.append(AliasRecord(
                        table_name=table_name,
                        column_name=source_title.upper(),
                        display_name=calc_title,
                        board_name=board_name,
                        item_id=item.attrib.get("id", ""),
                        source_file=source_file,
                        usage_type="calc",
                        source_db=source_db,
                    ))
                # 参照元fidが解決できない計算項目(元カラムが同一データソース内に無い等)は
                # 記録しない(既知の制約。孤立項目判定への影響はない=計算項目自体は
                # find_orphan_columnsの対象外のため)
    return records


def _exfield_target_fids(item: ET.Element) -> List[str]:
    """計算項目(ExField)の子要素(DateGroups等)が持つtargetItemFid属性から、参照して
    いる元カラムのfidを重複なく集める。"0"は「未設定」を表す値のため対象外とする
    (Interpolation等の未使用項目にも既定値として現れるため)。"""
    seen = set()
    fids: List[str] = []
    for child in item.iter():
        target = child.attrib.get("targetItemFid", "").strip()
        if target and target != "0" and target not in seen:
            seen.add(target)
            fids.append(target)
    return fids


# ============================================================
# 自動検出モード: XML
# ============================================================
def _apply_board_name_override(records: List[AliasRecord], board_name_override: Optional[str]) -> List[AliasRecord]:
    """board_name_overrideが指定されていれば、検出済みレコードのboard_nameを問答無用で
    上書きする。呼び出し元(.fs-fileフォルダ名から本当のボード名を確実に知っている
    auto_parse_all)が優先され、データソース定義のname属性等ファイル内部のヒューリスティックな
    推測より信頼できるため(DD-017)。"""
    if board_name_override:
        for r in records:
            r.board_name = board_name_override
    return records


def auto_parse_xml(source_name: str, content: bytes, index: ColumnIndex,
                    source_file: Optional[str] = None,
                    board_name_override: Optional[str] = None) -> List[AliasRecord]:
    """source_nameは表示・フォールバック用のファイル名(ZIP内のエントリ名でもよい)。
    contentは生バイト列で渡す(ET.fromstringがXML宣言のencoding指定を見て
    自前でデコードするため、Shift-JIS等で書かれたファイルもそのまま渡せる)。
    source_fileは差分取り込み(--watch)でレコードの出所を追跡するための識別子
    (省略時はsource_nameを使う)。board_name_overrideは`_apply_board_name_override`参照。"""
    try:
        root = _parse_xml_bytes(content)
    except (ET.ParseError, ValueError, LookupError, UnicodeDecodeError):
        return []

    source_file = source_file or source_name

    if _local_tag(root.tag) == "DataSource" and root.attrib.get("type") == "drsum":
        # 実機確認(DD-002-3)により、MotionBoardの実データソース定義は下の汎用ロジック
        # (属性値の完全一致 + 同一要素内のラベル探索)が想定する構造と異なると判明した
        # ため、専用の抽出関数に委譲する(index引数はこの形式では使用しない)。
        return _apply_board_name_override(_parse_drsum_datasource(root, source_file), board_name_override)

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
        return Path(source_name).stem  # 見つからなければファイル名で代用

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

        # NON_ALIAS_CONTEXT_TAGS配下(検索条件のキャプション・集計軸設定等)は、
        # カラムのエイリアスとは無関係な概念であるため抽出対象から除外する(DD-023/DD-027)
        in_non_alias_context = _in_non_alias_context(stack)

        for attr_key, attr_val in match_sources:
            extracted = _extract_match(index, attr_val) if not in_non_alias_context else None
            if extracted:
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
                        source_file=source_file,
                    ))
            elif not in_non_alias_context and (_looks_like_formula_key(attr_key) or _looks_like_formula_value(attr_val)):
                # 完全一致はしないが、計算式らしい値の中に物理カラム名が
                # 部分文字列として埋め込まれていないか調べる(カスタム項目・事後計算項目対策)
                cols_in_formula = _find_columns_in_formula(index, attr_val)
                if cols_in_formula:
                    calc_name = find_label_on_element(el, attr_key, attr_val) or attr_val
                    for col_upper in cols_in_formula:
                        table_name = index.resolve_table(col_upper, list(el.attrib.values()))
                        records.append(AliasRecord(
                            table_name=table_name,
                            column_name=col_upper,
                            display_name=calc_name,
                            board_name=find_ancestor_name(stack),
                            item_id=find_ancestor_id(stack),
                            source_file=source_file,
                            usage_type="calc",
                        ))
        for child in el:
            walk(child, stack)
        stack.pop()

    walk(root, [])
    return _apply_board_name_override(records, board_name_override)


# ============================================================
# 自動検出モード: JSON
# ============================================================
def auto_parse_json(source_name: str, content: bytes, index: ColumnIndex,
                     source_file: Optional[str] = None,
                     board_name_override: Optional[str] = None) -> List[AliasRecord]:
    """source_nameは表示・フォールバック用のファイル名(ZIP内のエントリ名でもよい)。
    source_fileは差分取り込み(--watch)でレコードの出所を追跡するための識別子
    (省略時はsource_nameを使う)。board_name_overrideは`_apply_board_name_override`参照。"""
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return []

    source_file = source_file or source_name
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
        return Path(source_name).stem

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
                        source_file=source_file,
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
                                source_file=source_file,
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
                                source_file=source_file,
                            ))
                    elif _looks_like_formula_key(k) or _looks_like_formula_value(v):
                        # 完全一致はしないが、計算式らしい値の中に物理カラム名が
                        # 部分文字列として埋め込まれていないか調べる(カスタム項目・事後計算項目対策)
                        cols_in_formula = _find_columns_in_formula(index, v)
                        if cols_in_formula:
                            calc_name = find_label_in_dict(node, k, v) or v
                            context_values = [x for x in node.values() if isinstance(x, str)]
                            for col_upper in cols_in_formula:
                                table_name = index.resolve_table(col_upper, context_values)
                                records.append(AliasRecord(
                                    table_name=table_name,
                                    column_name=col_upper,
                                    display_name=calc_name,
                                    board_name=find_ancestor_name(new_stack),
                                    item_id=find_ancestor_id(new_stack),
                                    source_file=source_file,
                                    usage_type="calc",
                                ))
            _try_parallel_arrays(node, new_stack)
            _try_linked_lookup_tables(node, new_stack)
            for v in node.values():
                walk(v, new_stack)
        elif isinstance(node, list):
            for item in node:
                walk(item, dict_stack)

    walk(data, [])
    return _apply_board_name_override(records, board_name_override)


def _decode_zip_entry_name(raw_name: str) -> str:
    """ZIP内エントリ名の文字化け対策。MotionBoardの内部コンテンツストア(`fs-snap`配下の
    入れ子ZIP等)はUTF-8フラグを立てずに日本語名を格納しており、Pythonの`zipfile`は
    既定でCP437としてデコードするため文字化けする。CP437の生バイト列に戻し、
    UTF-8→Shift_JISの順で再デコードを試みる(実機確認DD-002-3で確認した実際の構成)。"""
    try:
        raw_bytes = raw_name.encode("cp437")
    except UnicodeEncodeError:
        return raw_name
    for enc in ("utf-8", "shift_jis"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_name


_ZIP_NEST_DEPTH_LIMIT = 4  # 実機確認では2階層(fs-xcabinets)の入れ子までだったが、安全マージンを見て設定


def _parse_zip_bytes(data: bytes, index: ColumnIndex, label_prefix: str,
                      source_file_prefix: str, depth: int = 0,
                      board_name_override: Optional[str] = None) -> List[AliasRecord]:
    """ZIPバイト列を展開せずメモリ上で解析する。エントリ自体がZIPの場合(MotionBoardの
    内部コンテンツストアのように入れ子になっている場合)は指定の深さまで再帰的に展開する。
    拡張子を持たないエントリ(内部ストアのボード本体・データソース定義等)も、中身の
    先頭バイトでXML/ZIPかどうかを判定して拾う(拡張子だけに頼らない)。
    board_name_overrideは`_apply_board_name_override`参照。再帰呼び出し・XML/JSON解析の
    どちらにもそのまま伝播させる。"""
    records: List[AliasRecord] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        print(f"  ※{label_prefix} はZIPとして読み込めませんでした(壊れている可能性があります)")
        return records

    with zf:
        for info in zf.infolist():
            name = _decode_zip_entry_name(info.filename)
            if name.endswith("/"):
                continue
            content = zf.read(info.filename)
            label = f"{label_prefix}:{name}"
            entry_source_file = f"{source_file_prefix}:{name}"
            if content[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
                if depth >= _ZIP_NEST_DEPTH_LIMIT:
                    print(f"  ※{label} は入れ子ZIPの上限深度({_ZIP_NEST_DEPTH_LIMIT})に達したためスキップしました")
                    continue
                recs = _parse_zip_bytes(content, index, label, entry_source_file, depth=depth + 1,
                                         board_name_override=board_name_override)
            elif name.lower().endswith(".xml") or content.lstrip()[:5] == b"<?xml":
                recs = auto_parse_xml(name, content, index, source_file=entry_source_file,
                                       board_name_override=board_name_override)
            elif name.lower().endswith(".json"):
                recs = auto_parse_json(name, content, index, source_file=entry_source_file,
                                        board_name_override=board_name_override)
            else:
                continue
            if recs:
                print(f"  検出: {label} → {len(recs)}件")
            records.extend(recs)
    return records


def _auto_parse_zip(zip_path: Path, index: ColumnIndex,
                     source_file: Optional[str] = None) -> List[AliasRecord]:
    """ZIPファイルを、展開せずメモリ上で直接解析する(入れ子ZIP・拡張子なしエントリにも対応)。"""
    zip_source_file = source_file or zip_path.name
    return _parse_zip_bytes(zip_path.read_bytes(), index, zip_path.name, zip_source_file)


def _latest_snapshot(fs_file_dir: Path) -> Optional[Path]:
    """MotionBoardの内部コンテンツストア(`<ボード名>.fs-file/fs-snap/snap_*`)から、
    連番が最大(最新)のスナップショットファイルを選ぶ。連番はゼロ埋めのため文字列
    ソートで時系列順になる。"""
    snap_dir = fs_file_dir / "fs-snap"
    if not snap_dir.is_dir():
        return None
    snapshots = sorted(p for p in snap_dir.iterdir() if p.is_file() and p.name.startswith("snap_"))
    return snapshots[-1] if snapshots else None


def auto_parse_all(root_dir: Path, columns_path: str) -> List[AliasRecord]:
    columns = json.loads(Path(columns_path).read_text(encoding="utf-8"))
    index = ColumnIndex(columns)

    all_records: List[AliasRecord] = []
    xml_files = list(root_dir.rglob("*.xml"))
    json_files = list(root_dir.rglob("*.json"))
    zip_files = list(root_dir.rglob("*.zip"))
    fs_file_dirs = [p for p in root_dir.rglob("*.fs-file") if p.is_dir()]
    print(f"XML {len(xml_files)}件 / JSON {len(json_files)}件 / ZIP {len(zip_files)}件 / "
          f"MotionBoard内部ストア(.fs-file) {len(fs_file_dirs)}件を自動検出モードで走査します")

    for path in xml_files:
        recs = auto_parse_xml(path.name, path.read_bytes(), index, source_file=str(path.relative_to(root_dir)))
        if recs:
            print(f"  検出: {path.name} → {len(recs)}件")
        all_records.extend(recs)

    for path in json_files:
        recs = auto_parse_json(path.name, path.read_bytes(), index, source_file=str(path.relative_to(root_dir)))
        if recs:
            print(f"  検出: {path.name} → {len(recs)}件")
        all_records.extend(recs)

    for zip_path in zip_files:
        all_records.extend(_auto_parse_zip(zip_path, index, source_file=str(zip_path.relative_to(root_dir))))

    for fs_file_dir in fs_file_dirs:
        snapshot = _latest_snapshot(fs_file_dir)
        if snapshot is None:
            print(f"  ※{fs_file_dir.relative_to(root_dir)} にfs-snapのスナップショットが見つかりませんでした")
            continue
        rel = str(fs_file_dir.relative_to(root_dir))
        # フォルダ名(拡張子.fs-fileを除いた部分)が本当のボード名。中のデータソース定義
        # 等が持つname属性(データソース自身の名前)より確実なため、これで上書きする(DD-017)
        recs = _parse_zip_bytes(snapshot.read_bytes(), index, fs_file_dir.name, rel,
                                 board_name_override=fs_file_dir.stem)
        all_records.extend(recs)

    if not all_records:
        print("  ※1件も検出できませんでした。暗号化/独自バイナリ形式の可能性があります。")
        print("    inspect_file.py で中身を確認し、必要なら --manual を検討してください")

    return all_records


# ============================================================
# 差分取り込み(--watch): MotionBoardのバッチ等が定義ファイルを随時吐き出す
# フォルダを、タスクスケジューラ等で定期的にこのモードにかけることで、
# 毎回フォルダ全体を読み直さずに新規/更新/削除ファイルだけを取り込む。
# ============================================================
WATCH_TARGET_SUFFIXES = (".xml", ".json", ".zip")


def _record_root_file(source_file: Optional[str]) -> str:
    """ZIP内エントリのsource_file("zip名:entry名")から、差分判定の単位となる
    実ファイル(ZIP自体)のパスだけを取り出す(ZIPが変わればエントリごと全部作り直す)。"""
    return (source_file or "").split(":", 1)[0]


def _scan_source_files(root_dir: Path) -> Dict[str, dict]:
    """root_dir以下のXML/JSON/ZIPファイルの一覧を、差分検出用の指紋(mtime+size)付きで返す。
    ファイル内容までは見ない軽量な指紋なので、mtimeが変わらない改変は検知できない点に注意。"""
    fingerprints: Dict[str, dict] = {}
    for path in root_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in WATCH_TARGET_SUFFIXES:
            rel = str(path.relative_to(root_dir))
            stat = path.stat()
            fingerprints[rel] = {"mtime": stat.st_mtime, "size": stat.st_size}
    return fingerprints


def _parse_one_file(path: Path, rel: str, index: ColumnIndex) -> List[AliasRecord]:
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return auto_parse_xml(path.name, path.read_bytes(), index, source_file=rel)
    if suffix == ".json":
        return auto_parse_json(path.name, path.read_bytes(), index, source_file=rel)
    if suffix == ".zip":
        return _auto_parse_zip(path, index, source_file=rel)
    return []


def incremental_parse(root_dir: Path, columns_path: str, out_path: Path,
                       state_path: Optional[Path] = None) -> Tuple[List[dict], dict]:
    """前回実行時からの新規/更新/削除ファイルだけを差分処理し、既存の--out(board_aliases.json)と
    マージする。差分判定はファイルパス+mtime+sizeの指紋比較による(内容のハッシュまでは見ない)。
    戻り値は (マージ後の全レコード(dictのリスト), 差分件数のサマリー)。
    """
    state_path = state_path or Path(str(out_path) + ".watch_state.json")
    old_state: Dict[str, dict] = {}
    if state_path.exists():
        old_state = json.loads(state_path.read_text(encoding="utf-8"))

    columns = json.loads(Path(columns_path).read_text(encoding="utf-8"))
    index = ColumnIndex(columns)

    current_state = _scan_source_files(root_dir)
    changed = sorted(rel for rel, fp in current_state.items() if old_state.get(rel) != fp)
    removed = sorted(rel for rel in old_state if rel not in current_state)

    existing_records: List[dict] = []
    if out_path.exists():
        existing_records = json.loads(out_path.read_text(encoding="utf-8"))

    stale_files = set(changed) | set(removed)
    kept_records = [r for r in existing_records
                     if _record_root_file(r.get("source_file")) not in stale_files]

    new_records: List[AliasRecord] = []
    for rel in changed:
        recs = _parse_one_file(root_dir / rel, rel, index)
        if recs:
            print(f"  検出: {rel} → {len(recs)}件")
        new_records.extend(recs)

    merged = kept_records + [asdict(r) for r in new_records]

    state_path.write_text(json.dumps(current_state, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "changed": len(changed),
        "removed": len(removed),
        "unchanged": len(current_state) - len(changed),
        "total_records": len(merged),
    }
    return merged, summary


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
                    source_file=path.name,
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
    return [AliasRecord(table_name=t, column_name=c, display_name=d, board_name=b, item_id=i, source_file="stub")
            for t, c, d, b, i in sample]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root_dir", nargs="?", help="ボード定義が入ったフォルダ")
    parser.add_argument("--columns", help="dr_sum_metadata.pyの出力(dr_sum_columns.json)。自動検出モードで必須")
    parser.add_argument("--manual", action="store_true", help="TAG_CONFIGによる手動モードを使う")
    parser.add_argument("--out", default="board_aliases.json")
    parser.add_argument("--stub", action="store_true", help="ダミーデータで動作確認する")
    parser.add_argument("--watch", action="store_true",
                         help="前回実行からの新規/更新/削除ファイルだけを差分処理し、既存の--outと"
                              "マージする(タスクスケジューラ等で定期実行し、MotionBoardのバッチ出力を"
                              "随時取り込む運用向け)")
    parser.add_argument("--watch-state", help="差分検出用の状態ファイル(--watch時。既定値: <out>.watch_state.json)")
    args = parser.parse_args()

    if args.watch:
        if not (args.root_dir and args.columns):
            parser.error("--watch には フォルダパス と --columns dr_sum_columns.json が必須です")
        out_path = Path(args.out)
        state_path = Path(args.watch_state) if args.watch_state else None
        merged, summary = incremental_parse(Path(args.root_dir), args.columns, out_path, state_path)
        out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n差分検出: 新規/更新 {summary['changed']}件 / 削除 {summary['removed']}件 / "
              f"変更なし {summary['unchanged']}件(スキップ)")
        print(f"{summary['total_records']}件のエイリアスレコード(マージ後の合計)を {out_path} に出力しました")
        return

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
