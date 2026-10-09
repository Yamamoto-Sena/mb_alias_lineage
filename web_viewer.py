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
import tempfile
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
<meta name="viewport" content="width=device-width, initial-scale=1">
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
    --highlight-bg: #fff3b0;
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
  .large-warning {
    background: var(--warn-bg); color: var(--warn); border: 1px solid #f3cf9a;
    border-radius: 8px; padding: 10px 14px; font-size: 13px; margin: 0 0 20px;
  }
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

  .wl-btn, .wl-remove-btn, .wl-confirm-btn, .wl-cancel-btn, .wl-del-confirm-btn, .wl-del-cancel-btn {
    font-size: 11px; border: none; border-radius: 6px; padding: 3px 8px;
    cursor: pointer; white-space: nowrap; margin-left: 6px;
  }
  .wl-btn, .wl-confirm-btn { color: var(--accent); background: var(--accent-bg); }
  .wl-remove-btn, .wl-del-confirm-btn { color: #b91c1c; background: #fde8e8; }
  .wl-cancel-btn, .wl-del-cancel-btn { color: var(--text-sub); background: #ececef; }
  .wl-del-confirm-label { font-size: 12px; color: var(--warn); }
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
  .upload-file-fields {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(240px,1fr)); gap: 8px 16px;
    margin-bottom: 10px;
  }
  .upload-file-fields label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-sub); }
  .upload-panel input[type=file] { font-size: 12px; margin-right: 8px; }
  .upload-panel .load-btn {
    font-size: 12px; padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer;
    color: var(--accent); background: var(--accent-bg); margin-left: 8px;
  }
  #upload-status, #connect-status { margin-top: 8px; font-size: 12px; color: var(--text-sub); white-space: pre-wrap; }
  .update-hint { margin: 0 0 16px; font-size: 12px; color: var(--text-sub); }
  .update-hint summary { cursor: pointer; color: var(--accent); font-weight: 500; }
  .update-hint p { margin: 8px 0 0; line-height: 1.7; }
  .update-hint pre {
    margin: 8px 0 0; padding: 12px 14px; background: var(--accent-bg); color: var(--accent);
    border-radius: 6px; font-size: 15px; line-height: 1.6; overflow-x: auto; white-space: pre-wrap; word-break: break-all;
  }
  .update-hint-form {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 8px 12px;
    margin: 10px 0 0;
  }
  .update-hint-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--text-sub); }
  .update-hint-form input {
    padding: 6px 9px; border: 1px solid var(--border); border-radius: 6px;
    font-size: 12px; background: var(--surface); color: var(--text);
  }
  .update-hint .load-btn { margin-top: 8px; }
  #update-cmd-status { margin-left: 8px; font-size: 12px; color: var(--text-sub); }
  thead th[data-sort-col] { cursor: pointer; user-select: none; white-space: nowrap; }
  thead th[data-sort-col]:hover { color: var(--accent); }
  .sort-arrow { display: inline-block; min-width: 10px; margin-left: 3px; font-size: 10px; color: var(--accent); }
  thead th[draggable="true"] { cursor: grab; }
  thead th.col-dragging { opacity: .4; }
  thead th.col-drop-target { outline: 2px dashed var(--accent); outline-offset: -2px; }
  .drag-handle { display: inline-block; margin-right: 4px; color: var(--text-sub); cursor: grab; }

  /* 論点1(DD-020): 物理カラム名クリック→テーブル定義サイドパネル */
  code.col-link {
    cursor: pointer; color: var(--accent); background: var(--accent-bg);
    border: none; font: inherit; padding: 2px 6px; border-radius: 4px;
  }
  code.col-link:hover { text-decoration: underline; }
  code.col-link.active { background: var(--accent); color: #fff; }
  .side-panel {
    position: fixed; top: 100px; width: 300px; max-height: calc(100vh - 140px); overflow-y: auto;
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.08); padding: 14px; font-size: 13px; display: none;
  }
  .side-panel.open { display: block; }
  .side-panel.inline-mode { position: static; width: auto; max-height: none; margin: 16px 0 0; }
  .side-panel h3 { margin: 0 0 2px; font-size: 14px; }
  .side-panel .panel-sub { color: var(--text-sub); font-size: 12px; margin: 0 0 10px; }
  .side-panel .close-btn { float: right; border: none; background: none; cursor: pointer; font-size: 15px; color: var(--text-sub); }
  .def-table { width: 100%; border-collapse: collapse; }
  .def-table th, .def-table td { text-align: left; padding: 5px 6px; font-size: 12px; border-bottom: 1px solid var(--border); }
  .def-table tr.highlight td { background: var(--highlight-bg); font-weight: 600; }
  /* DD-021論点3: データ型が数値コードの場合、Dr.Sum内部コードであることを示す注記 */
  .type-code-note { color: var(--text-sub); font-size: 11px; margin-left: 4px; cursor: help; border-bottom: 1px dotted var(--text-sub); }
  /* DD-033: 既定は「物理カラム名」「データ型」のみ表示し、「すべて表示」展開時だけ精度・スケール・NULL許可・ユニーク列を出す */
  .def-table .def-detail-col { display: none; }
  #table-def-panel.show-detail .def-table .def-detail-col { display: table-cell; }
  .def-table-toggle { font-size: 11px; border: 1px solid var(--border); background: var(--surface); border-radius: 4px; padding: 2px 8px; cursor: pointer; margin-bottom: 8px; }

  /* 論点3(DD-020): 使用ボード列 = ボード名｜表示名、以降の表示名は下に重ねる */
  /* DD-021論点1: セル全体をグリッド化し、ボード名列の幅を揃えて区切り線・表示名の開始位置を揃える */
  .board-cell { display: grid; grid-template-columns: max-content auto; column-gap: 6px; row-gap: 8px; align-items: baseline; }
  .board-group { display: contents; }
  .board-name { font-weight: 600; white-space: nowrap; }
  .board-name .sep { color: var(--text-sub); font-weight: 400; margin-left: 2px; }
  .alias-list { display: flex; flex-direction: column; }
  .alias-list .alias-line.calc { color: var(--text-sub); }
  /* DD-022: 物理名そのまま使用(エイリアス未設定)を本物のエイリアスと区別する */
  .alias-list .alias-line.unaliased { color: var(--text-sub); }
  .alias-list .unaliased-tag { font-size: 0.85em; color: var(--text-sub); }
  /* DD-021論点2: 「他N件」を全表示/省略表示切り替えボタンにする */
  .board-list-rest { display: contents; }
  .board-list-rest.board-list-collapsed { display: none; }
  .board-list-toggle {
    grid-column: 1 / -1; justify-self: start;
    font-size: 11px; color: var(--accent); background: var(--accent-bg); border: none;
    border-radius: 6px; padding: 2px 8px; cursor: pointer;
  }
  .board-list-toggle:hover { text-decoration: underline; }

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
  <div id="large-dataset-warning" class="large-warning" style="display:none;"></div>

  <details class="update-hint">
    <summary>🔧 データを更新するには</summary>
    <p>最新のDr.Sum/MotionBoardデータを取り込むには、以下を実行してください。
    下の項目にお使いの環境の値を入力すると、コマンドが自動的に書き換わります
    （未入力の項目はプレースホルダのままです）。</p>
    <div class="update-hint-form">
      <label>MotionBoardバックアップフォルダ <input type="text" id="cmd-backup-dir"></label>
      <label>Dr.Sumホスト名 <input type="text" id="cmd-host"></label>
      <label>Dr.SumのDB名 <input type="text" id="cmd-db"></label>
      <label>Dr.Sumユーザー名 <input type="text" id="cmd-user"></label>
      <label>JDBCドライバーのパス <input type="text" id="cmd-jdbc-jar"></label>
    </div>
    <pre><code id="update-cmd-output"></code></pre>
    <button class="load-btn" id="copy-update-cmd-btn" type="button">コピー</button>
    <button class="load-btn" id="open-terminal-btn" type="button">ターミナルを開く</button>
    <span id="update-cmd-status"></span>
    <p>詳細はREADME.mdを参照してください。</p>
  </details>

  <div class="mode-toggle">
    <button class="mode-btn" id="mode-upload-btn">実データをアップロードして見る</button>
    <button class="mode-btn" id="mode-connect-btn">Dr.Sumに接続</button>
  </div>
  <div class="upload-panel" id="upload-panel">
    <p class="upload-hint">
      お使いの環境で<code>python main.py</code>等を実行して作成した<code>lineage.db</code>を選んでください。
      ファイルはこのブラウザの中だけで処理され、どこにも送信されません。
      <code>naming_whitelist.json</code>は任意です(登録内容の閲覧のみ。追加・削除はこのモードでは行えません)。
    </p>
    <div class="upload-file-fields">
      <label>①lineage.dbファイル(必須) <input type="file" id="db-file-input" accept=".db"></label>
      <label>②ホワイトリストファイル(naming_whitelist.json・任意) <input type="file" id="whitelist-file-input" accept=".json"></label>
    </div>
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
      <tr id="main-thead-row"></tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">該当するカラムがありません</div>
  <div id="table-def-inline-anchor"></div>

  <h2 title="異なる物理カラムに同じ表示名が使われている候補です(意図的な使い回しか表記の混同かは目視確認が必要です)">多対1マッピング候補</h2>
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

  <h2 title="表記が似ている表示名の組を機械的に検出した候補です(実際に同じ意味かは目視確認が必要です)">表記ゆれ候補(類似度判定・要目視確認)</h2>
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
        <th style="width:12%" title="「エイリアス」=表示名がMotionBoard上で設定されている／「物理名そのまま」=表示名が設定されず物理カラム名がそのまま使われている／「計算式」=カスタム項目・事後計算項目の計算式の中でこの物理カラムが参照されている">種別</th>
        <th style="width:10%" title="ボード定義ファイル内でこの項目を識別する内部ID(デバッグ・問い合わせ用の補助情報です。画面上のパーツ番号ではありません)">アイテムID</th>
      </tr>
    </thead>
    <tbody id="drilldown-tbody"></tbody>
  </table>

  <h2 id="excluded-aliases-heading" title="ボード定義自身が別DB向けと申告している(接続中のDBと所属DBが異なることが確定している)ため、不一致候補一覧には含めず除外したエイリアスです">他DBのボードのため除外</h2>
  <div class="toolbar">
    <input type="text" id="excluded-aliases-search"
           placeholder="表示名(エイリアス)・物理カラム名・テーブル名・ボード名・所属DBで検索(エイリアス名だけ分かっていて所属DBが不明な場合はこちら)">
  </div>
  <div id="excluded-aliases-empty" class="empty" style="display:none">除外したエイリアスはありません</div>
  <table id="excluded-aliases-table" style="display:none">
    <thead>
      <tr>
        <th style="width:16%">所属DB</th>
        <th style="width:20%">テーブル/ビュー</th>
        <th style="width:20%">物理カラム名</th>
        <th style="width:20%">表示名</th>
        <th style="width:24%">ボード</th>
      </tr>
    </thead>
    <tbody id="excluded-aliases-tbody"></tbody>
  </table>
