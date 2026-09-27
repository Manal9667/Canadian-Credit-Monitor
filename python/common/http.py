"""Shared HTTP settings for ingestion.

Security posture:
  * TLS certificate verification is ON by default (secure).
  * `requests` already honours the standard REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE
    environment variables when verification is on, so users behind a corporate
    proxy can point at their own CA bundle without code changes.
  * As a documented last resort for locked-down networks that perform TLS
    inspection with an untrusted root, verification can be explicitly disabled
    by setting SSL_VERIFY=false. This is opt-in only and emits a warning.
"""
from __future__ import annotations

import os
import warnings
from functools import lru_cache

from .logging_utils import get_logger

logger = get_logger("common.http")


@lru_cache(maxsize=1)
def ssl_verify():
    """Return the value to pass as requests' `verify` argument.

    Returns True (default, secure) or False (explicit opt-out). When a custom
    bundle path is provided via REQUESTS_CA_BUNDLE, requests uses it
    automatically while verify stays True.
    """
    setting = os.getenv("SSL_VERIFY", "true").strip().lower()
    if setting in {"false", "0", "no", "off"}:
        logger.warning(
            "SSL_VERIFY is disabled via environment. This is intended only for "
            "restricted networks performing TLS inspection. Do not use in production."
        )
        # Silence the repeated urllib3 warning once we have logged our own.
        try:
            from urllib3.exceptions import InsecureRequestWarning

            warnings.simplefilter("ignore", InsecureRequestWarning)
        except Exception:  # pragma: no cover - urllib3 always present with requests
            pass
        return False
    return True
