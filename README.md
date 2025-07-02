# Keyword Metrics Batch API

A high-performance batch API for retrieving Google Ads search volume and Google Trends data for up to 200 keywords per request.

## Features

- ✅ Batch processing of up to 200 keywords per request
- ✅ Google Ads API integration for monthly search volumes
- ✅ Google Trends (pytrends) integration for trend scores
- ✅ 24-hour caching with Redis support (falls back to Pickle)
- ✅ Comprehensive logging with daily rotation
- ✅ Circuit breaker pattern for external API failures
- ✅ Async processing for optimal performance
- ✅ Health check endpoint
- ✅ Raspberry Pi optimized

## Requirements

- Python 3.9+
- Raspberry Pi 4 Model B or higher
- Google Ads API credentials
- Redis (optional, for caching)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/keyword-api.git
cd keyword-api
```

2. Create virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment:
```bash
cp .env.sample .env
# Edit .env with your credentials
```

5. Set up Google Ads credentials:
```bash
# Edit ads_client.yaml with your Google Ads API credentials
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| GOOGLE_ADS_DEVELOPER_TOKEN | Google Ads developer token | Required |
| GOOGLE_ADS_CLIENT_ID | OAuth2 client ID | Required |
| GOOGLE_ADS_CLIENT_SECRET | OAuth2 client secret | Required |
| GOOGLE_ADS_REFRESH_TOKEN | OAuth2 refresh token | Required |
| GOOGLE_ADS_CUSTOMER_ID | Google Ads customer ID | Required |
| REDIS_HOST | Redis server host | localhost |
| REDIS_PORT | Redis server port | 6379 |
| API_HOST | API bind address | 127.0.0.1 |
| API_PORT | API port | 8000 |
| LOG_LEVEL | Logging level | INFO |
| CACHE_TTL | Cache TTL in seconds | 86400 |

## Usage

### Starting the API

```bash
python main.py
```

### API Endpoints

#### POST /batch_search_volume
Process batch keyword search request.

**Request:**
```json
{
  "keywords": ["keyword1", "keyword2", "..."]
}
```

**Response:**
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

#### GET /healthz
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "timestamp": 1719720000
}
```

### Example Usage

```bash
curl -X POST http://localhost:8000/batch_search_volume \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["python programming", "machine learning", "data science"]}'
```

## Deployment on Raspberry Pi

1. Copy the systemd service file:
```bash
sudo cp keyword_api.service /etc/systemd/system/
```

2. Reload systemd and enable the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable keyword_api
sudo systemctl start keyword_api
```

3. Check service status:
```bash
sudo systemctl status keyword_api
```

4. View logs:
```bash
sudo journalctl -u keyword_api -f
```

## Testing

Run the test suite:
```bash
pytest tests/test_api.py -v
```

Run with coverage:
```bash
pytest tests/test_api.py --cov=. --cov-report=html
```

## Performance

- Handles 200 keywords in ≤ 30 seconds on Raspberry Pi 4
- Concurrent processing of Google Ads and Trends APIs
- Redis caching reduces API calls by up to 90%
- Circuit breaker prevents cascade failures

## Logs

Logs are stored in the `./logs` directory with daily rotation:
- `access.log` - API access logs
- `error.log` - Application errors
- `ads.log` - Google Ads API logs
- `trends.log` - Google Trends logs

## Troubleshooting

### Google Ads API Issues
1. Verify credentials in `.env` and `ads_client.yaml`
2. Check customer ID format (no dashes)
3. Ensure developer token is approved

### Google Trends Rate Limiting
- The API includes automatic rate limiting (1 request/second)
- Circuit breaker activates after 5 consecutive failures
- Wait 5 minutes if CAPTCHA is detected

### Cache Issues
- Redis connection failures automatically fall back to Pickle file cache
- Delete `cache.pkl` to clear Pickle cache
- Check Redis connectivity with `redis-cli ping`

## License

MIT License

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request