</div>

<div class="side-panel" id="table-def-panel">
  <button class="close-btn" id="table-def-close" type="button" title="閉じる">×</button>
  <h3 id="table-def-title">テーブル定義</h3>
  <p class="panel-sub" id="table-def-sub"></p>
  <button class="def-table-toggle" id="table-def-detail-toggle" type="button">すべて表示</button>
  <table class="def-table">
    <thead><tr>
      <th>物理カラム名</th><th>データ型</th>
      <th class="def-detail-col" title="精度・桁数(例: VARCHARの最大長、NUMERICの全体桁数)">精度</th>
      <th class="def-detail-col" title="小数点以下の桁数(NUMERIC等のみ)">スケール</th>
      <th class="def-detail-col">NULL</th>
      <th class="def-detail-col">ユニーク</th>
    </tr></thead>
    <tbody id="table-def-tbody"></tbody>
  </table>
</div>

<script>
let STATIC_EXPORT = false; // export_static.pyが埋め込みビルド時にtrueへ書き換える
let UPLOADED_MODE = false; // 実データアップロードモード中はtrue(DD-006)。編集ボタンを無効化する
let allRows = [];
let activeCardFilter = null; // null | 'naming' | 'unaliased' | 'orphan'
let sortColumn = null; // null | 'table_name' | 'column_name' | 'display_name' | 'usage_count' | 'boards'
let sortDirection = 'asc'; // 'asc' | 'desc'
let columnOrder = ['table_name', 'column_name', 'display_name', 'usage_count', 'boards']; // 表示上の列の並び順(左→右)
let selectedBoardName = ''; // ボード別ドリルダウンで選択中のボード名(DD-014: データ再読込後も選択状態を保持するため)
let allExcludedAliases = []; // 「他DBのボードのため除外」テーブルの全件(DD-029: 専用検索欄でのフィルタに使う)

// Python側のLARGE_DATASET_WARNING_THRESHOLD(web_viewer.py)と同じ値に保つこと(DD-014)
const LARGE_DATASET_WARNING_THRESHOLD = 3000;

