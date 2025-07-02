"""キーワードメトリクスバッチAPIのテストスイート。"""
import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


@pytest.fixture
def client():
    """テストクライアントを作成。"""
    return TestClient(app)


class TestHealthEndpoint:
    """ヘルスチェックエンドポイントのテストケース。"""
    
    def test_health_check(self, client):
        """ヘルスチェックがOKを返すことをテスト。"""
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestBatchSearchVolume:
    """バッチ検索ボリュームエンドポイントのテストケース。"""
    
    def test_empty_keywords_list(self, client):
        """空のキーワードリストが422を返すことをテスト。"""
        response = client.post(
            "/batch_search_volume",
            json={"keywords": []}
        )
        assert response.status_code == 422
    
    def test_too_many_keywords(self, client):
        """200個以上のキーワードが422を返すことをテスト。"""
        keywords = [f"keyword{i}" for i in range(201)]
        response = client.post(
            "/batch_search_volume",
            json={"keywords": keywords}
        )
        assert response.status_code == 422
    
    def test_duplicate_keywords_removed(self, client):
        """重複キーワードが処理されることをテスト。"""
        with patch('api_routes.cache_manager.get_batch_data') as mock_cache:
            mock_cache.return_value = ({}, ["test", "unique"])
            
            with patch('api_routes.ads_manager.get_bulk_metrics') as mock_ads:
                mock_ads.return_value = {"test": 100, "unique": 200}
                
                with patch('api_routes.trends_manager.get_bulk_trends') as mock_trends:
                    async def mock_get_trends(keywords):
                        return {"test": 50.0, "unique": 75.0}
                    mock_trends.side_effect = mock_get_trends
                    
                    response = client.post(
                        "/batch_search_volume",
                        json={"keywords": ["test", "test", "unique"]}
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data) == 2
    
    @patch('api_routes.cache_manager.get_batch_data')
    @patch('api_routes.cache_manager.set_keyword_data')
    @patch('api_routes.ads_manager.get_bulk_metrics')
    @patch('api_routes.trends_manager.get_bulk_trends')
    def test_successful_batch_request(
        self,
        mock_trends,
        mock_ads,
        mock_set_cache,
        mock_get_cache,
        client
    ):
        """モックAPIを使用した成功バッチリクエストをテスト。"""
        mock_get_cache.return_value = (
            {"cached_keyword": {"googleAdsAvgMonthlySearches": 500, "googleTrendsScore": 80.0}},
            ["new_keyword"]
        )
        
        mock_ads.return_value = {"new_keyword": 1000}
        
        async def mock_get_trends(keywords):
            return {"new_keyword": 65.0}
        mock_trends.side_effect = mock_get_trends
        
        mock_set_cache.return_value = True
        
        response = client.post(
            "/batch_search_volume",
            json={"keywords": ["cached_keyword", "new_keyword"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        
        cached_result = next(r for r in data if r["keyword"] == "cached_keyword")
        assert cached_result["googleAdsAvgMonthlySearches"] == 500
        assert cached_result["googleTrendsScore"] == 80.0
        
        new_result = next(r for r in data if r["keyword"] == "new_keyword")
        assert new_result["googleAdsAvgMonthlySearches"] == 1000
        assert new_result["googleTrendsScore"] == 65.0
    
    @patch('api_routes.cache_manager.get_batch_data')
    @patch('api_routes.ads_manager.get_bulk_metrics')
    @patch('api_routes.trends_manager.get_bulk_trends')
    def test_api_failure_handling(
        self,
        mock_trends,
        mock_ads,
        mock_get_cache,
        client
    ):
        """API障害のハンドリングをテスト。"""
        mock_get_cache.return_value = ({}, ["test_keyword"])
        
        mock_ads.side_effect = Exception("Ads API error")
        
        async def mock_get_trends(keywords):
            return {"test_keyword": None}
        mock_trends.side_effect = mock_get_trends
        
        response = client.post(
            "/batch_search_volume",
            json={"keywords": ["test_keyword"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["keyword"] == "test_keyword"
        assert data[0]["googleAdsAvgMonthlySearches"] is None


class TestCacheIntegration:
    """キャッシュ統合をテスト。"""
    
    def test_pickle_cache_fallback(self):
        """Redisが利用できない場合にPickleキャッシュが機能することをテスト。"""
        from cache import PickleCache
        
        cache = PickleCache("test_cache.pkl", max_entries=10)
        
        cache.set("test_key", {"value": "test"}, ttl=60)
        
        result = cache.get("test_key")
        assert result is not None
        assert result["value"] == "test"
        
        assert cache.exists("test_key") is True
        
        cache.delete("test_key")
        assert cache.exists("test_key") is False
        
        if os.path.exists("test_cache.pkl"):
            os.remove("test_cache.pkl")
    
    def test_cache_eviction(self):
        """PickleキャッシュのFIFO除去をテスト。"""
        from cache import PickleCache
        
        cache = PickleCache("test_eviction.pkl", max_entries=3)
        
        for i in range(4):
            cache.set(f"key{i}", {"value": i}, ttl=60)
        
        assert cache.get("key0") is None
        assert cache.get("key1") is not None
        assert cache.get("key3") is not None
        
        if os.path.exists("test_eviction.pkl"):
            os.remove("test_eviction.pkl")


class TestLoggerConfiguration:
    """ロガー設定をテスト。"""
    
    def test_logger_singleton(self):
        """LoggerManagerがシングルトンであることをテスト。"""
        from logger import LoggerManager
        
        manager1 = LoggerManager()
        manager2 = LoggerManager()
        
        assert manager1 is manager2
    
    def test_logger_methods(self):
        """ロガーメソッドがエラーなく動作することをテスト。"""
        from logger import logger_manager
        
        logger_manager.log_access("GET", "/test", 200, "127.0.0.1", 10.5)
        
        logger_manager.log_error("Test error", exc_info=False)
        
        logger_manager.log_ads_request(10, True, 100.0)
        logger_manager.log_ads_request(5, False, 50.0, "API Error")
        
        logger_manager.log_trends_request("test", True, 25.0)
        logger_manager.log_trends_request("test", False, 30.0, "Quota exceeded")


class TestCircuitBreaker:
    """サーキットブレーカー機能をテスト。"""
    
    def test_ads_circuit_breaker(self):
        """Google Adsサーキットブレーカーをテスト。"""
        from ads import GoogleAdsManager
        
        manager = GoogleAdsManager()
        manager.consecutive_failures = 5
        manager.circuit_breaker_timeout = 0.1
        
        with pytest.raises(Exception):
            manager._check_circuit_breaker()
        
        import time
        time.sleep(0.2)
        
        manager._check_circuit_breaker()
        assert manager.consecutive_failures == 0
    
    def test_trends_circuit_breaker(self):
        """Google Trendsサーキットブレーカーをテスト。"""
        from trends import GoogleTrendsManager
        
        manager = GoogleTrendsManager()
        manager.consecutive_failures = 5
        manager.circuit_breaker_timeout = 0.1
        
        with pytest.raises(Exception):
            manager._check_circuit_breaker()
        
        import time
        time.sleep(0.2)
        
        manager._check_circuit_breaker()
        assert manager.consecutive_failures == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])