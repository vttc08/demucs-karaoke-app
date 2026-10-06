"""Small per-process admission limit for admin password checks."""

import hashlib
import math
import threading
import time
from collections import deque


class LoginAttemptLimiter:
    """Reserve attempts atomically before running an expensive password check."""

    IP_LIMIT = 10
    IP_WINDOW_SECONDS = 60
    ACCOUNT_LIMIT = 20
    ACCOUNT_WINDOW_SECONDS = 300
    MAX_KEYS = 4096

    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def reserve(self, client_ip: str, username: str) -> int:
        """Return zero when admitted, otherwise seconds until another attempt."""
        now = time.monotonic()
        ip_key = ("ip", client_ip)
        with self._lock:
            ip_attempts = self._attempts.get(ip_key)
            if ip_attempts is not None:
                while ip_attempts and ip_attempts[0] <= now - self.IP_WINDOW_SECONDS:
                    ip_attempts.popleft()
                if len(ip_attempts) >= self.IP_LIMIT:
                    return math.ceil(ip_attempts[0] + self.IP_WINDOW_SECONDS - now)

        account = hashlib.sha256(username.strip().casefold().encode("utf-8")).hexdigest()
        limits = (
            (ip_key, self.IP_LIMIT, self.IP_WINDOW_SECONDS),
            (("account", account), self.ACCOUNT_LIMIT, self.ACCOUNT_WINDOW_SECONDS),
        )
        with self._lock:
            retry_after = 0
            for key, limit, window in limits:
                attempts = self._attempts.get(key)
                if attempts is None:
                    continue
                while attempts and attempts[0] <= now - window:
                    attempts.popleft()
                if len(attempts) >= limit:
                    retry_after = max(retry_after, math.ceil(attempts[0] + window - now))
            if retry_after:
                return retry_after

            missing_keys = sum(key not in self._attempts for key, _, _ in limits)
            if len(self._attempts) + missing_keys > self.MAX_KEYS:
                self._attempts = {key: attempts for key, attempts in self._attempts.items() if attempts}
                missing_keys = sum(key not in self._attempts for key, _, _ in limits)
                if len(self._attempts) + missing_keys > self.MAX_KEYS:
                    return self.IP_WINDOW_SECONDS

            for key, _, _ in limits:
                self._attempts.setdefault(key, deque()).append(now)
            return 0

    def clear(self) -> None:
        """Reset process-local history, mainly for isolated tests."""
        with self._lock:
            self._attempts.clear()


login_attempt_limiter = LoginAttemptLimiter()