function updateLargeDatasetWarning(rowCount) {
  const el = document.getElementById('large-dataset-warning');
  if (!el) return;
  if (rowCount > LARGE_DATASET_WARNING_THRESHOLD) {
    el.textContent = `※ カラム数が${rowCount}件と多いため、ブラウザでの表示が重くなる可能性があります` +
      `(現時点ではページネーション未対応です)`;
    el.style.display = 'block';
  } else {
    el.style.display = 'none';
  }
}

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
    SELECT c.id, c.table_name, c.column_name, c.data_type,
           GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS display_names,
           GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='calc' THEN a.display_name END) AS calc_names,
           COUNT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS alias_count,
           COUNT(a.id) AS usage_count,
           GROUP_CONCAT(DISTINCT a.board_name) AS boards,
           c.table_type,
           c.column_size, c.decimal_digits, c.is_nullable, c.is_unique
    FROM columns c
    LEFT JOIN aliases a ON a.column_id = c.id
    GROUP BY c.id
    ORDER BY alias_count DESC, c.table_name, c.column_name
  `);
  if (!res.length) return [];
  return res[0].values.map(row => {
    const [id, table_name, column_name, data_type, displayNamesRaw, calcNamesRaw, aliasCount, usageCount, boardsRaw, tableType,
           columnSize, decimalDigits, isNullable, isUnique] = row;
    const display_names = displayNamesRaw ? displayNamesRaw.split(",") : [];
    const isWhitelisted = whitelistSet.has(normalizeKey(table_name, column_name));
    return {
      id, table_name, column_name, data_type, display_names,
      calc_names: calcNamesRaw ? calcNamesRaw.split(",") : [],
      alias_count: aliasCount || 0,
      usage_count: usageCount || 0,
      boards: boardsRaw ? boardsRaw.split(",") : [],
      is_unaliased: display_names.some(n => normalizeText(column_name) === normalizeText(n)),
      is_orphan: (usageCount || 0) === 0,
      is_naming_variant: (aliasCount || 0) > 1 && !isWhitelisted,
      // DD-025: match_aliases.pyが接続中DBの物理カラムと一致しないエイリアスを
      // table_type='(不明)'で仮登録したもの(別DBのボード混入やカラム名変更等の兆候)
      is_unmatched: tableType === "(不明)",
      // DD-033: テーブル定義パネルの「すべて表示」展開時に使う(未取得ならnull=フロント側で「-」表示)
      column_size: columnSize, decimal_digits: decimalDigits, is_nullable: isNullable, is_unique: isUnique,
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

// DD-026: excluded_aliasesテーブルはDD-026より前に生成されたlineage.dbには存在しないため、
// 無い場合は空扱いにする(fetch_excluded_aliases側のsqlite3.OperationalError握りつぶしと同じ意図)
function jsFetchExcludedAliases(db) {
  let res;
  try {
    res = db.exec(`
      SELECT source_db, table_name, column_name, display_name, board_name
      FROM excluded_aliases
      ORDER BY source_db, table_name, column_name
    `);
  } catch (e) {
    return [];
  }
  if (!res.length) return [];
  return res[0].values.map(([source_db, table_name, column_name, display_name, board_name]) => ({
    source_db, table_name, column_name, display_name, board_name,
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
    const excludedAliases = jsFetchExcludedAliases(db);
    lastPatterns = patterns;
    buildBoardAliasMap(boardDetails);
    sortColumn = null;
    renderTableHeader();
    updateLargeDatasetWarning(allRows.length);
    renderCards(allRows, patterns);
    renderTable(allRows);
    renderManyToOne(patterns.many_to_one || []);
    renderSimilarPairs(patterns.similar_pairs || []);
    renderWhitelist(whitelistEntries);
    initBoardDrilldown(boardDetails);
    renderExcludedAliases(excludedAliases);
    db.close();
    statusEl.textContent = `読み込み完了(${allRows.length}カラム)`;
  } catch (err) {
    statusEl.textContent = "エラー: " + err.message;
  }
}

const CARD_DEFS = [
  { key: null, label: "総カラム数", value: (rows, patterns) => rows.length },
  { key: "naming", label: "表記ゆれ候補", value: (rows) => rows.filter(r => r.is_naming_variant).length,
    tooltip: "同じ物理カラムに、表記の異なる表示名が複数使われている可能性がある項目の件数です" },
  { key: null, label: "使用箇所(延べ)", value: (rows) => rows.reduce((sum, r) => sum + (r.usage_count || 0), 0) },
  { key: "calc", label: "カスタム項目/計算式で使用", value: (rows) => rows.filter(r => r.calc_names && r.calc_names.length > 0).length,
    tooltip: "MotionBoardのカスタム項目・計算式の中でこの物理カラムが参照されている件数です" },
  { key: "unaliased", label: "物理名そのまま", value: (rows) => rows.filter(r => r.is_unaliased).length,
    tooltip: "表示名が設定されず、物理カラム名がそのままMotionBoardの画面に表示されている項目の件数です" },
  { key: "orphan", label: "未使用カラム", value: (rows) => rows.filter(r => r.is_orphan).length,
    tooltip: "Dr.Sum上には存在するが、MotionBoardのどのボードからも参照されていない物理カラムの件数です" },
  { key: "many_to_one", label: "多対1候補", value: (rows, patterns) => (patterns.many_to_one || []).length,
    tooltip: "異なる物理カラムに同じ表示名が使われている候補の件数です(意図的な使い回しか表記の混同かは目視確認が必要です)" },
  { key: "similar", label: "類似度候補", value: (rows, patterns) => (patterns.similar_pairs || []).length,
    tooltip: "表記が似ている表示名の組を機械的に検出した候補の件数です(実際に同じ意味かは目視確認が必要です)" },
];

// サーバーモード・静的配布モード(export_static.py)で共通の描画処理。検索語・カード絞り込み・
// 列ソート・列並び替え・ドリルダウン選択中のボードは呼び出し元でリセットしない限り保持される(DD-014)
function renderAll(rows, patterns, boardDetails, whitelistEntries, excludedAliases) {
  allRows = rows;
  lastPatterns = patterns;
  buildBoardAliasMap(boardDetails);
  updateLargeDatasetWarning(allRows.length);
  renderCards(allRows, patterns);
  applyFilters();
  renderManyToOne(patterns.many_to_one || []);
  renderSimilarPairs(patterns.similar_pairs || []);
  renderWhitelist(whitelistEntries);
  initBoardDrilldown(boardDetails);
  allExcludedAliases = excludedAliases || [];
  applyExcludedAliasesFilter();
}

function matchesExcludedSearch(e, q) {
  if (!q) return true;
  return (e.source_db || '').toLowerCase().includes(q) ||
    (e.table_name || '').toLowerCase().includes(q) ||
    (e.column_name || '').toLowerCase().includes(q) ||
    (e.display_name || '').toLowerCase().includes(q) ||
    (e.board_name || '').toLowerCase().includes(q);
}

function applyExcludedAliasesFilter() {
  const q = document.getElementById('excluded-aliases-search').value.trim().toLowerCase();
  renderExcludedAliases(allExcludedAliases.filter(e => matchesExcludedSearch(e, q)));
}

async function load() {
  const [colRes, patRes, boardRes, whitelistRes, excludedRes] = await Promise.all([
    fetch('/api/columns'), fetch('/api/patterns'), fetch('/api/board_details'), fetch('/api/whitelist'),
    fetch('/api/excluded_aliases'),
  ]);
  let colData = await colRes.json();
  let patterns = await patRes.json();
  let boardDetails = await boardRes.json();
  let whitelistEntries = await whitelistRes.json();
  let excludedAliases = await excludedRes.json();
  // lineage.dbがまだ存在しない場合(DD-007の--connect起動直後)、各APIは
  // {"error": ...}を返す。配列/オブジェクトでない値はレンダリング関数を壊すため空にする
  if (!Array.isArray(colData)) colData = [];
  if (!patterns || typeof patterns !== 'object' || Array.isArray(patterns)) patterns = {};
  if (!Array.isArray(boardDetails)) boardDetails = [];
  if (!Array.isArray(whitelistEntries)) whitelistEntries = [];
  if (!Array.isArray(excludedAliases)) excludedAliases = [];
  renderAll(colData, patterns, boardDetails, whitelistEntries, excludedAliases);
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
  await load();
}

function renderCards(rows, patterns) {
  buildPatternKeySets(patterns);
  document.getElementById('cards').innerHTML = CARD_DEFS.map(def => {
    const clickable = !!def.key;
    const selected = clickable && activeCardFilter === def.key;
    const classes = ["card", clickable ? "clickable" : "", selected ? "selected" : ""].filter(Boolean).join(" ");
    const hint = clickable ? '<span class="hint">クリックで絞込</span>' : '';
    const a11y = clickable
      ? `role="button" tabindex="0" aria-pressed="${selected}" aria-label="${escapeHtml(def.label)}でカラム一覧を絞り込む"`
      : '';
    const titleAttr = def.tooltip ? ` title="${escapeHtml(def.tooltip)}"` : '';
    return `<div class="${classes}" data-key="${def.key || ''}" data-clickable="${clickable}" ${a11y}${titleAttr}>
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

