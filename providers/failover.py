"""Provider-level failover across independently configured API routes."""

from __future__ import annotations

import hashlib
from random import uniform
from threading import Lock
from time import monotonic, sleep

from .base import ModelProvider


_FAILOVER_LOCK = Lock()
_FAILOVER_COUNTER = 0
_CIRCUIT_LOCK = Lock()
_CIRCUITS = {}


def _next_candidate_slot(size):
    global _FAILOVER_COUNTER
    with _FAILOVER_LOCK:
        slot = _FAILOVER_COUNTER % size
        _FAILOVER_COUNTER += 1
    return slot


def _candidate_identity(candidate):
    """Return a process-local circuit key without exposing a credential."""
    endpoint = getattr(candidate, "endpoint", None)
    model = getattr(candidate, "model", None)
    secrets = []
    api_key = getattr(candidate, "api_key", None)
    if isinstance(api_key, str) and api_key:
        secrets.append(api_key)
    api_keys = getattr(candidate, "api_keys", ())
    if api_keys:
        secrets.extend(api_keys)
    credential_fingerprint = ""
    if secrets:
        digest = hashlib.sha256()
        for secret in secrets:
            digest.update(secret.encode("utf-8"))
            digest.update(b"\0")
        credential_fingerprint = digest.hexdigest()
    if endpoint is None:
        # Test/local providers have no stable route identity and should not share
        # circuit state merely because they use the same Python class.
        return (candidate.__class__.__qualname__, id(candidate))
    return (
        candidate.__class__.__qualname__,
        endpoint,
        model,
        credential_fingerprint,
    )


def _new_circuit_state():
    return {
        "consecutive_failures": 0,
        "open_until": 0.0,
        "open_count": 0,
        "probe_in_flight": False,
    }


