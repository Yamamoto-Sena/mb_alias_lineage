# DD-002-3: MotionBoard解析精度向上

| 作成日 | 更新日 | ステータス | 補足 |
|--------|--------|-----------|------|
| 2026-09-30 | 2026-09-30 | 完了 | 親: DD-002。実物ボードで検証済み。pytest 124件パス |

> アプローチ: 標準（探索的実装。精度調整はサンプルデータではなく実物MB定義ファイルでの
  誤検出/検出漏れ確認が前提のため、DD-002-2同様TDDでは進めない）
> リスク: なし（db_schema.sqlは無変更想定。外部システムへの接続・認可・機密情報の送信を
  伴わないローカルファイル解析。ただし実物MB定義ファイルに顧客の業務データが含まれる
  可能性があるため、取り扱いは本DDのスコープ内でのみ行い外部送信しない）

## 目的

`board_parser.py`の自動検出モード（ヒューリスティックによるカラム名/表示名抽出）を、
実物のMotionBoardボード定義ファイルに対して検証し、誤検出・検出漏れがあれば
`LABEL_KEY_HINTS`/`FORMULA_KEY_HINTS`等のヒント調整、または新規パターン対応によって
精度を向上させる。DD-002-1で確定した判定基準（表記ゆれ5分類）が正しく機能する前提となる
「MB側から取得するデータの正確さ」を担保する。

## 背景・課題

- `board_parser.py`は`sample_data/motionboard_backup/`の合成テストケース（1対多・多対1・
  ZIP内エントリ・SJISエンコード等14パターン）でのみ検証されており、実物のMotionBoard
  ボード定義ファイルでは未検証（README.md「現時点で調整が必要な箇所」に明記済み）。
- 実物ファイルでは、タグ名・属性名の命名傾向（`LABEL_KEY_HINTS`/`ID_KEY_HINTS`/
  `NAME_KEY_HINTS`で拾いきれない独自命名）や、計算式の書き方（`FORMULA_KEY_HINTS`/
  `_FORMULA_OPERATOR_RE`が想定しない記法）が合成テストケースと乖離している可能性がある。
- DD-002本体の決定事項により、本DD起票時点でDD-002-1の判定基準（表記ゆれ5分類・
  ホワイトリスト粒度・類似度方式）に照らし、MB側でどこまでのデータ範囲を取得対象とするか
  （データソース定義エイリアスまで追跡するか等）を確認する必要がある。

## 検討内容

### DD-002-1判定基準に照らした範囲確認

- DD-002-1で確定した5分類（1対多・多対1・物理名直接使用・孤立項目・類似度候補）は
  いずれも「物理カラム→表示名→ボード名/アイテムID」の`AliasRecord`単位で成立する。
  `board_parser.py`が対象とすべきなのは、この`AliasRecord`を正しく生成できることに
  限定されるため、判定基準（分類ロジック）自体への影響はなく、範囲は「既存の
  自動検出モードが対象とするXML/JSON/ZIP形式のボード定義ファイル」で変更しない。
- MotionBoardの「データソース定義」（ボード本体とは別に、接続先テーブル/ビューの
  エイリアスを定義するファイル）まで追跡対象を広げるかは、実物ファイルの構成を
  確認した上で判断する（Phase 1で確認）。

### 実物ファイルの構造確認（2026-09-30、`C:\MotionBoard64`実機確認）

- ユーザー環境のMotionBoardサーバー本体（`C:\MotionBoard64`）を直接確認。ボード本体は
  `data/mb/mbds_def/mbDef/[My Boards]/<ドメイン>/<ユーザー>/<ボードフォルダ>/<ボード名>.fs-file/`
  という内部コンテンツストア形式で、実体は`fs-snap/snap_*`配下の**最新版ZIPファイル**
  （`fs-manifest.xml` + ボード本体XML + `fs-xcabinets/0`）。`fs-xcabinets/0`はさらに
  **入れ子ZIP**で、その中の`mbds_def/dsDef/<データソース名>`にデータソース定義XML、
  `mbds_def/mcDef/<チャート名>`にチャート定義XMLが格納されている（ZIP内ファイル名は
  Shift_JISでエンコードされておりPython`zipfile`の既定cp437デコードでは文字化けするため、
  読み取り時は`info.filename.encode("cp437").decode("shift_jis")`等の再デコードが必要）。
