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
import os
import sqlite3
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from match_aliases import (
    _normalize_key,
    _normalize_text,
    add_whitelist_entry,
    find_many_to_one_mappings,
    find_similar_display_name_pairs,
    load_whitelist,
    load_whitelist_entries,
    remove_whitelist_entry,
)

DEFAULT_WHITELIST_PATH = "naming_whitelist.json"

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
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px; transition: border-color .15s, box-shadow .15s;
  }
  .card.clickable { cursor: pointer; user-select: none; }
  .card.clickable:hover { border-color: #c7c9f5; }
  .card.selected { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-bg) inset; }
  .card .label { font-size: 12px; color: var(--text-sub); margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
  .card .label .hint { font-size: 10px; color: var(--accent); }
  .card .value { font-size: 22px; font-weight: 600; }
  .toolbar { margin-bottom: 12px; display: flex; gap: 8px; align-items: center; }
  .toolbar input[type=text] {
    flex: 1; padding: 9px 12px; border: 1px solid var(--border); border-radius: 8px;
    font-size: 13px; background: var(--surface); color: var(--text);
  }
  .clear-filter {
    font-size: 12px; color: var(--accent); background: var(--accent-bg); border: none;
    border-radius: 6px; padding: 8px 12px; cursor: pointer; white-space: nowrap;
  }
  .clear-filter:disabled { opacity: .4; cursor: default; }
  table { width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  thead th {
    text-align: left; font-size: 12px; color: var(--text-sub); font-weight: 500;
    padding: 10px 12px; border-bottom: 1px solid var(--border); background: #fafafb;
  }
  tbody td { padding: 10px 12px; font-size: 13px; border-bottom: 1px solid var(--border); vertical-align: top; }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr.warn { background: var(--warn-bg); }
  tbody tr.orphan { opacity: 0.55; }
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px;
    background: var(--accent-bg); color: var(--accent); margin: 2px 4px 2px 0;
  }
  .badge.warn { background: #fde8cc; color: var(--warn); }
  .badge.calc { background: #e3f5e9; color: #1a7f4b; }
  .badge.unaliased { background: #ececef; color: var(--text-sub); }
  .calc-line { margin-top: 6px; font-size: 11px; color: var(--text-sub); }
  .status-ok { color: var(--text-sub); font-size: 12px; }
  .status-warn { color: var(--warn); font-size: 12px; font-weight: 600; }
  .boards { color: var(--text-sub); font-size: 12px; }
  .empty { text-align: center; padding: 40px; color: var(--text-sub); }
  h2 { font-size: 15px; font-weight: 600; margin: 32px 0 10px; }
  .ratio { color: var(--text-sub); font-size: 12px; }

  .drilldown-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
  .drilldown-toolbar select {
    flex: 1; padding: 9px 12px; border: 1px solid var(--border); border-radius: 8px;
    font-size: 13px; background: var(--surface); color: var(--text);
  }
  .drilldown-count { font-size: 12px; color: var(--text-sub); white-space: nowrap; }
  .drilldown-hint { text-align: center; padding: 32px; color: var(--text-sub); font-size: 13px; }

  .wl-btn, .wl-remove-btn, .wl-confirm-btn, .wl-cancel-btn {
    font-size: 11px; border: none; border-radius: 6px; padding: 3px 8px;
    cursor: pointer; white-space: nowrap; margin-left: 6px;
  }
  .wl-btn, .wl-confirm-btn { color: var(--accent); background: var(--accent-bg); }
  .wl-remove-btn { color: #b91c1c; background: #fde8e8; }
  .wl-cancel-btn { color: var(--text-sub); background: #ececef; }
  .wl-reason-input {
    font-size: 12px; padding: 2px 6px; border: 1px solid var(--border); border-radius: 6px;
    width: 140px; margin-left: 6px;
  }

  .mode-toggle { display: flex; gap: 8px; margin-bottom: 12px; }
  .mode-btn {
    font-size: 12px; padding: 8px 14px; border: 1px solid var(--border); border-radius: 8px;
    background: var(--surface); color: var(--text-sub); cursor: pointer;
  }
  .mode-btn.active { border-color: var(--accent); color: var(--accent); background: var(--accent-bg); }
  .upload-panel {
    display: none; background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px; margin-bottom: 20px; font-size: 13px;
  }
  .upload-hint { color: var(--text-sub); margin: 0 0 10px; }
  .upload-panel input[type=file] { font-size: 12px; margin-right: 8px; }
  .upload-panel .load-btn {
    font-size: 12px; padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer;
    color: var(--accent); background: var(--accent-bg); margin-left: 8px;
  }
  #upload-status, #connect-status { margin-top: 8px; font-size: 12px; color: var(--text-sub); white-space: pre-wrap; }
  .connect-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); gap: 8px 16px; margin-bottom: 10px; }
  .connect-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-sub); }
  .connect-form input {
    padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px;
    font-size: 13px; background: var(--surface); color: var(--text);
  }
</style>
</head>
<body>
<div class="wrap">
  <h1>カラム・エイリアス使用状況マップ</h1>
  <p class="sub">Dr.Sum物理カラム ⇔ MotionBoard表示名の対応関係(lineage.dbより)</p>

  <div class="mode-toggle">
    <button class="mode-btn active" id="mode-demo-btn">このデータを見る</button>
    <button class="mode-btn" id="mode-upload-btn">実データをアップロードして見る</button>
    <button class="mode-btn" id="mode-connect-btn">Dr.Sumに接続</button>
  </div>
  <div class="upload-panel" id="upload-panel">
    <p class="upload-hint">
      お使いの環境で<code>python main.py</code>等を実行して作成した<code>lineage.db</code>を選んでください。
      ファイルはこのブラウザの中だけで処理され、どこにも送信されません。
      <code>naming_whitelist.json</code>は任意です(登録内容の閲覧のみ。追加・削除はこのモードでは行えません)。
    </p>
    <input type="file" id="db-file-input" accept=".db">
    <input type="file" id="whitelist-file-input" accept=".json">
    <button class="load-btn" id="load-uploaded-btn">読み込む</button>
    <div id="upload-status"></div>
  </div>
  <div class="upload-panel" id="connect-panel">
    <p class="upload-hint">
      Dr.Sum・MotionBoardの接続情報を入力すると、このサーバー上で<code>main.py</code>を実行して
      <code>lineage.db</code>を作成・更新します(<code>--connect</code>オプション付きで起動した場合のみ)。
      入力内容はこのサーバーだけで使われ、パスワードはファイルに保存されません。
    </p>
    <div class="connect-form">
      <label>ホスト名 <input type="text" id="connect-host"></label>
      <label>DB名 <input type="text" id="connect-db"></label>
      <label>ユーザー名 <input type="text" id="connect-user"></label>
      <label>パスワード <input type="password" id="connect-password"></label>
      <label>JDBCドライバーのパス <input type="text" id="connect-jdbc-jar" placeholder="dwodsjd4.jar"></label>
      <label>MotionBoardバックアップフォルダ <input type="text" id="connect-backup-dir"></label>
      <label>ホワイトリストファイル(任意) <input type="text" id="connect-whitelist"></label>
      <label>類似度閾値(任意、既定0.8) <input type="text" id="connect-threshold" placeholder="0.8"></label>
    </div>
    <button class="load-btn" id="do-connect-btn">取得</button>
    <div id="connect-status"></div>
  </div>

  <div class="cards" id="cards"></div>

  <div class="toolbar">
    <input type="text" id="search" placeholder="物理カラム名・テーブル名・表示名・ボード名で検索">
    <button class="clear-filter" id="clear-filter" disabled>カード絞り込み解除</button>
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

  <h2>多対1マッピング候補</h2>
  <table>
    <thead>
      <tr>
        <th style="width:40%">表示名</th>
        <th style="width:60%">対象物理カラム</th>
      </tr>
    </thead>
    <tbody id="many-to-one-tbody"></tbody>
  </table>
  <div id="many-to-one-empty" class="empty" style="display:none">多対1マッピング候補は見つかりませんでした</div>

  <h2>表記ゆれ候補(類似度判定・要目視確認)</h2>
  <table>
    <thead>
      <tr>
        <th style="width:38%">カラムA</th>
        <th style="width:38%">カラムB</th>
        <th style="width:24%">類似度</th>
      </tr>
    </thead>
    <tbody id="similar-pairs-tbody"></tbody>
  </table>
  <div id="similar-pairs-empty" class="empty" style="display:none">類似度による表記ゆれ候補は見つかりませんでした</div>

  <h2>ホワイトリスト登録一覧</h2>
  <table>
    <thead>
      <tr>
        <th style="width:22%">テーブル/ビュー</th>
        <th style="width:22%">物理カラム名</th>
        <th style="width:44%">理由</th>
        <th style="width:12%"></th>
      </tr>
    </thead>
    <tbody id="whitelist-tbody"></tbody>
  </table>
  <div id="whitelist-empty" class="empty" style="display:none">ホワイトリストへの登録はありません</div>

  <h2>ボード別ドリルダウン</h2>
  <div class="drilldown-toolbar">
    <select id="board-select">
      <option value="">ボードを選択してください</option>
    </select>
    <span class="drilldown-count" id="drilldown-count"></span>
  </div>
  <div id="drilldown-hint" class="drilldown-hint">ボードを選択すると、そのボードが使用している物理カラム→表示名の対応が一覧表示されます</div>
  <table id="drilldown-table" style="display:none">
    <thead>
      <tr>
        <th style="width:22%">テーブル/ビュー</th>
        <th style="width:22%">物理カラム名</th>
        <th style="width:34%">表示名</th>
        <th style="width:12%">種別</th>
        <th style="width:10%">アイテムID</th>
      </tr>
    </thead>
    <tbody id="drilldown-tbody"></tbody>
  </table>
</div>

<script>
let STATIC_EXPORT = false; // export_static.pyが埋め込みビルド時にtrueへ書き換える
let UPLOADED_MODE = false; // 実データアップロードモード中はtrue(DD-006)。編集ボタンを無効化する
let allRows = [];
let activeCardFilter = null; // null | 'naming' | 'unaliased' | 'orphan'

// ============================================================
// 類似度アルゴリズム(difflib.SequenceMatcher.ratioの移植、DD-006)
// tests/js/similarity.js と一字一句同じ内容に保つこと(tests/test_similarity_port.pyで保証)
// ============================================================
function findLongestMatch(a, b, alo, ahi, blo, bhi, b2j) {
  let besti = alo, bestj = blo, bestsize = 0;
  let j2len = {};
  for (let i = alo; i < ahi; i++) {
    const newj2len = {};
    const indices = b2j[a[i]] || [];
    for (const j of indices) {
      if (j < blo) continue;
      if (j >= bhi) break;
      const k = (j2len[j - 1] || 0) + 1;
      newj2len[j] = k;
      if (k > bestsize) {
        besti = i - k + 1;
        bestj = j - k + 1;
        bestsize = k;
      }
    }
    j2len = newj2len;
  }
  return [besti, bestj, bestsize];
}

function getMatchingBlocks(a, b) {
  const b2j = {};
  for (let j = 0; j < b.length; j++) {
    const c = b[j];
    (b2j[c] = b2j[c] || []).push(j);
  }
  const queue = [[0, a.length, 0, b.length]];
  const matchingBlocks = [];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = findLongestMatch(a, b, alo, ahi, blo, bhi, b2j);
    if (k) {
      matchingBlocks.push([i, j, k]);
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  return matchingBlocks;
}

function sequenceMatcherRatio(a, b) {
  const blocks = getMatchingBlocks(a, b);
  let matches = 0;
  for (const block of blocks) matches += block[2];
  const total = a.length + b.length;
  return total === 0 ? 1.0 : (2.0 * matches) / total;
}

// ============================================================
// 実データアップロードモード用のクエリ層(web_viewer.pyのfetch_data等と同一のSQL文、DD-006)
// ============================================================
function normalizeText(s) {
  return (s || "").trim().normalize("NFKC").toUpperCase();
}

function normalizeKey(tableName, columnName) {
  return normalizeText(tableName) + "\\u0000" + normalizeText(columnName);
}

function jsFetchData(db, whitelistSet) {
  const res = db.exec(`
    SELECT c.id, c.table_name, c.column_name,
           GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS display_names,
           GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='calc' THEN a.display_name END) AS calc_names,
           COUNT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS alias_count,
           COUNT(a.id) AS usage_count,
           GROUP_CONCAT(DISTINCT a.board_name) AS boards
    FROM columns c
    LEFT JOIN aliases a ON a.column_id = c.id
    GROUP BY c.id
    ORDER BY alias_count DESC, c.table_name, c.column_name
  `);
  if (!res.length) return [];
  return res[0].values.map(row => {
    const [id, table_name, column_name, displayNamesRaw, calcNamesRaw, aliasCount, usageCount, boardsRaw] = row;
    const display_names = displayNamesRaw ? displayNamesRaw.split(",") : [];
    const isWhitelisted = whitelistSet.has(normalizeKey(table_name, column_name));
    return {
      id, table_name, column_name, display_names,
      calc_names: calcNamesRaw ? calcNamesRaw.split(",") : [],
      alias_count: aliasCount || 0,
      usage_count: usageCount || 0,
      boards: boardsRaw ? boardsRaw.split(",") : [],
      is_unaliased: display_names.some(n => normalizeText(column_name) === normalizeText(n)),
      is_orphan: (usageCount || 0) === 0,
      is_naming_variant: (aliasCount || 0) > 1 && !isWhitelisted,
    };
  });
}

function jsFindManyToOne(db, whitelistSet) {
  const res = db.exec(`
    SELECT a.display_name, c.table_name, c.column_name
    FROM aliases a
    JOIN columns c ON c.id = a.column_id
    WHERE a.usage_type = 'alias'
  `);
  const byDisplayName = new Map();
  if (res.length) {
    for (const [display_name, table_name, column_name] of res[0].values) {
      if (whitelistSet.has(normalizeKey(table_name, column_name))) continue;
      if (!byDisplayName.has(display_name)) byDisplayName.set(display_name, new Map());
      byDisplayName.get(display_name).set(`${table_name}\\u0000${column_name}`, { table_name, column_name });
    }
  }
  const results = [];
  for (const [display_name, cols] of byDisplayName) {
    if (cols.size > 1) results.push({ display_name, columns: Array.from(cols.values()) });
  }
  return results;
}

function jsFindSimilarPairs(db, whitelistSet, threshold) {
  const res = db.exec(`
    SELECT DISTINCT c.id, c.table_name, c.column_name, a.display_name
    FROM aliases a
    JOIN columns c ON c.id = a.column_id
    WHERE a.usage_type = 'alias'
  `);
  if (!res.length) return [];
  const entries = res[0].values
    .filter(([, table_name, column_name]) => !whitelistSet.has(normalizeKey(table_name, column_name)))
    .map(([column_id, table_name, column_name, display_name]) => ({ column_id, table_name, column_name, display_name }));

  const results = [];
  for (let i = 0; i < entries.length; i++) {
    for (let j = i + 1; j < entries.length; j++) {
      const a = entries[i], b = entries[j];
      if (a.column_id === b.column_id) continue;
      const ratio = sequenceMatcherRatio(a.display_name, b.display_name);
      if (ratio >= threshold) {
        results.push({
          column_a: { table_name: a.table_name, column_name: a.column_name, display_name: a.display_name },
          column_b: { table_name: b.table_name, column_name: b.column_name, display_name: b.display_name },
          ratio,
        });
      }
    }
  }
  return results;
}

function jsFetchCrossColumnPatterns(db, whitelistSet, threshold) {
  return {
    many_to_one: jsFindManyToOne(db, whitelistSet),
    similar_pairs: jsFindSimilarPairs(db, whitelistSet, threshold),
  };
}

function jsFetchBoardDetails(db) {
  const res = db.exec(`
    SELECT a.board_name, c.table_name, c.column_name, a.display_name, a.usage_type, a.item_id
    FROM aliases a
    JOIN columns c ON c.id = a.column_id
    ORDER BY a.board_name, c.table_name, c.column_name
  `);
  if (!res.length) return [];
  return res[0].values.map(([board_name, table_name, column_name, display_name, usage_type, item_id]) => ({
    board_name, table_name, column_name, display_name, usage_type, item_id,
  }));
}

let sqlJsPromise = null;
function loadSqlJs() {
  if (!sqlJsPromise) {
    const SQLJS_BASE = "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.14.1/";
    sqlJsPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SQLJS_BASE + "sql-wasm.js";
      script.onload = () => {
        initSqlJs({ locateFile: f => SQLJS_BASE + f }).then(resolve, reject);
      };
      script.onerror = () => reject(new Error("sql.jsの読み込みに失敗しました(ネットワーク接続を確認してください)"));
      document.head.appendChild(script);
    });
  }
  return sqlJsPromise;
}

async function handleLoadUploaded() {
  const dbFile = document.getElementById("db-file-input").files[0];
  const wlFile = document.getElementById("whitelist-file-input").files[0];
  const statusEl = document.getElementById("upload-status");
  if (!dbFile) {
    statusEl.textContent = "lineage.dbファイルを選択してください";
    return;
  }
  statusEl.textContent = "読み込み中...";
  try {
    const SQL = await loadSqlJs();
    const buf = await dbFile.arrayBuffer();
    const db = new SQL.Database(new Uint8Array(buf));

    let whitelistEntries = [];
    if (wlFile) {
      const parsed = JSON.parse(await wlFile.text());
      whitelistEntries = parsed.excluded_columns || [];
    }
    const whitelistSet = new Set(
      whitelistEntries.map(e => normalizeKey(e.table_name, e.column_name))
    );

    UPLOADED_MODE = true;
    allRows = jsFetchData(db, whitelistSet);
    const patterns = jsFetchCrossColumnPatterns(db, whitelistSet, 0.8);
    const boardDetails = jsFetchBoardDetails(db);
    lastPatterns = patterns;
    renderCards(allRows, patterns);
    renderTable(allRows);
    renderManyToOne(patterns.many_to_one || []);
    renderSimilarPairs(patterns.similar_pairs || []);
    renderWhitelist(whitelistEntries);
    initBoardDrilldown(boardDetails);
    db.close();
    statusEl.textContent = `読み込み完了(${allRows.length}カラム)`;
  } catch (err) {
    statusEl.textContent = "エラー: " + err.message;
  }
}

const CARD_DEFS = [
  { key: null, label: "総カラム数", value: (rows, patterns) => rows.length },
  { key: "naming", label: "表記ゆれ候補", value: (rows) => rows.filter(r => r.is_naming_variant).length },
  { key: null, label: "使用箇所(延べ)", value: (rows) => rows.reduce((sum, r) => sum + (r.usage_count || 0), 0) },
  { key: null, label: "カスタム項目/計算式で使用", value: (rows) => rows.filter(r => r.calc_names && r.calc_names.length > 0).length },
  { key: "unaliased", label: "物理名そのまま", value: (rows) => rows.filter(r => r.is_unaliased).length },
  { key: "orphan", label: "未使用カラム", value: (rows) => rows.filter(r => r.is_orphan).length },
  { key: null, label: "多対1候補", value: (rows, patterns) => (patterns.many_to_one || []).length },
  { key: null, label: "類似度候補", value: (rows, patterns) => (patterns.similar_pairs || []).length },
];

async function load() {
  const [colRes, patRes, boardRes, whitelistRes] = await Promise.all([
    fetch('/api/columns'), fetch('/api/patterns'), fetch('/api/board_details'), fetch('/api/whitelist'),
  ]);
  let colData = await colRes.json();
  let patterns = await patRes.json();
  let boardDetails = await boardRes.json();
  let whitelistEntries = await whitelistRes.json();
  // lineage.dbがまだ存在しない場合(DD-007の--connect起動直後)、各APIは
  // {"error": ...}を返す。配列/オブジェクトでない値はレンダリング関数を壊すため空にする
  if (!Array.isArray(colData)) colData = [];
  if (!patterns || typeof patterns !== 'object' || Array.isArray(patterns)) patterns = {};
  if (!Array.isArray(boardDetails)) boardDetails = [];
  if (!Array.isArray(whitelistEntries)) whitelistEntries = [];
  allRows = colData;
  lastPatterns = patterns;
  renderCards(allRows, patterns);
  renderTable(allRows);
  renderManyToOne(patterns.many_to_one || []);
  renderSimilarPairs(patterns.similar_pairs || []);
  renderWhitelist(whitelistEntries);
  initBoardDrilldown(boardDetails);
}

function whitelistAddButton(tableName, columnName) {
  if (STATIC_EXPORT || UPLOADED_MODE) return '';
  return `<span class="wl-add" data-table="${escapeHtml(tableName)}" data-column="${escapeHtml(columnName)}">${wlButtonHtml()}</span>`;
}

function wlButtonHtml() {
  return `<button class="wl-btn">ホワイトリストに追加</button>`;
}

function wlFormHtml() {
  return `<input type="text" class="wl-reason-input" placeholder="理由(任意)">` +
    `<button class="wl-confirm-btn">登録</button>` +
    `<button class="wl-cancel-btn">キャンセル</button>`;
}

async function submitWhitelistAdd(wrap) {
  const reason = wrap.querySelector('.wl-reason-input').value;
  await fetch('/api/whitelist', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({table_name: wrap.dataset.table, column_name: wrap.dataset.column, reason}),
  });
  location.reload();
}

