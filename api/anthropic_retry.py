"""Shared Anthropic client.messages.create with exponential backoff on 429 / rate limits."""
from __future__ import annotations

import inspect
import os
import random
import time
from typing import Any

# Sampling parameters that anthropic-sdk-python 1.0.0 removed from the
# generated method signatures. They still exist on the wire, so on 1.0+ we
# forward them through extra_body, which is merged into the request JSON
# as-is and produces a byte-identical request to the old typed kwargs.
SAMPLING_PARAMS = ("temperature", "top_p", "top_k")


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


def _is_sampling_rejection(exc: BaseException) -> bool:
	"""True when the API refused the request *because of* a sampling parameter.

	Newer Claude models reject non-default temperature / top_p / top_k with a
	400 rather than ignoring them, so a model change should degrade to an
	unsampled call instead of taking the whole endpoint down.
	"""
	s = str(exc).lower()
	if not any(p in s for p in SAMPLING_PARAMS):
		return False
	return "400" in str(exc) or "invalid_request" in s or "bad request" in s


def _accepts_sampling_kwargs(client: Any) -> bool:
	"""Whether this SDK version still takes temperature as a direct kwarg."""
	try:
		params = inspect.signature(client.messages.create).parameters
	except (TypeError, ValueError):
		return True
	if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
		return True
	return "temperature" in params


def _adapt_sampling_params(client: Any, kwargs: dict) -> dict:
	"""Move sampling params into extra_body when the SDK no longer accepts them."""
	present = [p for p in SAMPLING_PARAMS if p in kwargs]
	if not present or _accepts_sampling_kwargs(client):
		return kwargs
	adapted = dict(kwargs)
	extra_body = dict(adapted.get("extra_body") or {})
	for name in present:
		value = adapted.pop(name)
		extra_body.setdefault(name, value)
	adapted["extra_body"] = extra_body
	return adapted


def _strip_sampling_params(kwargs: dict) -> dict | None:
	"""Drop sampling params entirely; None when there were none to drop."""
	extra_body = dict(kwargs.get("extra_body") or {})
	present = [p for p in SAMPLING_PARAMS if p in kwargs or p in extra_body]
	if not present:
		return None
	stripped = {k: v for k, v in kwargs.items() if k not in SAMPLING_PARAMS}
	for name in SAMPLING_PARAMS:
		extra_body.pop(name, None)
	if extra_body:
		stripped["extra_body"] = extra_body
	else:
		stripped.pop("extra_body", None)
	return stripped


def _create_with_rate_limit_retries(client: Any, kwargs: dict) -> Any:
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


def messages_create_with_retries(client: Any, **kwargs: Any) -> Any:
	"""
	Call client.messages.create(**kwargs), retrying on token TPM / rate limits.

	Sampling parameters (temperature / top_p / top_k) are routed to suit the
	installed SDK version, and dropped on a retry if the model rejects them.

	Env:
	  ANTHROPIC_RATE_LIMIT_RETRIES — max attempts (default 6)
	  ANTHROPIC_RATE_LIMIT_BASE_SEC — initial backoff seconds (default 3)
	"""
	adapted = _adapt_sampling_params(client, kwargs)
	try:
		return _create_with_rate_limit_retries(client, adapted)
	except BaseException as e:
		if not _is_sampling_rejection(e):
			raise
		stripped = _strip_sampling_params(adapted)
		if stripped is None:
			raise
		print(f"Anthropic rejected sampling parameters ({e}); retrying without them...")
		return _create_with_rate_limit_retries(client, stripped)
