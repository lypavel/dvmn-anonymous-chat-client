from asyncio import StreamReader, StreamWriter
import json
import logging
from pathlib import Path

import aiofiles

from chat_utils.chat_strings import AUTH_REQUIRED, CHAT_GREETING, \
    ENTER_NICKNAME
from chat_utils.connection import connect_to_chat, process_server_response
from chat_utils.errors import InvalidTokenError
from chat_utils.gui import NicknameReceived
from chat_utils.queues import Queues

logger = logging.getLogger(Path(__file__).name)


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


async def register_user(host: str,
                        port: int,
                        nickname: str) -> tuple[str]:
    async with connect_to_chat(host, port) as (reader, writer):
        while True:
            response, json_response = process_server_response(
                await reader.readline()
            )

            if response == AUTH_REQUIRED:
                writer.write('\n'.encode())
                await writer.drain()
            elif response == ENTER_NICKNAME:
                writer.write(f'{nickname}\n'.encode())
                await writer.drain()
            elif json_response is not None:
                nickname = json_response['nickname']
                token = json_response['account_hash']
                credentials_path = Path('credentials.json')
                async with aiofiles.open(credentials_path, 'w') as stream:
                    await stream.write(json.dumps(json_response,
                                                  ensure_ascii=True,
                                                  indent=2))
                return nickname, token