function renderCards(rows, patterns) {
  document.getElementById('cards').innerHTML = CARD_DEFS.map(def => {
    const clickable = !!def.key;
    const selected = clickable && activeCardFilter === def.key;
    const classes = ["card", clickable ? "clickable" : "", selected ? "selected" : ""].filter(Boolean).join(" ");
    const hint = clickable ? '<span class="hint">クリックで絞込</span>' : '';
    const a11y = clickable
      ? `role="button" tabindex="0" aria-pressed="${selected}" aria-label="${escapeHtml(def.label)}でカラム一覧を絞り込む"`
      : '';
    return `<div class="${classes}" data-key="${def.key || ''}" data-clickable="${clickable}" ${a11y}>
      <div class="label">${def.label}${hint}</div>
      <div class="value">${def.value(rows, patterns)}</div>
    </div>`;
  }).join('');

  document.querySelectorAll('.card[data-clickable="true"]').forEach(el => {
    const toggle = () => {
      const key = el.dataset.key;
      activeCardFilter = (activeCardFilter === key) ? null : key;
      renderCards(allRows, lastPatterns);
      applyFilters();
    };
    el.addEventListener('click', toggle);
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
    });
  });
}

let lastPatterns = {};

function matchesCardFilter(r) {
  if (!activeCardFilter) return true;
  if (activeCardFilter === "naming") return r.is_naming_variant;
  if (activeCardFilter === "unaliased") return r.is_unaliased;
  if (activeCardFilter === "orphan") return r.is_orphan;
  return true;
}

