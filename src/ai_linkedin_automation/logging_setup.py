import logging
from typing import Optional


def configure_logging(level: str = "INFO", fmt: Optional[str] = None) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format=fmt or "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