// 「多対1候補」「類似度候補」カードのクリック絞り込み用に、該当する物理カラムの
// キー集合を都度組み立てておく(カードクリックのたびに毎回全件走査しないため、DD-016)
let manyToOneKeySet = new Set();
let similarKeySet = new Set();

function buildPatternKeySets(patterns) {
  manyToOneKeySet = new Set();
  (patterns.many_to_one || []).forEach(group => {
    (group.columns || []).forEach(c => manyToOneKeySet.add(normalizeKey(c.table_name, c.column_name)));
  });
  similarKeySet = new Set();
  (patterns.similar_pairs || []).forEach(pair => {
    similarKeySet.add(normalizeKey(pair.column_a.table_name, pair.column_a.column_name));
    similarKeySet.add(normalizeKey(pair.column_b.table_name, pair.column_b.column_name));
  });
}

function matchesCardFilter(r) {
  if (!activeCardFilter) return true;
  if (activeCardFilter === "naming") return r.is_naming_variant;
  if (activeCardFilter === "unaliased") return r.is_unaliased;
  if (activeCardFilter === "orphan") return r.is_orphan;
  if (activeCardFilter === "calc") return !!(r.calc_names && r.calc_names.length > 0);
  if (activeCardFilter === "many_to_one") return manyToOneKeySet.has(normalizeKey(r.table_name, r.column_name));
  if (activeCardFilter === "similar") return similarKeySet.has(normalizeKey(r.table_name, r.column_name));
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

function compareRows(a, b, column, direction) {
  const dir = direction === 'desc' ? -1 : 1;
  switch (column) {
    case 'table_name':
      return dir * a.table_name.localeCompare(b.table_name, 'ja');
    case 'column_name':
      return dir * a.column_name.localeCompare(b.column_name, 'ja');
    case 'display_name': {
      const an = (a.display_names && a.display_names[0]) || '';
      const bn = (b.display_names && b.display_names[0]) || '';
      if (an === '' && bn === '') return 0;
      if (an === '') return 1; // エイリアス未設定行は方向に関わらず末尾
      if (bn === '') return -1;
      return dir * an.localeCompare(bn, 'ja');
    }
    case 'usage_count':
      return dir * ((a.usage_count || 0) - (b.usage_count || 0));
    case 'boards': {
      const al = a.boards ? a.boards.length : 0;
      const bl = b.boards ? b.boards.length : 0;
      if (al !== bl) return dir * (al - bl);
      const an = (a.boards && a.boards[0]) || '';
      const bn = (b.boards && b.boards[0]) || '';
      return dir * an.localeCompare(bn, 'ja');
    }
    default:
      return 0;
  }
}

function sortRows(rows) {
  if (!sortColumn) return rows;
  return rows.slice().sort((a, b) => compareRows(a, b, sortColumn, sortDirection));
}

// 指定した表示名/計算式名(usageType: 'alias'|'calc')を実際に使っているボード名の一覧を
// board_detailsから引く(DD-018。表示名バッジのホバーで「どのボードのものか」を出すため)
function boardNamesForDisplay(r, displayName, usageType) {
  const details = boardAliasesByColumn[normalizeKey(r.table_name, r.column_name)] || [];
  const boards = new Set();
  details.forEach(d => {
    if (d.display_name === displayName && d.usage_type === usageType) boards.add(d.board_name);
  });
  return Array.from(boards);
}

function renderDisplayNameCell(r) {
  const isWarn = !!r.is_naming_variant;
  const isOrphan = !!r.is_orphan;
  const calcNames = r.calc_names || [];
  const aliasBadges = r.display_names.map(n => {
    const boards = boardNamesForDisplay(r, n, 'alias');
    const lines = [];
    if (boards.length) lines.push(`使用ボード: ${boards.join(', ')}`);
    if (isWarn) lines.push('表記ゆれ候補として検出された表示名です');
    const titleAttr = lines.length ? ` title="${escapeHtml(lines.join('\\n'))}"` : '';
    return `<span class="badge ${isWarn ? 'warn' : ''}"${titleAttr}>${escapeHtml(n)}</span>`;
  }).join('');
  const calcBadges = calcNames.map(n => {
    const boards = boardNamesForDisplay(r, n, 'calc');
    const lines = [];
    if (boards.length) lines.push(`使用ボード: ${boards.join(', ')}`);
    lines.push('カスタム項目・計算式の中でこの物理カラムが参照されています');
    return `<span class="badge calc" title="${escapeHtml(lines.join('\\n'))}">${escapeHtml(n)}</span>`;
  }).join('');
  const unaliasedBadge = r.is_unaliased ? '<span class="badge unaliased" title="表示名が設定されず、物理カラム名がそのまま使われています">物理名そのまま</span>' : '';
  return `
    ${aliasBadges || (calcBadges ? '' : '<span class="status-ok">-</span>')}
    ${unaliasedBadge}
    ${isWarn ? `<div class="status-warn">表記ゆれ ${r.alias_count}種 ${whitelistAddButton(r.table_name, r.column_name)}</div>` : ''}
    ${calcBadges ? `<div class="calc-line">カスタム項目/計算式で使用: ${calcBadges}</div>` : ''}
    ${isOrphan ? '<div class="calc-line">未使用(MotionBoardで参照なし)</div>' : ''}
  `;
}

// 物理カラム(table_name+column_name)ごとに、どのボードがどの表示名/計算式名で
// 使っているかをboard_detailsから組み立てる(DD-016。使用ボード欄でエイリアス対応を
// 一目で分かるようにするため。/api/board_details はドリルダウンで既に取得済みのデータを再利用する)
let boardAliasesByColumn = {};

function buildBoardAliasMap(boardDetails) {
  boardAliasesByColumn = {};
  (boardDetails || []).forEach(d => {
    const key = normalizeKey(d.table_name, d.column_name);
    (boardAliasesByColumn[key] = boardAliasesByColumn[key] || []).push(d);
  });
}

// ボード名を1行目(｜区切り)に、同ボードの表示名(2件目以降)・計算式使用分をその下に重ねて表示する(DD-020)
// ボード名＋区切り線を1個のグリッドアイテムにまとめ、呼び出し元の.board-cellグリッドで
// 複数ボード間のボード名列の幅を揃える(DD-021論点1)
// physicalName(その物理カラム名)が渡された場合、物理名そのまま使用(エイリアス未設定)の
// 表示名を本物のエイリアスと見分けがつくよう印をつける(DD-022)
function renderBoardGroup(name, entry, physicalName) {
  const lines = [...Array.from(entry.alias), ...Array.from(entry.calc).map(c => `計算式: ${c}`)];
  const aliasHtml = lines.map(l => {
    const isCalc = l.startsWith('計算式: ');
    const isUnaliased = !isCalc && physicalName !== undefined && normalizeText(l) === normalizeText(physicalName);
    const cls = 'alias-line' + (isCalc ? ' calc' : '') + (isUnaliased ? ' unaliased' : '');
    const tag = isUnaliased ? ' <span class="unaliased-tag">(物理名のまま)</span>' : '';
    return `<div class="${cls}">${escapeHtml(l)}${tag}</div>`;
  }).join('');
  return `<div class="board-group">` +
    `<span class="board-name">${escapeHtml(name)}<span class="sep">｜</span></span>` +
    `<div class="alias-list">${aliasHtml}</div></div>`;
}

function formatBoardText(name, entry) {
  const parts = [];
  if (entry.alias.size) parts.push(Array.from(entry.alias).join('/'));
  if (entry.calc.size) parts.push('計算式: ' + Array.from(entry.calc).join('/'));
  return parts.length ? `${name}(${parts.join('・')})` : name;
}

function renderBoardsCell(r) {
  const details = boardAliasesByColumn[normalizeKey(r.table_name, r.column_name)] || [];
  if (details.length === 0) {
    if (!r.boards.length) return '-';
    const allGroups = r.boards.map(b => renderBoardGroup(b, { alias: new Set(), calc: new Set() }, r.column_name)).join('');
    return `<div class="board-cell">${allGroups}</div>`;
  }
  const byBoard = new Map();
  details.forEach(d => {
    if (!byBoard.has(d.board_name)) byBoard.set(d.board_name, { alias: new Set(), calc: new Set() });
    const entry = byBoard.get(d.board_name);
    (d.usage_type === 'calc' ? entry.calc : entry.alias).add(d.display_name);
  });
  const boardNames = Array.from(byBoard.keys());
  // 件数が多い場合は先頭3件のみ表示し、残りは「他N件」ボタンで全表示/省略表示を切り替える(DD-018→DD-021論点2)
  const groups = boardNames.slice(0, 3).map(name => renderBoardGroup(name, byBoard.get(name), r.column_name)).join('');
  const restNames = boardNames.slice(3);
  const fullTitle = boardNames.map(name => formatBoardText(name, byBoard.get(name))).join('\\n');
  let restHtml = '';
  if (restNames.length > 0) {
    const restGroups = restNames.map(name => renderBoardGroup(name, byBoard.get(name), r.column_name)).join('');
    restHtml = `<div class="board-list-rest board-list-collapsed">${restGroups}</div>` +
      `<button type="button" class="board-list-toggle" data-count="${restNames.length}">他${restNames.length}件 すべて表示</button>`;
  }
  return `<div class="board-cell" title="${escapeHtml(fullTitle)}">${groups}${restHtml}</div>`;
}

const MAIN_COLUMN_DEFS = {
  table_name: {
    label: 'テーブル/ビュー', width: '16%',
    cell: r => escapeHtml(r.table_name) + (r.is_unmatched
      ? ` <span class="badge warn" title="接続中のDBの物理カラムと一致しませんでした。関係ない別DBのボード定義が紛れ込んでいるか、Dr.Sum側でカラム名が変更/削除された可能性があります">DB不一致の可能性</span>`
      : ''),
  },
  column_name: {
    label: '物理カラム名', width: '16%',
    cell: r => `<code class="col-link" data-table="${escapeHtml(r.table_name)}" data-column="${escapeHtml(r.column_name)}" title="クリックするとテーブル定義を表示します">${escapeHtml(r.column_name)}</code>`,
  },
  display_name: { label: '表示名(エイリアス)', width: '30%', cell: renderDisplayNameCell },
  usage_count: { label: '使用件数', width: '8%', cell: r => `${r.usage_count}件` },
  boards: { label: '使用ボード(実際のエイリアス名)', width: '30%', className: 'boards', cell: renderBoardsCell },
};

function renderTableHeader() {
  const headRow = document.getElementById('main-thead-row');
  headRow.innerHTML = columnOrder.map((key) => {
    const def = MAIN_COLUMN_DEFS[key];
    const arrow = (sortColumn === key) ? (sortDirection === 'asc' ? '▲' : '▼') : '';
    return `<th style="width:${def.width}" data-sort-col="${key}" draggable="true">` +
      `<span class="drag-handle" title="ドラッグで列の並び替え">⠿</span>` +
      `<span class="th-label">${def.label}</span><span class="sort-arrow">${arrow}</span></th>`;
  }).join('');
}

// 論点2(DD-020): 列見出しのドラッグ並び替え(←/→ボタンは廃止)
let dragColumnKey = null;

function reorderColumn(fromKey, toKey) {
  if (!fromKey || fromKey === toKey) return;
  const from = columnOrder.indexOf(fromKey);
  const to = columnOrder.indexOf(toKey);
  if (from === -1 || to === -1) return;
  columnOrder.splice(from, 1);
  columnOrder.splice(to, 0, fromKey);
  renderTableHeader();
  applyFilters();
}

const mainThead = document.querySelector('#main-thead-row').closest('thead');

mainThead.addEventListener('dragstart', (e) => {
  const th = e.target.closest('th[data-sort-col]');
  if (!th) return;
  dragColumnKey = th.dataset.sortCol;
  th.classList.add('col-dragging');
  e.dataTransfer.effectAllowed = 'move';
});

mainThead.addEventListener('dragover', (e) => {
  const th = e.target.closest('th[data-sort-col]');
  if (!th || th.dataset.sortCol === dragColumnKey) return;
  e.preventDefault();
  th.classList.add('col-drop-target');
});

mainThead.addEventListener('dragleave', (e) => {
  const th = e.target.closest('th[data-sort-col]');
  if (th) th.classList.remove('col-drop-target');
});

mainThead.addEventListener('dragend', () => {
  mainThead.querySelectorAll('th').forEach(th => th.classList.remove('col-dragging', 'col-drop-target'));
  dragColumnKey = null;
});

mainThead.addEventListener('drop', (e) => {
  const th = e.target.closest('th[data-sort-col]');
  if (!th) return;
  e.preventDefault();
  th.classList.remove('col-drop-target');
  reorderColumn(dragColumnKey, th.dataset.sortCol);
  dragColumnKey = null;
});

mainThead.addEventListener('click', (e) => {
  const th = e.target.closest('th[data-sort-col]');
  if (!th) return;
  const col = th.dataset.sortCol;
  if (sortColumn !== col) {
    sortColumn = col;
    sortDirection = 'asc';
  } else if (sortDirection === 'asc') {
    sortDirection = 'desc';
  } else {
    sortColumn = null;
    sortDirection = 'asc';
  }
  renderTableHeader();
  applyFilters();
});

// DD-021論点3→DD-024: Dr.Sum実機ではdata_typeが内部の数値コードのまま返ってくることがある。
// 実機から取得したデータ(25カラム)で0=VARCHAR/3=DATE/7=NUMERICのみ確認できた(doc/decisions.md D-004)ため、
// この3種類だけ型名に変換する。対応表に無い値は誤った型名を出さないよう、引き続き数値+内部コード注記のままにする
const DR_SUM_TYPE_CODE_MAP = { '0': 'VARCHAR', '3': 'DATE', '7': 'NUMERIC' };

function formatDataType(dataType) {
  if (dataType === null || dataType === undefined || dataType === '') return '-';
  const text = String(dataType);
  const trimmed = text.trim();
  if (!/^-?\\d+$/.test(trimmed)) return escapeHtml(text);
  if (Object.prototype.hasOwnProperty.call(DR_SUM_TYPE_CODE_MAP, trimmed)) {
    return escapeHtml(DR_SUM_TYPE_CODE_MAP[trimmed]);
  }
  return `${escapeHtml(text)}<span class="type-code-note" title="Dr.Sum内部の数値コードです。型名への変換は未対応のため、実際のデータ型はDr.Sum管理画面でご確認ください">(内部コード)</span>`;
}

// DD-033: 精度・スケール・NULL許可・ユニークは未取得(null/undefined)の場合「-」と表示する
// (実機Dr.Sumで値が取れない場合も同じ表示になる。doc/decisions.md D-004参照)
function formatDefDetail(value) {
  return (value === null || value === undefined || value === '') ? '-' : escapeHtml(String(value));
}

function formatNullable(isNullable) {
  if (isNullable === 'YES') return 'NULL可';
  if (isNullable === 'NO') return 'NOT NULL';
  return '-';
}

function formatUnique(isUnique) {
  if (isUnique === 'YES') return '○';
  if (isUnique === 'NO') return '-';
  return '-';
}

// 論点1(DD-020): 物理カラム名クリック→テーブル定義サイドパネル(横の空きスペース、無ければ一覧下にインライン表示)
function openTableDefPanel(table, column) {
  const defs = allRows
    .filter(r => r.table_name === table)
    .map(r => ({
      column_name: r.column_name, data_type: r.data_type,
      column_size: r.column_size, decimal_digits: r.decimal_digits,
      is_nullable: r.is_nullable, is_unique: r.is_unique,
    }))
    .sort((a, b) => a.column_name.localeCompare(b.column_name));
  document.getElementById('table-def-title').textContent = `テーブル定義: ${table}`;
  document.getElementById('table-def-sub').textContent = `${defs.length}カラム中、クリックしたカラムを強調表示`;
  document.getElementById('table-def-tbody').innerHTML = defs.map(c => {
    const hl = c.column_name === column ? ' class="highlight"' : '';
    return `<tr${hl}><td><code>${escapeHtml(c.column_name)}</code></td><td>${formatDataType(c.data_type)}</td>` +
      `<td class="def-detail-col">${formatDefDetail(c.column_size)}</td>` +
      `<td class="def-detail-col">${formatDefDetail(c.decimal_digits)}</td>` +
      `<td class="def-detail-col">${formatNullable(c.is_nullable)}</td>` +
      `<td class="def-detail-col">${formatUnique(c.is_unique)}</td></tr>`;
  }).join('');
  document.querySelectorAll('.col-link').forEach(el => el.classList.remove('active'));
  document.querySelectorAll(`.col-link[data-table="${CSS.escape(table)}"][data-column="${CSS.escape(column)}"]`)
    .forEach(el => el.classList.add('active'));
  document.getElementById('table-def-panel').classList.add('open');
  positionTableDefPanel();
}

function closeTableDefPanel() {
  document.getElementById('table-def-panel').classList.remove('open');
  document.querySelectorAll('.col-link').forEach(el => el.classList.remove('active'));
}

// DD-033: 既定は「物理カラム名」「データ型」のみ表示し、ボタンで精度・スケール・NULL許可・ユニーク列を展開する
document.getElementById('table-def-detail-toggle').addEventListener('click', (e) => {
  const panel = document.getElementById('table-def-panel');
  const expanded = panel.classList.toggle('show-detail');
  e.target.textContent = expanded ? '折りたたむ' : 'すべて表示';
});

// 画面右に十分な空きスペースがあればそこに固定表示し、無ければ一覧の下にインライン表示する
function positionTableDefPanel() {
  const panel = document.getElementById('table-def-panel');
  if (!panel.classList.contains('open')) return;
  const wrap = document.querySelector('.wrap');
  const wrapRect = wrap.getBoundingClientRect();
  const spaceRight = window.innerWidth - wrapRect.right;
  const PANEL_WIDTH_WITH_MARGIN = 340;
  if (spaceRight >= PANEL_WIDTH_WITH_MARGIN) {
    panel.classList.remove('inline-mode');
    panel.style.left = (wrapRect.right + 24) + 'px';
    if (panel.parentElement !== document.body) document.body.appendChild(panel);
  } else {
    panel.classList.add('inline-mode');
    panel.style.left = '';
    const anchor = document.getElementById('table-def-inline-anchor');
    if (panel.parentElement !== anchor) anchor.appendChild(panel);
  }
}

window.addEventListener('resize', positionTableDefPanel);
document.getElementById('table-def-close').addEventListener('click', closeTableDefPanel);
document.getElementById('tbody').addEventListener('click', (e) => {
  const link = e.target.closest('.col-link');
  if (link) {
    openTableDefPanel(link.dataset.table, link.dataset.column);
    return;
  }
  // DD-021論点2: 使用ボード欄の「他N件」ボタンで全表示/省略表示を切り替える
  const toggleBtn = e.target.closest('.board-list-toggle');
  if (toggleBtn) {
    const cell = toggleBtn.closest('.board-cell');
    const rest = cell && cell.querySelector('.board-list-rest');
    if (!rest) return;
    const collapsed = rest.classList.toggle('board-list-collapsed');
    toggleBtn.textContent = collapsed ? `他${toggleBtn.dataset.count}件 すべて表示` : '折りたたむ';
  }
});

function applyFilters() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  document.getElementById('clear-filter').disabled = !activeCardFilter;
  const filtered = allRows.filter(r => matchesCardFilter(r) && matchesSearch(r, q));
  renderTable(sortRows(filtered));
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
    const rowTitle = isWarn
      ? ' title="表記ゆれ候補: 同じ物理カラムに複数の表示名が使われています"'
      : (isOrphan ? ' title="未使用: どのMotionBoardボードからも参照されていません"' : '');
    const cells = columnOrder.map(key => {
      const def = MAIN_COLUMN_DEFS[key];
      const cls = def.className ? ` class="${def.className}"` : '';
      return `<td${cls}>${def.cell(r)}</td>`;
    }).join('');
    return `<tr class="${isWarn ? 'warn' : ''} ${isOrphan ? 'orphan' : ''}"${rowTitle}>${cells}</tr>`;
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
      <td>${(STATIC_EXPORT || UPLOADED_MODE) ? '' : wlRemoveTriggerHtml(e.table_name, e.column_name)}</td>
    </tr>
  `).join('');
}

// DD-026: ボード定義自身が別DB向けと申告しているため除外したエイリアスを画面下部に表示する
// DD-029: 専用検索欄でのフィルタ後に呼ばれるため、見出しの件数は全件数(allExcludedAliases)で固定する
function renderExcludedAliases(items) {
  const heading = document.getElementById('excluded-aliases-heading');
  const table = document.getElementById('excluded-aliases-table');
  const tbody = document.getElementById('excluded-aliases-tbody');
  const empty = document.getElementById('excluded-aliases-empty');
  heading.textContent = `他DBのボードのため除外（${allExcludedAliases.length}件）`;
  if (!items || items.length === 0) {
    tbody.innerHTML = '';
    table.style.display = 'none';
    empty.textContent = allExcludedAliases.length === 0
      ? '除外したエイリアスはありません'
      : '検索条件に一致するエイリアスはありません';
    empty.style.display = 'block';
    return;
  }
  table.style.display = '';
  empty.style.display = 'none';
  tbody.innerHTML = items.map(e => `
    <tr>
      <td>${escapeHtml(e.source_db)}</td>
      <td>${escapeHtml(e.table_name)}</td>
      <td><code>${escapeHtml(e.column_name)}</code></td>
      <td>${escapeHtml(e.display_name)}</td>
      <td>${escapeHtml(e.board_name)}</td>
    </tr>
  `).join('');
}

function wlRemoveTriggerHtml(tableName, columnName) {
  return `<span class="wl-del" data-table="${escapeHtml(tableName)}" data-column="${escapeHtml(columnName)}">` +
    `<button class="wl-remove-btn">削除</button></span>`;
}

function wlRemoveConfirmHtml(columnName) {
  // 誤クリックでの即削除を防ぐため、確認ステップをその場に展開する(DD-014。
  // window.confirm()等のネイティブダイアログは、wlFormHtml同様に自動操作ブラウザでの
  // 検証を妨げる可能性があるため使わない)
  return `<span class="wl-del-confirm-label">${escapeHtml(columnName)}を削除しますか？</span>` +
    `<button class="wl-del-confirm-btn">削除する</button>` +
    `<button class="wl-del-cancel-btn">キャンセル</button>`;
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
  // データ再読込後も選択中のボードを保持する(DD-014)。再読込後に存在しなくなった
  // ボードが選択されていた場合は選択なし状態に戻す
  if (!selectedBoardName || !boardDetailsByBoard[selectedBoardName]) {
    selectedBoardName = '';
  }
  select.value = selectedBoardName;
  renderDrilldown(selectedBoardName);
}

// changeリスナーはページ初期化時に一度だけ登録する(initBoardDrilldownは再読込のたびに
// <select>のoption一覧を作り直すが、select要素自体は使い回すため、ここで登録すると
// 呼び出すたびにリスナーが重複登録されてしまう)
document.getElementById('board-select').addEventListener('change', () => {
  selectedBoardName = document.getElementById('board-select').value;
  renderDrilldown(selectedBoardName);
});

// ドリルダウンの「種別」バッジを組み立てる。usage_type='alias'でも、表示名が物理カラム名と
// 同じ(MotionBoard上でエイリアス未設定)なら「使用ボード」欄の判定(DD-022)と揃え、
// 本当にエイリアスが命名された行と区別できるよう「物理名そのまま」で表示する(DD-032)
function drilldownUsageBadge(d) {
  if (d.usage_type === 'calc') {
    return '<span class="badge calc">計算式</span>';
  }
  if (normalizeText(d.display_name) === normalizeText(d.column_name)) {
    return '<span class="badge unaliased" title="表示名が設定されず、物理カラム名がそのまま使われています">物理名そのまま</span>';
  }
  return '<span class="badge">エイリアス</span>';
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
      <td>${drilldownUsageBadge(d)}</td>
      <td>${escapeHtml(d.item_id || '')}</td>
    </tr>
  `).join('');
}

