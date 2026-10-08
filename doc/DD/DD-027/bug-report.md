# DD-027 バグ再現レポート

確認日: 2026-10-07
環境: 実機 `C:\MotionBoard64`（`[My Boards]\Dr.SumDomain\Administrator\演習課題\地域別売上.fs-file\fs-snap\snap_00000010_1791276634315`、最新スナップショット）

---

## Bug#001: `支店`列に無関係な`年度`がエイリアスとして記録される

**現象**: `lineage.db`上で`支店`列(`販売実績_練習用`テーブル)に、正規のエイリアス(`支店`)とは別に`年度`という無関係な値がエイリアスとして記録されている(id=19, board=`地域別売上`, item_id=9)。

### 実機XMLでの再現

最新スナップショット(`地域別売上.fs-file`のZIPルート直下、`地域別売上`エントリ＝ボード本体のmcDef定義)に、以下の構造が存在する(集計表/クロス集計パーツの軸設定):

```xml
<ItemOrderChange category="支店" series="年度" summary="売上額">
  <CategoryDisp>
    <Item label="支店" data="支店" selected="true" fid="6"></Item>
  </CategoryDisp>
  <SeriesDisp>
    <Item label="年度" data="年度" selected="true" fid="10000"></Item>
  </SeriesDisp>
  <SummaryDisp invisibleSelectedItems="">
    <Item label="売上額" data="売上額" selected="true" fid="10" visible="true"></Item>
  </SummaryDisp>
</ItemOrderChange>
```

`<ItemOrderChange>`要素は、クロス集計の行軸(`category`)・列軸(`series`)・集計値(`summary`)という**3つの無関係なフィールド参照**を同一要素の属性として持つ。

`board_parser.py`の`walk()`が`category="支店"`を物理カラム名と認識すると、`find_label_on_element()`が同一要素の**他の属性**(`series="年度"`、`summary="売上額"`)からラベル候補を探す。`LABEL_KEY_HINTS`にマッチする属性名が無いため、「日本語を含む最初の属性値」にフォールバックし、属性宣言順で先に現れる`series="年度"`を`支店`のエイリアスとして採用してしまう。

## Bug#002: `支店`列に`true`という値がエイリアスとして記録される

**現象**: 同列に`true`という値もエイリアスとして記録されている(id=20, board=`地域別売上`, item_id=6)。

### 実機XMLでの再現

同じ`<ItemOrderChange>`内の`<CategoryDisp><Item label="支店" data="支店" selected="true" fid="6"></Item></CategoryDisp>`で、`walk()`が`label="支店"`(または`data="支店"`)を物理カラム名と認識する。`find_label_on_element()`が同一要素の他の属性を探すが、`data`/`label`は値が`支店`で一致するため候補から除外され、残るのは`selected="true"`と`fid="6"`のみ。いずれも`LABEL_KEY_HINTS`に一致せず、日本語も含まないため、最終フォールバック(「候補リストの先頭」)で`selected="true"`が採用され、`display_name="true"`という不自然な値が記録される。

---

## 確認結果サマリー

| Bug# | 概要 | 再現 | エビデンス手段 | 備考 |
|------|------|------|--------------|------|
| 001 | `支店`→`年度` | OK | 実機XML(`<ItemOrderChange category="支店" series="年度" .../>`) | DD-023と同根の誤検出クラスだが別タグ(`ItemOrderChange`) |
| 002 | `支店`→`true` | OK | 実機XML(`<Item label="支店" data="支店" selected="true" fid="6">`) | Bug#001と同一要素の子要素が原因 |

## 二重確認: ユーザー提供のボード定義XMLとの一致

2026-10-08、ユーザーから`地域別売上`ボードの`BoardDefinition`全文(XML)が提供された。この独立した取得経路のXMLでも、`dataSetId="9"`(`地域別売上_集計表`)の箇所に以下が含まれており、本レポートの実機確認結果と完全に一致した。

```xml
<DataSet dataSetId="9" dataSetName="地域別売上_集計表">
  ...
  <ItemOrderChange category="支店" series="年度" summary="売上額">
    <CategoryDisp><Item label="支店" data="支店" selected="true" fid="6"></Item></CategoryDisp>
    <SeriesDisp><Item label="年度" data="年度" selected="true" fid="10000"></Item></SeriesDisp>
    <SummaryDisp invisibleSelectedItems=""><Item label="売上額" data="売上額" selected="true" fid="10" visible="true"></Item></SummaryDisp>
  </ItemOrderChange>
```

これにより、原因箇所の特定に誤りがないことを二重に確認できた。

## 付記: 他ボードでも同種のパターンを確認

`lineage.db`には、別ボード`達成率ダッシュボード`(dsDef`月次売上明細`)由来の`価格`列→`true`というレコード(id=111, item_id=9)も存在する。今回確認した`地域別売上`とは別のXMLだが、`selected="true"`のフォールバックという同じ発生パターンである可能性が高い（詳細XMLは未確認。Phase 1の横展開確認で合わせて対応する）。

### 横展開調査の結論(2026-10-08、Phase 1)

上記の疑いをExplore agentで実機確認した結果、**`ItemOrderChange`とは無関係の別バグと判明した**:

- `達成率ダッシュボード`内の`ItemOrderChange`は`category="支店" series="年" summary="目標売上額"`のみで、`価格`列とは無関係
- 真の原因は`dsDef/月次売上明細`内の`<Item id="9" fid="9" title="価格" aliasTitle="" type="NUMBER" disp="true" orderNum="9" ...>`要素。`aliasTitle`が空のため候補から除外された後、**属性キー`disp`自体**が`LABEL_KEY_HINTS`の`"disp"`に部分一致してしまい、本来は表示フラグである属性値`"true"`がラベルとして採用されている
- `達成率ダッシュボード`では`価格`以外のほぼ全列(`会社名`/`地域`/`受注日`/`品名`/`数量`/`氏名`/`売上額`/`支店`等)でも同じ`true`誤抽出が確認されており、同ボードのdsDef(月次売上明細)全体に同一パターンが広く存在する
- DD-023/DD-027と同じ欠陥クラス(無関係な属性をラベルとして拾う)だが、発生箇所(dsDef内`Item`要素自身の属性キー名)・ガードの当て方(タグ配下除外では塞げない)が異なるため、**DD-027のスコープには含めず、別バグとして新規DD起票する**(ユーザー確認済み)

なお、横展開調査時点(2026-10-08)で`達成率ダッシュボード.fs-file`の実機スナップショットを単体で再解析したところ、修正前・修正後いずれのコードでも0件(パースエラー)となった。`C:\MotionBoard64`側でこのボードの定義が調査後に更新され、現在のスナップショットが解析不能な状態になっていると見られる。これはDD-027の修正とは無関係の事象であり、上記の原因特定(XML直接確認によるもの)の正しさには影響しない。新規DD起票時は、別途取得し直したスナップショットで再確認が必要。
