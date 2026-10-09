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
    # DD-034: __all_tables__(assortment='column')に実在すると実機確認済みの4列。
    # column_size=column_precision、decimal_digits=column_scale、
    # is_unique="YES"/"NO"(column_unique: 1/0)、is_nullable="YES"/"NO"
    # (column_null: 0=NULL許容→YES、1=NOT NULL制約あり→NO。実機データでPK的な列が
    # column_null=1かつcolumn_unique=1だったことから、column_nullは「NOT NULL制約の
    # 有無」を表すとユーザー確認済み。D-004参照)
    column_size: int = None
    decimal_digits: int = None
    is_nullable: str = None
    is_unique: str = None


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
        # column_precision/column_scale/column_null/column_uniqueはDD-034で実機確認済み。
        query = """
            SELECT table_name, column_name, column_type,
                   column_precision, column_scale, column_null, column_unique
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
        for table_name, column_name, column_type, column_precision, column_scale, column_null, column_unique in rows:
            ordinal = ordinal_by_table.get(table_name, 0) + 1
            ordinal_by_table[table_name] = ordinal
            columns.append(ColumnMeta(
                table_name=table_name,
                table_type="TABLE",
                column_name=column_name,
                data_type=column_type,
                ordinal=ordinal,
                column_size=column_precision,
                decimal_digits=column_scale,
                is_nullable=("NO" if column_null else "YES") if column_null is not None else None,
                is_unique=("YES" if column_unique else "NO") if column_unique is not None else None,
            ))
        return columns

    def dump_raw_columns(self, limit: int = 50) -> dict:
        """DD-034調査用: `__all_tables__`(assortment='column')の全列をそのまま取得する。

        精度・スケール・NULL許可・ユニークに相当する列が存在するかを実機で確認するための
        使い捨て調査モード(`--dump-raw`)専用。`fetch_columns()`と違い列を絞らず`SELECT *`する。
        Dr.SumのSQL方言でLIMIT構文が使えるか未確認のため、絞り込みはPython側(fetchall後)で行う。
        """
        assert self._conn is not None, "先にconnect()を呼んでください"
        cursor = self._conn.cursor()
        query = """
            SELECT *
            FROM __all_tables__
            WHERE assortment = 'column'
        """
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            column_names = [d[0] for d in cursor.description] if cursor.description else []
        except Exception as e:
            raise DrSumConnectionError(
                "システムカタログ(__all_tables__)の全列取得クエリに失敗しました。\n"
                "  → 実機のDr.Sumバージョンでシステムテーブル構成が異なる可能性があります。\n"
                f"  元のエラー: {e}"
            ) from e
        finally:
            cursor.close()

        return {
            "columns": column_names,
            "total_rows": len(rows),
            "rows": [list(row) for row in rows[:limit]],
        }


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
    parser.add_argument("--dump-raw", action="store_true",
                         help="DD-034調査用: __all_tables__(assortment='column')の全列をそのまま出力する"
                              "(精度・スケール・NULL許可・ユニークに相当する列の有無を確認するため。"
                              "通常のカラム取得は行わない)")
    parser.add_argument("--dump-raw-limit", type=int, default=50,
                         help="--dump-raw時に出力する最大行数(既定50)")
    parser.add_argument("--raw-out", default="dr_sum_catalog_raw.json",
                         help="--dump-raw時の出力先")
    args = parser.parse_args()

    if args.dump_raw:
        if not (args.host and args.db and args.user and args.jdbc_jar):
            parser.error("--dump-raw を使う場合も --host --db --user --jdbc-jar が必須です")
        connector = DrSumConnector(
            host=args.host, database=args.db, user=args.user,
            password=args.password, jdbc_jar=args.jdbc_jar, port=args.port,
        )
        try:
            connector.connect()
            raw = connector.dump_raw_columns(limit=args.dump_raw_limit)
        except DrSumConnectionError as e:
            print(f"エラー: {e}", file=sys.stderr)
            if args.debug:
                raise
            sys.exit(1)

        raw_out_path = Path(args.raw_out)
        raw_out_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"__all_tables__(assortment='column')の列名: {raw['columns']}")
        print(f"全{raw['total_rows']}行中、先頭{len(raw['rows'])}行を{raw_out_path}に出力しました")
        print("精度・スケール・NULL許可・ユニークに相当する列が無いか、上記の列名一覧・出力JSONを確認してください(DD-034)。")
        return

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
