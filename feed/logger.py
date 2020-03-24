import logging
import sys
import os

logger = logging.getLogger(__name__)
ch = logging.StreamHandler(stream=sys.stderr)
ch.setLevel(os.getenv("LOG_LEVEL", "INFO"))

logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
logger.addHandler(ch)

def getLogger(name, toFile=False):
    logger = logging.getLogger(name)


    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s -%(message)s')
    ch.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    ch.setFormatter(formatter)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    logger.addHandler(ch)
    if not os.path.exists('/tmp/logs/'):
        os.mkdir('/tmp/logs')
    if toFile:
        fileHandler = logging.FileHandler(f'/tmp/logs/{name}.log')
        fileHandler.setFormatter(formatter)
        fileHandler.setLevel(os.getenv('FILE_LOGLEVEL', 'INFO'))
        logger.addHandler(fileHandler)
    return logger


