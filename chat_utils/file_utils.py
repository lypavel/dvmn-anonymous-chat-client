from asyncio import Queue
import logging
from pathlib import Path

import aiofiles

logger = logging.getLogger(Path(__file__).name)


async def save_messages(filepath: Path, messages_to_save_queue: Queue) -> None:
    while True:
        message = await messages_to_save_queue.get()

        async with aiofiles.open(filepath, 'a', encoding='utf-8') as stream:
            await stream.write(f'{message}\n')
            await stream.flush()


async def load_messages(filepath: Path, messages_queue: Queue) -> None:
    if filepath.exists():
        async with aiofiles.open(filepath, 'r', encoding='utf-8') as stream:
            chat_history = await stream.read()
            messages_queue.put_nowait(chat_history.rstrip('\n'))
            return
    logger.info(f'Unable to load history from {filepath.resolve()}')
