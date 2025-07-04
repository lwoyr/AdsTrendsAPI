# Google Ads API 検索ボリュームメトリクス ドキュメント

## 概要
このドキュメントは、AdsTrendsAPIプロジェクトで実装されているGoogle Ads APIで利用可能な検索ボリューム関連のパラメータとメトリクスの包括的な概要を提供します。

## 1. KeywordPlanHistoricalMetrics オブジェクト構造

`KeywordPlanHistoricalMetrics`オブジェクトは、過去の検索ボリュームデータの主要なコンテナです。以下を含みます：

### 主要な検索ボリュームフィールド：
- **avg_monthly_searches** (int, オプション)
  - 過去12ヶ月間の平均月間検索数の概算値
  - 現在の実装で使用されている主要メトリクス

- **monthly_search_volumes** (MonthlySearchVolume の配列)
  - 過去12ヶ月の月別詳細検索ボリュームデータ
  - 詳細な履歴データを提供

### 追加メトリクス：
- **competition** (KeywordPlanCompetitionLevel 列挙型)
  - クエリの競争レベル（LOW、MEDIUM、HIGH、UNSPECIFIED、UNKNOWN）

- **competition_index** (int, オプション)
  - 競争指数 [0, 100] の範囲
  - キーワードの広告配置の競争力を示す
  - 計算式：（埋められた広告枠 / 利用可能な総広告枠）× 100

- **low_top_of_page_bid_micros** (int, オプション)
  - ページ上部表示の入札単価の下限（20パーセンタイル）（マイクロ単位）

- **high_top_of_page_bid_micros** (int, オプション)
  - ページ上部表示の入札単価の上限（80パーセンタイル）（マイクロ単位）

- **average_cpc_micros** (int, オプション)
  - キーワードの平均クリック単価（マイクロ単位）

## 2. MonthlySearchVolume 配列構造

各 `MonthlySearchVolume` オブジェクトは以下を含みます：
- **year** (int, オプション)
  - 検索ボリュームの年（例：2025）

- **month** (MonthOfYear 列挙型)
  - 検索ボリュームの月（JANUARY から DECEMBER）

- **monthly_searches** (int, オプション)
  - その特定の月の概算検索数
  - null値は、その月の検索ボリュームが利用できないことを示す

## 3. APIリクエストパラメータ

### GenerateKeywordHistoricalMetricsRequest パラメータ：
- **customer_id** (文字列, 必須)
  - Google Ads 顧客ID

- **keywords** (文字列の配列, 必須)
  - 履歴メトリクスを取得するキーワードのリスト
  - リクエストあたり最大10,000キーワード
  - ほぼ重複するものは自動的に重複排除される

- **language** (文字列, オプション)
  - ターゲットとする言語のリソース名
  - 形式：「languageConstants/XXXX」
  - 設定されていない場合、すべてのキーワードが含まれる

- **geo_target_constants** (文字列の配列)
  - ターゲットとする地域のリソース名
  - 形式：「geoTargetConstants/XXXX」
  - 最大10地域
  - 空のリストはすべての地域をターゲットとする

- **keyword_plan_network** (列挙型, オプション)
  - GOOGLE_SEARCH
  - GOOGLE_SEARCH_AND_PARTNERS（設定されていない場合のデフォルト）

- **include_adult_keywords** (ブール値)
  - デフォルト：false

- **aggregate_metrics** (KeywordPlanAggregateMetrics)
  - 取得する集計メトリクスを指定（例：デバイス別の内訳）

- **historical_metrics_options** (HistoricalMetricsOptions)
  - 履歴データ取得をカスタマイズするオプション

## 4. HistoricalMetricsOptions

履歴データのカスタマイズを可能にします：
- **year_month_range** (YearMonthRange, オプション)
  - 履歴メトリクスのカスタム日付範囲を指定
  - 指定されていない場合、過去12ヶ月を返す
  - 検索メトリクスは過去4年間利用可能

- **include_average_cpc** (ブール値)
  - 平均CPCデータを含めるかどうか
  - レガシーサポートのために提供

## 5. 現在の実装詳細

現在の実装（`ads.py`）では以下を使用：
```python
# 基本的な使用法
request.customer_id = self.customer_id
request.keywords.extend(keywords)
request.language = "languageConstants/1000"  # 英語
request.geo_target_constants.append("geoTargetConstants/2840")  # アメリカ

# 現在抽出されているのは：
metric.avg_monthly_searches  # 使用されている主要メトリクス
```

## 6. 潜在的な機能拡張

APIは現在利用されていない追加データを提供します：
1. **月別内訳**：トレンド分析のための`monthly_search_volumes`配列へのアクセス
2. **競争メトリクス**：キーワード難易度評価のための競争レベルと指数
3. **入札見積もり**：予算計画のためのページ上部入札範囲
4. **カスタム日付範囲**：特定期間の履歴データ
5. **地理的バリエーション**：地域分析のための複数の地域ターゲット
6. **ネットワークターゲティング**：検索と検索パートナーの個別メトリクス
7. **デバイス別内訳**：デバイスタイプ別の検索ボリューム（aggregate_metrics経由）

## 7. レスポンス構造

```python
# レスポンス構造
response.results[i].keyword_metrics:
  - avg_monthly_searches: int
  - monthly_search_volumes: [
      {
        year: int,
        month: MonthOfYear,
        monthly_searches: int
      },
      ...
    ]
  - competition: CompetitionLevel
  - competition_index: int
  - low_top_of_page_bid_micros: int
  - high_top_of_page_bid_micros: int
  - average_cpc_micros: int
```

## 8. 言語と地域の定数

よく使用される定数：
- 言語：「languageConstants/1000」（英語）
- 地域：「geoTargetConstants/2840」（アメリカ合衆国）

その他の言語や地域については、Google Ads APIドキュメントで定数IDを参照してください。