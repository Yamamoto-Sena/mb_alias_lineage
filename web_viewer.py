"""
lineage.db をローカルのWebブラウザで見られるようにする軽量ビューア。

標準ライブラリのみで動作するので、追加のpip installは不要です。

使い方:
    python web_viewer.py

    実行すると自動的にブラウザが開きます。
    手動で開く場合は http://localhost:8000 にアクセスしてください。

    別のポートで動かしたい場合:
    python web_viewer.py --port 8080

    lineage.db が別の場所にある場合:
    python web_viewer.py --db path/to/lineage.db

    終了するには、実行中のコマンドプロンプトで Ctrl+C を押してください。
"""
import argparse
import json
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

INDEX_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>カラム・エイリアス使用状況マップ</title>
<style>
  :root {
    --bg: #f7f7f8;
    --surface: #ffffff;
    --border: #e3e3e6;
    --text: #1f1f23;
    --text-sub: #6b6b74;
    --accent: #4f46e5;
    --accent-bg: #eef0fd;
    --warn: #b45309;
    --warn-bg: #fef3e2;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, "Segoe UI", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
  }
  .wrap { max-width: 980px; margin: 0 auto; padding: 32px 24px 64px; }
  h1 { font-size: 19px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: var(--text-sub); font-size: 13px; margin: 0 0 24px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr)); gap: 12px; margin-bottom: 24px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
  .card .label { font-size: 12px; color: var(--text-sub); margin-bottom: 6px; }
  .card .value { font-size: 22px; font-weight: 600; }
  .toolbar { margin-bottom: 12px; }
  input[type=text] {
    width: 100%; padding: 9px 12px; border: 1px solid var(--border); border-radius: 8px;
    font-size: 13px; background: var(--surface); color: var(--text);
  }
  table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  thead th {
    text-align: left; font-size: 12px; color: var(--text-sub); font-weight: 500;
    padding: 10px 12px; border-bottom: 1px solid var(--border); background: #fafafb;
  }
  tbody td { padding: 10px 12px; font-size: 13px; border-bottom: 1px solid var(--border); vertical-align: top; }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr.warn { background: var(--warn-bg); }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px;
    background: var(--accent-bg); color: var(--accent); margin: 2px 4px 2px 0;
  }
  .badge.warn { background: #fde8cc; color: var(--warn); }
  .status-ok { color: var(--text-sub); font-size: 12px; }
  .status-warn { color: var(--warn); font-size: 12px; font-weight: 600; }
  .boards { color: var(--text-sub); font-size: 12px; }
  .empty { text-align: center; padding: 40px; color: var(--text-sub); }
</style>
</head>
<body>
<div class="wrap">
  <h1>カラム・エイリアス使用状況マップ</h1>
  <p class="sub">Dr.Sum物理カラム ⇔ MotionBoard表示名の対応関係(lineage.dbより)</p>

  <div class="cards" id="cards"></div>

  <div class="toolbar">
    <input type="text" id="search" placeholder="物理カラム名・テーブル名・表示名で検索">
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:16%">テーブル/ビュー</th>
        <th style="width:16%">物理カラム名</th>
        <th style="width:34%">表示名(エイリアス)</th>
        <th style="width:10%">使用件数</th>
        <th style="width:24%">使用ボード</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">該当するカラムがありません</div>
</div>

<script>
let allRows = [];

async function load() {
  const res = await fetch('/api/columns');
  allRows = await res.json();
  renderCards(allRows);
  renderTable(allRows);
}

function renderCards(rows) {
  const totalColumns = rows.length;
  const naming = rows.filter(r => r.alias_count > 1).length;
  const totalUsage = rows.reduce((sum, r) => sum + (r.usage_count || 0), 0);
  document.getElementById('cards').innerHTML = `
    <div class="card"><div class="label">総カラム数</div><div class="value">${totalColumns}</div></div>
    <div class="card"><div class="label">表記ゆれ候補</div><div class="value">${naming}</div></div>
    <div class="card"><div class="label">使用箇所(延べ)</div><div class="value">${totalUsage}</div></div>
  `;
}

function renderTable(rows) {
  const tbody = document.getElementById('tbody');
  const empty = document.getElementById('empty');
  if (rows.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = rows.map(r => {
    const isWarn = r.alias_count > 1;
    const aliasBadges = r.display_names.map(n =>
      `<span class="badge ${isWarn ? 'warn' : ''}">${escapeHtml(n)}</span>`
    ).join('');
    const boardList = r.boards.slice(0, 3).join(', ') + (r.boards.length > 3 ? ` 他${r.boards.length - 3}件` : '');
    return `
      <tr class="${isWarn ? 'warn' : ''}">
        <td>${escapeHtml(r.table_name)}</td>
        <td><code>${escapeHtml(r.column_name)}</code></td>
        <td>
          ${aliasBadges || '<span class="status-ok">-</span>'}
          ${isWarn ? `<div class="status-warn">表記ゆれ ${r.alias_count}種</div>` : ''}
        </td>
        <td>${r.usage_count}件</td>
        <td class="boards">${escapeHtml(boardList) || '-'}</td>
      </tr>
    `;
  }).join('');
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

document.getElementById('search').addEventListener('input', (e) => {
  const q = e.target.value.trim().toLowerCase();
  if (!q) { renderTable(allRows); return; }
  const filtered = allRows.filter(r =>
    r.table_name.toLowerCase().includes(q) ||
    r.column_name.toLowerCase().includes(q) ||
    r.display_names.some(n => n.toLowerCase().includes(q))
  );
  renderTable(filtered);
});

load();
</script>
</body>
</html>
"""


# 全件をページネーション無しでブラウザに転送する設計のため、件数が多いと
# 初期描画が重くなる可能性がある。本格的なページネーションは実データ規模が
# 分かってから検討する(それまでの軽量な安全策として警告のみ出す)。
LARGE_DATASET_WARNING_THRESHOLD = 3000


def warn_if_large(row_count: int) -> None:
    if row_count > LARGE_DATASET_WARNING_THRESHOLD:
        print(f"※ カラム数が{row_count}件と多いため、ブラウザでの表示が重くなる可能性があります"
              f"(現時点ではページネーション未対応です)")


def fetch_data(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.table_name, c.column_name,
               GROUP_CONCAT(DISTINCT a.display_name) AS display_names,
               COUNT(DISTINCT a.display_name) AS alias_count,
               COUNT(a.id) AS usage_count,
               GROUP_CONCAT(DISTINCT a.board_name) AS boards
        FROM columns c
        LEFT JOIN aliases a ON a.column_id = c.id
        GROUP BY c.id
        ORDER BY alias_count DESC, c.table_name, c.column_name
    """)
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "id": row[0],
            "table_name": row[1],
            "column_name": row[2],
            "display_names": row[3].split(",") if row[3] else [],
            "alias_count": row[4] or 0,
            "usage_count": row[5] or 0,
            "boards": row[6].split(",") if row[6] else [],
        })
    return result


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(INDEX_HTML)
        elif parsed.path == "/api/columns":
            try:
                data = fetch_data(self.server.db_path)
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        else:
            self.send_response(404)
            self.end_headers()

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # コンソールのアクセスログを静かにする


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="lineage.db")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="自動でブラウザを開かない")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"エラー: {args.db} が見つかりません。")
        print("先に match_aliases.py を実行して lineage.db を作成してください。")
        return

    with sqlite3.connect(args.db) as conn:
        row_count = conn.execute("SELECT COUNT(*) FROM columns").fetchone()[0]
    warn_if_large(row_count)

    server = HTTPServer(("localhost", args.port), Handler)
    server.db_path = args.db
    url = f"http://localhost:{args.port}"
    print(f"サーバーを起動しました: {url}")
    print("終了するには Ctrl+C を押してください")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止しました")


if __name__ == "__main__":
    main()
