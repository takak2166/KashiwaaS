"""
ロギング設定モジュール
アプリケーション全体で一貫したロギングを提供します
"""
import os
import sys
from pathlib import Path

from loguru import logger

# ログディレクトリの作成
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 環境変数からログレベルと保持期間を取得
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_RETENTION = os.getenv("LOG_RETENTION", "7 days")

# ロガーの設定
logger.remove()  # デフォルトのハンドラを削除

# 標準エラー出力へのログ
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)

# ファイルへのログ
logger.add(
    log_dir / "app.log",
    rotation="1 day",
    retention=LOG_RETENTION,
    level=LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)

# エラーログは別ファイルにも出力
logger.add(
    log_dir / "error.log",
    rotation="1 day",
    retention=LOG_RETENTION,
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8",
)


def get_logger(name):
    """
    名前付きロガーを取得します

    Args:
        name (str): ロガー名（通常はモジュール名）

    Returns:
        loguru.Logger: 設定済みのロガーインスタンス
    """
    return logger.bind(name=name)