- 実際のDr.Sum接続ボード（`Test1_EC_SALES`、データソース名「新規データソース」）を解析した
  結果、`board_parser.py`が前提とする「1要素に`column`/`label`等の意味のある属性名が
  同居する」構造とは全く異なり、**汎用`<Property name="キー" value="値">`（またはItemの
  フラット属性列）でキー/値ペアを表現する**設計であることが判明:
  ```xml
  <DataSource name="新規データソース" type="drsum" comId="Dr.Sum"
              src="Test/T_EC_CUSTOMER" srcName="T_EC_CUSTOMER" version="4.0.1">
    <Layout>
      <Field>
        <Item id="1" fid="1" title="order_id" aliasTitle="" type="NUMBER" .../>
        <Item id="3" fid="3" title="customer_name" aliasTitle="" type="VARCHAR" .../>
        ...
      </Field>
      <ExField>
        <Item id="1" fid="10000" title="注文年月" aliasTitle="" exType="DATE_GROUPING" ...>
          <DateGroups targetItemFid="2" format="yyyy/MM" .../>
        </Item>
      </ExField>
      <Category><Item fid="4" aliasTitle="" disp="true"/></Category>
      <Series><Item fid="9" aliasTitle="" disp="true"/></Series>
      <Summary><Item fid="8" sumType="SUM_ALL" aliasTitle="" disp="true"/></Summary>
    </Layout>
  </DataSource>
  ```
  - `srcName`属性が物理テーブル名そのもの（`T_EC_CUSTOMER`）を正確に示す。現行の
    `ColumnIndex.resolve_table`によるテーブル名の推測は本形式では不要（`srcName`を
    直接使えば曖昧性なく確定できる）。
  - 物理カラム（`<Field><Item>`）は`title`＝物理カラム名（Dr.Sumの実カラム名と完全一致）、
    `aliasTitle`＝ユーザーが表示名を上書きした場合のみ非空文字列。本ボードでは9カラム
    すべて`aliasTitle=""`（=物理名をそのまま使用＝DD-002-1の「物理名直接使用」パターン）。
  - 計算項目（`<ExField><Item>`）は`title`が計算結果の表示名（例:「注文年月」）で、
    元カラムへの参照は文字列埋め込みの計算式ではなく**`fid`（フィールドID）による
    構造的参照**（`DateGroups targetItemFid="2"` → `fid=2`の`order_date`を参照）。
    既存の`FORMULA_KEY_HINTS`/`_find_columns_in_formula`（値の中に物理カラム名の
    部分文字列を探す方式）はこの参照方式を検出できない。
- **現行`board_parser.py`を実際にこのフォルダに対して実行した結果**
  （`python board_parser.py <実物フォルダ> --columns dr_sum_columns.json --out board_aliases.json`）:
  - 9物理カラムすべてが「マッチ」はしたが、`display_name`が**すべて`"true"`という
    誤った値**になった。原因: `_extract_match`が`title="order_id"`等の属性値でカラム名
    一致を検出した後、`find_label_on_element`が同じ`<Item>`要素の**他の属性の中から
    先頭にある文字列**（`disp="true"`)をラベル候補としてフォールバック採用してしまうため
    （日本語を含む属性が無く、`_looks_like_label_key`にも一致する属性名が無いケース）。
  - 計算項目「注文年月」（`ExField`）は**1件も検出されなかった**（`fid`参照方式のため）。
  - `BoardDefinition`本体（`Test1_EC_SALES`）・チャート定義（`mcDef/*`）からは0件
    （これらは`Property`のvalueに直接カラム名が入らず、`Layout`側の`fid`を介した
    間接参照のみのため、現行ロジックでは原理的に検出不可）。
  - 上記は誤検出（`display_name="true"`）と検出漏れ（ExField計算項目・チャート内表示名）
    の両方が実際に確認できた具体例であり、本DDの目的（精度向上）に合致する。
- 2つ目の実ボード（「店舗別・担当者別 目標管理」フォルダ、複数`.fs-file`）でも同一の
  `<DataSource type="drsum" src=... srcName="T_STORE_KPI">`形式を確認。同一データソースの
  店舗別サブセット（`T_STORE_KPI_名古屋店`等）が複数存在するが、いずれも`srcName`は
  基底テーブル名で共通しており、命名パターンに再現性があることを確認した。

## 決定事項

