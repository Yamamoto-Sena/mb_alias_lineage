"""
フェーズ3: dr_sum_metadata.py の出力(dr_sum_columns.json)と
board_parser.py の出力(board_aliases.json)を突き合わせ、
SQLite(lineage.db)に保存したうえで、表記ゆれ候補を一覧表示する。

使い方:
    python match_aliases.py --columns dr_sum_columns.json --aliases board_aliases.json
"""
import argparse
import difflib
import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _normalize_text(s: str) -> str:
    """全角/半角・大文字小文字の違いを吸収した比較用文字列を作る。"""
    return unicodedata.normalize("NFKC", (s or "").strip()).upper()


def _normalize_key(table_name: str, column_name: str) -> tuple:
    """全角/半角・大文字小文字の違いを吸収した突き合わせ用キーを作る。
    保存する値そのものには使わない(表示・保存は元の表記のまま)。"""
    return (_normalize_text(table_name), _normalize_text(column_name))


def load_whitelist(path: str) -> set:
    """物理カラム単位の除外設定(naming_whitelist.json)を読み込む。

    フォーマット: {"excluded_columns": [{"table_name": ..., "column_name": ..., "reason": ...}]}
    "reason"は監査用のコメントでロジックには使わない。キー欠落・空ファイルの場合はエラーにせず
    空集合を返す。
    """
    data = load_json(path)
    excluded = data.get("excluded_columns") or []
    return {_normalize_key(e["table_name"], e["column_name"]) for e in excluded}


def load_whitelist_entries(path: str) -> list:
    """UI編集用に、正規化前の生データ(table_name/column_name/reasonの元表記)のまま返す。

    ファイルが存在しない場合はエラーにせず空リストを返す(DD-003: --whitelist未指定・
    ファイル未作成の状態でも一覧取得できるようにするため)。
    """
    p = Path(path)
    if not p.exists():
        return []
    data = load_json(path)
    return data.get("excluded_columns") or []


