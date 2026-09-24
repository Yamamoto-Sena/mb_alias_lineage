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

from web_viewer import INDEX_HTML, fetch_data, warn_if_large


def build_static_html(db_path: str) -> str:
    data = fetch_data(db_path)
    warn_if_large(len(data))
    data_json = json.dumps(data, ensure_ascii=False)
    # 表示名・ボード名に"</script>"のような文字列が含まれていても<script>タグが
    # 途中で終了しないよう、埋め込み前に"</"をエスケープする(JSONの値としては同じ意味のまま)
    data_json = data_json.replace("</", "<\\/")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = INDEX_HTML

    # fetch('/api/columns') でサーバーに問い合わせている部分を、
    # 埋め込み済みのJSONデータを直接使う形に置き換える
    html = html.replace(
        """async function load() {
  const res = await fetch('/api/columns');
  allRows = await res.json();
  renderCards(allRows);
  renderTable(allRows);
}""",
        f"""const EMBEDDED_DATA = {data_json};

async function load() {{
  allRows = EMBEDDED_DATA;
  renderCards(allRows);
  renderTable(allRows);
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
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"エラー: {args.db} が見つかりません。先に match_aliases.py を実行してください。")
        return

    html = build_static_html(args.db)
    out_path = Path(args.out)
    out_path.write_text(html, encoding="utf-8")
    print(f"{out_path} を書き出しました({out_path.stat().st_size:,} bytes)")
    print("このファイルをそのまま相手に渡せば、ブラウザだけで開けます(Python不要)")


if __name__ == "__main__":
    main()
