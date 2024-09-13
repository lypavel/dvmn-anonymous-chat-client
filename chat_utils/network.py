import asyncio
from asyncio import StreamReader, StreamWriter
from datetime import datetime
import logging
from pathlib import Path
from socket import gaierror

from anyio import create_task_group

from chat_utils.authentication import authorize_user
from chat_utils.connection import connect_to_chat
from chat_utils.file_utils import save_messages
from chat_utils.gui import ReadConnectionStateChanged, \
    SendingConnectionStateChanged
from chat_utils.watchdog import watch_for_connection, ping_server
from chat_utils.queues import Queues

logger = logging.getLogger(Path(__file__).name)


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
