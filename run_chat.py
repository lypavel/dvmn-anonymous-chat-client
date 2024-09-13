import asyncio
import logging
from tkinter import Tk, messagebox, TclError

from anyio import create_task_group

import chat_utils.gui as gui
from chat_utils.errors import InvalidTokenError
from chat_utils.file_utils import load_messages
from chat_utils.network import handle_connection
from chat_utils.parse_args import parse_arguments
from chat_utils.queues import Queues


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
