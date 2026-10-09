-- lineage.db のスキーマ
-- TODO: 実データを見てから型・インデックス・主キー構成を調整してください
--
-- match_aliases.py を実行するたびに、このスキーマでテーブルごと作り直す
-- (DROP→CREATE)運用にしている。lineage.dbは「その時点のスナップショット」
-- であり、過去の実行結果を積み上げていく設計ではないため。

DROP TABLE IF EXISTS aliases;
DROP TABLE IF EXISTS columns;
DROP TABLE IF EXISTS excluded_aliases;

CREATE TABLE columns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    table_type TEXT,
    column_name TEXT NOT NULL,
    data_type TEXT,
    -- DD-033: 以下4列はすべてNULL許容。実機Dr.Sumカタログでの取得可否は未確認のため
    -- (doc/decisions.md D-004)、現時点ではデモデータのみ値を持つ
    column_size INTEGER,   -- 精度・桁数(JDBC DatabaseMetaData.getColumns()のCOLUMN_SIZE相当)
    decimal_digits INTEGER, -- スケール(同DECIMAL_DIGITS相当)
    is_nullable TEXT,       -- NULL許可("YES"/"NO"。同IS_NULLABLE相当)
    is_unique TEXT,         -- ユニーク("YES"/"NO"。JDBC標準に対応列が無い独自項目)
    UNIQUE(table_name, column_name)
);

CREATE TABLE aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    column_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    board_name TEXT NOT NULL,
    item_id TEXT,
    -- "alias"(表示名/エイリアスとして使用) or "calc"(カスタム項目・事後計算項目の
    -- 計算式の中で物理カラムが参照されている)
    usage_type TEXT NOT NULL DEFAULT 'alias',
    source_file TEXT,
    FOREIGN KEY (column_id) REFERENCES columns(id),
    UNIQUE(column_id, display_name, board_name, item_id, usage_type)
);

CREATE INDEX idx_aliases_column_id ON aliases(column_id);
CREATE INDEX idx_aliases_display_name ON aliases(display_name);

-- DD-026: ボード定義の`src`属性から所属DB名が分かり、かつ接続中のDBと異なることが
-- 確定しているエイリアス。`columns`/`aliases`には登録せず(無関係なDBのボードを
-- 「不一致」として紛れ込ませないため)、代わりにここへ記録して画面下部にサマリ表示する。
-- `columns`への参照を持たない(物理カラムと照合すらしていない)ため、column_idは使わない
CREATE TABLE excluded_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_db TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    board_name TEXT NOT NULL,
    usage_type TEXT NOT NULL DEFAULT 'alias'
);