def _is_circuit_failure(error):
    """Only transport/overload failures should quarantine an API route."""
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, ConnectionError)):
            return True
        status = getattr(current, "status", None)
        if status in {408, 409, 425, 429, 500, 502, 503, 504}:
            return True
        message = str(current).lower()
        if any(
            marker in message
            for marker in (
                "http 408",
                "http 409",
                "http 425",
                "http 429",
                "http 500",
                "http 502",
                "http 503",
                "http 504",
                "timed out",
                "timeout",
                "temporarily unavailable",
                "overloaded",
                "connection reset",
                "connection refused",
                "remote end closed",
            )
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


class FailoverProvider(ModelProvider):
    """Try healthy routes with bounded backoff and isolated circuit breaking."""

    def __init__(
        self,
        candidates,
        model=None,
        timeout=None,
        max_candidates_per_request=None,
        circuit_failure_threshold=2,
        circuit_cooldown_seconds=300,
        circuit_max_cooldown_seconds=600,
        failover_backoff_base_seconds=0,
        failover_backoff_max_seconds=15,
        failover_backoff_jitter_seconds=0,
        **generation_defaults,
    ):
        self.candidates = tuple(candidates)
        if not self.candidates:
            raise ValueError("failover provider requires at least one candidate")
        self.model = model
        self.timeout = timeout
        if timeout is not None:
            for candidate in self.candidates:
                if hasattr(candidate, "timeout"):
                    candidate.timeout = timeout
        self.max_candidates_per_request = min(
            len(self.candidates),
            max(
                1,
                int(max_candidates_per_request or len(self.candidates)),
            ),
        )
        self.circuit_failure_threshold = max(
            1, int(circuit_failure_threshold)
        )
        self.circuit_cooldown_seconds = max(
            0.0, float(circuit_cooldown_seconds)
        )
        self.circuit_max_cooldown_seconds = max(
            self.circuit_cooldown_seconds,
            float(circuit_max_cooldown_seconds),
        )
        self.failover_backoff_base_seconds = max(
            0.0, float(failover_backoff_base_seconds)
        )
        self.failover_backoff_max_seconds = max(
            self.failover_backoff_base_seconds,
            float(failover_backoff_max_seconds),
        )
        self.failover_backoff_jitter_seconds = max(
            0.0, float(failover_backoff_jitter_seconds)
        )
        # Keep circuit state inside one logical role/trajectory. A bad request
        # must not quarantine the same endpoint for unrelated concurrent jobs.
        self._circuit_scope = object()
        self._candidate_identities = tuple(
            (self._circuit_scope, _candidate_identity(candidate))
            for candidate in self.candidates
        )
        self.generation_defaults = generation_defaults
        self._request_count = 0
        self._failed_request_count = 0
        self._candidate_attempts = {}
        self._candidate_successes = {}
        self._candidate_circuit_skips = {}
        self._circuit_open_events = 0
        self._backoff_seconds = 0.0

    def reset(self):
        self._request_count = 0
        self._failed_request_count = 0
        self._candidate_attempts = {}
        self._candidate_successes = {}
        self._candidate_circuit_skips = {}
        self._circuit_open_events = 0
        self._backoff_seconds = 0.0
        for candidate in self.candidates:
            candidate.reset()

    def _claim_candidate(self, slot):
        identity = self._candidate_identities[slot]
        now = monotonic()
        with _CIRCUIT_LOCK:
            state = _CIRCUITS.setdefault(identity, _new_circuit_state())
            if state["open_until"] > now:
                return False
            half_open = (
                state["open_until"] > 0
                and state["consecutive_failures"]
                >= self.circuit_failure_threshold
            )
            if half_open:
                if state["probe_in_flight"]:
                    return False
                state["probe_in_flight"] = True
            return True

    def _record_candidate_success(self, slot):
        identity = self._candidate_identities[slot]
        with _CIRCUIT_LOCK:
            state = _CIRCUITS.setdefault(identity, _new_circuit_state())
            state.update(_new_circuit_state())

    def _record_candidate_failure(self, slot):
        identity = self._candidate_identities[slot]
        opened = False
        with _CIRCUIT_LOCK:
            state = _CIRCUITS.setdefault(identity, _new_circuit_state())
            was_probe = state["probe_in_flight"]
            state["probe_in_flight"] = False
            state["consecutive_failures"] += 1
            if state["consecutive_failures"] >= self.circuit_failure_threshold:
                if state["open_until"] <= monotonic() or was_probe:
                    state["open_count"] += 1
                multiplier = 2 ** max(0, state["open_count"] - 1)
                cooldown = min(
                    self.circuit_max_cooldown_seconds,
                    self.circuit_cooldown_seconds * multiplier,
                )
                state["open_until"] = monotonic() + cooldown
                opened = True
        if opened:
            self._circuit_open_events += 1

    def _backoff(self, failure_number):
        if self.failover_backoff_base_seconds <= 0:
            return
        delay = min(
            self.failover_backoff_max_seconds,
            self.failover_backoff_base_seconds
            * (2 ** max(0, failure_number - 1)),
        )
        if self.failover_backoff_jitter_seconds:
            delay += uniform(0, self.failover_backoff_jitter_seconds)
        self._backoff_seconds += delay
        sleep(delay)

    def complete(self, messages, **generation):
        options = {**self.generation_defaults, **generation}
        start = _next_candidate_slot(len(self.candidates))
        last_error = None
        attempted = 0
        skipped = 0
        for offset in range(len(self.candidates)):
            if attempted >= self.max_candidates_per_request:
                break
            slot = (start + offset) % len(self.candidates)
            candidate = self.candidates[slot]
            if not self._claim_candidate(slot):
                skipped += 1
                self._candidate_circuit_skips[slot] = (
                    self._candidate_circuit_skips.get(slot, 0) + 1
                )
                continue
            attempted += 1
            self._request_count += 1
            self._candidate_attempts[slot] = (
                self._candidate_attempts.get(slot, 0) + 1
            )
            try:
                content = candidate.complete(messages, **options)
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("provider returned empty content")
            except Exception as exc:
                self._failed_request_count += 1
                if _is_circuit_failure(exc):
                    self._record_candidate_failure(slot)
                else:
                    # Empty/malformed model output means the route answered.
                    # Switch candidates, but do not globally penalize transport.
                    self._record_candidate_success(slot)
                last_error = exc
                if (
                    attempted < self.max_candidates_per_request
                    and offset + 1 < len(self.candidates)
                ):
                    self._backoff(attempted)
                continue
            self._record_candidate_success(slot)
            self._candidate_successes[slot] = (
                self._candidate_successes.get(slot, 0) + 1
            )
            return content
        if last_error is not None:
            raise last_error
        if skipped:
            raise RuntimeError(
                "all failover provider candidates are temporarily circuit-open"
            )
        raise RuntimeError("failover provider candidate pool is empty")

    @property
    def audit_records(self):
        records = []
        for slot, candidate in enumerate(self.candidates):
            for item in getattr(candidate, "audit_records", []):
                records.append({"candidate_slot": slot, **item})
        return records

    @property
    def usage(self):
        totals = {}
        for candidate in self.candidates:
            for key, amount in candidate.usage.items():
                if isinstance(amount, int) and not isinstance(amount, bool):
                    totals[key] = totals.get(key, 0) + amount
        return totals

    @property
    def metrics(self):
        duration = sum(
            candidate.metrics.get("request_duration_seconds", 0.0)
            for candidate in self.candidates
        )
        now = monotonic()
        with _CIRCUIT_LOCK:
            circuit_states = {}
            for slot, identity in enumerate(self._candidate_identities):
                state = _CIRCUITS.get(identity, _new_circuit_state())
                circuit_states[slot] = {
                    "consecutive_failures": state["consecutive_failures"],
                    "cooldown_remaining_seconds": round(
                        max(0.0, state["open_until"] - now), 3
                    ),
                }
        return {
            "request_count": self._request_count,
            "failed_request_count": self._failed_request_count,
            "request_duration_seconds": round(duration, 3),
            "candidate_pool_size": len(self.candidates),
            "max_candidates_per_request": self.max_candidates_per_request,
            "candidate_attempts": dict(self._candidate_attempts),
            "candidate_successes": dict(self._candidate_successes),
            "candidate_circuit_skips": dict(self._candidate_circuit_skips),
            "circuit_open_events": self._circuit_open_events,
            "circuit_states": circuit_states,
            "failover_backoff_seconds": round(self._backoff_seconds, 3),
            "usage": self.usage,
        }

    @property
    def provenance(self):
        return {
            "provider": "failover",
            "model": self.model,
            "candidates": [candidate.provenance for candidate in self.candidates],
        }
