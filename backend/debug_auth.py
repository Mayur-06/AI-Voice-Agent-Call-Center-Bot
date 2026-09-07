import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from unittest.mock import AsyncMock, MagicMock
from app.orchestration.pipeline import SessionPipelineState, safe_put_nowait, make_event
from app.orchestration.stages import ws_in_task, ws_out_task
from app.services.conversation_mgr import ConversationManager
from app.services.vad import VADBuffer
from app.services.session import resolve_persona_id

mock_ws = AsyncMock()
state = SessionPipelineState(
    session_id="sess-1",
    db_session_id="db-1",
    persona_id="p-1",
    voice_id="v-1",
    websocket=mock_ws,
    audio_in_queue=asyncio.Queue(),
    text_in_queue=asyncio.Queue(),
    sentence_queue=asyncio.Queue(),
    audio_out_queue=asyncio.Queue(),
    control_queue=asyncio.Queue(),
    ws_event_queue=asyncio.Queue(),
    conversation_mgr=ConversationManager(),
    vad=VADBuffer(sample_rate=16000),
    speech_detected=asyncio.Event(),
    cancelled_turns=set(),
)

async def main():
    state.ws_in_task = asyncio.create_task(ws_in_task(state))
    state.ws_out_task = asyncio.create_task(ws_out_task(state))
    
    async def _control_loop():
        while True:
            event = await state.control_queue.get()
            print(f"CONTROL LOOP GOT: {event}")
            if event is None:
                break
            if event.get("type") in ("disconnect", "stop_call"):
                break
            if event.get("type") == "auth":
                data = event.get("data", {})
                try:
                    state.persona_id = await resolve_persona_id(data.get("persona_id", state.persona_id))
                    state.voice_id = data.get("voice_id") or state.voice_id
                    evt = make_event(state, "status", message="authenticated")
                    print(f"PUTTING EVENT: {evt}")
                    safe_put_nowait(state.ws_event_queue, evt)
                    print(f"QUEUE SIZE: {state.ws_event_queue.qsize()}")
                except Exception as e:
                    print(f"AUTH ERROR: {e}")
            state.control_queue.task_done()
    
    control_task = asyncio.create_task(_control_loop())
    mock_ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": '{"type": "auth", "persona_id": "p1", "voice_id": "v1"}'},
        {"type": "websocket.disconnect"},
    ])
    
    await asyncio.sleep(0.5)
    print("PUTTING DISCONNECT")
    state.control_queue.put_nowait({"type": "disconnect"})
    await asyncio.wait_for(state.ws_in_task, timeout=2)
    print("WS_IN_DONE")
    state.control_queue.put_nowait(None)
    await asyncio.wait_for(control_task, timeout=2)
    print("CONTROL_DONE")
    
    print(f"QUEUE SIZE AFTER: {state.ws_event_queue.qsize()}")
    await asyncio.sleep(0.5)
    print(f"send_json calls: {mock_ws.send_json.call_args_list}")
    print(f"send_bytes calls: {mock_ws.send_bytes.call_args_list}")
    
    state.ws_out_task.cancel()
    try:
        await state.ws_out_task
    except asyncio.CancelledError:
        pass

asyncio.run(main())