def save_whitelist_entries(path: str, entries: list) -> None:
    Path(path).write_text(
        json.dumps({"excluded_columns": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_whitelist_entry(path: str, table_name: str, column_name: str, reason: str = "") -> list:
    """(table_name, column_name)のエントリを追加して保存する(UI編集用、DD-003)。

    正規化キーが既存エントリと一致する場合は何もしない(重複登録を防ぐ。既存のreasonも
    上書きしない)。戻り値: 保存後の全エントリ。
    """
    entries = load_whitelist_entries(path)
    key = _normalize_key(table_name, column_name)
    already_exists = any(
        _normalize_key(e["table_name"], e["column_name"]) == key for e in entries
    )
    if not already_exists:
        entries.append({"table_name": table_name, "column_name": column_name, "reason": reason})
        save_whitelist_entries(path, entries)
    return entries


def remove_whitelist_entry(path: str, table_name: str, column_name: str) -> list:
    """(table_name, column_name)に正規化キーが一致するエントリを削除して保存する(UI編集用、DD-003)。

    一致するエントリがなければ何もしない。戻り値: 保存後の全エントリ。
    """
    entries = load_whitelist_entries(path)
    key = _normalize_key(table_name, column_name)
    remaining = [e for e in entries if _normalize_key(e["table_name"], e["column_name"]) != key]
    if len(remaining) != len(entries):
        save_whitelist_entries(path, remaining)
    return remaining


def build_db(db_path: str, columns: list, aliases: list, connected_db: str = None) -> None:
    schema_path = Path(__file__).parent / "db_schema.sql"
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_path.read_text(encoding="utf-8"))

    cur = conn.cursor()

    # カラムを登録し、table_name+column_name -> id の対応表を作る(完全一致キーと、
    # 全角半角/大文字小文字を正規化したキーの両方を用意する)
    column_id_map = {}
    normalized_id_map = {}
    for col in columns:
        cur.execute(
            """
            INSERT OR IGNORE INTO columns (table_name, table_type, column_name, data_type)
            VALUES (?, ?, ?, ?)
            """,
            (col["table_name"], col.get("table_type"), col["column_name"], col.get("data_type")),
        )
        cur.execute(
            "SELECT id FROM columns WHERE table_name=? AND column_name=?",
            (col["table_name"], col["column_name"]),
        )
        row = cur.fetchone()
        if row:
            key = (col["table_name"], col["column_name"])
            column_id_map[key] = row[0]
            normalized_id_map[_normalize_key(*key)] = row[0]

    # エイリアスを登録。完全一致で見つからなければ正規化キーで再試行し、
    # それでも見つからない場合は警告して table_name="(不明)" で仮登録
    unmatched = 0
    normalized_matches = 0
    excluded = 0
    connected_db_normalized = _normalize_text(connected_db) if connected_db else None
    for alias in aliases:
        source_db = alias.get("source_db") or ""
        # DD-026: ボード定義自身が「別DBのものだ」と申告している(source_dbが分かっていて
        # 接続中DBと違う)場合は、物理カラムと照合するまでもなく無関係と確定しているため、
        # 不一致候補としてcolumns/aliasesに混ぜず、excluded_aliasesへ分けて記録する
        if connected_db_normalized and source_db and _normalize_text(source_db) != connected_db_normalized:
            excluded += 1
            cur.execute(
                """
                INSERT INTO excluded_aliases (source_db, table_name, column_name, display_name, board_name, usage_type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source_db, alias["table_name"], alias["column_name"], alias["display_name"],
                 alias["board_name"], alias.get("usage_type", "alias")),
            )
            continue

        key = (alias["table_name"], alias["column_name"])
        column_id = column_id_map.get(key)
        if column_id is None:
            column_id = normalized_id_map.get(_normalize_key(*key))
            if column_id is not None:
                normalized_matches += 1

        if column_id is None:
            unmatched += 1
            cur.execute(
                """
                INSERT OR IGNORE INTO columns (table_name, table_type, column_name, data_type)
                VALUES (?, '(不明)', ?, NULL)
                """,
                (alias["table_name"] or "(不明)", alias["column_name"]),
            )
            cur.execute(
                "SELECT id FROM columns WHERE table_name=? AND column_name=?",
                (alias["table_name"] or "(不明)", alias["column_name"]),
            )
            column_id = cur.fetchone()[0]
            column_id_map[key] = column_id

        cur.execute(
            """
            INSERT OR IGNORE INTO aliases (column_id, display_name, board_name, item_id, usage_type, source_file)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (column_id, alias["display_name"], alias["board_name"], alias.get("item_id"),
             alias.get("usage_type", "alias"), alias.get("source_file")),
        )

    conn.commit()
    conn.close()

    if normalized_matches:
        print(f"※ 全角半角/大文字小文字の正規化により追加で一致したエイリアスが"
              f"{normalized_matches}件ありました")
    if unmatched:
        print(f"※ Dr.Sum側のカラム一覧に見つからないエイリアスが{unmatched}件ありました"
              f"（テーブル名の表記ゆれや、取得漏れの可能性があります）")
    if excluded:
        print(f"※ 接続中のDB(「{connected_db}」)とは別のDB用と分かったエイリアスが"
              f"{excluded}件あり、除外しました（画面下部の「他DBのボードのため除外」欄を参照）")


def find_naming_inconsistencies(db_path: str, whitelist: set = None) -> list:
    """同じ物理カラムに複数の表示名(usage_type='alias')が付与されているケースを検出する。

    戻り値: [(table_name, column_name, alias_count, display_names, usage_count), ...]
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.table_name, c.column_name,
               COUNT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS alias_count,
               GROUP_CONCAT(DISTINCT CASE WHEN a.usage_type='alias' THEN a.display_name END) AS display_names,
               COUNT(CASE WHEN a.usage_type='alias' THEN 1 END) AS usage_count
        FROM aliases a
        JOIN columns c ON c.id = a.column_id
        GROUP BY c.id
        HAVING alias_count > 1
        ORDER BY alias_count DESC, usage_count DESC
        """
    )
    rows = cur.fetchall()
    conn.close()

    if whitelist:
        rows = [r for r in rows if _normalize_key(r[0], r[1]) not in whitelist]
    return rows


def report_naming_inconsistencies(db_path: str, whitelist: set = None) -> None:
    rows = find_naming_inconsistencies(db_path, whitelist=whitelist)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM aliases WHERE usage_type='calc'")
    calc_count = cur.fetchone()[0]
    conn.close()

    if calc_count:
        print(f"※ カスタム項目・事後計算項目の計算式内で使用されている項目: {calc_count}件"
              f"(表記ゆれの集計には含めていません)\n")

    if not rows:
        print("表記ゆれ候補は見つかりませんでした")
        return

    print(f"\n表記ゆれ候補: {len(rows)}件\n" + "-" * 60)
    for table_name, column_name, alias_count, display_names, usage_count in rows:
        print(f"[{table_name}].{column_name}")
        print(f"  表示名({alias_count}種): {display_names}")
        print(f"  使用ボード数(延べ): {usage_count}件\n")


def find_many_to_one_mappings(db_path: str, whitelist: set = None) -> list:
    """異なる物理カラムに同じ表示名(usage_type='alias')が付与されているケースを検出する。

    戻り値: [{"display_name": str, "columns": [{"table_name":.., "column_name":..}, ...]}]
    (whitelist除外後に残りカラム数が1以下になったものは「多対1」ではないため除外する)
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.display_name, c.table_name, c.column_name
        FROM aliases a
        JOIN columns c ON c.id = a.column_id
        WHERE a.usage_type = 'alias'
        """
    )
    rows = cur.fetchall()
    conn.close()

    whitelist = whitelist or set()
    by_display_name = {}
    for display_name, table_name, column_name in rows:
        if _normalize_key(table_name, column_name) in whitelist:
            continue
        cols = by_display_name.setdefault(display_name, {})
        cols[(table_name, column_name)] = {"table_name": table_name, "column_name": column_name}

    results = []
    for display_name, cols in by_display_name.items():
        if len(cols) > 1:
            results.append({"display_name": display_name, "columns": list(cols.values())})
    return results


