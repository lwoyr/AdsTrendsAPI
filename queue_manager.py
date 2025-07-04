"""キーワード処理用のキューマネージャー。"""
import asyncio
import time
from collections import deque
from typing import Dict, List, Optional, Set

from logger import logger_manager


class QueueManager:
    """キーワード処理をキューで管理するマネージャー。"""
    
    def __init__(self) -> None:
        """キューマネージャーを初期化。"""
        self.pending_queue: deque = deque()
        self.processing: Set[str] = set()
        self.completed: Dict[str, Dict] = {}
        self.failed: Set[str] = set()
        self.lock = asyncio.Lock()
        self.max_concurrent = 20  # 同時処理する最大キーワード数
        self.batch_delay = 5.0  # バッチ間の遅延（秒）
        self.last_batch_time = 0
    
    async def add_keywords(self, keywords: List[str]) -> None:
        """キーワードをキューに追加。"""
        async with self.lock:
            # 重複を除外してキューに追加
            for keyword in keywords:
                if (keyword not in self.pending_queue and 
                    keyword not in self.processing and 
                    keyword not in self.completed):
                    self.pending_queue.append(keyword)
            
            logger_manager.access_logger.info(
                f"キューに{len(keywords)}個のキーワードを追加 "
                f"(待機中: {len(self.pending_queue)}, 処理中: {len(self.processing)}, 完了: {len(self.completed)})"
            )
    
    async def get_next_batch(self) -> List[str]:
        """次に処理するバッチを取得。"""
        async with self.lock:
            # レート制限チェック
            current_time = time.time()
            time_since_last = current_time - self.last_batch_time
            if time_since_last < self.batch_delay:
                wait_time = self.batch_delay - time_since_last
                logger_manager.access_logger.info(f"レート制限のため{wait_time:.1f}秒待機")
                await asyncio.sleep(wait_time)
            
            # 次のバッチを取得
            batch = []
            while len(batch) < self.max_concurrent and self.pending_queue:
                keyword = self.pending_queue.popleft()
                self.processing.add(keyword)
                batch.append(keyword)
            
            if batch:
                self.last_batch_time = time.time()
                logger_manager.access_logger.info(
                    f"次のバッチを取得: {len(batch)}個のキーワード"
                )
            
            return batch
    
    async def mark_completed(self, keyword: str, ads_data: Optional[int], trends_data: Optional[float]) -> None:
        """キーワードの処理を完了としてマーク。"""
        async with self.lock:
            if keyword in self.processing:
                self.processing.remove(keyword)
            
            self.completed[keyword] = {
                "googleAdsAvgMonthlySearches": ads_data,
                "googleTrendsScore": trends_data,
                "completed_at": time.time()
            }
    
    async def mark_failed(self, keyword: str) -> None:
        """キーワードの処理を失敗としてマーク。"""
        async with self.lock:
            if keyword in self.processing:
                self.processing.remove(keyword)
            self.failed.add(keyword)
    
    async def get_status(self) -> Dict[str, int]:
        """現在のキューステータスを取得。"""
        async with self.lock:
            return {
                "pending": len(self.pending_queue),
                "processing": len(self.processing),
                "completed": len(self.completed),
                "failed": len(self.failed)
            }
    
    async def get_results(self, keywords: List[str]) -> Dict[str, Dict]:
        """指定されたキーワードの結果を取得。"""
        async with self.lock:
            results = {}
            for keyword in keywords:
                if keyword in self.completed:
                    results[keyword] = self.completed[keyword]
                elif keyword in self.failed:
                    results[keyword] = {
                        "googleAdsAvgMonthlySearches": None,
                        "googleTrendsScore": None,
                        "error": "Processing failed"
                    }
                else:
                    results[keyword] = {
                        "googleAdsAvgMonthlySearches": None,
                        "googleTrendsScore": None,
                        "status": "pending" if keyword in self.pending_queue else "processing"
                    }
            return results
    
    def reset(self) -> None:
        """キューをリセット。"""
        self.pending_queue.clear()
        self.processing.clear()
        self.completed.clear()
        self.failed.clear()
        self.last_batch_time = 0
        logger_manager.access_logger.info("キューマネージャーをリセットしました")


queue_manager = QueueManager()