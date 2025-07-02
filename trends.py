"""Google Trends (pytrends)統合モジュール（非同期サポート付き）。"""
import asyncio
import time
from typing import Dict, List, Optional

import httpx
from pytrends.request import TrendReq

from logger import logger_manager


class TrendsAPIError(Exception):
    """Google Trends APIエラー用のカスタム例外。"""
    pass


class TrendQuotaExceededError(Exception):
    """CAPTCHAまたはクォータ制限が検出されたときに発生する例外。"""
    pass


class GoogleTrendsManager:
    """Google Trends APIマネージャー（非同期処理とレート制限付き）。"""
    
    def __init__(self) -> None:
        """Google Trendsマネージャーを初期化。"""
        self.semaphore = asyncio.Semaphore(10)
        self.rate_limit_delay = 1.0
        self.consecutive_failures = 0
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_timeout = 300
        self.circuit_breaker_opened_at: Optional[float] = None
    
    def _check_circuit_breaker(self) -> None:
        """サーキットブレーカーが開いているか確認。"""
        if self.consecutive_failures >= self.circuit_breaker_threshold:
            if self.circuit_breaker_opened_at is None:
                self.circuit_breaker_opened_at = time.time()
                logger_manager.trends_logger.warning("Trends APIのサーキットブレーカーが開きました")
            
            elapsed = time.time() - self.circuit_breaker_opened_at
            if elapsed < self.circuit_breaker_timeout:
                raise TrendsAPIError(
                    f"サーキットブレーカーが開いています。{self.circuit_breaker_timeout - elapsed:.0f}秒後に再試行してください"
                )
            else:
                self.circuit_breaker_opened_at = None
                self.consecutive_failures = 0
                logger_manager.trends_logger.info("Trends APIのサーキットブレーカーがリセットされました")
    
    async def _get_single_trend_score(self, keyword: str) -> Optional[float]:
        """単一キーワードのトレンドスコアを取得。"""
        start_time = time.time()
        
        try:
            self._check_circuit_breaker()
            
            async with self.semaphore:
                await asyncio.sleep(self.rate_limit_delay)
                
                pytrends = TrendReq(hl='en-US', tz=360, timeout=(10.0, 30.0))
                
                loop = asyncio.get_event_loop()
                
                # build_payloadの正しい引数順序: kw_list, timeframe, geo, gprop
                def build_payload_wrapper():
                    pytrends.build_payload(
                        kw_list=[keyword],
                        timeframe='today 12-m',
                        geo='US',
                        gprop=''
                    )
                
                await loop.run_in_executor(None, build_payload_wrapper)
                
                interest_df = await loop.run_in_executor(
                    None,
                    pytrends.interest_over_time
                )
                
                if interest_df.empty:
                    score = 0.0
                else:
                    score = float(interest_df[keyword].mean())
                
                duration_ms = (time.time() - start_time) * 1000
                logger_manager.log_trends_request(
                    keyword=keyword,
                    success=True,
                    duration_ms=duration_ms
                )
                
                self.consecutive_failures = 0
                return score
                
        except Exception as e:
            error_msg = str(e).lower()
            
            if 'captcha' in error_msg or '429' in error_msg or 'quota' in error_msg:
                self.consecutive_failures = self.circuit_breaker_threshold
                duration_ms = (time.time() - start_time) * 1000
                logger_manager.log_trends_request(
                    keyword=keyword,
                    success=False,
                    duration_ms=duration_ms,
                    error="CAPTCHA/クォータ超過"
                )
                raise TrendQuotaExceededError("Google Trendsのクォータを超過またはCAPTCHAが必要です")
            
            self.consecutive_failures += 1
            duration_ms = (time.time() - start_time) * 1000
            logger_manager.log_trends_request(
                keyword=keyword,
                success=False,
                duration_ms=duration_ms,
                error=str(e)
            )
            
            return None
    
    async def get_bulk_trends(self, keywords: List[str]) -> Dict[str, Optional[float]]:
        """
        複数キーワードのトレンドスコアを非同期で取得。
        
        Args:
            keywords: トレンドを取得するキーワードのリスト
            
        Returns:
            キーワードとトレンドスコアのマッピング辞書
        """
        results = {}
        
        tasks = []
        for keyword in keywords:
            task = asyncio.create_task(self._get_single_trend_score(keyword))
            tasks.append((keyword, task))
        
        for keyword, task in tasks:
            try:
                score = await task
                results[keyword] = score
            except TrendQuotaExceededError:
                logger_manager.trends_logger.error(
                    f"クォータ超過のためトレンド収集を停止します"
                )
                for remaining_keyword, remaining_task in tasks:
                    if not remaining_task.done():
                        remaining_task.cancel()
                        results[remaining_keyword] = None
                break
            except Exception as e:
                logger_manager.error_logger.error(
                    f"{keyword}のトレンド取得に失敗しました: {e}"
                )
                results[keyword] = None
        
        return results
    
    def get_trends_sync(self, keywords: List[str]) -> Dict[str, Optional[float]]:
        """get_bulk_trendsの同期ラッパー。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_bulk_trends(keywords))
        finally:
            loop.close()


trends_manager = GoogleTrendsManager()