document.getElementById('search').addEventListener('input', applyFilters);
document.getElementById('excluded-aliases-search').addEventListener('input', applyExcludedAliasesFilter);

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
    const wrap = delBtn.closest('.wl-del');
    wrap.innerHTML = wlRemoveConfirmHtml(wrap.dataset.column);
    return;
  }
  const delCancelBtn = e.target.closest('.wl-del-cancel-btn');
  if (delCancelBtn) {
    const wrap = delCancelBtn.closest('.wl-del');
    wrap.innerHTML = `<button class="wl-remove-btn">削除</button>`;
    return;
  }
  const delConfirmBtn = e.target.closest('.wl-del-confirm-btn');
  if (delConfirmBtn) {
    const wrap = delConfirmBtn.closest('.wl-del');
    await fetch('/api/whitelist/delete', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({table_name: wrap.dataset.table, column_name: wrap.dataset.column}),
    });
    await load();
  }
});

document.body.addEventListener('keydown', async (e) => {
  if (e.key !== 'Enter' || !e.target.classList.contains('wl-reason-input')) return;
  e.preventDefault();
  await submitWhitelistAdd(e.target.closest('.wl-add'));
});

// 「このデータを見る」ボタンは既定表示そのものを指すだけで操作として不要なため廃止し(DD-016)、
// 残り2ボタンは開閉トグルとして独立動作させる。activeBtnIdにnullを渡すと両パネルとも閉じる
function setActiveMode(activeBtnId) {
  ['mode-upload-btn', 'mode-connect-btn'].forEach(id => {
    document.getElementById(id).classList.toggle('active', id === activeBtnId);
  });
  document.getElementById('upload-panel').style.display = activeBtnId === 'mode-upload-btn' ? 'block' : 'none';
  document.getElementById('connect-panel').style.display = activeBtnId === 'mode-connect-btn' ? 'block' : 'none';
}

