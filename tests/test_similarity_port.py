import difflib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import web_viewer as wv

NODE = shutil.which("node")

TEST_PAIRS = [
    ("", ""),
    ("a", ""),
    ("", "a"),
    ("abc", "abc"),
    ("売上金額", "売上"),
    ("エリア", "地域区分"),
    ("Region", "エリア"),
    ("商品コード", "商品コード"),
    ("売上", "売上日"),
    ("顧客コード", "顧客ID"),
    ("abcdefg", "xabxcdxxefxgx"),
    ("東京都渋谷区", "東京都新宿区"),
]

JS_PATH = Path(__file__).parent / "js" / "similarity.js"


def _js_ratios(pairs) -> list:
    """tests/js/similarity.jsのsequenceMatcherRatioを実行し、全ペアの結果を取得する。"""
    runner = (
        f"const {{ sequenceMatcherRatio }} = require({json.dumps(str(JS_PATH))});\n"
        f"const pairs = {json.dumps(pairs)};\n"
        "console.log(JSON.stringify(pairs.map(([a, b]) => sequenceMatcherRatio(a, b))));\n"
    )
    result = subprocess.run(
        [NODE, "-e", runner], capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(NODE is None, reason="Node.jsが未導入のためスキップ(CIでは実行される)")
def test_sequence_matcher_ratio_matches_python_difflib():
    js_results = _js_ratios(TEST_PAIRS)
    for (a, b), js_ratio in zip(TEST_PAIRS, js_results):
        expected = difflib.SequenceMatcher(None, a, b).ratio()
        assert js_ratio == pytest.approx(expected), f"{a!r} vs {b!r}: js={js_ratio} python={expected}"


def test_similarity_js_matches_index_html_embedded_copy():
    """web_viewer.pyのINDEX_HTMLに埋め込んだsequenceMatcherRatio一式が、tests/js/similarity.js
    (module.exports行を除く)と一字一句同じであることを保証する(実装の乖離防止、DD-006)。"""
    js_source = JS_PATH.read_text(encoding="utf-8")
    func_only = js_source.split("module.exports")[0].strip()
    assert func_only in wv.INDEX_HTML
