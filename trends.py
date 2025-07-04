"""Google Trends (pytrends)統合モジュール（非同期サポート付き）。"""
import asyncio
import json
import os
import random
import time
from typing import Dict, List, Optional, Set

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
        self.semaphore = asyncio.Semaphore(1)  # 同時実行を1に制限
        self.rate_limit_delay = 5.0  # 基本遅延を大幅に増加
        self.consecutive_failures = 0
        self.circuit_breaker_threshold = 3  # より早くサーキットブレーカーを開く
        self.circuit_breaker_timeout = 600  # 10分間のクールダウン
        self.circuit_breaker_opened_at: Optional[float] = None
        self.retry_delays = [30, 60, 120, 300]  # より長いリトライ遅延
        self.max_retries = 3  # リトライ回数を減らす
        self.request_count = 0
        self.hourly_limit = 50  # 1時間あたりの最大リクエスト数
        self.last_hour_reset = time.time()
        self.successful_requests_in_row = 0
        self.progress_file = "trends_progress.json"
        self.failed_keywords: Set[str] = set()
    
    def _check_circuit_breaker(self) -> None:
        """サーキットブレーカーが開いているか確認。"""
        # 時間ベースのレート制限チェック
        current_time = time.time()
        if current_time - self.last_hour_reset >= 3600:  # 1時間経過
            self.request_count = 0
            self.last_hour_reset = current_time
            logger_manager.trends_logger.info("時間制限カウンターをリセットしました")
        
        if self.request_count >= self.hourly_limit:
            remaining_time = 3600 - (current_time - self.last_hour_reset)
            raise TrendsAPIError(
                f"時間あたりのリクエスト制限に達しました。{remaining_time:.0f}秒後に再試行してください"
            )
        
        # 既存のサーキットブレーカーロジック
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
                self.successful_requests_in_row = 0
                logger_manager.trends_logger.info("Trends APIのサーキットブレーカーがリセットされました")
    
    async def _get_single_trend_score_with_retry(self, keyword: str, retry_count: int = 0) -> Optional[float]:
        """単一キーワードのトレンドスコアを取得（リトライ機能付き）。"""
        start_time = time.time()
        
        try:
            self._check_circuit_breaker()
            
            async with self.semaphore:
                # ランダムな遅延を追加してリクエストを分散
                jitter = random.uniform(0.5, 1.5)
                await asyncio.sleep(self.rate_limit_delay * jitter)
                
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
                self.request_count += 1
                self.successful_requests_in_row += 1
                
                # 連続成功が続いた場合のみ遅延を減らす
                if self.successful_requests_in_row > 5:
                    self.rate_limit_delay = max(3.0, self.rate_limit_delay * 0.95)
                
                logger_manager.trends_logger.debug(
                    f"リクエスト成功 (今時間: {self.request_count}/{self.hourly_limit}, 遅延: {self.rate_limit_delay:.1f}秒)"
                )
                return score
                
        except Exception as e:
            error_msg = str(e).lower()
            
            if 'captcha' in error_msg or '429' in error_msg or 'quota' in error_msg or 'too many requests' in error_msg:
                # 429エラーの場合、リトライを試みる
                if retry_count < self.max_retries:
                    retry_delay = self.retry_delays[retry_count]
                    logger_manager.trends_logger.warning(
                        f"{keyword}のリクエストが429エラーで失敗。{retry_delay}秒後にリトライ（{retry_count + 1}/{self.max_retries}）"
                    )
                    
                    # レート制限遅延を大幅に増やす
                    self.rate_limit_delay = min(30.0, self.rate_limit_delay * 2.0)
                    self.successful_requests_in_row = 0
                    
                    # 指数バックオフで待機
                    await asyncio.sleep(retry_delay)
                    
                    # リトライ
                    return await self._get_single_trend_score_with_retry(keyword, retry_count + 1)
                else:
                    # リトライ上限に達した
                    self.consecutive_failures = self.circuit_breaker_threshold
                    duration_ms = (time.time() - start_time) * 1000
                    logger_manager.log_trends_request(
                        keyword=keyword,
                        success=False,
                        duration_ms=duration_ms,
                        error="CAPTCHA/クォータ超過（リトライ上限到達）"
                    )
                    raise TrendQuotaExceededError("Google Trendsのクォータを超過またはCAPTCHAが必要です")
            
            self.consecutive_failures += 1
            self.successful_requests_in_row = 0
            duration_ms = (time.time() - start_time) * 1000
            logger_manager.log_trends_request(
                keyword=keyword,
                success=False,
                duration_ms=duration_ms,
                error=str(e)
            )
            
            # 一般的なエラーの場合も遅延を増やす
            self.rate_limit_delay = min(20.0, self.rate_limit_delay * 1.2)
            
            return None
    
    async def _get_single_trend_score(self, keyword: str) -> Optional[float]:
        """単一キーワードのトレンドスコアを取得。"""
        return await self._get_single_trend_score_with_retry(keyword, 0)
    
    def _save_progress(self, results: Dict[str, Optional[float]], remaining_keywords: List[str]) -> None:
        """進捗をファイルに保存。"""
        progress_data = {
            "completed": results,
            "remaining": remaining_keywords,
            "failed": list(self.failed_keywords),
            "timestamp": time.time()
        }
        with open(self.progress_file, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
        logger_manager.trends_logger.info(f"進捗を保存しました: {len(results)}件完了")
    
    def _load_progress(self) -> tuple[Dict[str, Optional[float]], List[str]]:
        """保存された進捗を読み込み。"""
        if not os.path.exists(self.progress_file):
            return {}, []
        
        try:
            with open(self.progress_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 24時間以上古いデータは無視
            if time.time() - data.get("timestamp", 0) > 86400:
                logger_manager.trends_logger.info("古い進捗データを無視します")
                return {}, []
            
            self.failed_keywords = set(data.get("failed", []))
            logger_manager.trends_logger.info(
                f"進捗を読み込みました: {len(data['completed'])}件完了, {len(data['remaining'])}件残り"
            )
            return data["completed"], data["remaining"]
        except Exception as e:
            logger_manager.trends_logger.warning(f"進捗ファイルの読み込みに失敗: {e}")
            return {}, []
    
    async def get_bulk_trends(self, keywords: List[str]) -> Dict[str, Optional[float]]:
        """
        複数キーワードのトレンドスコアを非同期で取得。
        
        Args:
            keywords: トレンドを取得するキーワードのリスト
            
        Returns:
            キーワードとトレンドスコアのマッピング辞書
        """
        # 進捗を確認
        saved_results, saved_remaining = self._load_progress()
        
        # 新しいキーワードリストと保存された残りを統合
        all_keywords = set(keywords)
        completed_keywords = set(saved_results.keys())
        remaining_keywords = list(all_keywords - completed_keywords)
        
        results = saved_results.copy()
        
        if not remaining_keywords:
            logger_manager.trends_logger.info("すべてのキーワードが既に処理済みです")
            # 完了後は進捗ファイルを削除
            if os.path.exists(self.progress_file):
                os.remove(self.progress_file)
            return {k: results.get(k) for k in keywords}
        
        # より小さなバッチサイズと長い遅延
        batch_size = 3
        batches = [remaining_keywords[i:i + batch_size] for i in range(0, len(remaining_keywords), batch_size)]
        
        for batch_idx, batch in enumerate(batches):
            if batch_idx > 0:
                # バッチ間により長い遅延
                batch_delay = min(10.0 + batch_idx * 2, 30.0)  # 徐々に遅延を増やす
                logger_manager.trends_logger.info(
                    f"バッチ {batch_idx + 1}/{len(batches)} 開始前に{batch_delay}秒待機"
                )
                await asyncio.sleep(batch_delay)
            
            tasks = []
            for keyword in batch:
                task = asyncio.create_task(self._get_single_trend_score(keyword))
                tasks.append((keyword, task))
            
            for keyword, task in tasks:
                try:
                    score = await task
                    results[keyword] = score
                except TrendQuotaExceededError:
                    logger_manager.trends_logger.error(
                        f"クォータ超過のためトレンド収集を停止します（処理済み: {len(results)}/{len(all_keywords)}件）"
                    )
                    # 今後のリクエストを制限
                    self.request_count = self.hourly_limit
                    # 残りのタスクをキャンセル
                    for remaining_keyword, remaining_task in tasks:
                        if not remaining_task.done():
                            remaining_task.cancel()
                            self.failed_keywords.add(remaining_keyword)
                    # 残りのバッチも追跡
                    remaining_unprocessed = []
                    for remaining_batch in batches[batch_idx + 1:]:
                        for remaining_keyword in remaining_batch:
                            self.failed_keywords.add(remaining_keyword)
                            remaining_unprocessed.append(remaining_keyword)
                    
                    # 進捗を保存
                    self._save_progress(results, remaining_unprocessed)
                    
                    # リクエストされたキーワードの結果を返す
                    return {k: results.get(k) for k in keywords}
                except Exception as e:
                    logger_manager.error_logger.error(
                        f"{keyword}のトレンド取得に失敗しました: {e}"
                    )
                    results[keyword] = None
                    self.failed_keywords.add(keyword)
            
            # 各バッチ後に進捗を保存
            if batch_idx % 5 == 4:  # 5バッチごとに保存
                remaining_unprocessed = []
                for future_batch in batches[batch_idx + 1:]:
                    remaining_unprocessed.extend(future_batch)
                self._save_progress(results, remaining_unprocessed)
        
        # 完了後のクリーンアップ
        if os.path.exists(self.progress_file):
            os.remove(self.progress_file)
        
        success_count = sum(1 for k in keywords if k in results and results.get(k) is not None)
        logger_manager.trends_logger.info(
            f"トレンド取得完了: 成功 {success_count}/{len(keywords)}件"
        )
        
        # リクエストされたキーワードの結果のみ返す
        return {k: results.get(k) for k in keywords}
    
    def get_trends_sync(self, keywords: List[str]) -> Dict[str, Optional[float]]:
        """get_bulk_trendsの同期ラッパー。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.get_bulk_trends(keywords))
        finally:
            loop.close()


trends_manager = GoogleTrendsManager()