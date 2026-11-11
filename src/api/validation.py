"""Чтение и разбор тела запроса /predict.

Порядок: Content-Type -> размер тела (потоково) -> строгий JSON.
Модель на этих шагах не вызывается.
"""

import json

from src.api.errors import ApiError

JSON_MEDIA_TYPE = "application/json"


def check_content_type(request):
    """Принимается только application/json в UTF-8."""
    raw = request.headers.get("content-type", "")
    media_type, _, params = raw.partition(";")
    if media_type.strip().lower() != JSON_MEDIA_TYPE:
        raise ApiError(
            415, "unsupported_media_type", "Поддерживается только application/json."
        )
    for param in params.split(";"):
        name, _, value = param.partition("=")
        charset = value.strip().strip('"').lower()
        if name.strip().lower() == "charset" and charset not in ("utf-8", "utf8"):
            raise ApiError(
                415, "unsupported_media_type", "Поддерживается только UTF-8."
            )


def _too_large(max_bytes):
    return ApiError(
        413, "body_too_large", f"Тело запроса превышает {max_bytes} байт."
    )


async def read_body_limited(request, max_bytes):
    """Читает тело по частям и обрывает чтение при превышении лимита.

    Content-Length — только ранняя проверка: при chunked-передаче его нет,
    поэтому основной контроль — подсчёт фактически полученных байтов.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        if not (declared.isascii() and declared.isdigit()):
            raise ApiError(
                400, "invalid_content_length", "Некорректный Content-Length."
            )
        if int(declared) > max_bytes:
            raise _too_large(max_bytes)

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise _too_large(max_bytes)
    return bytes(body)


def _reject_constant(name):
    # json по умолчанию принимает NaN, Infinity, -Infinity — запрещаем
    raise ValueError(f"Недопустимое значение {name}.")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Повторяющийся ключ.")
        result[key] = value
    return result


def parse_json(body):
    try:
        return json.loads(
            body.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_keys,
        )
    except (ValueError, RecursionError):
        # ValueError включает JSONDecodeError и UnicodeDecodeError;
        # RecursionError — слишком глубокая вложенность ([[[[...]]]])
        raise ApiError(
            400,
            "invalid_json",
            "Тело должно быть корректным JSON в UTF-8 "
            "без NaN/Infinity и повторяющихся ключей.",
        ) from None


async def read_json_payload(request, max_bytes):
    check_content_type(request)
    body = await read_body_limited(request, max_bytes)
    return parse_json(body)

