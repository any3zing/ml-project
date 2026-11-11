"""Ограничение параллелизма и времени предсказания.

- Не больше max_concurrent вычислений одновременно; если слот не освободился
  за queue_timeout — 503 busy.
- Ответ ждём не дольше inference_timeout — 504 timeout.

Поток Python нельзя прервать снаружи, поэтому тайм-аут освобождает клиента,
но не вычисление. Слот освобождается в finally внутри потока — только когда
вычисление действительно завершилось. Так число работающих вычислений
никогда не превышает max_concurrent, даже если клиенты бросают запросы.
"""

import asyncio

from src.api.errors import ApiError


def _consume_result(future):
    # Результат вычисления, завершившегося после тайм-аута, никому не нужен;
    # забираем исключение, чтобы asyncio не писал предупреждение
    if not future.cancelled():
        future.exception()


class InferenceLimiter:
    def __init__(self, max_concurrent, queue_timeout, inference_timeout):
        self._slots = asyncio.Semaphore(max_concurrent)
        self._queue_timeout = queue_timeout
        self._inference_timeout = inference_timeout

    async def run(self, func, *args):
        try:
            await asyncio.wait_for(self._slots.acquire(), self._queue_timeout)
        except TimeoutError:
            raise ApiError(
                503, "busy", "Сервис занят, повторите позже.",
                headers={"Retry-After": "1"},
            ) from None

        loop = asyncio.get_running_loop()

        def job():
            try:
                return func(*args)
            finally:
                loop.call_soon_threadsafe(self._slots.release)

        future = loop.run_in_executor(None, job)
        future.add_done_callback(_consume_result)
        try:
            # shield: при тайм-ауте не отменяем future, слот отпустит job()
            return await asyncio.wait_for(
                asyncio.shield(future), self._inference_timeout
            )
        except TimeoutError:
            raise ApiError(504, "timeout", "Превышено время обработки.") from None
