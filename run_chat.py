import asyncio
from asyncio import StreamReader, StreamWriter, Queue
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import time
from tkinter import Tk, messagebox

import aiofiles
from anyio import create_task_group
from async_timeout import timeout
from configargparse import ArgParser, Namespace

from errors import InvalidTokenError
import gui
from gui import ReadConnectionStateChanged, SendingConnectionStateChanged, \
    NicknameReceived
from socket_utils import connect_to_chat

logger = logging.getLogger(Path(__file__).name)

AUTH_REQUIRED = (
    'Hello %username%! Enter your personal hash '
    'or leave it empty to create new account.'
)

CHAT_GREETING = (
    'Welcome to chat! Post your message below. End it with an empty line.'
)

ENTER_NICKNAME = 'Enter preferred nickname below:'


@dataclass(frozen=True)
class Queues:
    received_messages: Queue = asyncio.Queue()
    sending_messages: Queue = asyncio.Queue()
    status_updates: Queue = asyncio.Queue()
    messages_to_save: Queue = asyncio.Queue()
    watchdog: Queue = asyncio.Queue()


def parse_arguments() -> Namespace:
    parser = ArgParser(default_config_files=('.env', ))
    parser.add('--host',
               '--HOST',
               type=str,
               default='minechat.dvmn.org',
               help='Host name')
    parser.add('--listen_port',
               '--LISTEN_PORT',
               type=int,
               default=5000,
               help='Listen port')
    parser.add('--write_port',
               '--WRITE_PORT',
               type=int,
               default=5050,
               help='Write port')
    parser.add('--chat_history_file',
               '--CHAT_HISTORY_FILE',
               type=Path,
               default='./chat_history.txt',
               help='Path to file where to save chat history')
    parser.add('--user_hash',
               '--USER_HASH',
               type=str,
               default='',
               help='Chat user hash')
    parser.add('--user_name',
               '--USER_NAME',
               type=str,
               default='anonymous',
               help='User name')

    args, _ = parser.parse_known_args()
    return args


async def get_user_credentials() -> str | None:
    user_hash = None
    try:
        with open('credentials.json', 'r') as stream:
            credentials = json.loads(stream.read())
        user_hash = credentials.get('account_hash', '')
    except FileNotFoundError:
        logger.info('User credentials not found.')
    except json.JSONDecodeError:
        logger.warning('Can\'t parse user credentials.')

    if user_hash:
        return user_hash


async def save_messages(filepath: Path, queues: Queues):
    while True:
        message = await queues.messages_to_save.get()

        async with aiofiles.open(filepath, 'a', encoding='utf-8') as stream:
            await stream.write(f'{message}\n')
            await stream.flush()


async def load_messages(filepath: Path, messages_queue: Queue):
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as stream:
            chat_history = stream.read()
            messages_queue.put_nowait(chat_history.rstrip('\n'))
            return
    logger.info(f'Unable to load history from {filepath.resolve()}')


async def read_msgs(socket_connection: tuple,
                    queues: Queues):
    reader, _ = socket_connection

    while True:
        raw_message = await reader.readline()

        queues.watchdog.put_nowait('New message in chat')

        formatted_message = (
            f'[{datetime.now().strftime("%d.%m.%y %H:%M")}] '
            f'{raw_message.decode().strip()}'
        )

        queues.received_messages.put_nowait(formatted_message)
        queues.messages_to_save.put_nowait(formatted_message)


async def send_msgs(socket_connection: tuple,
                    user_hash: str,
                    queues: Queues):
    reader, writer = socket_connection

    while True:
        message = await queues.sending_messages.get()
        writer.write(f'{message}\n\n'.encode())
        await writer.drain()
        queues.watchdog.put_nowait('Message sent')


async def authorize(writer: StreamWriter, user_hash: str) -> None:
    writer.write(f'{user_hash}\n'.encode())
    await writer.drain()
    logger.debug(user_hash)


async def authenticate_user(user_hash: str,
                            socket_connection: tuple,
                            queues: Queues):
    reader, writer = socket_connection

    if not user_hash:
        user_hash = await get_user_credentials()

    while True:
        text_response, json_response = process_server_response(
            await reader.readline()
        )
        if text_response == AUTH_REQUIRED:
            await authorize(writer, user_hash)
            queues.watchdog.put_nowait('Server greeting prompt')
        elif text_response == CHAT_GREETING:
            print('чеееееел')
            queues.watchdog.put_nowait('Authorization done')
            return
        elif json_response:
            print('u worx?')
            nickname = json_response.get('nickname')
            if nickname:
                queues.watchdog.put_nowait('User data received')
                queues.status_updates.put_nowait(NicknameReceived(nickname))
        elif json_response is None:
            logger.error('Invalid token. '
                         'Run register.py to register new user.')
            raise InvalidTokenError()


def process_server_response(raw_response: bytes) -> tuple[str]:
    text_response = raw_response.decode().strip()

    try:
        json_response = json.loads(text_response)
    except json.JSONDecodeError:
        json_response = None

    logger.debug(text_response)
    logger.debug(json_response)
    return text_response, json_response


async def watch_for_connection(queues: Queues):
    while True:
        try:
            async with timeout(2) as timer:
                message = await queues.watchdog.get()
                logger.debug(f'[{time.time():.0f}] Connection is alive. {message}')
                queues.status_updates.put_nowait(ReadConnectionStateChanged.ESTABLISHED)
                queues.status_updates.put_nowait(SendingConnectionStateChanged.ESTABLISHED)
        except asyncio.TimeoutError:
            if timer.expired:
                logger.error('2s timeout is elapsed.')
                queues.status_updates.put_nowait(ReadConnectionStateChanged.CLOSED)
                queues.status_updates.put_nowait(SendingConnectionStateChanged.CLOSED)
                print('raise!')
                raise ConnectionError()


async def handle_connection(args, queues: Queues):
    while True:
        try:
            async with connect_to_chat(
                args.host, args.listen_port
            ) as read_connection:
                async with connect_to_chat(
                    args.host, args.write_port
                ) as write_connection:
                    await authenticate_user(args.user_hash, write_connection, queues)

                    async with create_task_group() as tasks:
                        tasks.start_soon(read_msgs, read_connection, queues)
                        tasks.start_soon(send_msgs, write_connection, args.user_hash, queues)
                        tasks.start_soon(save_messages, args.chat_history_file, queues)
                        tasks.start_soon(watch_for_connection, queues)
        except ConnectionError as connection_error:
            # logger.exception(connection_error)
            await asyncio.sleep(5)


async def main():
    logging.basicConfig(
        level=logging.DEBUG
    )

    args = parse_arguments()

    queues = Queues()

    await load_messages(
        args.chat_history_file,
        queues.received_messages
    )

    try:
        await asyncio.gather(
            handle_connection(args, queues),
            gui.draw(queues.received_messages,
                     queues.sending_messages,
                     queues.status_updates)
        )
    except InvalidTokenError:
        root = Tk()
        root.withdraw()

        messagebox.showerror('Invalid token!', 'Invalid token.')


if __name__ == '__main__':
    asyncio.run(main())
