# core/rate_limit.py
"""
Thread-safe rate limiter and smart key scheduler for Gemini Pro TABLE MODE.

Behavior:
- Each API key has its own last-used timestamp and penalty cooldown.
- The "per-key cooldown" is computed as: base_interval / num_keys.
  - base_interval defaults to 60 seconds (i.e. 60 rpm per key).
  - So with more keys the effective wait per key is smaller.
- acquire_key_for_table_mode(keys) returns a key that is ready to use, waiting if necessary.
- penalize_key(key) increases the cooldown for keys that triggered a rate-limit error.
- safe_use(key) marks the key as used (updates last-used timestamp).
"""

import time
import threading
import math
import logging

logger = logging.getLogger(__name__)

# default - per-key allowed requests per minute (typical cap we assume)
_DEFAULT_PER_KEY_RPM = 60.0

# penalty multiplier when a key triggers a rate-limit error
_DEFAULT_PENALTY_MULTIPLIER = 4.0

# internal lock for thread-safety
_lock = threading.Lock()

# per-key metadata
_key_meta = {}  # key -> {"last_used": float, "penalty": float, "fail_count": int}


def _now():
    return time.time()


def _ensure_key(key: str):
    if key not in _key_meta:
        _key_meta[key] = {"last_used": 0.0, "penalty": 1.0, "fail_count": 0}


def set_per_key_rpm(rpm: float):
    """If you want to override the assumed per-key RPM, call this early."""
    global _DEFAULT_PER_KEY_RPM
    try:
        v = float(rpm)
        if v > 0:
            _DEFAULT_PER_KEY_RPM = v
    except Exception:
        pass


def penalize_key(key: str, multiplier: float = _DEFAULT_PENALTY_MULTIPLIER):
    """Increase the penalty for a key (called when server responds with rate-limit)."""
    with _lock:
        _ensure_key(key)
        _key_meta[key]["fail_count"] += 1
        # increase penalty multiplicatively but cap
        _key_meta[key]["penalty"] = min(_key_meta[key].get("penalty", 1.0) * multiplier, 60.0)
        logger.warning(f"RateLimit: penalized key {key[:6]}..., new penalty={_key_meta[key]['penalty']:.1f}s")


def safe_use(key: str):
    """Mark key as used at current time (resets penalty decay slowly)."""
    with _lock:
        _ensure_key(key)
        _key_meta[key]["last_used"] = _now()
        # slowly decay penalty toward 1.0 (on successful calls)
        current = _key_meta[key].get("penalty", 1.0)
        new_penalty = max(1.0, current * 0.85)
        _key_meta[key]["penalty"] = new_penalty


def get_ready_time_for_key(key: str, keys_count: int):
    """
    Compute earliest timestamp when this key becomes available.
    Interval formula:
      interval = (60.0 / base_rpm) * penalty / max(1, keys_count)
    So adding keys reduces per-key wait.
    """
    with _lock:
        _ensure_key(key)
        last = _key_meta[key]["last_used"]
        penalty = _key_meta[key].get("penalty", 1.0)
    per_key_interval = 60.0 / _DEFAULT_PER_KEY_RPM
    # effective interval scaled inversely with keys_count
    effective_interval = (per_key_interval * penalty) / max(1, keys_count)
    return last + effective_interval


def acquire_key_for_table_mode(keys: list, max_wait: float = 60.0):
    """
    Choose the best key and block (sleep) until it is ready.
    - keys: list of API keys (strings)
    - max_wait: maximum seconds to wait in total before returning the best candidate anyway

    Returns (key, waited_seconds)
    """
    if not keys:
        return None, 0.0

    start = _now()
    keys = list(keys)
    # dedupe and preserve order (config order preferred)
    seen = set()
    keys = [k for k in keys if not (k in seen or seen.add(k))]

    while True:
        with _lock:
            now = _now()
            ready_list = []
            soonest_key = None
            soonest_time = float("inf")

            for k in keys:
                _ensure_key(k)
                rt = get_ready_time_for_key(k, len(keys))
                if rt <= now:
                    ready_list.append((k, rt))
                if rt < soonest_time:
                    soonest_time = rt
                    soonest_key = k

            if ready_list:
                # pick least recently used among ready ones
                ready_list.sort(key=lambda x: _key_meta[x[0]]["last_used"])
                chosen = ready_list[0][0]
                _key_meta[chosen]["last_used"] = now
                logger.debug(f"RateLimit: returning ready key {chosen[:6]}...")
                return chosen, (now - start)

            # none ready yet: compute wait for the earliest to be ready
            wait_for = soonest_time - now
            remaining_budget = max_wait - (now - start)
            if remaining_budget <= 0:
                # budget exhausted: return the soonest_key (without waiting)
                logger.debug("RateLimit: wait budget exhausted, returning soonest key immediately")
                _key_meta[soonest_key]["last_used"] = now
                return soonest_key, (now - start)

        # Sleep a small amount (bounded)
        sleep_for = min(wait_for, 1.0)
        if sleep_for <= 0:
            sleep_for = min(0.2, remaining_budget)
        logger.debug(f"RateLimit: sleeping {sleep_for:.2f}s waiting for key readiness...")
        time.sleep(sleep_for)

        # loop and re-evaluate


def get_status_snapshot():
    """Return a simple snapshot for diagnostics."""
    with _lock:
        snap = {}
        for k, v in _key_meta.items():
            snap[k[:8] + "..."] = dict(v)
        return snap
