import asyncio
print("start")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
print("path set")

from unittest.mock import AsyncMock, MagicMock
print("mock imported")

from app.services.conversation_mgr import ConversationManager
print("conversation_mgr imported")

from app.services.vad import VADBuffer
print("vad imported")

print("all imports done")
sys.exit(0)
