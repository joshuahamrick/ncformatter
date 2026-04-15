"""Shared Anthropic client.messages.create with exponential backoff on 429 / rate limits."""
from __future__ import annotations

import os
import random
import time
from typing import Any


def _is_rate_limit_error(exc: BaseException) -> bool:
	s = str(exc).lower()
	if "429" in str(exc):
		return True
	if "rate_limit" in s or "rate limit" in s or "too many requests" in s:
		return True
	name = type(exc).__name__
	if "RateLimit" in name or "rate_limit" in name:
		return True
	return False


def messages_create_with_retries(client: Any, **kwargs: Any) -> Any:
	"""
	Call client.messages.create(**kwargs), retrying on token TPM / rate limits.

	Env:
	  ANTHROPIC_RATE_LIMIT_RETRIES — max attempts (default 6)
	  ANTHROPIC_RATE_LIMIT_BASE_SEC — initial backoff seconds (default 3)
	"""
	attempts = max(1, int(os.environ.get("ANTHROPIC_RATE_LIMIT_RETRIES", "6")))
	base = max(0.5, float(os.environ.get("ANTHROPIC_RATE_LIMIT_BASE_SEC", "3")))
	last: BaseException | None = None
	for i in range(attempts):
		try:
			return client.messages.create(**kwargs)
		except BaseException as e:
			last = e
			if not _is_rate_limit_error(e) or i >= attempts - 1:
				raise
			delay = min(120.0, base * (2**i) + random.uniform(0, 1.5))
			print(
				f"Anthropic rate limit (attempt {i + 1}/{attempts}); "
				f"sleeping {delay:.1f}s then retrying..."
			)
			time.sleep(delay)
	raise last  # pragma: no cover