def report_many_to_one_mapping(db_path: str, whitelist: set = None) -> None:
    results = find_many_to_one_mappings(db_path, whitelist=whitelist)
    if not results:
        print("多対1マッピング候補は見つかりませんでした")
        return

    print(f"\n多対1マッピング候補: {len(results)}件\n" + "-" * 60)
    for r in results:
        cols_text = ", ".join(f"[{c['table_name']}].{c['column_name']}" for c in r["columns"])
        print(f"表示名「{r['display_name']}」が {len(r['columns'])}個の物理カラムに使用: {cols_text}\n")


def find_unaliased_columns(db_path: str) -> list:
    """表示名が物理カラム名そのまま(正規化基準で一致)になっているケースを検出する。

    戻り値: [{"table_name":.., "column_name":..}]
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT c.table_name, c.column_name, a.display_name
        FROM aliases a
        JOIN columns c ON c.id = a.column_id
        WHERE a.usage_type = 'alias'
        """
    )
    rows = cur.fetchall()
    conn.close()

    seen = {}
    for table_name, column_name, display_name in rows:
        if _normalize_text(column_name) == _normalize_text(display_name):
            seen[(table_name, column_name)] = {"table_name": table_name, "column_name": column_name}
    return list(seen.values())


def report_unaliased_columns(db_path: str) -> None:
    results = find_unaliased_columns(db_path)
    if not results:
        print("物理名直接使用の候補は見つかりませんでした")
        return

    print(f"\n物理名直接使用(エイリアス未設定)の候補: {len(results)}件\n" + "-" * 60)
    for r in results:
        print(f"[{r['table_name']}].{r['column_name']}\n")


