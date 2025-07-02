
# Keyword Metrics Batch API 要件定義書  
**Version 1.0 – 2025‑06‑30**  

---

## 1. 概要  
- **目的**: Google Ads API と Google Trends (pytrends) を使用し、最大 200 キーワードを一括で送信すると平均月間検索数と Trends スコアを JSON で返すバッチ API を構築する。  
- **利用者**: システム開発者本人のみ。記事生成ワークフロー内で CLI または別スクリプトから呼び出す。  
- **運用環境**: Raspberry Pi 4 Model B 以上、Raspberry Pi OS (64‑bit)。ローカルネットワーク内専用。  

---

## 2. スコープ  
| # | 項目 | 含む / 含まない |
|---|------|----------------|
| S1 | キーワード一括検索 API (POST `/batch_search_volume`) | 含む |
| S2 | 取得結果の JSON 返却 | 含む |
| S3 | 結果キャッシュ (24h) | 含む |
| S4 | ログ出力 (詳細 & ローテート) | 含む |
| S5 | 外部公開 (HTTPS) | **含まない**<br>※将来 Cloudflare Tunnel 等で拡張可 |
| S6 | UI フロントエンド | 含まない |

---

## 3. 用語  
| 用語 | 定義 |
|------|------|
| **Ads API** | Google Ads API `GenerateKeywordHistoricalMetrics` エンドポイント |
| **Trends API** | pytrends ライブラリ (`interest_over_time`) |
| **バッチ** | 1 リクエストに含まれる 1〜200 キーワード |

---

## 4. 施設・品質要件  

### 4.1 機能要件 (FR)  
| ID | 要件 | 詳細 |
|----|------|------|
| **FR‑01** | 最大 200 キーワードを受信 | `keywords: List[str]` |
| **FR‑02** | Ads 検索数取得 | バルク 1 回で 200 語取得可 |
| **FR‑03** | Trends スコア取得 | 各キーワード個別取得、非同期制御 |
| **FR‑04** | JSON で一括返却 | `<keyword, adsVolume, trendsScore>` 配列 |
| **FR‑05** | 24h 有効キャッシュ | Redis (推奨) / Pickle ファイル |
| **FR‑06** | `/healthz` エンドポイント | 稼働確認 (200 OK) |

### 4.2 非機能要件 (NFR)  
| ID | 区分 | 要件 |
|----|------|------|
| **NFR‑01** | 性能 | 200 キーワードで ≤ 30 s (@Raspberry Pi 4) |
| **NFR‑02** | 障害耐性 | 無限ループ・無限リトライ禁止。最大 3 回リトライ＋指数バックオフ。 |
| **NFR‑03** | ログ | `access.log`, `error.log`, `ads.log`, `trends.log` を日次ローテート。 |
| **NFR‑04** | セキュリティ | ローカル IP のみバインド (`127.0.0.1`)。認証不要。 |
| **NFR‑05** | 保守性 | 100% type‑hint, docstring, pylint score ≥ 8.0 |
| **NFR‑06** | コスト | 電気代のみ。外部 API は無料枠内。 |

---

## 5. システム構成  

```
┌────────────┐  POST /batch_search_volume
│ キーワード取得 │────┐
└────────────┘    │
                  ▼
          ┌──────────────────────┐
          │ FastAPI (uvicorn)    │
          │  ├─ ads.py           │─▶ Google Ads API
          │  ├─ trends.py        │─▶ Google (pytrends)
          │  ├─ cache.py (Redis) │
          │  └─ logger.py        │
          └──────────────────────┘
```

---

## 6. ルート直下フォルダ構成  

```
/keyword-api/
├─ ads_client.yaml         # Google Ads 認証設定
├─ .env                    # 環境変数
├─ main.py                 # FastAPI Entrypoint
├─ ads.py                  # Ads API ラッパ
├─ trends.py               # Trends ラッパ
├─ cache.py                # キャッシュ層 (Redis/Pickle)
├─ logger.py               # ロガー設定
├─ api_routes.py           # ルーター定義
├─ requirements.txt
├─ README.md
└─ tests/
   └─ test_api.py
```