- **Phase 2の実装方針（2026-09-30、ユーザー確認済み）**: 既存の汎用ヒューリスティック
  （`LABEL_KEY_HINTS`等の属性名調整）では対応できないため、MotionBoardの
  `<DataSource type="drsum">`専用の抽出関数（`_parse_drsum_datasource`）を新設した。
  - ルート要素が`DataSource`かつ`type="drsum"`の場合のみ専用パスへ分岐する
    （既存の汎用自動検出はサンプルデータ等の他形式向けにそのまま温存し、後方互換を保つ）。
  - `table_name`は`srcName`属性から直接取得する（`ColumnIndex.resolve_table`による
    推測は本形式では使わない）。
  - `<Field><Item title=X aliasTitle=Y>`: `display_name`は`Y`が非空なら`Y`、空なら`X`
    自身とする（物理名直接使用のケースを`find_unaliased_columns`側の既存ロジックへ
    自然に流し込める。新規の分類ロジックは追加していない）。
  - `<ExField><Item fid=Z title=W>`: ユーザー確認の結果、**`fid`を解決して元カラムに
    紐付ける**方針を採用（`_exfield_target_fids`で`DateGroups`等の子要素が持つ
    `targetItemFid`属性を収集し、同一データソース内の`<Field>`から逆引きする）。
    `targetItemFid="0"`は「未設定」を表す値のため対象外とする。解決できない計算項目は
    記録しない（既知の制約。`find_orphan_columns`は計算項目自体を対象にしないため
    孤立項目判定への影響はない）。
  - `Category`/`Series`/`Summary`内の`fid`参照＋チャート表示時の個別`aliasTitle`上書きは
    **本DDのスコープ外**とした（`<Field>`/`<ExField>`側の`aliasTitle`で基本的な表示名は
    捕捉できるため。チャート単位の個別上書きは追跡されない既知の制約として残す。
    必要になれば別DDで扱う）。
  - MotionBoardサーバーの内部コンテンツストア（`<ボード名>.fs-file/fs-snap/snap_*`、
    UTF-8フラグなしの入れ子ZIP、拡張子のないエントリ）を`board_parser.py`が直接走査
    できるよう、`_parse_zip_bytes`（再帰対応・内容スニッフィング）と
    `_latest_snapshot`（最新スナップショットの選択）を追加した。これが無いと
    `auto_parse_all`の`rglob("*.xml"/"*.json"/"*.zip")`が実機のボード定義を一件も
    発見できず、専用抽出ロジック自体が実行されないため、精度向上の実効性を担保する
    上で必須と判断した。
  - 上記の設計変更は`board_parser.py`への新規関数追加であり、既存の合成テストケース
    （`sample_data/motionboard_backup/`）の検出結果には影響しない（ルート要素判定で
    分岐するため）。実際に`pytest tests/test_board_parser.py`で回帰がないことを確認済み。

## 受け入れ基準

| # | 基準（操作 → 期待結果） | 検証方法 |
|---|------------------------|---------|
| 1 | 実物MB定義ファイル一式の構造（タグ/属性/キー名の傾向）を確認 → 本DDの検討内容に反映される | Phase 1（ユーザー提供ファイルの目視確認） |
| 2 | `python board_parser.py <実物フォルダ> --columns dr_sum_columns.json --out board_aliases.json`を実行 → 既知の正しいエイリアス対応と比較し、誤検出/検出漏れの件数を確認できる | Phase 1（ユーザーによる実行結果の目視確認） |
| 3 | Phase 1で判明した誤検出/検出漏れパターンに対し、ヒント調整または新規パターン対応を実施 → 同じ実物ファイルで再実行した際に改善が確認できる | Phase 2（再実行結果の比較） |
| 4 | 既存の合成テストケース（`sample_data/motionboard_backup/`）に対する検出結果に回帰がない | `pytest tests/test_board_parser.py` |
| 5 | 既存の全機能に回帰がない | `pytest`（全件） |

## タスク一覧

### Phase 1: 実物MB定義ファイルでの精度確認（ユーザー依頼）
- [x] ユーザーに実物のMotionBoardボード定義ファイルの提供を依頼する
      （回答: `C:\MotionBoard64`〔実機サーバー本体〕を自由に参照してよいとの許可を得た）
- [x] 提供されたファイルの形式（内部コンテンツストア＋入れ子ZIP＋`DataSource`/`Field`/
      `ExField`のXML構造）を確認し、本DDの「検討内容」に反映する