document.getElementById('mode-upload-btn').addEventListener('click', () => {
  const isActive = document.getElementById('mode-upload-btn').classList.contains('active');
  setActiveMode(isActive ? null : 'mode-upload-btn');
});

document.getElementById('mode-connect-btn').addEventListener('click', () => {
  const isActive = document.getElementById('mode-connect-btn').classList.contains('active');
  setActiveMode(isActive ? null : 'mode-connect-btn');
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
    setActiveMode(null);
    sortColumn = null;
    renderTableHeader();
    await load();
  } catch (err) {
    statusEl.textContent = 'エラー: ' + err.message;
  }
});

if (STATIC_EXPORT) {
  document.getElementById('mode-connect-btn').style.display = 'none';
  document.getElementById('open-terminal-btn').style.display = 'none'; // 静的HTMLにはサーバーが無く/api/open_terminalを呼べない(DD-029)
}

const UPDATE_CMD_FIELDS = [
  { id: 'cmd-backup-dir', flag: '--backup-dir', placeholder: 'MotionBoardバックアップフォルダ' },
  { id: 'cmd-host', flag: '--host', placeholder: 'Dr.Sumホスト名' },
  { id: 'cmd-db', flag: '--db', placeholder: 'Dr.SumのDB名' },
  { id: 'cmd-user', flag: '--user', placeholder: 'Dr.Sumユーザー名' },
  { id: 'cmd-jdbc-jar', flag: '--jdbc-jar', placeholder: 'JDBCドライバーのパス' },
];

