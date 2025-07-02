"""FastAPIアプリケーションエントリーポイント。"""
import os
import signal
import sys
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from api_routes import router
from logger import logger_manager

load_dotenv()

# グローバル変数でサーバーインスタンスを保持
server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフサイクルマネージャー。"""
    logger_manager.access_logger.info("キーワードメトリクスバッチAPIを起動しています")
    yield
    logger_manager.access_logger.info("キーワードメトリクスバッチAPIをシャットダウンしています")


app = FastAPI(
    title="キーワードメトリクスバッチAPI",
    description="キーワードリサーチ用のGoogle AdsとTrendsメトリクスバッチAPI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """グローバル例外ハンドラー。"""
    logger_manager.log_error(f"Unhandled exception: {exc}")
    return {"detail": "内部サーバーエラー"}, 500


def signal_handler(signum, frame):
    """シグナルハンドラー: Ctrl+Cで確実に終了する。"""
    logger_manager.access_logger.info("Ctrl+Cを受信しました。APIを終了します...")
    
    # サーバーが存在する場合は停止
    if server:
        server.should_exit = True
    
    # プロセスを終了
    sys.exit(0)


if __name__ == "__main__":
    # シグナルハンドラーを設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    workers = int(os.getenv("API_WORKERS", "1"))
    
    try:
        # workers=1の場合のみサーバーインスタンスを制御可能
        if workers == 1:
            config = uvicorn.Config(
                "main:app",
                host=host,
                port=port,
                reload=False,
                log_config=None
            )
            server = uvicorn.Server(config)
            server.run()
        else:
            # 複数ワーカーの場合は通常の起動
            uvicorn.run(
                "main:app",
                host=host,
                port=port,
                workers=workers,
                reload=False,
                log_config=None
            )
    except KeyboardInterrupt:
        logger_manager.access_logger.info("KeyboardInterruptを受信しました。")
    except Exception as e:
        logger_manager.error_logger.error(f"予期しないエラー: {e}")
    finally:
        logger_manager.access_logger.info("APIを完全に終了しました。")
        sys.exit(0)