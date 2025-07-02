"""キーワードメトリクスバッチAPIのAPIルート定義。"""
import asyncio
import time
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, validator

from ads import ads_manager
from cache import cache_manager
from logger import logger_manager
from trends import trends_manager

router = APIRouter()


class KeywordBatchRequest(BaseModel):
    """バッチキーワード検索用のリクエストモデル。"""
    keywords: List[str] = Field(..., min_items=1, max_items=200)
    
    @validator('keywords')
    def validate_keywords(cls, v):
        """キーワードリストを検証。"""
        unique_keywords = list(set(v))
        if len(unique_keywords) != len(v):
            logger_manager.access_logger.warning(
                f"Duplicate keywords removed: {len(v)} -> {len(unique_keywords)}"
            )
        return unique_keywords


class KeywordMetric(BaseModel):
    """個別キーワードメトリクス用のレスポンスモデル。"""
    keyword: str
    googleAdsAvgMonthlySearches: Optional[int]
    googleTrendsScore: Optional[float]


class HealthResponse(BaseModel):
    """ヘルスチェック用のレスポンスモデル。"""
    status: str
    timestamp: int


async def process_keywords_batch(
    keywords: List[str]
) -> List[KeywordMetric]:
    """キーワードのバッチを処理してメトリクスを返す。"""
    cached_data, missing_keywords = cache_manager.get_batch_data(keywords)
    
    results = []
    
    for keyword, data in cached_data.items():
        results.append(KeywordMetric(
            keyword=keyword,
            googleAdsAvgMonthlySearches=data.get('googleAdsAvgMonthlySearches'),
            googleTrendsScore=data.get('googleTrendsScore')
        ))
    
    if missing_keywords:
        ads_task = asyncio.create_task(
            asyncio.to_thread(ads_manager.get_bulk_metrics, missing_keywords)
        )
        trends_task = asyncio.create_task(
            trends_manager.get_bulk_trends(missing_keywords)
        )
        
        try:
            ads_results, trends_results = await asyncio.gather(
                ads_task, trends_task, return_exceptions=True
            )
            
            if isinstance(ads_results, Exception):
                logger_manager.error_logger.error(
                    f"Ads APIエラー: {ads_results}", exc_info=False
                )
                ads_results = {kw: None for kw in missing_keywords}
            
            if isinstance(trends_results, Exception):
                logger_manager.error_logger.error(
                    f"Trends APIエラー: {trends_results}", exc_info=False
                )
                trends_results = {kw: None for kw in missing_keywords}
            
        except asyncio.TimeoutError:
            logger_manager.error_logger.error("キーワードバッチ処理がタイムアウトしました")
            ads_results = {kw: None for kw in missing_keywords}
            trends_results = {kw: None for kw in missing_keywords}
        
        for keyword in missing_keywords:
            ads_volume = ads_results.get(keyword)
            trends_score = trends_results.get(keyword)
            
            results.append(KeywordMetric(
                keyword=keyword,
                googleAdsAvgMonthlySearches=ads_volume,
                googleTrendsScore=trends_score
            ))
            
            cache_manager.set_keyword_data(keyword, ads_volume, trends_score)
    
    return results


@router.post("/batch_search_volume", response_model=List[KeywordMetric])
async def batch_search_volume(
    request: Request,
    batch_request: KeywordBatchRequest
) -> List[KeywordMetric]:
    """
    バッチキーワード検索リクエストを処理。
    
    Args:
        request: FastAPIリクエストオブジェクト
        batch_request: キーワードを含むバッチリクエスト
        
    Returns:
        キーワードメトリクスのリスト
    """
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        results = await asyncio.wait_for(
            process_keywords_batch(batch_request.keywords),
            timeout=90.0
        )
        
        status_code = 200
        latency_ms = (time.time() - start_time) * 1000
        
        logger_manager.log_access(
            method="POST",
            path="/batch_search_volume",
            status_code=status_code,
            client_ip=client_ip,
            latency_ms=latency_ms
        )
        
        return results
        
    except asyncio.TimeoutError:
        status_code = 504
        latency_ms = (time.time() - start_time) * 1000
        
        logger_manager.log_access(
            method="POST",
            path="/batch_search_volume",
            status_code=status_code,
            client_ip=client_ip,
            latency_ms=latency_ms
        )
        
        raise HTTPException(
            status_code=504,
            detail="リクエストが90秒後にタイムアウトしました"
        )
        
    except Exception as e:
        status_code = 500
        latency_ms = (time.time() - start_time) * 1000
        
        logger_manager.log_access(
            method="POST",
            path="/batch_search_volume",
            status_code=status_code,
            client_ip=client_ip,
            latency_ms=latency_ms
        )
        
        logger_manager.log_error(f"Batch processing error: {e}")
        
        raise HTTPException(
            status_code=500,
            detail=f"内部サーバーエラー: {str(e)}"
        )


@router.get("/healthz", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """
    ヘルスチェックエンドポイント。
    
    Returns:
        ヘルスステータスと現在のタイムスタンプ
    """
    client_ip = request.client.host if request.client else "unknown"
    
    logger_manager.log_access(
        method="GET",
        path="/healthz",
        status_code=200,
        client_ip=client_ip,
        latency_ms=0.1
    )
    
    return HealthResponse(
        status="ok",
        timestamp=int(time.time())
    )