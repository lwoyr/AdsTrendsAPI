"""複数ファイル出力とログローテーション機能を持つロガー設定モジュール。"""
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str,
    log_file: str,
    level: int = logging.INFO,
    log_dir: str = "./logs"
) -> logging.Logger:
    """
    TimedRotatingFileHandlerを使用してロガーを設定する。
    
    Args:
        name: ロガー名
        log_file: ログファイル名
        level: ロギングレベル
        log_dir: ログファイルのディレクトリ
        
    Returns:
        設定済みのロガーインスタンス
    """
    Path(log_dir).mkdir(exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if logger.handlers:
        return logger
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, log_file),
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    handler.setFormatter(formatter)
    handler.suffix = "%Y%m%d"
    
    logger.addHandler(handler)
    
    return logger


class LoggerManager:
    """アプリケーション用の集中ロガー管理。"""
    
    _instance: Optional['LoggerManager'] = None
    
    def __new__(cls) -> 'LoggerManager':
        """シングルトンパターンの実装。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        """ロガーインスタンスを初期化。"""
        if hasattr(self, '_initialized'):
            return
        
        log_dir = os.getenv('LOG_DIR', './logs')
        log_level_str = os.getenv('LOG_LEVEL', 'INFO')
        log_level = getattr(logging, log_level_str.upper(), logging.INFO)
        
        self.access_logger = setup_logger('access', 'access.log', log_level, log_dir)
        self.error_logger = setup_logger('error', 'error.log', logging.ERROR, log_dir)
        self.ads_logger = setup_logger('ads', 'ads.log', log_level, log_dir)
        self.trends_logger = setup_logger('trends', 'trends.log', log_level, log_dir)
        
        self._initialized = True
    
    def log_access(
        self,
        method: str,
        path: str,
        status_code: int,
        client_ip: str,
        latency_ms: float
    ) -> None:
        """APIアクセス情報をログに記録。"""
        self.access_logger.info(
            f"method={method} path={path} status={status_code} "
            f"client_ip={client_ip} latency_ms={latency_ms:.2f}"
        )
    
    def log_error(self, message: str, exc_info: bool = True) -> None:
        """エラーをオプションの例外情報と共にログに記録。"""
        self.error_logger.error(message, exc_info=exc_info)
    
    def log_ads_request(
        self,
        keywords_count: int,
        success: bool,
        duration_ms: float,
        error: Optional[str] = None
    ) -> None:
        """Google Ads APIリクエストをログに記録。"""
        status = "success" if success else "failed"
        log_msg = (
            f"keywords_count={keywords_count} status={status} "
            f"duration_ms={duration_ms:.2f}"
        )
        if error:
            log_msg += f" error={error}"
        
        if success:
            self.ads_logger.info(log_msg)
        else:
            self.ads_logger.warning(log_msg)
    
    def log_trends_request(
        self,
        keyword: str,
        success: bool,
        duration_ms: float,
        error: Optional[str] = None
    ) -> None:
        """Google Trendsリクエストをログに記録。"""
        status = "success" if success else "failed"
        log_msg = (
            f"keyword={keyword} status={status} "
            f"duration_ms={duration_ms:.2f}"
        )
        if error:
            log_msg += f" error={error}"
        
        if success:
            self.trends_logger.info(log_msg)
        else:
            self.trends_logger.warning(log_msg)


logger_manager = LoggerManager()