function updateCommandPreview() {
  const parts = ['python main.py'];
  for (const f of UPDATE_CMD_FIELDS) {
    const val = document.getElementById(f.id).value.trim();
    // 値にスペースを含むパス(例: MotionBoardの既定フォルダ名"[My Boards]")でもそのまま
    // ターミナルにコピペして実行できるよう、入力値は常にダブルクオートで囲む(DD-016)
    parts.push(`${f.flag} ${val ? '"' + val + '"' : '<' + f.placeholder + '>'}`);
  }
  document.getElementById('update-cmd-output').textContent = parts.join(' ');
}

UPDATE_CMD_FIELDS.forEach(f => {
  document.getElementById(f.id).addEventListener('input', updateCommandPreview);
});
updateCommandPreview();

async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      // 失敗時はフォールバックへ
    }
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch (err) {
    return false;
  }
}

document.getElementById('copy-update-cmd-btn').addEventListener('click', async () => {
  const statusEl = document.getElementById('update-cmd-status');
  const ok = await copyTextToClipboard(document.getElementById('update-cmd-output').textContent);
  statusEl.textContent = ok ? 'コピーしました' : 'コピーに失敗しました。手動で選択してコピーしてください';
  setTimeout(() => { statusEl.textContent = ''; }, 2500);
});

