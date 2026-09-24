-- lineage.db のスキーマ
-- TODO: 実データを見てから型・インデックス・主キー構成を調整してください

CREATE TABLE IF NOT EXISTS columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    table_type TEXT,
    column_name TEXT NOT NULL,
    data_type TEXT,
    UNIQUE(table_name, column_name)
);

CREATE TABLE IF NOT EXISTS aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    column_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    board_name TEXT NOT NULL,
    item_id TEXT,
    FOREIGN KEY (column_id) REFERENCES columns(id)
);

CREATE INDEX IF NOT EXISTS idx_aliases_column_id ON aliases(column_id);
CREATE INDEX IF NOT EXISTS idx_aliases_display_name ON aliases(display_name);
