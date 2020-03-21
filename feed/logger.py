import logging
import sys
import os

logger = logging.getLogger(__name__)
ch = logging.StreamHandler(stream=sys.stderr)
ch.setLevel(os.getenv("LOG_LEVEL", "INFO"))

logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
logger.addHandler(ch)

