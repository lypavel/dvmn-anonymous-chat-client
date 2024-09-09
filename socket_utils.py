import asyncio
from asyncio import Queue
from contextlib import asynccontextmanager
from socket import gaierror
import sys

from gui import ReadConnectionStateChanged, SendingConnectionStateChanged


@asynccontextmanager
async def connect_to_chat(host: str, port: int, status_queue: Queue = None):
    while True:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            yield reader, writer
            break
        except gaierror:
            print('Connection error: check your internet connection.',
                  file=sys.stderr)
            await asyncio.sleep(10)
        finally:
            if 'writer' in locals():
                writer.close()
                await writer.wait_closed()

                if status_queue:
                    status_queue.put_nowait(ReadConnectionStateChanged.CLOSED)
                    status_queue.put_nowait(
                        SendingConnectionStateChanged.CLOSED
                    )
