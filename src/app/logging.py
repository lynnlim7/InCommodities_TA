"""Logging configuration for the power position tool."""

import logging


def configure_logging(
    level: int = logging.INFO,
) -> None:

    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s: "
            "%(message)s"
        ),
    )