> ※ すべて **ルート直下** に配置し、サブディレクトリは `tests/` のみ。

---

## 7. モジュール詳細  

### 7.1 `ads.py`  
- `get_bulk_metrics(keywords: list[str]) -> dict[str, int]`  
- 自動リトライ: 最大 3 回、`backoff_factor = 2`, `jitter ±0.2s`  
- 失敗時は `None` を格納し API レスポンスへも反映。

### 7.2 `trends.py`  
- 非同期 I/O (`httpx.AsyncClient`) + `asyncio.Semaphore(10)`  
- 1 リクエスト毎に `await asyncio.sleep(1)` でレート制御。  
- CAPTCHA 検知時は即中断し `TrendQuotaExceededError` を raise。  

### 7.3 `cache.py`  
- 優先: Redis。未導入時は `pickle` ファイル (FIFO 3000 件)。  
- TTL 86,400 秒。ヒット時は外部 API 呼び出し無し。  

### 7.4 `logger.py`  
- Python `logging` + `TimedRotatingFileHandler`.  
- フォーマット: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`  
- レベル: INFO (access), WARNING (ads/trends), ERROR (全体)。  

---

## 8. API 仕様  

### 8.1 POST `/batch_search_volume`

| 項目 | 内容 |
|------|------|
| **Headers** | `Content-Type: application/json` |
| **Request Body** | `{ "keywords": ["kw1", "kw2", ...] }` |
| **200 Response** | `[ { "keyword": "kw1", "googleAdsAvgMonthlySearches": 123, "googleTrendsScore": 45 }, ... ]` |
| **4xx** | 不正リクエスト (`keywords` 不備) |
| **5xx** | 外部 API 失敗／内部例外 |

### 8.2 GET `/healthz`

| Field | Detail |
|-------|--------|
| 200 OK | `{ "status": "ok", "timestamp": 1719720000 }` |

---

## 9. ログ仕様  

| ログファイル | 内容 | ローテーション |
|--------------|------|----------------|
| `access.log` | リクエストメタ (IP, path, status, latency) | 1 日 |
| `error.log`  | スタックトレース | 1 日 |
| `ads.log`    | Ads API 呼び出し結果 & 失敗詳細 | 1 日 |
| `trends.log` | pytrends 呼び出し結果 & CAPTCHA 検知 | 1 日 |

---

## 10. エラー & 冗長制御  

| 仕組み | 内容 |
|--------|------|
| **Circuit Breaker** | `consecutive_failures >= 5` で 5 分間 API 呼び出し停止 |
| **Retry Limiter**   | 各外部 API 最大 3 回。合計処理時間上限 60 s。 |
| **Global Timeout**  | `/batch_search_volume` トータル 90 s で打ち切り |
| **Watchdog**        | systemd `Restart=on-failure` & `StartLimitBurst=3/5min` |

---

## 11. デプロイフロー (Raspberry Pi)  

```bash
git clone https://example.com/keyword-api.git
cd keyword-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env        # 値を編集
sudo cp keyword_api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable keyword_api
sudo systemctl start keyword_api
```

---

## 12. テスト  

- **Unit**: `pytest` で 95% カバレッジ  
- **Integration**: モックで Ads/Trends を置換し 200 語テスト  
- **Load**: `locust` で RPS 1, 同時 5 ユーザーを 5 分  

---

## 13. 変更履歴  

| Date | Ver | Author | Description |
|------|-----|--------|-------------|
| 2025‑06‑30 | 1.0 | プロジェクト担当 | 初版 |

---

## 14. 参考  

- Google Ads API Developer Guide (v18)  
- pytrends GitHub 4.10.0  
- FastAPI 0.111.0 ドキュメント  
