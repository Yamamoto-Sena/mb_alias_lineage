"""
フェーズ2: Dr.SumからJDBC経由でテーブル/ビュー/カラムのメタデータを取得する。

事前準備:
  - Development Kitに含まれるJDBCドライバー(例: dwodsjd4.jar)を用意し、
    DR_SUM_JDBC_JAR 環境変数 or --jdbc-jar オプションでパスを指定する
  - pip install -r requirements.txt (JayDeBeApi, JPype1)

TODO: 実環境の接続文字列の形式（JDBC URLの書式）はDr.Sumのバージョンにより
      異なることがあるため、DrSumConnector._build_jdbc_url() を実機の
      マニュアルに合わせて調整してください。ここではダミーの書式にしています。
"""
import argparse
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


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
        # TODO: 実際のDr.Sum JDBC URL書式に置き換える
        return f"jdbc:dsjdbc://{self.host}:{self.port}/{self.database}"

    def connect(self):
        import jaydebeapi  # 遅延importにして、未インストールでも他機能を使えるようにする

        driver_class = "jp.co.uwsc.drsum.jdbc.DsDriver"  # TODO: 正式なドライバークラス名に置換
        self._conn = jaydebeapi.connect(
            driver_class,
            self._build_jdbc_url(),
            [self.user, self.password],
            self.jdbc_jar,
        )
        return self._conn

    def fetch_columns(self) -> List[ColumnMeta]:
        """全テーブル/ビューのカラム一覧を取得する。

        TODO: Dr.Sumのシステムカタログ（システムビュー）の正式名称に合わせて
              クエリを書き換える。以下は一般的なSQLメタデータ取得の書式の例。
        """
        assert self._conn is not None, "先にconnect()を呼んでください"
        cursor = self._conn.cursor()

        query = """
            SELECT
                TABLE_NAME,
                TABLE_TYPE,
                COLUMN_NAME,
                DATA_TYPE,
                ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            ORDER BY TABLE_NAME, ORDINAL_POSITION
        """  # TODO: Dr.Sum固有のシステムカタログ名に置き換える
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()

        return [
            ColumnMeta(
                table_name=row[0],
                table_type=row[1],
                column_name=row[2],
                data_type=row[3],
                ordinal=row[4],
            )
            for row in rows
        ]


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
        connector.connect()
        columns = connector.fetch_columns()

    out_path = Path(args.out)
    out_path.write_text(
        json.dumps([asdict(c) for c in columns], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(columns)}件のカラム情報を {out_path} に出力しました")


if __name__ == "__main__":
    main()
