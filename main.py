"""
全体を通しで実行するオーケストレーター。

実接続がまだできない段階では --stub をつけて、
ダミーデータでパイプライン全体の動作を確認できます。

使い方（本番想定）:
    python main.py --backup-dir /path/to/backup/data \
        --host drsumserver --db mydb --user analyst --jdbc-jar /path/to/dwodsjd4.jar

使い方（動作確認だけしたい場合）:
    python main.py --stub
"""
import argparse
import subprocess
import sys


def run(cmd: list) -> None:
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stub", action="store_true", help="ダミーデータで一気通貫の動作確認をする")
    parser.add_argument("--backup-dir", help="MotionBoardのボード定義バックアップフォルダ")
    parser.add_argument("--host")
    parser.add_argument("--db")
    parser.add_argument("--user")
    parser.add_argument("--jdbc-jar")
    args = parser.parse_args()

    py = sys.executable

    if args.stub:
        run([py, "dr_sum_metadata.py", "--stub", "--out", "dr_sum_columns.json"])
        run([py, "board_parser.py", "--stub", "--out", "board_aliases.json"])
    else:
        if not (args.backup_dir and args.host and args.db and args.user and args.jdbc_jar):
            parser.error("--stub を使わない場合は --backup-dir --host --db --user --jdbc-jar が必須です")
        run([py, "dr_sum_metadata.py", "--host", args.host, "--db", args.db,
             "--user", args.user, "--jdbc-jar", args.jdbc_jar, "--out", "dr_sum_columns.json"])
        # 自動検出モード: Dr.Sumのカラム一覧を手がかりにタグ構造を推測するので、
        # ボード定義ファイルのタグ名を事前に調べる必要はない
        run([py, "board_parser.py", args.backup_dir,
             "--columns", "dr_sum_columns.json", "--out", "board_aliases.json"])

    run([py, "match_aliases.py", "--columns", "dr_sum_columns.json", "--aliases", "board_aliases.json"])


if __name__ == "__main__":
    main()
