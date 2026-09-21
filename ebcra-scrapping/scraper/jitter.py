import logging
import random
import time

logger = logging.getLogger(__name__)


def jittered_delay(max_minutes: float, label: str = "run") -> None:
    """Sleep a random duration in [0, max_minutes] before proceeding.

    Meant to de-align a scheduled trigger from a fixed clock minute, so a
    recurring hit against a bot-sensitive target doesn't look like a
    metronomic, obviously-automated pattern. No-op if max_minutes <= 0.

    Deliberately not applied inside scraper/playwright_base.py itself —
    it's a per-caller decision, not a blanket policy for every
    Playwright-based scraper.
    """
    if max_minutes <= 0:
        return
    delay_seconds = random.uniform(0, max_minutes * 60)
    logger.info(
        "%s: jittering start by %.1f minute(s) before proceeding",
        label, delay_seconds / 60,
    )
    time.sleep(delay_seconds)
