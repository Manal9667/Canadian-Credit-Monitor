"""Entry point: validate the latest Statistics Canada raw snapshot."""
from __future__ import annotations

from ..common.logging_utils import get_logger
from .engine import validate_source

logger = get_logger("validation.statistics_canada")

SOURCE = "statistics_canada"


def main() -> None:
    results, summary = validate_source(SOURCE)
    for r in results:
        logger.info("[%s] %s -> %s (%s affected)", r.status, r.rule, r.severity, r.records_affected)
    if summary["checks_failed"]:
        logger.error("%s has %s failing check(s).", SOURCE, summary["checks_failed"])


if __name__ == "__main__":
    main()
