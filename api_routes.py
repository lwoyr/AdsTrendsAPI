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
from queue_manager import queue_manager

router = APIRouter()


class KeywordBatchRequest(BaseModel):
    """バッチキーワード検索用のリクエストモデル。"""
    keywords: List[str] = Field(..., min_items=1, max_items=200)
    chunk_size: Optional[int] = Field(default=20, ge=1, le=50, description="一度に処理するキーワード数")
    
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


class JobSubmitResponse(BaseModel):
    """ジョブ送信レスポンスモデル。"""
    job_id: str
    keywords_count: int
    estimated_time_seconds: int
    message: str


class JobStatusResponse(BaseModel):
    """ジョブステータスレスポンスモデル。"""
    job_id: str
    status: str
    pending: int
    processing: int
    completed: int
    failed: int
    results: Optional[List[KeywordMetric]] = None


async def process_keywords_batch(
    keywords: List[str],
    chunk_size: int = 20
) -> List[KeywordMetric]:
    """キーワードのバッチを処理してメトリクスを返す。"""
    cached_data, missing_keywords = cache_manager.get_batch_data(keywords)
    
    results = []
    
    for keyword, data in cached_data.items():
        trends_score = data.get('googleTrendsScore')
        results.append(KeywordMetric(
            keyword=keyword,
            googleAdsAvgMonthlySearches=data.get('googleAdsAvgMonthlySearches'),
            googleTrendsScore=round(trends_score, 1) if trends_score is not None else None
        ))
    
    if missing_keywords:
        # キーワードをチャンクに分割して順次処理
        chunks = [missing_keywords[i:i + chunk_size] for i in range(0, len(missing_keywords), chunk_size)]
        logger_manager.access_logger.info(
            f"未キャッシュのキーワード{len(missing_keywords)}件を{len(chunks)}チャンクに分割して処理"
        )
        
        all_ads_results = {}
        all_trends_results = {}
        
        for chunk_idx, chunk in enumerate(chunks):
            logger_manager.access_logger.info(
                f"チャンク {chunk_idx + 1}/{len(chunks)} を処理中 ({len(chunk)}キーワード)"
            )
            
            # チャンク間に遅延を入れる（最初のチャンクは除く）
            if chunk_idx > 0:
                delay = min(5 + chunk_idx * 2, 15)  # 5秒から始めて最大15秒まで
                logger_manager.access_logger.info(f"次のチャンク処理前に{delay}秒待機")
                await asyncio.sleep(delay)
            
            ads_task = asyncio.create_task(
                asyncio.to_thread(ads_manager.get_bulk_metrics, chunk)
            )
            trends_task = asyncio.create_task(
                trends_manager.get_bulk_trends(chunk)
            )
            
            try:
                ads_results, trends_results = await asyncio.gather(
                    ads_task, trends_task, return_exceptions=True
                )
                
                if isinstance(ads_results, Exception):
                    logger_manager.error_logger.error(
                        f"Ads APIエラー (チャンク {chunk_idx + 1}): {ads_results}", exc_info=False
                    )
                    ads_results = {kw: None for kw in chunk}
                
                if isinstance(trends_results, Exception):
                    logger_manager.error_logger.error(
                        f"Trends APIエラー (チャンク {chunk_idx + 1}): {trends_results}", exc_info=False
                    )
                    trends_results = {kw: None for kw in chunk}
                
                all_ads_results.update(ads_results)
                all_trends_results.update(trends_results)
                
            except asyncio.TimeoutError:
                logger_manager.error_logger.error(f"チャンク {chunk_idx + 1} の処理がタイムアウトしました")
                for kw in chunk:
                    all_ads_results[kw] = None
                    all_trends_results[kw] = None
        
        # 結果を統合
        for keyword in missing_keywords:
            ads_volume = all_ads_results.get(keyword)
            trends_score = all_trends_results.get(keyword)
            
            results.append(KeywordMetric(
                keyword=keyword,
                googleAdsAvgMonthlySearches=ads_volume,
                googleTrendsScore=round(trends_score, 1) if trends_score is not None else None
            ))
            
            cache_manager.set_keyword_data(keyword, ads_volume, round(trends_score, 1) if trends_score is not None else None)
    
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
        # より長いタイムアウトを設定（チャンク処理のため）
        timeout_seconds = max(90.0, len(batch_request.keywords) * 2)  # キーワード数に応じて調整
        
        results = await asyncio.wait_for(
            process_keywords_batch(batch_request.keywords, batch_request.chunk_size),
            timeout=timeout_seconds
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


@router.post("/async/batch_search_volume", response_model=JobSubmitResponse)
async def async_batch_search_volume(
    request: Request,
    batch_request: KeywordBatchRequest
) -> JobSubmitResponse:
    """
    非同期バッチキーワード検索リクエストを送信。
    
    Args:
        request: FastAPIリクエストオブジェクト
        batch_request: キーワードを含むバッチリクエスト
        
    Returns:
        ジョブIDとステータス情報
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # キーワードをキューに追加
    await queue_manager.add_keywords(batch_request.keywords)
    
    # ジョブIDを生成（現在はタイムスタンプを使用）
    job_id = f"job_{int(time.time() * 1000)}"
    
    # 推定時間を計算（キーワードあたり約3秒と仮定）
    estimated_time = len(batch_request.keywords) * 3
    
    logger_manager.log_access(
        method="POST",
        path="/async/batch_search_volume",
        status_code=202,
        client_ip=client_ip,
        latency_ms=10
    )
    
    # バックグラウンドで処理を開始
    asyncio.create_task(process_queue_in_background())
    
    return JobSubmitResponse(
        job_id=job_id,
        keywords_count=len(batch_request.keywords),
        estimated_time_seconds=estimated_time,
        message="ジョブを受け付けました。/async/statusエンドポイントで進捗を確認できます。"
    )


@router.get("/async/status", response_model=JobStatusResponse)
async def get_job_status(
    request: Request,
    keywords: Optional[str] = None
) -> JobStatusResponse:
    """
    非同期ジョブのステータスを取得。
    
    Args:
        request: FastAPIリクエストオブジェクト
        keywords: 結果を取得したいキーワード（カンマ区切り）
        
    Returns:
        ジョブステータスと結果
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # キューステータスを取得
    status = await queue_manager.get_status()
    
    # 特定のキーワードの結果を取得
    results = None
    if keywords:
        keyword_list = [k.strip() for k in keywords.split(",")]
        raw_results = await queue_manager.get_results(keyword_list)
        
        results = []
        for keyword, data in raw_results.items():
            results.append(KeywordMetric(
                keyword=keyword,
                googleAdsAvgMonthlySearches=data.get("googleAdsAvgMonthlySearches"),
                googleTrendsScore=round(data["googleTrendsScore"], 1) if data.get("googleTrendsScore") is not None else None
            ))
    
    logger_manager.log_access(
        method="GET",
        path="/async/status",
        status_code=200,
        client_ip=client_ip,
        latency_ms=5
    )
    
    # 全体のステータスを判定
    if status["pending"] == 0 and status["processing"] == 0:
        overall_status = "completed"
    elif status["processing"] > 0:
        overall_status = "processing"
    else:
        overall_status = "pending"
    
    return JobStatusResponse(
        job_id="current",
        status=overall_status,
        pending=status["pending"],
        processing=status["processing"],
        completed=status["completed"],
        failed=status["failed"],
        results=results
    )


async def process_queue_in_background():
    """バックグラウンドでキューを処理。"""
    while True:
        # 次のバッチを取得
        batch = await queue_manager.get_next_batch()
        
        if not batch:
            # キューが空の場合は終了
            break
        
        logger_manager.access_logger.info(f"バックグラウンド処理: {len(batch)}キーワード")
        
        # Google AdsとTrendsのAPIを並列で呼び出し
        ads_task = asyncio.create_task(
            asyncio.to_thread(ads_manager.get_bulk_metrics, batch)
        )
        trends_task = asyncio.create_task(
            trends_manager.get_bulk_trends(batch)
        )
        
        try:
            ads_results, trends_results = await asyncio.gather(
                ads_task, trends_task, return_exceptions=True
            )
            
            if isinstance(ads_results, Exception):
                logger_manager.error_logger.error(
                    f"Ads APIエラー: {ads_results}", exc_info=False
                )
                ads_results = {kw: None for kw in batch}
            
            if isinstance(trends_results, Exception):
                logger_manager.error_logger.error(
                    f"Trends APIエラー: {trends_results}", exc_info=False
                )
                trends_results = {kw: None for kw in batch}
            
            # 結果をキューマネージャーに登録
            for keyword in batch:
                ads_volume = ads_results.get(keyword)
                trends_score = trends_results.get(keyword)
                
                if ads_volume is not None or trends_score is not None:
                    await queue_manager.mark_completed(
                        keyword, ads_volume, trends_score
                    )
                    # キャッシュにも保存
                    cache_manager.set_keyword_data(
                        keyword, ads_volume, 
                        round(trends_score, 1) if trends_score is not None else None
                    )
                else:
                    await queue_manager.mark_failed(keyword)
                    
        except Exception as e:
            logger_manager.error_logger.error(
                f"バッチ処理中にエラー: {e}"
            )
            for keyword in batch:
                await queue_manager.mark_failed(keyword)