def find_orphan_columns(db_path: str) -> list:
    """MotionBoard定義から一度も使われていない(usage_type問わず0件)Dr.Sumカラムを検出する。

    戻り値: [{"table_name":.., "column_name":..}]
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.table_name, c.column_name
        FROM columns c
        LEFT JOIN aliases a ON a.column_id = c.id
        WHERE a.id IS NULL
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [{"table_name": t, "column_name": c} for t, c in rows]


def report_orphan_columns(db_path: str) -> None:
    results = find_orphan_columns(db_path)
    if not results:
        print("孤立項目(未使用カラム)は見つかりませんでした")
        return

    print(f"\n孤立項目(MotionBoardで未使用のDr.Sumカラム): {len(results)}件\n" + "-" * 60)
    for r in results:
        print(f"[{r['table_name']}].{r['column_name']}\n")


def find_similar_display_name_pairs(db_path: str, threshold: float = 0.8, whitelist: set = None) -> list:
    """異なる物理カラムに紐づく表示名同士をdifflib.SequenceMatcherで比較し、
    ratio >= thresholdのペアを抽出する(同一カラム内の表示名同士は比較しない)。

    戻り値: [{"column_a": {...}, "column_b": {...}, "ratio": float}]
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT c.id, c.table_name, c.column_name, a.display_name
        FROM aliases a
        JOIN columns c ON c.id = a.column_id
        WHERE a.usage_type = 'alias'
        """
    )
    rows = cur.fetchall()
    conn.close()

    whitelist = whitelist or set()
    entries = [
        {"column_id": column_id, "table_name": table_name, "column_name": column_name, "display_name": display_name}
        for column_id, table_name, column_name, display_name in rows
        if _normalize_key(table_name, column_name) not in whitelist
    ]

    if len(entries) > 2000:
        print(f"※ 類似度計算の比較対象が{len(entries)}件と多いため、計算に時間がかかる場合があります")

    results = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            if a["column_id"] == b["column_id"]:
                continue
            ratio = difflib.SequenceMatcher(None, a["display_name"], b["display_name"]).ratio()
            if ratio >= threshold:
                results.append({
                    "column_a": {"table_name": a["table_name"], "column_name": a["column_name"],
                                 "display_name": a["display_name"]},
                    "column_b": {"table_name": b["table_name"], "column_name": b["column_name"],
                                 "display_name": b["display_name"]},
                    "ratio": ratio,
                })
    return results


def report_similar_display_name_pairs(db_path: str, threshold: float = 0.8, whitelist: set = None) -> None:
    results = find_similar_display_name_pairs(db_path, threshold=threshold, whitelist=whitelist)
    if not results:
        print("類似度による表記ゆれ候補は見つかりませんでした")
        return

    print(f"\n類似度による表記ゆれ候補(閾値{threshold}): {len(results)}件\n" + "-" * 60)
    for r in results:
        a, b = r["column_a"], r["column_b"]
        print(f"[{a['table_name']}].{a['column_name']}「{a['display_name']}」 <-> "
              f"[{b['table_name']}].{b['column_name']}「{b['display_name']}」"
              f" (類似度: {r['ratio']:.2f})\n")


def collect_category_counts(db_path: str, whitelist: set = None, threshold: float = 0.8) -> dict:
    """5カテゴリの検出件数をまとめて取得する(実行履歴・通知連携での差分検知用)。"""
    return {
        "naming_inconsistencies": len(find_naming_inconsistencies(db_path, whitelist=whitelist)),
        "many_to_one": len(find_many_to_one_mappings(db_path, whitelist=whitelist)),
        "unaliased_columns": len(find_unaliased_columns(db_path)),
        "orphan_columns": len(find_orphan_columns(db_path)),
        "similar_display_name_pairs": len(
            find_similar_display_name_pairs(db_path, threshold=threshold, whitelist=whitelist)
        ),
    }


def report_history_diff(history_path: str, counts: dict) -> None:
    """前回実行時の件数(history_path)と今回のcountsを比較し、新規/増減を表示してから保存する。

    lineage.db自体は実行ごとにDROP→CREATEするスナップショット設計(db_schema.sql参照)のため、
    履歴はDBの外側にこのJSONファイルとして持つ。定期実行(タスクスケジューラ等)での運用や、
    将来の通知連携(送信先確定後)での「新規検出・増減があった時のみ通知」判定にそのまま使える。
    """
    path = Path(history_path)
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    prev_counts = previous.get("counts", {}) if previous else {}

    print(f"\n実行履歴との差分(前回: {previous['recorded_at'] if previous else 'なし'})\n" + "-" * 60)
    for category, count in counts.items():
        prev = prev_counts.get(category)
        if prev is None:
            print(f"{category}: {count}件(前回実行なし)")
            continue
        delta = count - prev
        if delta == 0:
            print(f"{category}: {count}件(変化なし)")
        else:
            print(f"{category}: {count}件(前回{prev}件から{delta:+d})")

    path.write_text(
        json.dumps(
            {"counts": counts, "recorded_at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--columns", required=True, help="dr_sum_metadata.pyの出力ファイル")
    parser.add_argument("--aliases", required=True, help="board_parser.pyの出力ファイル")
    parser.add_argument("--db", default="lineage.db")
    parser.add_argument("--whitelist", help="表記ゆれ候補から除外する物理カラムの設定ファイル(naming_whitelist.json)")
    parser.add_argument("--similarity-threshold", type=float, default=0.8,
                         help="類似度による表記ゆれ候補の閾値(0〜1、デフォルト0.8)")
    parser.add_argument("--history-file",
                         help="前回実行との差分検知に使う実行履歴ファイル"
                              "(既定値: <db>.history.json。--dbが違えば履歴も混在しない)")
    parser.add_argument("--connected-db",
                         help="今回接続したDr.SumのDB名(DD-026)。board_parser.pyが"
                              "ボード定義から読み取った所属DB名(source_db)と比較し、"
                              "確実に別DBのボードと分かるエイリアスを除外するために使う。"
                              "未指定時(--stub/--demo等)は除外ロジックを無効化し、"
                              "従来どおり全エイリアスを不一致判定の対象にする")
    args = parser.parse_args()
    history_file = args.history_file or f"{args.db}.history.json"

    if args.whitelist and not Path(args.whitelist).exists():
        parser.error(f"--whitelist で指定されたファイルが見つかりません: {args.whitelist}")
    whitelist = load_whitelist(args.whitelist) if args.whitelist else None

    columns = load_json(args.columns)
    aliases = load_json(args.aliases)

    build_db(args.db, columns, aliases, connected_db=args.connected_db)
    print(f"{args.db} にデータを保存しました\n")
    report_naming_inconsistencies(args.db, whitelist=whitelist)
    report_many_to_one_mapping(args.db, whitelist=whitelist)
    report_unaliased_columns(args.db)
    report_orphan_columns(args.db)
    report_similar_display_name_pairs(args.db, threshold=args.similarity_threshold, whitelist=whitelist)

    counts = collect_category_counts(args.db, whitelist=whitelist, threshold=args.similarity_threshold)
    report_history_diff(history_file, counts)


if __name__ == "__main__":
    main()
