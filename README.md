# キーワードメトリクスバッチAPI

Google Ads検索ボリュームとGoogleトレンドデータを最大200キーワードまで一括取得する高性能バッチAPI。

## 機能

- ✅ 1リクエストで最大200キーワードのバッチ処理
- ✅ Google Ads API統合による月間検索ボリューム取得
- ✅ Google Trends (pytrends)統合によるトレンドスコア取得
- ✅ Redisサポート付き24時間キャッシュ（Pickleへのフォールバック）
- ✅ 日次ローテーション付き包括的なロギング
- ✅ 外部APIの障害に対するサーキットブレーカーパターン
- ✅ 最適なパフォーマンスのための非同期処理
- ✅ ヘルスチェックエンドポイント
- ✅ Raspberry Pi最適化

## 必要要件

- Python 3.9以上
- Raspberry Pi 4 Model B以上
- Google Ads API認証情報
- Redis（オプション、キャッシュ用）

## インストール

1. リポジトリをクローン：
```bash
git clone https://github.com/yourusername/keyword-api.git
cd keyword-api
```

2. 仮想環境を作成：
```bash
python -m venv .venv
source .venv/bin/activate
```

3. 依存関係をインストール：
```bash
pip install -r requirements.txt
```

4. 環境設定：
```bash
cp .env.sample .env
# .envファイルを編集して認証情報を設定
```

5. Google Ads認証情報を設定：
```bash
# ads_client.yamlにGoogle Ads API認証情報を編集
```

## 設定

### 環境変数

| 変数名 | 説明 | デフォルト値 |
|--------|------|-------------|
| GOOGLE_ADS_DEVELOPER_TOKEN | Google Ads開発者トークン | 必須 |
| GOOGLE_ADS_CLIENT_ID | OAuth2クライアントID | 必須 |
| GOOGLE_ADS_CLIENT_SECRET | OAuth2クライアントシークレット | 必須 |
| GOOGLE_ADS_REFRESH_TOKEN | OAuth2リフレッシュトークン | 必須 |
| GOOGLE_ADS_CUSTOMER_ID | Google Ads顧客ID | 必須 |
| REDIS_HOST | Redisサーバーホスト | localhost |
| REDIS_PORT | Redisサーバーポート | 6379 |
| API_HOST | APIバインドアドレス | 127.0.0.1 |
| API_PORT | APIポート | 8000 |
| LOG_LEVEL | ログレベル | INFO |
| CACHE_TTL | キャッシュTTL（秒） | 86400 |

## 使用方法

### APIの起動

```bash
python main.py
```

### APIエンドポイント

#### POST /batch_search_volume
バッチキーワード検索リクエストを処理します。

**リクエスト：**
```json
{
  "keywords": ["keyword1", "keyword2", "..."]
}
```

**レスポンス：**
```json
[
  {
    "keyword": "keyword1",
    "googleAdsAvgMonthlySearches": 1000,
    "googleTrendsScore": 75.5
  },
  {
    "keyword": "keyword2",
    "googleAdsAvgMonthlySearches": 500,
    "googleTrendsScore": 60.0
  }
]
```

#### 方法2: 非同期バッチ検索（429エラー対策・推奨）

大量のキーワードを429エラーを回避しながら処理します。

##### POST /async/batch_search_volume
ジョブを送信します。

**リクエスト：**
```json
{
  "keywords": ["keyword1", "keyword2", "..."]  // 最大200キーワード
}
```

**レスポンス：**
```json
{
  "job_id": "job_1234567890",
  "keywords_count": 200,
  "estimated_time_seconds": 600,
  "message": "ジョブを受け付けました。/async/statusエンドポイントで進捗を確認できます。"
}
```

##### GET /async/status
進捗と結果を確認します。

**パラメーター:**
- `keywords`: 結果を取得したいキーワード（カンマ区切り、オプション）

**レスポンス：**
```json
{
  "job_id": "current",
  "status": "processing",  // "pending", "processing", "completed"
  "pending": 150,
  "processing": 20,
  "completed": 30,
  "failed": 0,
  "results": [  // keywordsパラメーターを指定した場合のみ
    {
      "keyword": "keyword1",
      "googleAdsAvgMonthlySearches": 1000,
      "googleTrendsScore": 75.5
    }
  ]
}
```

#### GET /healthz
ヘルスチェックエンドポイント。

**レスポンス：**
```json
{
  "status": "ok",
  "timestamp": 1719720000
}
```

### 使用例

#### 同期リクエスト（少数のキーワード）
```bash
curl -X POST http://localhost:8000/batch_search_volume \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["pythonプログラミング", "機械学習", "データサイエンス"], "chunk_size": 10}'
```

#### 非同期リクエスト（大量のキーワード）
```bash
# ジョブを送信
curl -X POST http://localhost:8000/async/batch_search_volume \
  -H "Content-Type: application/json" \
  -d @keywords.json  # 200キーワードを含むJSONファイル

# ステータスを確認
curl http://localhost:8000/async/status

# 特定のキーワードの結果を取得
curl "http://localhost:8000/async/status?keywords=python,javascript,rust"
```

## Raspberry Piへのデプロイ

1. systemdサービスファイルをコピー：
```bash
sudo cp keyword_api.service /etc/systemd/system/
```

2. systemdをリロードしてサービスを有効化：
```bash
sudo systemctl daemon-reload
sudo systemctl enable keyword_api
sudo systemctl start keyword_api
```

3. サービスステータスを確認：
```bash
sudo systemctl status keyword_api
```

4. ログを表示：
```bash
sudo journalctl -u keyword_api -f
```

## テスト

テストスイートを実行：
```bash
pytest tests/test_api.py -v
```

カバレッジ付きで実行：
```bash
pytest tests/test_api.py --cov=. --cov-report=html
```

## パフォーマンス

- Raspberry Pi 4で200キーワードを30秒以内で処理
- Google AdsとTrends APIの並行処理
- Redisキャッシュにより最大90%のAPI呼び出しを削減
- サーキットブレーカーによるカスケード障害の防止

## ログ

ログは`./logs`ディレクトリに日次ローテーション付きで保存されます：
- `access.log` - APIアクセスログ
- `error.log` - アプリケーションエラー
- `ads.log` - Google Ads APIログ
- `trends.log` - Googleトレンドログ

## トラブルシューティング

### Google Ads APIの問題
1. `.env`と`ads_client.yaml`の認証情報を確認
2. 顧客IDのフォーマットを確認（ダッシュなし）
3. 開発者トークンが承認されていることを確認

### Googleトレンドのレート制限
- APIには自動レート制限（1リクエスト/秒）が含まれています
- 5回連続失敗後にサーキットブレーカーが作動
- CAPTCHAが検出された場合は5分待機

### キャッシュの問題
- Redis接続失敗時は自動的にPickleファイルキャッシュにフォールバック
- Pickleキャッシュをクリアするには`cache.pkl`を削除
- `redis-cli ping`でRedis接続を確認

## ライセンス

MIT License

## 貢献

1. リポジトリをフォーク
2. 機能ブランチを作成（`git checkout -b feature/amazing-feature`）
3. 変更をコミット（`git commit -m 'Add amazing feature'`）
4. ブランチにプッシュ（`git push origin feature/amazing-feature`）
5. プルリクエストを作成