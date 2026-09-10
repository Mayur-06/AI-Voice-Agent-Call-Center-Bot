from typing import Optional

from app.services.session import load_turns


class ConversationManager:
    def __init__(self) -> None:
        self.turns: list[dict[str, str]] = []

    def append_user(self, text: str) -> None:
        self.turns.append({"role": "user", "content": text})

    def append_assistant(self, text: str) -> None:
        self.turns.append({"role": "assistant", "content": text})

    def get_history(self) -> list[dict[str, str]]:
        return list(self.turns)

    def __len__(self) -> int:
        return len(self.turns)

    def clear(self) -> None:
        self.turns.clear()

    async def load_from_db(self, session_id: str) -> None:
        self.turns = await load_turns(session_id)
