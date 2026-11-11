"""Аутентификация по API-токену и ограничение частоты запросов.

Токен: заголовок Authorization: Bearer <token>. Серверное значение — из
API_TOKEN_FILE или API_TOKEN (не из git и не из образа). Сравнение — за
постоянное время (hmac.compare_digest). Токен не пишется в логи и ответы.

Rate limiting — скользящее окно в памяти процесса:
  * по токену: не больше rate_limit запросов за rate_window секунд;
  * по адресу клиента: после auth_fail_limit неудачных попыток за
    auth_fail_window секунд адрес блокируется до конца окна (подбор токена).
Ограничения: счётчики не общие для нескольких workers и сбрасываются
при перезапуске. X-Forwarded-For не используется: proxy нет, uvicorn
запускается с --no-proxy-headers.
"""

import hashlib
import hmac
import math
import threading
import time
from collections import deque

from src.api.errors import ApiError

MIN_TOKEN_LENGTH = 32
MAX_TRACKED_KEYS = 10_000
WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


class SlidingWindow:
    """Число событий по ключу за последние window секунд."""

    def __init__(self, limit, window, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._events = {}
        self._lock = threading.Lock()

    def _recent(self, key, now):
        events = self._events.get(key)
        if events is None:
            return None
        while events and events[0] <= now - self.window:
            events.popleft()
        if not events:
            del self._events[key]
            return None
        return events

    def _append(self, key, now):
        if len(self._events) >= MAX_TRACKED_KEYS:
            for old_key in list(self._events):  # убрать устаревшие ключи
                self._recent(old_key, now)
        self._events.setdefault(key, deque()).append(now)

    def exceeded(self, key):
        with self._lock:
            events = self._recent(key, self._clock())
            return events is not None and len(events) >= self.limit

    def record(self, key):
        with self._lock:
            now = self._clock()
            self._recent(key, now)
            self._append(key, now)

    def allow(self, key):
        """Учитывает событие, если лимит не исчерпан; иначе False."""
        with self._lock:
            now = self._clock()
            events = self._recent(key, now)
            if events is not None and len(events) >= self.limit:
                return False
            self._append(key, now)
            return True

    def retry_after(self, key):
        """Через сколько секунд освободится место в окне."""
        with self._lock:
            now = self._clock()
            events = self._recent(key, now)
            if not events:
                return 0
            return max(1, math.ceil(events[0] + self.window - now))


def token_key(token_bytes):
    """Ключ лимита: префикс SHA256 токена; сам токен не хранится."""
    return hashlib.sha256(token_bytes).hexdigest()[:12]


def client_address(request):
    return request.client.host if request.client else "unknown"


def _too_many(code, retry_after):
    return ApiError(
        429, code, "Слишком много запросов, повторите позже.",
        headers={"Retry-After": str(retry_after)},
    )


class Guard:
    """Проверка токена и лимитов для /predict (до чтения тела)."""

    def __init__(self, settings):
        token = settings.api_token
        if not token:
            self.problem = "api_token_missing"
        elif len(token) < MIN_TOKEN_LENGTH:
            self.problem = "api_token_too_short"
        else:
            self.problem = None
        self._expected = token.encode() if self.problem is None else None

        self.per_token = SlidingWindow(settings.rate_limit, settings.rate_window)
        self.failed_auth = SlidingWindow(
            settings.auth_fail_limit, settings.auth_fail_window
        )

    @property
    def configured(self):
        return self._expected is not None

    def check(self, request):
        address = client_address(request)
        if self.failed_auth.exceeded(address):
            raise _too_many("auth_blocked", self.failed_auth.retry_after(address))

        header = request.headers.get("authorization")
        if not header:
            self.failed_auth.record(address)
            raise ApiError(
                401, "auth_missing", "Требуется API-токен.",
                headers=WWW_AUTHENTICATE,
            )

        scheme, _, presented = header.partition(" ")
        presented = presented.strip().encode()
        if scheme.lower() != "bearer" or not hmac.compare_digest(
            presented, self._expected
        ):
            self.failed_auth.record(address)
            raise ApiError(
                401, "auth_invalid", "Неверный API-токен.",
                headers=WWW_AUTHENTICATE,
            )

        key = token_key(presented)
        if not self.per_token.allow(key):
            raise _too_many("rate_limited", self.per_token.retry_after(key))
def require_metrics_token(request, expected):
    """Bearer-токен сборщика метрик; отдельный от API-токена."""
    header = request.headers.get("authorization", "")
    scheme, _, presented = header.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        presented.strip().encode(), expected.encode()
    ):
        raise ApiError(
            401, "metrics_unauthorized", "Требуется токен метрик.",
            headers=WWW_AUTHENTICATE,
        )
