"""RedisサポートとPickleファイルフォールバックを持つキャッシュモジュール。"""
import json
import os
import pickle
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional, Union

import redis
from dotenv import load_dotenv

from logger import logger_manager

load_dotenv()


class CacheInterface:
    """抽象キャッシュインターフェース。"""
    
    def get(self, key: str) -> Optional[Any]:
        """キャッシュから値を取得。"""
        raise NotImplementedError
    
    def set(self, key: str, value: Any, ttl: int = 86400) -> bool:
        """TTL付きでキャッシュに値を設定。"""
        raise NotImplementedError
    
    def exists(self, key: str) -> bool:
        """キーがキャッシュに存在するか確認。"""
        raise NotImplementedError
    
    def delete(self, key: str) -> bool:
        """キャッシュからキーを削除。"""
        raise NotImplementedError


class RedisCache(CacheInterface):
    """Redisベースのキャッシュ実装。"""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None
    ) -> None:
        """Redis接続を初期化。"""
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True
        )
        try:
            self.client.ping()
        except redis.ConnectionError as e:
            logger_manager.error_logger.warning(f"Redis connection failed: {e}")
            raise
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Redisから値を取得。"""
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger_manager.error_logger.error(f"Redis get error: {e}")
            return None
    
    def set(self, key: str, value: Dict[str, Any], ttl: int = 86400) -> bool:
        """TTL付きでRedisに値を設定。"""
        try:
            return bool(self.client.setex(key, ttl, json.dumps(value)))
        except Exception as e:
            logger_manager.error_logger.error(f"Redis set error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """キーがRedisに存在するか確認。"""
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger_manager.error_logger.error(f"Redis exists error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Redisからキーを削除。"""
        try:
            return bool(self.client.delete(key))
        except Exception as e:
            logger_manager.error_logger.error(f"Redis delete error: {e}")
            return False


class PickleCache(CacheInterface):
    """FIFO除去機能付きPickleファイルベースのキャッシュ実装。"""
    
    def __init__(self, cache_file: str = "cache.pkl", max_entries: int = 3000) -> None:
        """Pickleキャッシュを初期化。"""
        self.cache_file = cache_file
        self.max_entries = max_entries
        self._load_cache()
    
    def _load_cache(self) -> None:
        """ファイルからキャッシュを読み込み。"""
        if Path(self.cache_file).exists():
            try:
                with open(self.cache_file, 'rb') as f:
                    self.cache: OrderedDict[str, Dict[str, Any]] = pickle.load(f)
            except Exception as e:
                logger_manager.error_logger.error(f"Failed to load cache: {e}")
                self.cache = OrderedDict()
        else:
            self.cache = OrderedDict()
    
    def _save_cache(self) -> None:
        """キャッシュをファイルに保存。"""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except Exception as e:
            logger_manager.error_logger.error(f"Failed to save cache: {e}")
    
    def _evict_if_needed(self) -> None:
        """キャッシュがmax_entriesを超えた場合、最も古いエントリを除去。"""
        while len(self.cache) >= self.max_entries:
            self.cache.popitem(last=False)
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Pickleキャッシュから値を取得。"""
        if key in self.cache:
            entry = self.cache[key]
            if time.time() < entry['expires_at']:
                self.cache.move_to_end(key)
                return entry['value']
            else:
                del self.cache[key]
                self._save_cache()
        return None
    
    def set(self, key: str, value: Dict[str, Any], ttl: int = 86400) -> bool:
        """TTL付きでPickleキャッシュに値を設定。"""
        try:
            self._evict_if_needed()
            self.cache[key] = {
                'value': value,
                'expires_at': time.time() + ttl
            }
            self.cache.move_to_end(key)
            self._save_cache()
            return True
        except Exception as e:
            logger_manager.error_logger.error(f"Pickle set error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """キーがPickleキャッシュに存在するか確認。"""
        if key in self.cache:
            if time.time() < self.cache[key]['expires_at']:
                return True
            else:
                del self.cache[key]
                self._save_cache()
        return False
    
    def delete(self, key: str) -> bool:
        """Pickleキャッシュからキーを削除。"""
        try:
            if key in self.cache:
                del self.cache[key]
                self._save_cache()
                return True
            return False
        except Exception as e:
            logger_manager.error_logger.error(f"Pickle delete error: {e}")
            return False


class CacheManager:
    """自動フォールバック機能付きキャッシュマネージャー。"""
    
    _instance: Optional['CacheManager'] = None
    
    def __new__(cls) -> 'CacheManager':
        """シングルトンパターンの実装。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        """キャッシュバックエンドを初期化。"""
        if hasattr(self, '_initialized'):
            return
        
        self.ttl = int(os.getenv('CACHE_TTL', '86400'))
        self.cache: CacheInterface
        
        try:
            self.cache = RedisCache(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                db=int(os.getenv('REDIS_DB', '0')),
                password=os.getenv('REDIS_PASSWORD') or None
            )
            logger_manager.access_logger.info("Using Redis cache backend")
        except Exception as e:
            logger_manager.access_logger.warning(
                f"Redis unavailable, falling back to Pickle cache: {e}"
            )
            self.cache = PickleCache(
                max_entries=int(os.getenv('CACHE_MAX_ENTRIES', '3000'))
            )
        
        self._initialized = True
    
    def get_keyword_data(self, keyword: str) -> Optional[Dict[str, Union[int, float]]]:
        """キャッシュからキーワードデータを取得。"""
        cache_key = f"keyword:{keyword}"
        return self.cache.get(cache_key)
    
    def set_keyword_data(
        self,
        keyword: str,
        ads_volume: Optional[int],
        trends_score: Optional[float]
    ) -> bool:
        """キャッシュにキーワードデータを設定。"""
        cache_key = f"keyword:{keyword}"
        value = {
            'googleAdsAvgMonthlySearches': ads_volume,
            'googleTrendsScore': trends_score,
            'cached_at': time.time()
        }
        return self.cache.set(cache_key, value, self.ttl)
    
    def get_batch_data(
        self,
        keywords: list[str]
    ) -> tuple[Dict[str, Dict[str, Union[int, float]]], list[str]]:
        """バッチデータをキャッシュから取得し、キャッシュ済みデータと欠落キーワードを返す。"""
        cached_data = {}
        missing_keywords = []
        
        for keyword in keywords:
            data = self.get_keyword_data(keyword)
            if data:
                cached_data[keyword] = data
            else:
                missing_keywords.append(keyword)
        
        return cached_data, missing_keywords


cache_manager = CacheManager()