"""
lineage.db の内容を、サーバー不要で開ける単一の静的HTMLファイルに書き出す。

web_viewer.py はPythonサーバーを立てて常に最新のlineage.dbを見るのに対し、
こちらは「その時点のスナップショット」を1つのHTMLファイルに固めるので、
メールやチャット、社内ファイル共有などでそのまま渡せる
（受け取った側はPythonが入っていなくても、ブラウザで開くだけで見られる）。

使い方:
    python export_static.py
    → column_alias_map.html が生成される

    出力ファイル名を変えたい場合:
    python export_static.py --out report_20260729.html
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from match_aliases import load_whitelist, load_whitelist_entries
from web_viewer import (
    INDEX_HTML,
    fetch_board_details,
    fetch_cross_column_patterns,
    fetch_data,
    warn_if_large,
)


def _escape_script_close(data) -> str:
    # 表示名・ボード名に"</script>"のような文字列が含まれていても<script>タグが
    # 途中で終了しないよう、埋め込み前に"</"をエスケープする(JSONの値としては同じ意味のまま)
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def build_static_html(db_path: str, whitelist: set = None, whitelist_entries: list = None,
                       threshold: float = 0.8) -> str:
    data = fetch_data(db_path, whitelist=whitelist)
    warn_if_large(len(data))
    patterns = fetch_cross_column_patterns(db_path, whitelist=whitelist, threshold=threshold)
    board_details = fetch_board_details(db_path)
    data_json = _escape_script_close(data)
    patterns_json = _escape_script_close(patterns)
    board_details_json = _escape_script_close(board_details)
    whitelist_json = _escape_script_close(whitelist_entries or [])
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = INDEX_HTML

    # 静的エクスポートはサーバーを持たないため、ホワイトリストの追加・削除ボタン
    # (fetchでAPIを叩く操作)は無効にし、登録一覧は読み取り専用の埋め込みデータで表示する(DD-003)
    html = html.replace("let STATIC_EXPORT = false;", "let STATIC_EXPORT = true;")

    # fetch('/api/columns')等でサーバーに問い合わせている部分を、埋め込み済みの
    # JSONデータを直接使う形に置き換える
    html = html.replace(
        """async function load() {
  const [colRes, patRes, boardRes, whitelistRes] = await Promise.all([
    fetch('/api/columns'), fetch('/api/patterns'), fetch('/api/board_details'), fetch('/api/whitelist'),
  ]);
  allRows = await colRes.json();
  const patterns = await patRes.json();
  const boardDetails = await boardRes.json();
  const whitelistEntries = await whitelistRes.json();
  lastPatterns = patterns;
  renderCards(allRows, patterns);
  renderTable(allRows);
  renderManyToOne(patterns.many_to_one || []);
  renderSimilarPairs(patterns.similar_pairs || []);
  renderWhitelist(whitelistEntries);
  initBoardDrilldown(boardDetails);
}""",
        f"""const EMBEDDED_DATA = {data_json};
const EMBEDDED_PATTERNS = {patterns_json};
const EMBEDDED_BOARD_DETAILS = {board_details_json};
const EMBEDDED_WHITELIST = {whitelist_json};

async function load() {{
  allRows = EMBEDDED_DATA;
  const patterns = EMBEDDED_PATTERNS;
  const boardDetails = EMBEDDED_BOARD_DETAILS;
  lastPatterns = patterns;
  renderCards(allRows, patterns);
  renderTable(allRows);
  renderManyToOne(patterns.many_to_one || []);
  renderSimilarPairs(patterns.similar_pairs || []);
  renderWhitelist(EMBEDDED_WHITELIST);
  initBoardDrilldown(boardDetails);
}}"""
    )

    # 「lineage.dbより」の説明文に生成日時を追加し、スナップショットであることを明示
    html = html.replace(
        "<p class=\"sub\">Dr.Sum物理カラム ⇔ MotionBoard表示名の対応関係(lineage.dbより)</p>",
        f"<p class=\"sub\">Dr.Sum物理カラム ⇔ MotionBoard表示名の対応関係"
        f"（{generated_at} 時点のスナップショット。以降の更新は反映されません）</p>"
    )

    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="lineage.db")
    parser.add_argument("--out", default="column_alias_map.html")
    parser.add_argument("--whitelist", help="表記ゆれ候補から除外する物理カラムの設定ファイル(naming_whitelist.json)")
    parser.add_argument("--similarity-threshold", type=float, default=0.8,
                         help="類似度による表記ゆれ候補の閾値(0〜1、デフォルト0.8)")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"エラー: {args.db} が見つかりません。先に match_aliases.py を実行してください。")
        return

    if args.whitelist and not Path(args.whitelist).exists():
        print(f"エラー: --whitelist で指定されたファイルが見つかりません: {args.whitelist}")
        return
    whitelist = load_whitelist(args.whitelist) if args.whitelist else None
    whitelist_entries = load_whitelist_entries(args.whitelist) if args.whitelist else []

    html = build_static_html(args.db, whitelist=whitelist, whitelist_entries=whitelist_entries,
                              threshold=args.similarity_threshold)
    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")
    print(f"{out_path} を書き出しました({out_path.stat().st_size:,} bytes)")
    print("このファイルをそのまま相手に渡せば、ブラウザだけで開けます(Python不要)")


if __name__ == "__main__":
    main()
