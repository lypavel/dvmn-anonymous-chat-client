import asyncio
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path

logger = logging.getLogger(Path(__file__).name)


@asynccontextmanager
async def connect_to_chat(host: str, port: int):
    try:
        reader, writer = await asyncio.open_connection(host, port)
        yield reader, writer
    finally:
        if 'writer' in locals():
            writer.close()
            await writer.wait_closed()


def process_server_response(raw_response: bytes) -> tuple[str]:
    text_response = raw_response.decode().strip()

    try:
        json_response = json.loads(text_response)
    except json.JSONDecodeError:
        json_response = None

    logger.debug(f'Text response: {text_response}')
    logger.debug(f'Json response: {json_response}')

    return text_response, json_response
