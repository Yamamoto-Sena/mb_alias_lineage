-- lineage.db のスキーマ
-- TODO: 実データを見てから型・インデックス・主キー構成を調整してください
--
-- match_aliases.py を実行するたびに、このスキーマでテーブルごと作り直す
-- (DROP→CREATE)運用にしている。lineage.dbは「その時点のスナップショット」
-- であり、過去の実行結果を積み上げていく設計ではないため。

DROP TABLE IF EXISTS aliases;
DROP TABLE IF EXISTS columns;

CREATE TABLE columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    table_type TEXT,
    column_name TEXT NOT NULL,
    data_type TEXT,
    UNIQUE(table_name, column_name)
);

CREATE TABLE aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    column_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    board_name TEXT NOT NULL,
    item_id TEXT,
    FOREIGN KEY (column_id) REFERENCES columns(id),
    UNIQUE(column_id, display_name, board_name, item_id)
);

CREATE INDEX idx_aliases_column_id ON aliases(column_id);
CREATE INDEX idx_aliases_display_name ON aliases(display_name);
