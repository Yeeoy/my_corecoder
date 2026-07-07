import logging
import sys
from pathlib import Path


def setup_logging(level: int = logging.INFO, log_file: str | None = None) -> None:
    # 获取 root logger
    root_logger = logging.getLogger()
    # 2. 防止重复添加 handler
    root_logger.handlers.clear()

    # 构建 handler
    if log_file is None:
        handler = logging.StreamHandler(stream=sys.stderr)
    else:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")

    # 3. 创建格式化器
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)

    # 4. 绑定格式 添加 root 设置日志级别
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
