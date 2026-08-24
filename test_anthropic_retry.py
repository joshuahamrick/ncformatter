#!/usr/bin/env python3
"""Checks that sampling parameters survive the anthropic-sdk 1.0 signature change.

Run: python test_anthropic_retry.py
"""
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent / "api"))

os.environ["ANTHROPIC_RATE_LIMIT_RETRIES"] = "3"
os.environ["ANTHROPIC_RATE_LIMIT_BASE_SEC"] = "0.5"

import anthropic_retry


FAILURES = []


def check(name, condition, detail=''):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


class _Recorder:
    """Base fake client; subclasses mimic each SDK's create() signature."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def _record(self, kwargs):
        self.calls.append(kwargs)
        return "response"


class OldSdkClient(_Recorder):
    """anthropic < 1.0 — create() accepts temperature directly."""

    def create(self, *, model, max_tokens, messages, system=None,
               temperature=None, top_p=None, top_k=None, extra_body=None):
        return self._record({
            'model': model, 'max_tokens': max_tokens, 'messages': messages,
            'system': system, 'temperature': temperature,
            'top_p': top_p, 'top_k': top_k, 'extra_body': extra_body,
        })


class NewSdkClient(_Recorder):
    """anthropic >= 1.0 — temperature removed; TypeError if passed."""

    def create(self, *, model, max_tokens, messages, system=None,
               extra_body=None, thinking=None, output_config=None):
        return self._record({
            'model': model, 'max_tokens': max_tokens, 'messages': messages,
            'system': system, 'extra_body': extra_body,
        })


class RejectingClient(NewSdkClient):
    """New SDK where the model itself 400s on non-default sampling values."""

    def create(self, *, model, max_tokens, messages, system=None,
               extra_body=None, thinking=None, output_config=None):
        if (extra_body or {}).get('temperature') is not None:
            raise RuntimeError(
                "Error code: 400 - {'type':'invalid_request_error',"
                "'message':'temperature is not supported by this model'}"
            )
        return super().create(model=model, max_tokens=max_tokens,
                              messages=messages, system=system,
                              extra_body=extra_body)


class RateLimitedClient(NewSdkClient):
    """Fails with a 429 once, then succeeds."""

    def __init__(self, failures=1):
        super().__init__()
        self.remaining = failures

    def create(self, *, model, max_tokens, messages, system=None,
               extra_body=None, thinking=None, output_config=None):
        if self.remaining > 0:
            self.remaining -= 1
            raise RuntimeError("Error code: 429 - rate_limit_error")
        return super().create(model=model, max_tokens=max_tokens,
                              messages=messages, system=system,
                              extra_body=extra_body)


BASE = dict(model='claude-sonnet-4-6', max_tokens=100,
            messages=[{'role': 'user', 'content': 'hi'}], system='sys')

print("Old SDK (temperature is a real parameter):")
c = OldSdkClient()
anthropic_retry.messages_create_with_retries(c, temperature=0, **BASE)
check("temperature passed as a direct kwarg", c.calls[0]['temperature'] == 0, c.calls[0])
check("extra_body left alone", c.calls[0]['extra_body'] is None, c.calls[0])

print("New SDK (temperature removed from the signature):")
c = NewSdkClient()
anthropic_retry.messages_create_with_retries(c, temperature=0, **BASE)
check("no TypeError raised", len(c.calls) == 1)
check("temperature routed through extra_body",
      c.calls[0]['extra_body'] == {'temperature': 0}, c.calls[0])

print("New SDK with top_p/top_k and a caller-supplied extra_body:")
c = NewSdkClient()
anthropic_retry.messages_create_with_retries(
    c, temperature=0, top_p=0.9, extra_body={'custom': 1}, **BASE)
check("all sampling params moved, custom key kept",
      c.calls[0]['extra_body'] == {'custom': 1, 'temperature': 0, 'top_p': 0.9},
      c.calls[0])

print("Model rejects sampling parameters:")
c = RejectingClient()
anthropic_retry.messages_create_with_retries(c, temperature=0, **BASE)
check("retried without sampling params instead of failing", len(c.calls) == 1, c.calls)
check("retry carried no temperature",
      not (c.calls[0]['extra_body'] or {}), c.calls[0])

print("Rate limit handling still works:")
c = RateLimitedClient()
anthropic_retry.messages_create_with_retries(c, temperature=0, **BASE)
check("succeeded after a 429 retry", len(c.calls) == 1, c.calls)

print("Non-sampling errors still propagate:")


class BrokenClient(NewSdkClient):
    def create(self, *, model, max_tokens, messages, system=None,
               extra_body=None, thinking=None, output_config=None):
        raise RuntimeError("Error code: 500 - internal server error")


try:
    anthropic_retry.messages_create_with_retries(BrokenClient(), temperature=0, **BASE)
    check("unrelated error raised", False, "no exception")
except RuntimeError as e:
    check("unrelated error raised", "500" in str(e))

print("Detection against the installed SDK:")
try:
    import anthropic
    real = anthropic.Anthropic(api_key="not-a-real-key")
    accepts = anthropic_retry._accepts_sampling_kwargs(real)
    major = int(anthropic.__version__.split('.')[0])
    expected = major < 1
    check(f"anthropic {anthropic.__version__} detected correctly "
          f"(accepts temperature={accepts})", accepts == expected)
except ImportError:
    print("  SKIP  anthropic not installed")

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
    sys.exit(1)
print("All checks passed.")
