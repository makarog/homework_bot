class SendMessageException(Exception):
    """Ошибка отправки сообщения."""


class GetAPIAnswerException(Exception):
    """Ошибка, эндпойнт не доступен."""


class CheckResponseException(Exception):
    """Ошибка доступа по заданному эндпойнту."""


class ParseStatusException(Exception):
    """Передан неизвестный статус работы."""


class GlobalsError(Exception):
    """Ошибка, если есть пустые глобальные переменные."""
