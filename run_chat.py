import asyncio
from asyncio import StreamReader, StreamWriter, Queue
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
from socket import gaierror
import time
from tkinter import Tk, messagebox, TclError

import aiofiles
from anyio import create_task_group
from async_timeout import timeout

from chat_strings import AUTH_REQUIRED, CHAT_GREETING, MESSAGE_SENT
from errors import InvalidTokenError
import gui
from gui import ReadConnectionStateChanged, SendingConnectionStateChanged, \
    NicknameReceived
from parse_args import parse_arguments
from connection import connect_to_chat, process_server_response

logger = logging.getLogger(Path(__file__).name)


@dataclass(frozen=True)
class Queues:
    received_messages: Queue = asyncio.Queue()
    sending_messages: Queue = asyncio.Queue()
    status_updates: Queue = asyncio.Queue()
    messages_to_save: Queue = asyncio.Queue()
    watchdog: Queue = asyncio.Queue()


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


async def authorize_user(user_hash: str,
                         write_connection: tuple[StreamReader, StreamWriter],
                         queues: Queues) -> None:
    reader, writer = write_connection

    if not user_hash:
        user_hash = await get_user_credentials()

    while True:
        text_response, json_response = process_server_response(
            await reader.readline()
        )
        if text_response == AUTH_REQUIRED:
            writer.write(f'{user_hash}\n'.encode())
            await writer.drain()

            logger.debug(user_hash)
            queues.watchdog.put_nowait('Server greeting prompt')
        elif text_response == CHAT_GREETING:
            queues.watchdog.put_nowait('Authorization done')
            return
        elif json_response:
            nickname = json_response.get('nickname')
            if nickname:
                queues.watchdog.put_nowait('User data received')
                queues.status_updates.put_nowait(NicknameReceived(nickname))
        elif json_response is None:
            logger.error('Invalid token. '
                         'Run register.py to register new user.')
            raise InvalidTokenError(user_hash)


async def save_messages(filepath: Path, messages_to_save_queue: Queue) -> None:
    while True:
        message = await messages_to_save_queue.get()

        async with aiofiles.open(filepath, 'a', encoding='utf-8') as stream:
            await stream.write(f'{message}\n')
            await stream.flush()


async def load_messages(filepath: Path, messages_queue: Queue) -> None:
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as stream:
            chat_history = stream.read()
            messages_queue.put_nowait(chat_history.rstrip('\n'))
            return
    logger.info(f'Unable to load history from {filepath.resolve()}')


async def read_msgs(read_connection: tuple[StreamReader, StreamWriter],
                    queues: Queues) -> None:
    reader, _ = read_connection

    while True:
        raw_message = await reader.readline()

        queues.watchdog.put_nowait('New message in chat')

        formatted_message = (
            f'[{datetime.now().strftime("%d.%m.%y %H:%M")}] '
            f'{raw_message.decode().strip()}'
        )

        queues.received_messages.put_nowait(formatted_message)
        queues.messages_to_save.put_nowait(formatted_message)


async def send_msgs(write_connection: tuple[StreamReader, StreamWriter],
                    queues: Queues) -> None:
    _, writer = write_connection

    while True:
        message = await queues.sending_messages.get()
        writer.write(f'{message}\n\n'.encode())
        await writer.drain()
        queues.watchdog.put_nowait('Message sent')


async def handle_connection(args, queues: Queues) -> None:
    while True:
        try:
            for connection_state in (ReadConnectionStateChanged,
                                     SendingConnectionStateChanged):
                queues.status_updates.put_nowait(connection_state.INITIATED)

            async with connect_to_chat(args.host, args.listen_port) as read_connection:
                async with connect_to_chat(args.host, args.write_port) as write_connection:
                    await authorize_user(args.user_hash,
                                         write_connection,
                                         queues)
                    try:
                        async with create_task_group() as tasks:
                            tasks.start_soon(read_msgs,
                                             read_connection,
                                             queues)
                            tasks.start_soon(send_msgs,
                                             write_connection,
                                             queues)
                            tasks.start_soon(save_messages,
                                             args.chat_history_file,
                                             queues.messages_to_save)
                            tasks.start_soon(watch_for_connection,
                                             args.connection_timeout,
                                             queues)
                            tasks.start_soon(ping_server,
                                             write_connection,
                                             args.connection_timeout,
                                             queues.watchdog)
                    except* gaierror:
                        raise gaierror
        except (gaierror, OSError):
            for connection_state in (ReadConnectionStateChanged,
                                     SendingConnectionStateChanged):
                queues.status_updates.put_nowait(connection_state
                                                 .CLOSED)
            logger.error('Connection error occured. Reconnecting...')
            await asyncio.sleep(args.connection_timeout)


async def watch_for_connection(connection_timeout: int,
                               queues: Queues) -> None:
    while True:
        try:
            async with timeout(connection_timeout) as timer:
                message = await queues.watchdog.get()
                logger.debug(f'[{time.time():.0f}] Connection is alive. '
                             f'{message}')
                for connection_state in (ReadConnectionStateChanged,
                                         SendingConnectionStateChanged):
                    queues.status_updates.put_nowait(connection_state
                                                     .ESTABLISHED)
        except asyncio.TimeoutError:
            if timer.expired:
                logger.error(f'{connection_timeout}s timeout is elapsed.')
                for connection_state in (ReadConnectionStateChanged,
                                         SendingConnectionStateChanged):
                    queues.status_updates.put_nowait(connection_state.CLOSED)


async def ping_server(write_connection: tuple[StreamReader, StreamWriter],
                      connection_timeout: int,
                      watchdog_queue: Queue) -> None:
    reader, writer = write_connection
    ping_message = ''

    while True:
        writer.write(f'{ping_message}\n\n'.encode())
        await writer.drain()

        watchdog_queue.put_nowait('Ping message send')

        text_response, _ = process_server_response(
            await reader.readline()
        )

        if text_response != MESSAGE_SENT:
            raise gaierror

        await asyncio.sleep(connection_timeout)


async def main() -> None:
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
        async with create_task_group() as tasks:
            tasks.start_soon(handle_connection, args, queues)
            tasks.start_soon(gui.draw, queues.received_messages,
                             queues.sending_messages,
                             queues.status_updates)
    except* InvalidTokenError as exception_group:
        root = Tk()
        root.withdraw()

        for exception in exception_group.exceptions:
            messagebox.showerror('Invalid token', exception)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except* (TclError, KeyboardInterrupt):
        pass