- [x] `python board_parser.py <実物フォルダ> --columns dr_sum_columns.json --out board_aliases.json`
      を実行し、誤検出（`display_name="true"`）・検出漏れ（`ExField`計算項目・チャート内
      表示名）を確認した
- [x] 🔬 機械検証の代わりに人的確認: 誤検出/検出漏れの内容を本DDの「検討内容」
      「決定事項」に反映済み。Phase 2の実装方針（案）は記載したが、着手前にユーザーへの
      確認が必要と判断したため、ステータスは「確認待ち」のまま維持する

### Phase 2: DataSource専用抽出ロジックの実装
- [x] `board_parser.py`に`_parse_drsum_datasource`（`DataSource type="drsum"`専用の抽出）
      と`_exfield_target_fids`（ExFieldのfid解決）を追加。`auto_parse_xml`のルート要素が
      `DataSource`かつ`type="drsum"`の場合に専用パスへ分岐するよう変更
- [x] `board_parser.py`に`_decode_zip_entry_name`（cp437文字化け対策）・`_parse_zip_bytes`
      （入れ子ZIP再帰・拡張子なしエントリの内容スニッフィング）・`_latest_snapshot`
      （`.fs-file/fs-snap`の最新版選択）を追加し、`auto_parse_all`が
      MotionBoard内部コンテンツストアを直接走査できるようにした
- [x] `tests/test_board_parser.py`に実物ファイルの構造を模した合成テストケースを追加
      （実ファイル自体はコミットしていない。列名・ボード名は架空のものに置き換えた
      最小限のXML文字列をテスト内に直接記述）: `TestDrSumDataSourceFormat`
      （table_name解決・aliasTitle有無・ExField解決・解決不可の除外・非drsumのフォール
      バック）、`TestNestedZipAndFsFileDiscovery`（入れ子ZIP・拡張子なし検出・
      fs-file/fs-snap発見・スナップショット無しでもクラッシュしない）
- [x] 🔬 機械検証: `pytest tests/test_board_parser.py` → 53 passed
- [x] 実物フォルダ（`C:\MotionBoard64\...\EC売上`）に対して直接
      `python board_parser.py <実物フォルダ> --columns dr_sum_columns.json --out ...`
      を再実行し改善を確認: ①`display_name="true"`の誤検出が解消（物理名直接使用の
      9カラムすべて正しい`display_name`〔物理名自身〕になった）、②計算項目「注文年月」
      が`ORDER_DATE`に紐づく`usage_type=calc`レコードとして正しく検出された、
      ③未検出だった2つ目のボード（`Test2_EC_SALES`、データソース5種）も含め
      計60件のエイリアスレコードが生成された（フォルダを直接指定するだけで、
      内部コンテンツストアの入れ子ZIPを手動展開する必要がなくなった）

### 完了前チェック
- [x] 受け入れ基準を1項目ずつ照合
      1. 実物ファイル構造 → 検討内容に反映済み
      2. 誤検出/検出漏れの確認 → `display_name="true"`・ExField未検出を確認済み
      3. 改善確認 → 実物フォルダ再実行で両方の問題が解消したことを確認済み
      4. 合成テストケースへの回帰なし → `pytest tests/test_board_parser.py` 53 passed
      5. 全体回帰なし → `pytest`（全件）124 passed
      全5件達成
- [x] 😈 セルフレビュー1巡: (1) `title`が空でも`aliasTitle`が設定されている異常系は
      レコードを生成しない実装だが、実運用でこのパターンが起きる可能性は低いと判断し
      対応を見送った（既知の制約）。(2) `_exfield_target_fids`は`targetItemFid="0"`を
      一律「未設定」として除外しているが、MotionBoard側の仕様上fid=0が実在する項目を
      指す可能性はゼロではない（実機データでは0=未設定という解釈で一貫していた）。
      (3) `.fs-file`の`rglob`はディレクトリツリー全体を走査するため、
      `C:\MotionBoard64`のようなサーバー全体（ログ・GISデータ等含む数十万ファイル）に
      直接向けると探索コストが大きい。実運用では`mbDef/[My Boards]/...`配下の
      特定ボードフォルダを指定する運用を想定し、パフォーマンス最適化は本DDのスコープ外
      とした（必要になれば別DDで扱う）
- [x] 🔬 全回帰1回: `pytest` → 124 passed

