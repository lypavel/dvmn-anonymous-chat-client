
from asyncio import Queue
from dataclasses import dataclass


@dataclass(frozen=True)
class Queues:
    received_messages: Queue = Queue()
    sending_messages: Queue = Queue()
    status_updates: Queue = Queue()
    messages_to_save: Queue = Queue()
    watchdog: Queue = Queue()
