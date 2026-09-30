"""
フェーズ2: Dr.SumからJDBC経由でテーブル/ビューのカラムメタデータを取得する。

事前準備:
  - Development Kitに含まれるJDBCドライバー(dwodsjd4.jar)を用意し、
    DR_SUM_JDBC_JAR 環境変数 or --jdbc-jar オプションでパスを指定する
  - pip install -r requirements.txt (JayDeBeApi, JPype1)

接続方式・システムカタログはDD-002-2（doc/DD/DD-002-2_Dr.Sum実環境対応.md）で
実機確認済みの仕様に基づく。ディストリビューター・マルチビューはスコープ外。
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List


class DrSumConnectionError(RuntimeError):
    """接続・メタデータ取得の失敗を、原因の推測+対処のヒント付きで伝えるための例外。"""


@dataclass
class ColumnMeta:
    table_name: str
    table_type: str  # "TABLE" or "VIEW"
    column_name: str
    data_type: str
    ordinal: int


class DrSumConnector:
    """Dr.SumへのJDBC接続をラップするクラス。

    実際のドライバークラス名・URL書式はDevelopment Kitのマニュアルに
    記載されているものに置き換えてください（ここはプレースホルダ）。
    """

    def __init__(self, host: str, database: str, user: str, password: str,
                 jdbc_jar: str, port: int = 6001):
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.jdbc_jar = jdbc_jar
        self.port = port
        self._conn = None

    def _build_jdbc_url(self) -> str:
        return f"jdbc:dwods:{self.host}:{self.port}:{self.database}"

    def connect(self):
        if not Path(self.jdbc_jar).exists():
            raise DrSumConnectionError(
                f"JDBCドライバーのjarファイルが見つかりません: {self.jdbc_jar}\n"
                "  → --jdbc-jar オプション(またはDR_SUM_JDBC_JAR環境変数)のパスを確認してください。"
            )
        try:
            import jaydebeapi  # 遅延importにして、未インストールでも他機能を使えるようにする
        except ImportError as e:
            raise DrSumConnectionError(
                "jaydebeapi (またはJPype1) がインストールされていません。\n"
                "  → pip install -r requirements.txt を実行してください。"
            ) from e

        driver_class = "jp.co.dw_sapporo.JDBC.JDBCDriver"
        try:
            self._conn = jaydebeapi.connect(
                driver_class,
                self._build_jdbc_url(),
                [self.user, self.password],
                self.jdbc_jar,
            )
        except Exception as e:
            raise DrSumConnectionError(
                f"Dr.Sumサーバーへの接続に失敗しました(host={self.host}, port={self.port}, "
                f"db={self.database})。\n"
                "  → host/port/db/user/jdbc-jarの値と、Dr.Sumサーバーへの疎通を確認してください。\n"
                f"  元のエラー: {e}"
            ) from e
        return self._conn

    def fetch_columns(self) -> List[ColumnMeta]:
        """通常のテーブル・ビューのカラム一覧を取得する（ディストリビューター・
        マルチビューは対象外。DD-002-2参照）。

        `__all_tables__`には明示的な列順序（ordinal）が無いため、実機確認済みの
        「返却順が列定義順と一致する」という前提のもと、テーブルごとに返却順で
        ordinalを採番する。
        """
        assert self._conn is not None, "先にconnect()を呼んでください"
        cursor = self._conn.cursor()

        # assortment='table'は各テーブル自体の見出し行(column_name等はNULL)であり、
        # 実際のカラム詳細はassortment='column'側に格納されている(実機確認で判明)。
        query = """
            SELECT table_name, column_name, column_type
            FROM __all_tables__
            WHERE assortment = 'column'
        """
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
        except Exception as e:
            raise DrSumConnectionError(
                "システムカタログ(__all_tables__)のクエリに失敗しました。\n"
                "  → 実機のDr.Sumバージョンでシステムテーブル構成が異なる可能性があります。\n"
                f"  元のエラー: {e}"
            ) from e
        finally:
            cursor.close()

        ordinal_by_table: Dict[str, int] = {}
        columns = []
        for table_name, column_name, column_type in rows:
            ordinal = ordinal_by_table.get(table_name, 0) + 1
            ordinal_by_table[table_name] = ordinal
            columns.append(ColumnMeta(
                table_name=table_name,
                table_type="TABLE",
                column_name=column_name,
                data_type=column_type,
                ordinal=ordinal,
            ))
        return columns


def fetch_columns_stub() -> List[ColumnMeta]:
    """接続先が無い状態でもパイプライン全体の動作確認ができるよう、
    ダミーデータを返すスタブ。--stub オプションで使う。
    """
    sample = [
        ("T_売上明細", "TABLE", "URIAGE_KIN", "DECIMAL", 1),
        ("T_売上明細", "TABLE", "CHIIKI_KBN", "VARCHAR", 2),
        ("T_顧客M", "TABLE", "KOKYAKU_CD", "VARCHAR", 1),
        ("T_在庫", "TABLE", "ZAIKO_SU", "INTEGER", 1),
    ]
    return [
        ColumnMeta(table_name=t, table_type=tt, column_name=c, data_type=dt, ordinal=o)
        for t, tt, c, dt, o in sample
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="Dr.Sumサーバーのホスト名")
    parser.add_argument("--port", type=int, default=6001)
    parser.add_argument("--db", help="データベース名")
    parser.add_argument("--user", help="接続ユーザー")
    parser.add_argument("--password", default=os.environ.get("DR_SUM_PASSWORD", ""))
    parser.add_argument("--jdbc-jar", default=os.environ.get("DR_SUM_JDBC_JAR", ""))
    parser.add_argument("--out", default="dr_sum_columns.json")
    parser.add_argument("--stub", action="store_true",
                         help="実接続せずダミーデータで動作確認する")
    parser.add_argument("--debug", action="store_true",
                         help="接続失敗時に元の例外のスタックトレースも表示する")
    args = parser.parse_args()

    if args.stub:
        columns = fetch_columns_stub()
        print("※ --stub モード: ダミーデータを使用しています")
    else:
        if not (args.host and args.db and args.user and args.jdbc_jar):
            parser.error("--stub を使わない場合は --host --db --user --jdbc-jar が必須です")
        connector = DrSumConnector(
            host=args.host, database=args.db, user=args.user,
            password=args.password, jdbc_jar=args.jdbc_jar, port=args.port,
        )
        try:
            connector.connect()
            columns = connector.fetch_columns()
        except DrSumConnectionError as e:
            print(f"エラー: {e}", file=sys.stderr)
            if args.debug:
                raise
            sys.exit(1)

    out_path = Path(args.out)
    out_path.write_text(
        json.dumps([asdict(c) for c in columns], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(columns)}件のカラム情報を {out_path} に出力しました")


if __name__ == "__main__":
    main()
