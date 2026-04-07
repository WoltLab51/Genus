import logging as _logging


class Logger:
    """Legacy logger — delegates to Python logging module.

    Deprecated: Use logging.getLogger(__name__) directly in new code.
    """

    @staticmethod
    def log(agent: str, action: str, data=None) -> None:
        _logger = _logging.getLogger(f"genus.legacy.{agent}")
        if data is not None:
            _logger.info("%s | data=%s", action, data)
        else:
            _logger.info("%s", action)