"""Google Ads API統合モジュール。"""
import os
import random
import time
from typing import Dict, List, Optional

from dotenv import load_dotenv
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from logger import logger_manager

load_dotenv()


class AdsAPIError(Exception):
    """Google Ads APIエラー用のカスタム例外。"""
    pass


class CircuitBreakerError(Exception):
    """サーキットブレーカーが開いているときに発生する例外。"""
    pass


class GoogleAdsManager:
    """Google Ads APIクライアントマネージャー（リトライロジック付き）。"""
    
    def __init__(self) -> None:
        """Google Adsクライアントを初期化。"""
        self.developer_token = os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN')
        self.client_id = os.getenv('GOOGLE_ADS_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_ADS_CLIENT_SECRET')
        self.refresh_token = os.getenv('GOOGLE_ADS_REFRESH_TOKEN')
        self.customer_id = os.getenv('GOOGLE_ADS_CUSTOMER_ID', '').replace('-', '')
        
        self.client: Optional[GoogleAdsClient] = None
        self._initialized = False
        
        self.max_retries = 3
        self.backoff_factor = 2
        self.jitter = 0.2
        
        self.consecutive_failures = 0
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_timeout = 300
        self.circuit_breaker_opened_at: Optional[float] = None
        
        # クライアントの初期化を試みるが、認証情報が設定されていない場合は失敗しない
        try:
            self._init_client()
            self._initialized = True
        except Exception as e:
            logger_manager.error_logger.warning(
                f"Google Ads client initialization deferred: {e}. "
                "APIコールを行う前に認証情報を設定してください。"
            )
    
    def _init_client(self) -> None:
        """設定からGoogle Adsクライアントを初期化。"""
        try:
            config = {
                "developer_token": self.developer_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "use_proto_plus": True
            }
            
            if os.path.exists("ads_client.yaml"):
                self.client = GoogleAdsClient.load_from_storage("ads_client.yaml")
            else:
                self.client = GoogleAdsClient.load_from_dict(config)
                
        except Exception as e:
            logger_manager.error_logger.error(f"Failed to initialize Google Ads client: {e}")
            raise AdsAPIError(f"Client initialization failed: {e}")
    
    def _check_circuit_breaker(self) -> None:
        """サーキットブレーカーが開いているか確認。"""
        if self.consecutive_failures >= self.circuit_breaker_threshold:
            if self.circuit_breaker_opened_at is None:
                self.circuit_breaker_opened_at = time.time()
                logger_manager.ads_logger.warning("サーキットブレーカーが開きました")
            
            elapsed = time.time() - self.circuit_breaker_opened_at
            if elapsed < self.circuit_breaker_timeout:
                raise CircuitBreakerError(
                    f"サーキットブレーカーが開いています。{self.circuit_breaker_timeout - elapsed:.0f}秒後に再試行してください"
                )
            else:
                self.circuit_breaker_opened_at = None
                self.consecutive_failures = 0
                logger_manager.ads_logger.info("サーキットブレーカーがリセットされました")
    
    def _execute_with_retry(self, func, *args, **kwargs):
        """リトライロジックで関数を実行。"""
        self._check_circuit_breaker()
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                result = func(*args, **kwargs)
                self.consecutive_failures = 0
                return result
                
            except GoogleAdsException as e:
                last_error = e
                self.consecutive_failures += 1
                
                if attempt < self.max_retries - 1:
                    sleep_time = (self.backoff_factor ** attempt) + random.uniform(-self.jitter, self.jitter)
                    logger_manager.ads_logger.warning(
                        f"リトライ {attempt + 1}/{self.max_retries} 回目、{sleep_time:.2f}秒待機: {e}"
                    )
                    time.sleep(sleep_time)
                else:
                    logger_manager.ads_logger.error(f"すべてのリトライが失敗しました: {e}")
                    
            except Exception as e:
                last_error = e
                self.consecutive_failures += 1
                logger_manager.error_logger.error(f"Google Ads APIで予期しないエラーが発生しました: {e}")
                break
        
        raise AdsAPIError(f"{self.max_retries}回の試行後に失敗しました: {last_error}")
    
    def get_bulk_metrics(self, keywords: List[str]) -> Dict[str, Optional[int]]:
        """
        複数のキーワードの検索ボリュームメトリクスを取得。
        
        Args:
            keywords: メトリクスを取得するキーワードのリスト
            
        Returns:
            キーワードと月間検索ボリュームのマッピング辞書
        """
        if not self._initialized:
            logger_manager.ads_logger.error(
                "Google Adsクライアントが初期化されていません。有効な認証情報を設定してください。"
            )
            return {keyword: None for keyword in keywords}
        
        if not self.client:
            raise AdsAPIError("Google Adsクライアントが初期化されていません")
        
        start_time = time.time()
        
        try:
            result = self._execute_with_retry(self._get_keyword_metrics, keywords)
            
            duration_ms = (time.time() - start_time) * 1000
            logger_manager.log_ads_request(
                keywords_count=len(keywords),
                success=True,
                duration_ms=duration_ms
            )
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger_manager.log_ads_request(
                keywords_count=len(keywords),
                success=False,
                duration_ms=duration_ms,
                error=str(e)
            )
            
            return {keyword: None for keyword in keywords}
    
    def _get_keyword_metrics(self, keywords: List[str]) -> Dict[str, Optional[int]]:
        """Google Ads APIからキーワードメトリクスを取得する内部メソッド。"""
        keyword_plan_idea_service = self.client.get_service("KeywordPlanIdeaService")
        request = self.client.get_type("GenerateKeywordHistoricalMetricsRequest")
        
        request.customer_id = self.customer_id
        request.keywords.extend(keywords)
        # 英語の言語定数ID
        request.language = "languageConstants/1000"
        
        # アメリカの地域定数
        request.geo_target_constants.append("geoTargetConstants/2840")
        
        try:
            response = keyword_plan_idea_service.generate_keyword_historical_metrics(
                request=request
            )
            
            results = {}
            for i, keyword in enumerate(keywords):
                if i < len(response.results):
                    metric = response.results[i].keyword_metrics
                    if metric and metric.avg_monthly_searches:
                        results[keyword] = metric.avg_monthly_searches
                    else:
                        results[keyword] = 0
                else:
                    results[keyword] = None
            
            return results
            
        except GoogleAdsException as e:
            logger_manager.ads_logger.error(f"Google Ads API error: {e}")
            raise


ads_manager = GoogleAdsManager()