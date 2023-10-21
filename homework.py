import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv
from pathlib import Path

import exceptions
from settings import ENDPOINT, HOMEWORK_VERDICTS, RETRY_PERIOD

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s - %(funcName)s:%(lineno)d'
)
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    TOKENS = (
        'PRACTICUM_TOKEN',
        'TELEGRAM_TOKEN',
        'TELEGRAM_CHAT_ID',
        'ENDPOINT'
    )
    missing_tokens = []

    for key in TOKENS:
        if globals().get(key) is None:
            missing_tokens.append(key)

    if missing_tokens:
        missing_tokens_str = ', '.join(missing_tokens)
        raise Exception(f'Недостающие переменные: {missing_tokens_str}')


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        logging.debug(f'Бот отправил сообщение: "{message}"')
        return bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError as error:
        raise exceptions.SendMessageException(error)


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API сервиса Практикум.Домашка."""
    current_timestamp = timestamp or int(time.time())
    params = {'from_date': current_timestamp}
    try:
        homework_verdicts = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params
        )
    except Exception as error:
        message = f'Эндпоинт {ENDPOINT} недоступен: {error}'
        logger.error(message)
        raise exceptions.GetAPIAnswerException(message)
    if homework_verdicts.status_code != HTTPStatus.OK:
        message = f'Код ответа API: {homework_verdicts.status_code}'
        logger.error(message)
        raise exceptions.GetAPIAnswerException(message)
    try:
        return homework_verdicts.json()
    except Exception as error:
        message = f'Ошибка преобразования к формату json: {error}'
        logger.error(message)
        raise exceptions.GetAPIAnswerException(message)


def check_response(response):
    """Проверяет корректность данных, запрошенных от API Практикум.Домашка."""
    if not isinstance(response, dict):
        message = (
            f'Тип данных в ответе от API не соотвествует ожидаемому.'
            f' Получен: {type(response)}'
        )
        logger.error(message)
        raise TypeError(message)

    error_messages = [
        ('homeworks', 'Ключ homeworks недоступен'),
        ('current_date', 'Ключ current_date недоступен')
    ]

    for key, error_message in error_messages:
        if key not in response:
            logger.error(error_message)
            raise exceptions.CheckResponseException(error_message)

    homeworks_list = response['homeworks']
    if not isinstance(homeworks_list, list):
        message = (
            f'В ответе от API домашки приходят не в виде списка. '
            f'Получен: {type(homeworks_list)}'
        )
        logger.error(message)
        raise TypeError(message)
    return homeworks_list


def parse_status(homework):
    """Извлекает из информации о конкретной домашке её статус."""
    if 'homework_name' not in homework:
        message = 'Ключ homework_name недоступен'
        logger.error(message)
        raise KeyError(message)

    if 'status' not in homework:
        message = 'Ключ status недоступен'
        logger.error(message)
        raise KeyError(message)

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS[homework_status]
        return (
            f'Изменился статус проверки работы '
            f'"{homework_name}". {verdict}'
        )
    raise exceptions.ParseStatusException(
        f'Передан неизвестный статус домашней работы "{homework_status}"'
    )


def initialize_logging():
    """Инициализирует настройки логирования."""
    logging.basicConfig(
        level=logging.DEBUG,
        filename=Path('main.log'),
        filemode='w'
    )


def process_homework(
    bot, homework,
    previous_status,
    previous_name,
    previous_error
):
    """Обрабатывает информацию о домашней работе отправляет сообщение."""
    homework_status = parse_status(homework)
    homework_name = homework['homework_name']

    if (
        previous_status == homework_status
        and previous_name == homework_name
    ):
        logger.info(homework_status)
    else:
        previous_status = homework_status
        previous_name = homework_name

        if previous_error:
            send_message(bot, previous_error)
            previous_error = None

        send_message(bot, homework_status)

    return previous_status, previous_name, previous_error


def main():
    """Основная логика работы бота."""
    try:
        check_tokens()
    except Exception as error:
        logger.critical(str(error))
        sys.exit(1)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    initialize_logging()

    timestamp = int(time.time())
    previous_status = None
    previous_error = None
    previous_name = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            timestamp = response.get('current_date')
            if not homeworks:
                logger.info('Статус не обновлен')
            else:
                for homework in homeworks:
                    (
                        previous_status,
                        previous_name,
                        previous_error
                    ) = process_homework(
                        bot, homework,
                        previous_status,
                        previous_name,
                        previous_error
                    )

        except exceptions.SendMessageException as error:
            message = f'Ошибка отправки сообщения: {error}'
            logger.error(message)
            if 'API Telegram недоступно' in str(error):
                continue
            previous_error = message
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            previous_error = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        filename=Path('main.log'),
        filemode='w'
    )
    main()