function matchesSearch(r, q) {
  if (!q) return true;
  return r.table_name.toLowerCase().includes(q) ||
    r.column_name.toLowerCase().includes(q) ||
    r.display_names.some(n => n.toLowerCase().includes(q)) ||
    (r.calc_names || []).some(n => n.toLowerCase().includes(q)) ||
    r.boards.some(b => b.toLowerCase().includes(q));
}

function applyFilters() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  document.getElementById('clear-filter').disabled = !activeCardFilter;
  renderTable(allRows.filter(r => matchesCardFilter(r) && matchesSearch(r, q)));
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
    const isWarn = !!r.is_naming_variant;
    const isOrphan = !!r.is_orphan;
    const calcNames = r.calc_names || [];
    const aliasBadges = r.display_names.map(n =>
      `<span class="badge ${isWarn ? 'warn' : ''}">${escapeHtml(n)}</span>`
    ).join('');
    const calcBadges = calcNames.map(n =>
      `<span class="badge calc">${escapeHtml(n)}</span>`
    ).join('');
    const unaliasedBadge = r.is_unaliased ? '<span class="badge unaliased">物理名そのまま</span>' : '';
    const boardList = r.boards.slice(0, 3).join(', ') + (r.boards.length > 3 ? ` 他${r.boards.length - 3}件` : '');
    return `
      <tr class="${isWarn ? 'warn' : ''} ${isOrphan ? 'orphan' : ''}">
        <td>${escapeHtml(r.table_name)}</td>
        <td><code>${escapeHtml(r.column_name)}</code></td>
        <td>
          ${aliasBadges || (calcBadges ? '' : '<span class="status-ok">-</span>')}
          ${unaliasedBadge}
          ${isWarn ? `<div class="status-warn">表記ゆれ ${r.alias_count}種 ${whitelistAddButton(r.table_name, r.column_name)}</div>` : ''}
          ${calcBadges ? `<div class="calc-line">カスタム項目/計算式で使用: ${calcBadges}</div>` : ''}
          ${isOrphan ? '<div class="calc-line">未使用(MotionBoardで参照なし)</div>' : ''}
        </td>
        <td>${r.usage_count}件</td>
        <td class="boards">${escapeHtml(boardList) || '-'}</td>
      </tr>
    `;
  }).join('');
}

