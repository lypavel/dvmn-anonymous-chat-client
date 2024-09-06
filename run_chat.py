import asyncio
from asyncio import Queue
from datetime import datetime
import json
import logging
from pathlib import Path

import aiofiles
from configargparse import ArgParser, Namespace

import gui
from socket_utils import connect_to_chat

logger = logging.getLogger(Path(__file__).name)


def parse_arguments() -> Namespace:
    parser = ArgParser(default_config_files=('.env', ))
    parser.add('--host',
               '--HOST',
               type=str,
               default='minechat.dvmn.org',
               help='Host name')
    parser.add('--port',
               '--LISTEN_PORT',
               type=int,
               default=5000,
               help='Port')
    parser.add('--chat_history_file',
               '--CHAT_HISTORY_FILE',
               type=Path,
               default='./chat_history.txt',
               help='Path to file where to save chat history')

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


async def generate_msgs(messages_queue: Queue,
                        message: str):
    messages_queue.put_nowait(message)


async def save_messages(filepath: Path, messages_to_save_queue: Queue):
    while True:
        message = await messages_to_save_queue.get()

        async with aiofiles.open(filepath, 'a') as stream:
            await stream.write(f'{message}\n')
            await stream.flush()


async def read_msgs(host: str,
                    port: str,
                    messages_queue: Queue,
                    messages_to_save_queue: Queue):
    async with connect_to_chat(host, port) as (reader, _):
        while True:
            raw_message = await reader.readline()
            formatted_message = (
                f'[{datetime.now().strftime("%d.%m.%y %H:%M")}] '
                f'{raw_message.decode().strip()}'
            )
            await generate_msgs(messages_queue, formatted_message)
            messages_to_save_queue.put_nowait(formatted_message)


async def main():
    logging.basicConfig(
        level=logging.DEBUG
    )

    args = parse_arguments()

    # user_name = args.user_name.replace(r'\n', '')
    # user_hash: str = args.user_hash

    # if not user_hash:
    #     user_hash = await get_user_credentials()

    # if not user_hash:
    #     user_hash = await register(args.host, args.port, user_name)

    # await submit_message(args.host, args.port, user_hash, user_message)

    messages_queue = asyncio.Queue()
    sending_queue = asyncio.Queue()
    status_updates_queue = asyncio.Queue()
    messages_to_save_queue = asyncio.Queue()

    await asyncio.gather(
        read_msgs(args.host,
                  args.port,
                  messages_queue,
                  messages_to_save_queue),
        save_messages(args.chat_history_file,
                      messages_to_save_queue),
        gui.draw(messages_queue,
                 sending_queue,
                 status_updates_queue)
    )


if __name__ == '__main__':
    asyncio.run(main())
