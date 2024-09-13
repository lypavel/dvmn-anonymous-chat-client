import asyncio
from asyncio import StreamReader, StreamWriter, Queue
import logging
from pathlib import Path
from socket import gaierror
import time

from async_timeout import timeout

from chat_utils.chat_strings import MESSAGE_SENT
from chat_utils.connection import process_server_response
from chat_utils.gui import ReadConnectionStateChanged, \
    SendingConnectionStateChanged
from chat_utils.queues import Queues

logger = logging.getLogger(Path(__file__).name)


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