function renderManyToOne(items) {
  const tbody = document.getElementById('many-to-one-tbody');
  const empty = document.getElementById('many-to-one-empty');
  if (!items || items.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  tbody.innerHTML = items.map(item => {
    const cols = item.columns.map(c =>
      `<code>[${escapeHtml(c.table_name)}].${escapeHtml(c.column_name)}</code>${whitelistAddButton(c.table_name, c.column_name)}`
    ).join('<br>');
    return `
      <tr>
        <td><span class="badge warn">${escapeHtml(item.display_name)}</span></td>
        <td>${cols}</td>
      </tr>
    `;
  }).join('');
}

function renderSimilarPairs(items) {
  const tbody = document.getElementById('similar-pairs-tbody');
  const empty = document.getElementById('similar-pairs-empty');
  if (!items || items.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  tbody.innerHTML = items.map(item => `
    <tr>
      <td><code>[${escapeHtml(item.column_a.table_name)}].${escapeHtml(item.column_a.column_name)}</code> 「${escapeHtml(item.column_a.display_name)}」${whitelistAddButton(item.column_a.table_name, item.column_a.column_name)}</td>
      <td><code>[${escapeHtml(item.column_b.table_name)}].${escapeHtml(item.column_b.column_name)}</code> 「${escapeHtml(item.column_b.display_name)}」${whitelistAddButton(item.column_b.table_name, item.column_b.column_name)}</td>
      <td class="ratio">${(item.ratio * 100).toFixed(0)}%</td>
    </tr>
  `).join('');
}

function renderWhitelist(entries) {
  const tbody = document.getElementById('whitelist-tbody');
  const empty = document.getElementById('whitelist-empty');
  if (!entries || entries.length === 0) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';
  tbody.innerHTML = entries.map(e => `
    <tr>
      <td>${escapeHtml(e.table_name)}</td>
      <td><code>${escapeHtml(e.column_name)}</code></td>
      <td>${escapeHtml(e.reason || '')}</td>
      <td>${(STATIC_EXPORT || UPLOADED_MODE) ? '' : `<button class="wl-remove-btn" data-table="${escapeHtml(e.table_name)}" data-column="${escapeHtml(e.column_name)}">削除</button>`}</td>
    </tr>
  `).join('');
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ============================================================
// ボード別ドリルダウン
// ============================================================
let boardDetailsByBoard = {};

function initBoardDrilldown(boardDetails) {
  boardDetailsByBoard = {};
  boardDetails.forEach(d => {
    (boardDetailsByBoard[d.board_name] = boardDetailsByBoard[d.board_name] || []).push(d);
  });
  const boardNames = Object.keys(boardDetailsByBoard)
    .sort((a, b) => boardDetailsByBoard[b].length - boardDetailsByBoard[a].length);

  const select = document.getElementById('board-select');
  select.innerHTML = '<option value="">ボードを選択してください</option>' +
    boardNames.map(name =>
      `<option value="${escapeHtml(name)}">${escapeHtml(name)}（${boardDetailsByBoard[name].length}件）</option>`
    ).join('');
  select.addEventListener('change', () => renderDrilldown(select.value));
  renderDrilldown('');
}

function renderDrilldown(boardName) {
  const hint = document.getElementById('drilldown-hint');
  const table = document.getElementById('drilldown-table');
  const tbody = document.getElementById('drilldown-tbody');
  const countLabel = document.getElementById('drilldown-count');

  if (!boardName) {
    hint.style.display = 'block';
    table.style.display = 'none';
    countLabel.textContent = '';
    return;
  }

  const rows = boardDetailsByBoard[boardName] || [];
  hint.style.display = 'none';
  table.style.display = 'table';
  countLabel.textContent = `${rows.length}件`;

  tbody.innerHTML = rows.map(d => `
    <tr>
      <td>${escapeHtml(d.table_name)}</td>
      <td><code>${escapeHtml(d.column_name)}</code></td>
      <td>${escapeHtml(d.display_name)}</td>
      <td><span class="badge ${d.usage_type === 'calc' ? 'calc' : ''}">${d.usage_type === 'calc' ? '計算式' : 'エイリアス'}</span></td>
      <td>${escapeHtml(d.item_id || '')}</td>
    </tr>
  `).join('');
}

document.getElementById('search').addEventListener('input', applyFilters);

document.getElementById('clear-filter').addEventListener('click', () => {
  activeCardFilter = null;
  renderCards(allRows, lastPatterns);
  applyFilters();
});

document.body.addEventListener('click', async (e) => {
  const addBtn = e.target.closest('.wl-btn');
  if (addBtn) {
    // window.prompt()は自動操作ブラウザでは未サポートのため、ページ内でその場に
    // 入力欄を展開する(DD-004)。
    const wrap = addBtn.closest('.wl-add');
    wrap.innerHTML = wlFormHtml();
    wrap.querySelector('.wl-reason-input').focus();
    return;
  }
  const cancelBtn = e.target.closest('.wl-cancel-btn');
  if (cancelBtn) {
    const wrap = cancelBtn.closest('.wl-add');
    wrap.innerHTML = wlButtonHtml();
    return;
  }
  const confirmBtn = e.target.closest('.wl-confirm-btn');
  if (confirmBtn) {
    await submitWhitelistAdd(confirmBtn.closest('.wl-add'));
    return;
  }
  const delBtn = e.target.closest('.wl-remove-btn');
  if (delBtn) {
    await fetch('/api/whitelist/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({table_name: delBtn.dataset.table, column_name: delBtn.dataset.column}),
    });
    location.reload();
  }
});

document.body.addEventListener('keydown', async (e) => {
  if (e.key !== 'Enter' || !e.target.classList.contains('wl-reason-input')) return;
  e.preventDefault();
  await submitWhitelistAdd(e.target.closest('.wl-add'));
});

function setActiveMode(activeBtnId) {
  ['mode-demo-btn', 'mode-upload-btn', 'mode-connect-btn'].forEach(id => {
    document.getElementById(id).classList.toggle('active', id === activeBtnId);
  });
  document.getElementById('upload-panel').style.display = activeBtnId === 'mode-upload-btn' ? 'block' : 'none';
  document.getElementById('connect-panel').style.display = activeBtnId === 'mode-connect-btn' ? 'block' : 'none';
}

document.getElementById('mode-upload-btn').addEventListener('click', () => {
  setActiveMode('mode-upload-btn');
});

document.getElementById('mode-connect-btn').addEventListener('click', () => {
  setActiveMode('mode-connect-btn');
});

document.getElementById('mode-demo-btn').addEventListener('click', () => {
  setActiveMode('mode-demo-btn');
  document.getElementById('upload-status').textContent = '';
  UPLOADED_MODE = false;
  load();
});

document.getElementById('load-uploaded-btn').addEventListener('click', handleLoadUploaded);

document.getElementById('do-connect-btn').addEventListener('click', async () => {
  const statusEl = document.getElementById('connect-status');
  const body = {
    host: document.getElementById('connect-host').value.trim(),
    db: document.getElementById('connect-db').value.trim(),
    user: document.getElementById('connect-user').value.trim(),
    password: document.getElementById('connect-password').value,
    jdbc_jar: document.getElementById('connect-jdbc-jar').value.trim(),
    backup_dir: document.getElementById('connect-backup-dir').value.trim(),
    whitelist: document.getElementById('connect-whitelist').value.trim(),
    similarity_threshold: document.getElementById('connect-threshold').value.trim(),
  };
  statusEl.textContent = '取得中...(Dr.Sumサーバー・MotionBoardフォルダの規模によっては時間がかかります)';
  try {
    const res = await fetch('/api/connect', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      statusEl.textContent = 'エラー: ' + (data.error || `HTTP ${res.status}`);
      return;
    }
    statusEl.textContent = '取得完了。画面を更新します...';
    setActiveMode('mode-demo-btn');
    await load();
  } catch (err) {
    statusEl.textContent = 'エラー: ' + err.message;
  }
});

if (STATIC_EXPORT) {
  document.getElementById('mode-connect-btn').style.display = 'none';
}

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


def fetch_data(db_path: str, whitelist: set = None):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.table_name, c.column_name,
               GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS display_names,
               GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='calc' THEN a.display_name END) AS calc_names,
               COUNT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS alias_count,
               COUNT(a.id) AS usage_count,
               GROUP_CONCAT(DISTINCT a.board_name) AS boards
        FROM columns c
        LEFT JOIN aliases a ON a.column_id = c.id
        GROUP BY c.id
        ORDER BY alias_count DESC, c.table_name, c.column_name
    """)
    rows = cur.fetchall()
    conn.close()

    whitelist = whitelist or set()
    result = []
    for row in rows:
        table_name = row[1]
        column_name = row[2]
        display_names = row[3].split(",") if row[3] else []
        alias_count = row[5] or 0
        usage_count = row[6] or 0
        is_whitelisted = _normalize_key(table_name, column_name) in whitelist
        result.append({
            "id": row[0],
            "table_name": table_name,
            "column_name": column_name,
            "display_names": display_names,
            "calc_names": row[4].split(",") if row[4] else [],
            "alias_count": alias_count,
            "usage_count": usage_count,
            "boards": row[7].split(",") if row[7] else [],
            "is_unaliased": any(_normalize_text(column_name) == _normalize_text(n) for n in display_names),
            "is_orphan": usage_count == 0,
            # 1対多の表記ゆれ候補としてハイライトするかどうか(alias_countが2以上でも、
            # ホワイトリスト対象なら候補としては扱わない)
            "is_naming_variant": alias_count > 1 and not is_whitelisted,
        })
    return result


def fetch_cross_column_patterns(db_path: str, whitelist: set = None, threshold: float = 0.8) -> dict:
    """複数カラムを横断する表記ゆれパターン(多対1マッピング・類似度候補)を取得する。"""
    return {
        "many_to_one": find_many_to_one_mappings(db_path, whitelist=whitelist),
        "similar_pairs": find_similar_display_name_pairs(db_path, threshold=threshold, whitelist=whitelist),
    }


def fetch_board_details(db_path: str) -> list:
    """ボード別ドリルダウン用に、aliasesの生レコード(1行1エイリアス)をboard_name単位で
    取得する。fetch_dataはカラム単位に集計するため「このボードではどの表示名か」が
    失われるが、こちらは集計前の対応をそのまま返す(DD-002-4)。"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT a.board_name, c.table_name, c.column_name, a.display_name, a.usage_type, a.item_id
        FROM aliases a
        JOIN columns c ON c.id = a.column_id
        ORDER BY a.board_name, c.table_name, c.column_name
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "board_name": row[0],
            "table_name": row[1],
            "column_name": row[2],
            "display_name": row[3],
            "usage_type": row[4],
            "item_id": row[5],
        }
        for row in rows
    ]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(INDEX_HTML)
        elif parsed.path == "/api/columns":
            try:
                data = fetch_data(self.server.db_path, whitelist=self.server.whitelist)
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        elif parsed.path == "/api/patterns":
            try:
                data = fetch_cross_column_patterns(
                    self.server.db_path,
                    whitelist=self.server.whitelist,
                    threshold=self.server.similarity_threshold,
                )
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        elif parsed.path == "/api/board_details":
            try:
                data = fetch_board_details(self.server.db_path)
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        elif parsed.path == "/api/whitelist":
            try:
                data = load_whitelist_entries(self.server.whitelist_path)
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self._read_json_body()
        except ValueError as e:
            self._send_json({"error": str(e)}, status=400)
            return

        if parsed.path == "/api/whitelist":
            self._handle_whitelist_add(body)
        elif parsed.path == "/api/whitelist/delete":
            self._handle_whitelist_delete(body)
        elif parsed.path == "/api/connect":
            self._handle_connect(body)
        else:
            self.send_response(404)
            self.end_headers()

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("リクエストボディがJSONとして解釈できません")
        if not isinstance(data, dict):
            raise ValueError("リクエストボディはJSONオブジェクトである必要があります")
        return data

    def _extract_table_column(self, body: dict):
        """table_name/column_nameを取り出す(DD-003)。不正な場合は400を返しNoneを返す。"""
        table_name = body.get("table_name")
        column_name = body.get("column_name")
        if not isinstance(table_name, str) or not table_name.strip() \
                or not isinstance(column_name, str) or not column_name.strip():
            self._send_json({"error": "table_nameとcolumn_nameは必須です"}, status=400)
            return None
        return table_name, column_name

    def _handle_whitelist_add(self, body: dict) -> None:
        parsed_names = self._extract_table_column(body)
        if parsed_names is None:
            return
        table_name, column_name = parsed_names
        reason = body.get("reason") or ""
        entries = add_whitelist_entry(self.server.whitelist_path, table_name, column_name, reason=reason)
        self.server.whitelist = {
            _normalize_key(e["table_name"], e["column_name"]) for e in entries
        }
        self._send_json({"ok": True, "entries": entries})

    def _handle_whitelist_delete(self, body: dict) -> None:
        parsed_names = self._extract_table_column(body)
        if parsed_names is None:
            return
        table_name, column_name = parsed_names
        entries = remove_whitelist_entry(self.server.whitelist_path, table_name, column_name)
        self.server.whitelist = {
            _normalize_key(e["table_name"], e["column_name"]) for e in entries
        }
        self._send_json({"ok": True, "entries": entries})

    def _handle_connect(self, body: dict) -> None:
        """DD-007: 画面からDr.Sum接続情報を受け取り、main.pyを実行してlineage.dbを更新する。

        --connect未指定時は無効(403)。パスワードはコマンドライン引数に乗せず、
        main.pyを起動するsubprocessの環境変数(DR_SUM_PASSWORD)経由で渡す
        (dr_sum_metadata.pyが既に読むフォールバック。プロセス一覧に平文表示されないようにするため)。
        """
        if not getattr(self.server, "connect_enabled", False):
            self._send_json(
                {"error": "この機能は無効です。--connect オプション付きで起動してください。"},
                status=403,
            )
            return

        required = ["host", "db", "user", "jdbc_jar", "backup_dir"]
        missing = [k for k in required if not str(body.get(k) or "").strip()]
        if missing:
            self._send_json({"error": f"必須項目が未入力です: {', '.join(missing)}"}, status=400)
            return

        cmd = [
            sys.executable, "main.py",
            "--backup-dir", body["backup_dir"],
            "--host", body["host"],
            "--db", body["db"],
            "--user", body["user"],
            "--jdbc-jar", body["jdbc_jar"],
        ]
        if body.get("whitelist"):
            cmd += ["--whitelist", body["whitelist"]]
        if body.get("similarity_threshold"):
            cmd += ["--similarity-threshold", str(body["similarity_threshold"])]

        env = dict(os.environ)
        if body.get("password"):
            env["DR_SUM_PASSWORD"] = body["password"]

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            self._send_json(
                {"error": (result.stdout + "\n" + result.stderr).strip() or "main.pyの実行に失敗しました"},
                status=500,
            )
            return
        self._send_json({"ok": True, "output": result.stdout})

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
    parser.add_argument("--whitelist", help="表記ゆれ候補から除外する物理カラムの設定ファイル"
                                             f"(未指定時は既定パス「{DEFAULT_WHITELIST_PATH}」を使用。"
                                             "ファイルが無くても画面からの追加操作で新規作成される)")
    parser.add_argument("--similarity-threshold", type=float, default=0.8,
                         help="類似度による表記ゆれ候補の閾値(0〜1、デフォルト0.8)")
    parser.add_argument("--connect", action="store_true",
                         help="画面の「Dr.Sumに接続」フォームからmain.pyを実行してlineage.dbを"
                              "作成・更新できるようにする(DD-007)。既定では無効")
    args = parser.parse_args()

    if not Path(args.db).exists() and not args.connect:
        print(f"エラー: {args.db} が見つかりません。")
        print("先に match_aliases.py を実行して lineage.db を作成するか、"
              "--connect オプションを付けて起動してください。")
        return

    # --whitelistを明示指定した場合はtypo検知のため実在確認する。未指定時は既定パスを使い、
    # ファイルが無くても起動時エラーにはしない(画面からの追加操作で新規作成される。DD-003)。
    if args.whitelist and not Path(args.whitelist).exists():
        print(f"エラー: --whitelist で指定されたファイルが見つかりません: {args.whitelist}")
        return
    whitelist_path = args.whitelist or DEFAULT_WHITELIST_PATH
    whitelist = load_whitelist(whitelist_path) if Path(whitelist_path).exists() else set()

    if Path(args.db).exists():
        with sqlite3.connect(args.db) as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM columns").fetchone()[0]
        warn_if_large(row_count)
    else:
        print(f"※ {args.db} がまだ存在しません。画面の「Dr.Sumに接続」から作成してください。")

    # 1リクエストずつしか処理できないHTTPServerだと、Promise.allで/api/columnsと
    # /api/patternsを並行取得する際にKeep-Alive接続待ちでハングすることがあるため、
    # リクエストごとにスレッドを立てるThreadingHTTPServerを使う
    server = ThreadingHTTPServer(("localhost", args.port), Handler)
    server.db_path = args.db
    server.whitelist = whitelist
    server.whitelist_path = whitelist_path
    server.similarity_threshold = args.similarity_threshold
    server.connect_enabled = args.connect
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
