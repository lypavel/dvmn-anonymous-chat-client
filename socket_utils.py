import asyncio
from contextlib import asynccontextmanager
from socket import gaierror
import sys


@asynccontextmanager
async def connect_to_chat(host: str, port: int):
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