document.getElementById('open-terminal-btn').addEventListener('click', async () => {
  const statusEl = document.getElementById('update-cmd-status');
  const command = document.getElementById('update-cmd-output').textContent;
  const unfilled = UPDATE_CMD_FIELDS.filter(f => !document.getElementById(f.id).value.trim());
  if (unfilled.length > 0) {
    statusEl.textContent = '未入力の項目があります(' + unfilled.map(f => f.placeholder).join('・') +
      ')。入力してから「ターミナルを開く」を押してください';
    return;
  }
  statusEl.textContent = 'ターミナルを起動中...';
  try {
    const res = await fetch('/api/open_terminal', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command}),
    });
    const data = await res.json();
    statusEl.textContent = res.ok
      ? 'ターミナルを開きました(コマンドは入力済み・未実行です。確認してEnterを押してください)'
      : 'エラー: ' + (data.error || `HTTP ${res.status}`);
  } catch (err) {
    statusEl.textContent = 'エラー: ' + err.message;
  }
  setTimeout(() => { statusEl.textContent = ''; }, 5000);
});

renderTableHeader();
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
        SELECT c.id, c.table_name, c.column_name, c.data_type,
               GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS display_names,
               GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='calc' THEN a.display_name END) AS calc_names,
               COUNT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS alias_count,
               COUNT(a.id) AS usage_count,
               GROUP_CONCAT(DISTINCT a.board_name) AS boards,
               c.table_type,
               c.column_size, c.decimal_digits, c.is_nullable, c.is_unique
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
        display_names = row[4].split(",") if row[4] else []
        alias_count = row[6] or 0
        usage_count = row[7] or 0
        is_whitelisted = _normalize_key(table_name, column_name) in whitelist
        result.append({
            "id": row[0],
            "table_name": table_name,
            "column_name": column_name,
            "data_type": row[3],
            "display_names": display_names,
            "calc_names": row[5].split(",") if row[5] else [],
            "alias_count": alias_count,
            "usage_count": usage_count,
            "boards": row[8].split(",") if row[8] else [],
            "is_unaliased": any(_normalize_text(column_name) == _normalize_text(n) for n in display_names),
            "is_orphan": usage_count == 0,
            # 1対多の表記ゆれ候補としてハイライトするかどうか(alias_countが2以上でも、
            # ホワイトリスト対象なら候補としては扱わない)
            "is_naming_variant": alias_count > 1 and not is_whitelisted,
            # DD-025: match_aliases.pyが接続中DBの物理カラムと一致しないエイリアスを
            # table_type='(不明)'で仮登録したもの(別DBのボード混入やカラム名変更等の兆候)
            "is_unmatched": row[9] == "(不明)",
            # DD-033: テーブル定義パネルの「すべて表示」展開時に使う(未取得ならNULL=フロント側で「-」表示)
            "column_size": row[10],
            "decimal_digits": row[11],
            "is_nullable": row[12],
            "is_unique": row[13],
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


def fetch_excluded_aliases(db_path: str) -> list:
    """DD-026: ボード定義自身が別DB向けと申告しているため除外したエイリアスの一覧を返す
    (画面下部の「他DBのボードのため除外」セクション用)。"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT source_db, table_name, column_name, display_name, board_name
            FROM excluded_aliases
            ORDER BY source_db, table_name, column_name
        """)
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        # excluded_aliasesテーブルが無い(DD-026より前に生成されたlineage.db)場合は空扱い
        rows = []
    conn.close()
    return [
        {
            "source_db": row[0],
            "table_name": row[1],
            "column_name": row[2],
            "display_name": row[3],
            "board_name": row[4],
        }
        for row in rows
    ]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_html(INDEX_HTML)
        elif parsed.path == "/api/columns":
            if not self._require_db():
                return
            try:
                data = fetch_data(self.server.db_path, whitelist=self.server.whitelist)
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        elif parsed.path == "/api/patterns":
            if not self._require_db():
                return
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
            if not self._require_db():
                return
            try:
                data = fetch_board_details(self.server.db_path)
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
        elif parsed.path == "/api/excluded_aliases":
            if not self._require_db():
                return
            try:
                data = fetch_excluded_aliases(self.server.db_path)
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

    def _require_db(self) -> bool:
        """lineage.dbがまだ無い場合(--connect起動直後等)にエラーを返し、
        sqlite3.connect()が未存在ファイルを自動生成してしまうのを防ぐ(DD-007で発覚した不具合の修正)。"""
        if not Path(self.server.db_path).exists():
            self._send_json(
                {"error": f"{self.server.db_path} がまだ存在しません。「Dr.Sumに接続」から作成してください。"},
                status=404,
            )
            return False
        return True

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
        elif parsed.path == "/api/open_terminal":
            self._handle_open_terminal(body)
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

    def _handle_open_terminal(self, body: dict) -> None:
        """DD-029: 更新コマンドをクリップボードに乗せた状態でcmd.exeを新規起動し、
        その場でCtrl+Vペーストする(Enterは送らないため未実行のまま、ユーザー自身の
        実行判断を介さずにコマンドが走ることはない)。Windows専用。

        SendKeysによるペーストはタイミング依存で失敗することがあるが、その場合も
        クリップボードにはコマンドが残っているため手動貼り付け(Ctrl+V)で代替できる。
        """
        command = body.get("command")
        if not isinstance(command, str) or not command.strip():
            self._send_json({"error": "commandは必須です"}, status=400)
            return
        if os.name != "nt":
            self._send_json({"error": "この機能はWindows専用です"}, status=400)
            return

        project_dir = str(Path(__file__).resolve().parent)
        window_title = f"mb_alias_lineage_terminal_{os.getpid()}_{id(body)}"
        cmd_file = None
        try:
            # encoding="utf-8-sig"でBOMを付与する(BOM無しだとWindows PowerShell 5.1の
            # Get-ContentがシステムのANSIコードページ(日本語環境ではCP932)で読んでしまい、
            # 日本語を含むコマンドが文字化けする。-Encoding utf8も明示して二重に防ぐ
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8-sig"
            ) as f:
                f.write(command)
                cmd_file = f.name

            subprocess.Popen(
                ["cmd.exe", "/k", f"title {window_title}"],
                cwd=project_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            paste_script = (
                f"$cmdText = Get-Content -Raw -Encoding utf8 -Path '{cmd_file}'; "
                "Set-Clipboard -Value $cmdText; "
                "Start-Sleep -Milliseconds 700; "
                "Add-Type -AssemblyName Microsoft.VisualBasic; "
                f"[Microsoft.VisualBasic.Interaction]::AppActivate('{window_title}'); "
                "Start-Sleep -Milliseconds 200; "
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.SendKeys]::SendWait('^v'); "
                f"Remove-Item -Path '{cmd_file}' -ErrorAction SilentlyContinue"
            )
            subprocess.Popen(["powershell", "-NoProfile", "-Command", paste_script])
        except OSError as e:
            self._send_json({"error": f"ターミナルの起動に失敗しました: {e}"}, status=500)
            return
        self._send_json({"ok": True})

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

    row_count = None
    if Path(args.db).exists():
        try:
            with sqlite3.connect(args.db) as conn:
                row_count = conn.execute("SELECT COUNT(*) FROM columns").fetchone()[0]
        except sqlite3.OperationalError:
            # columnsテーブルが無い(--connect起動直後にAPIがsqlite3.connect()で
            # 自動生成した空ファイル等)。--connectで作り直せばよいだけなので
            # クラッシュさせず、未作成と同じ扱いにする
            row_count = None
    if row_count is not None:
        warn_if_large(row_count)
    else:
        print(f"※ {args.db} にまだ有効なデータがありません。画面の「Dr.Sumに接続」から作成してください。")

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
