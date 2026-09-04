with open('app/websocket/handler.py', 'r') as f:
    content = f.read()

# Fix the indentation issue: elif blocks inside try need to be at 20 spaces, not 16
# The pattern: after "elif "text" in message:" and "try:", the elif/if blocks should be indented by 4 more spaces

old = '''            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS text message session={session_id} type={msg_type}"})

                    if msg_type == "auth":
                        persona_id = await resolve_persona_id(data.get("persona_id", persona_id))
                        voice_id = data.get("voice_id", voice_id)
                        await manager.send_json(session_id, {"type": "status", "message": "authenticated"})
                        await _append_log(
                            session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS authenticated session={session_id} persona={persona_id} voice={voice_id} db_session={db_session_id}"}
                        )

                elif msg_type == "voice_select":'''

new = '''            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS text message session={session_id} type={msg_type}"})

                    if msg_type == "auth":
                        persona_id = await resolve_persona_id(data.get("persona_id", persona_id))
                        voice_id = data.get("voice_id", voice_id)
                        await manager.send_json(session_id, {"type": "status", "message": "authenticated"})
                        await _append_log(
                            session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS authenticated session={session_id} persona={persona_id} voice={voice_id} db_session={db_session_id}"}
                        )

                    elif msg_type == "voice_select":'''

if old in content:
    content = content.replace(old, new)
    with open('app/websocket/handler.py', 'w') as f:
        f.write(content)
    print('Fixed first elif')
else:
    print('Pattern not found')