## ログ

### 2026-09-30
- DD作成。DD-002が定義する着手順②（DD-002-1の判定基準に照らした要件範囲確認）として
  起票。DD-002-2（Dr.Sum実環境対応）が完了し前提条件が整ったため着手
- 精度検証には実物のMotionBoardボード定義ファイルが必須だが、現状は
  `sample_data/motionboard_backup/`の合成テストケースしかなく、README.mdの
  「現時点で調整が必要な箇所」にも実ファイルでの調整が必要と明記されている。
  そのためステータスを「確認待ち」とし、実物MB定義ファイルの提供をユーザーに依頼
- ユーザーから`C:\MotionBoard64`（実機サーバー本体）を自由に参照してよいとの許可を得たため
  Phase 1に着手。ボード本体は内部コンテンツストア形式（`fs-file`/`fs-snap`/入れ子ZIP）で
  あることが判明し、Python`zipfile`のデフォルトcp437デコードによるファイル名文字化けに
  対応しつつ中身を取り出す調査スクリプトを作成して構造を解析した
- 実ボード「Test1_EC_SALES」（データソース: Dr.Sum `T_EC_CUSTOMER`）を解析し、
  `<DataSource type="drsum" srcName="...">`配下の`<Field>`（物理カラム、`title`/`aliasTitle`）
  ・`<ExField>`（計算項目、`fid`による構造参照）という、`board_parser.py`が全く想定して
  いない構造であることを確認
- 現行`board_parser.py`を実際にこのボードに対して実行し、9カラム全件で`display_name`が
  誤った値`"true"`になる誤検出と、計算項目「注文年月」が1件も検出されない検出漏れを
  具体的に確認（`disp="true"`属性がラベル候補としてフォールバック採用されてしまうことが
  誤検出の原因）
- 2つ目の実ボード群（「店舗別・担当者別 目標管理」、データソース`T_STORE_KPI`）でも
  同一の`<DataSource type="drsum">`構造を確認し、パターンの再現性を確認した
- 上記知見をもとにPhase 2の実装方針（`DataSource`専用の抽出関数を新設、`srcName`で
  テーブル名を直接取得、`aliasTitle`の有無で表示名を決定）を「決定事項」に**案として**
  記載。ただし既存の汎用ヒューリスティックとは別の専用パスを新設する設計変更であり、
  計算項目（ExField）の扱い・チャート個別上書きのスコープ判断が残っているため、
  実装着手前にユーザーへ方針を確認する（ステータスは「確認待ち」で維持）
- ユーザーに実装方針を確認: (1)`DataSource`専用の抽出ロジックを新設する方針で進めてよい
  →「進めてよい」、(2)`ExField`計算項目のfid参照を解決して元カラムまで紐付けるか
  →「解決して紐付ける」で確定。Category/Series/Summaryのチャート個別上書きは
  スコープ外とすることを自己判断で決定（決定事項に明記）
- Phase 2実装: `board_parser.py`に`_parse_drsum_datasource`・`_exfield_target_fids`
  （DataSource専用抽出）、`_decode_zip_entry_name`・`_parse_zip_bytes`・`_latest_snapshot`
  （内部コンテンツストアの入れ子ZIP・拡張子なしエントリ対応）を追加。
  `tests/test_board_parser.py`に架空データによる合成テスト12件を追加し
  `pytest tests/test_board_parser.py` → 53 passed を確認
- 実フォルダ（`C:\MotionBoard64\...\EC売上`）に対して`board_parser.py`を再実行し、
  誤検出（`display_name="true"`）の解消・計算項目「注文年月」の正しい検出
  （`ORDER_DATE`にusage_type=calcで紐付け）・内部ストアを直接指定するだけで
  2ボード分計60件のレコードが生成されることを確認。事前に手動でZIPを展開する
  必要がなくなった
- 🔬 全回帰: `pytest`（全件）→ 124 passed。既存機能への回帰なしを確認
- 受け入れ基準5件を全て照合し達成を確認。セルフレビュー実施（title空+aliasTitle設定の
  異常系、targetItemFid=0の解釈、.fs-fileのrglob探索コストを既知の制約として記録）
- ステータスを「完了」に更新。実ファイル自体（`C:\MotionBoard64`配下の内容）は
  一切コミットしていない（分析はOSの一時ディレクトリ上でのみ実施し、テストは架空データ
  で作成した）
