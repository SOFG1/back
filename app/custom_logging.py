import logging

loggers = {}

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(threadName)8s:%(message)s")


def get_logger(name: str) -> logging.Logger:
    if name in loggers:
        return loggers[name]
    logger = logging.getLogger(name)
    loggers[name] = logger
    return logger
