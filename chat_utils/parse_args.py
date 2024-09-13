from configargparse import ArgParser, Namespace
from pathlib import Path


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
    parser.add('--connection_timeout',
               '--CONNECTION_TIMEOUT',
               type=int,
               default=10,
               help='Connection timeout')

    args, _ = parser.parse_known_args()
    return args
