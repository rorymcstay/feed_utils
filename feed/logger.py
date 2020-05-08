import logging
import sys
import os

logger = logging.getLogger(__name__)
ch = logging.StreamHandler(stream=sys.stderr)
ch.setLevel(os.getenv("LOG_LEVEL", "INFO"))

logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

def getLogger(name, toFile=False):
    logger = logging.getLogger(name)
    feedLogger = logging.getLogger('feed')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s -%(message)s |%(filename)s:%(lineno)d')
    ch.setLevel(os.getenv("LOG_LEVEL", "DEBUG"))
    ch.setFormatter(formatter)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

    # logger.addHandler(ch)
    if not os.path.exists('/tmp/logs/'):
        os.mkdir('/tmp/logs')
    if toFile:
        fileHandler = logging.FileHandler(f'/tmp/logs/{name}.log')
        fileHandler.setFormatter(formatter)
        fileHandler.setLevel(os.getenv('FILE_LOGLEVEL', 'INFO'))
        logger.addHandler(fileHandler)
    feedLogger.addHandler(ch)
    return logger

def initialiseSrcLogger():
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setLevel(os.getenv("LOG_LEVEL", "DEBUG"))
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s -%(message)s |%(filename)s:%(lineno)d')
    handler.setFormatter(formatter)
    srcLogger = logging.getLogger('src.main')
    srcLogger.addHandler(handler)


