"""
全体を通しで実行するオーケストレーター。

実接続がまだできない段階では --stub をつけて、
ダミーデータでパイプライン全体の動作を確認できます。

社内説明・デモ用には --demo をつけると、demo_data/ 以下の
(dummygen_jp_guiで作成した)合成データで一気通貫のデモを再現できます。

使い方（本番想定）:
    python main.py --backup-dir /path/to/backup/data \
        --host drsumserver --db mydb --user analyst --jdbc-jar /path/to/dwodsjd4.jar

使い方（動作確認だけしたい場合）:
    python main.py --stub

使い方（社内デモ用）:
    python main.py --demo
    python web_viewer.py --db demo_data/lineage.db
"""
import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional


def run(cmd: list, expect_file: Optional[str] = None) -> None:
    step_name = cmd[1] if len(cmd) > 1 else cmd[0]
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\nエラー: ステップ「{step_name}」が失敗しました(exit code {result.returncode})",
              file=sys.stderr)
        sys.exit(result.returncode)
    if expect_file and not Path(expect_file).exists():
        print(f"\nエラー: ステップ「{step_name}」は正常終了しましたが、"
              f"期待される出力ファイル {expect_file} が生成されませんでした", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stub", action="store_true", help="ダミーデータで一気通貫の動作確認をする")
    parser.add_argument("--demo", action="store_true",
                         help="demo_data/ の合成データで一気通貫のデモを再現する(社内説明用)")
    parser.add_argument("--backup-dir", help="MotionBoardのボード定義バックアップフォルダ")
    parser.add_argument("--host")
    parser.add_argument("--db")
    parser.add_argument("--user")
    parser.add_argument("--jdbc-jar")
    args = parser.parse_args()

    py = sys.executable

    if args.demo:
        run([py, "board_parser.py", "demo_data/motionboard_backup",
             "--columns", "demo_data/dr_sum_columns.json", "--out", "demo_data/board_aliases.json"],
            expect_file="demo_data/board_aliases.json")
        run([py, "match_aliases.py", "--columns", "demo_data/dr_sum_columns.json",
             "--aliases", "demo_data/board_aliases.json", "--db", "demo_data/lineage.db"])
        print("\nデモの結果を見るには: python web_viewer.py --db demo_data/lineage.db")
        return

    if args.stub:
        run([py, "dr_sum_metadata.py", "--stub", "--out", "dr_sum_columns.json"],
            expect_file="dr_sum_columns.json")
        run([py, "board_parser.py", "--stub", "--out", "board_aliases.json"],
            expect_file="board_aliases.json")
    else:
        if not (args.backup_dir and args.host and args.db and args.user and args.jdbc_jar):
            parser.error("--stub を使わない場合は --backup-dir --host --db --user --jdbc-jar が必須です")
        run([py, "dr_sum_metadata.py", "--host", args.host, "--db", args.db,
             "--user", args.user, "--jdbc-jar", args.jdbc_jar, "--out", "dr_sum_columns.json"],
            expect_file="dr_sum_columns.json")
        # 自動検出モード: Dr.Sumのカラム一覧を手がかりにタグ構造を推測するので、
        # ボード定義ファイルのタグ名を事前に調べる必要はない
        run([py, "board_parser.py", args.backup_dir,
             "--columns", "dr_sum_columns.json", "--out", "board_aliases.json"],
            expect_file="board_aliases.json")

    run([py, "match_aliases.py", "--columns", "dr_sum_columns.json", "--aliases", "board_aliases.json"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断しました", file=sys.stderr)
        sys.exit(130)
