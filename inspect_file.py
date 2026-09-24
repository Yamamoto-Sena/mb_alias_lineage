"""
フェーズ1: MotionBoardのボード定義ファイル（実物）の形式を調べるための調査ツール。

実際のファイルがどんな形式か（XML / JSON / 独自バイナリ）が分かっていない前提で、
とりあえず突っ込んでみて中身のヒントを得るためのスクリプト。

使い方:
    python inspect_file.py <調べたいファイルのパス>
    python inspect_file.py <調べたいフォルダのパス>   # フォルダなら中の各ファイルを一覧
"""
import argparse
import io
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from board_parser import _parse_xml_bytes

ZIP_ENTRY_DISPLAY_LIMIT = 20


def guess_and_show(path: Path, max_depth: int = 4) -> None:
    print(f"\n=== {path} ===")
    print(f"サイズ: {path.stat().st_size:,} bytes")
    _inspect_bytes(path.read_bytes(), max_depth)


def _inspect_bytes(content: bytes, max_depth: int) -> None:
    """ファイル本体、またはZIP内エントリの中身を種類判定して表示する。"""
    head = content[:200]

    # XML判定
    if head.lstrip().startswith(b"<?xml") or head.lstrip().startswith(b"<"):
        print("形式: XMLの可能性が高い")
        try:
            _show_xml_tree(content, max_depth)
        except (ET.ParseError, ValueError, LookupError, UnicodeDecodeError) as e:
            print(f"  ※XMLとして読めませんでした: {e}")
        return

    # JSON判定
    if head.lstrip().startswith(b"{") or head.lstrip().startswith(b"["):
        print("形式: JSONの可能性が高い")
        try:
            data = json.loads(content.decode("utf-8"))
            _show_json_tree(data, max_depth)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"  ※JSONとして読めませんでした: {e}")
        return

    # ZIP判定（先頭マジックナンバーで簡易判定）。中のXML/JSONエントリを
    # ディスクに展開せず、そのまま再帰的に中身を表示する。
    if head[:2] == b"PK":
        print("形式: ZIP圧縮ファイル。中身を展開して表示します")
        _show_zip_contents(content, max_depth)
        return

    print("形式: 未知/バイナリの可能性あり")
    print("  先頭200バイトのプレビュー:")
    print(" ", head[:120])
    print("  ※暗号化 or 独自バイナリ形式の場合、パースにはWeb API経由の取得に")
    print("    切り替える方が現実的です")


def _show_zip_contents(content: bytes, max_depth: int) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        print(f"  ※ZIPとして読めませんでした: {e}")
        return

    with zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        print(f"  {len(names)}件のエントリが見つかりました"
              f"(最大{ZIP_ENTRY_DISPLAY_LIMIT}件まで表示)")
        for name in names[:ZIP_ENTRY_DISPLAY_LIMIT]:
            entry_bytes = zf.read(name)
            print(f"\n  --- ZIP内: {name} ({len(entry_bytes):,} bytes) ---")
            _inspect_bytes(entry_bytes, max_depth)
        remaining = len(names) - ZIP_ENTRY_DISPLAY_LIMIT
        if remaining > 0:
            print(f"\n  ... 他{remaining}件のエントリを省略 ...")


def _show_xml_tree(content: bytes, max_depth: int) -> None:
    root = _parse_xml_bytes(content)

    def walk(el: ET.Element, depth: int) -> None:
        if depth > max_depth:
            return
        attrs = f" attrs={dict(el.attrib)}" if el.attrib else ""
        text = (el.text or "").strip()
        text_preview = f" text='{text[:30]}'" if text else ""
        print("  " * depth + f"<{el.tag}>{attrs}{text_preview}")
        # 同じタグ名の兄弟が多い場合は最初の2件だけ表示してヒントを出す
        seen_tags = {}
        for child in el:
            seen_tags[child.tag] = seen_tags.get(child.tag, 0) + 1
        shown = {}
        for child in el:
            shown[child.tag] = shown.get(child.tag, 0) + 1
            if shown[child.tag] <= 2:
                walk(child, depth + 1)
            elif shown[child.tag] == 3:
                remaining = seen_tags[child.tag] - 2
                print("  " * (depth + 1) + f"... 同じ<{child.tag}>があと{remaining}件省略 ...")

    walk(root, 0)
    print("\n  ヒント: 「項目名」「表示名」「エイリアス」「カラム」「テーブル」")
    print("  のような意味を持つタグ・属性名を探し、board_parser.pyのTODOに反映してください")


def _show_json_tree(data, max_depth: int, depth: int = 0) -> None:
    indent = "  " * depth
    if depth > max_depth:
        print(indent + "...")
        return
    if isinstance(data, dict):
        for i, (k, v) in enumerate(data.items()):
            if i >= 10:
                print(indent + f"... 他{len(data) - 10}件のキーを省略 ...")
                break
            print(indent + f"{k}: {type(v).__name__}")
            if isinstance(v, (dict, list)):
                _show_json_tree(v, max_depth, depth + 1)
    elif isinstance(data, list):
        print(indent + f"(リスト、要素数={len(data)})")
        if data:
            _show_json_tree(data[0], max_depth, depth + 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="調べたいファイルまたはフォルダのパス")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"パスが見つかりません: {target}", file=sys.stderr)
        sys.exit(1)

    if target.is_dir():
        files = sorted(target.rglob("*"))
        files = [f for f in files if f.is_file()][:20]
        print(f"{len(files)}件のファイルが見つかりました（最大20件まで表示）")
        for f in files:
            guess_and_show(f)
    else:
        guess_and_show(target)


if __name__ == "__main__":
    main()
