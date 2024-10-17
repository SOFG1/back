from app.custom_logging import get_logger


def file_expiration_job() -> None:
    logger = get_logger("file_expiration")
    logger.info("expiring files not implemented")
