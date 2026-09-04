import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AudioBuffer:
    def __init__(self) -> None:
        self._buffer: bytearray = bytearray()

    def append(self, chunk: bytes) -> None:
        self._buffer.extend(chunk)

    def get_bytes(self) -> bytes:
        return bytes(self._buffer)

    def get_recent_bytes(self, max_bytes: int) -> bytes:
        if len(self._buffer) <= max_bytes:
            return bytes(self._buffer)
        return bytes(self._buffer[-max_bytes:])

    def __len__(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()
