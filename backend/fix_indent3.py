with open('app/websocket/handler.py', 'r') as f:
    content = f.read()

# The text processing block should have all elif/if bodies indented by 4 more spaces
# since they're inside a try block now

# Fix the elif blocks and their bodies
# Pattern: "                    elif msg_type == " should have bodies at 24 spaces
# Current bodies are at 20 spaces

old_block = '''                    elif msg_type == "voice_select":
                    voice_id = data.get("voice_id", voice_id)
                    await manager.send_json(session_id, {"type": "status", "message": f"voice_selected:{voice_id}"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS voice selected session={session_id} voice={voice_id}"})
                    try:
                        supabase = get_supabase()
                        supabase.table("sessions").update({"selected_voice": voice_id}).eq("id", db_session_id).execute()
                    except Exception:
                        pass

                    elif msg_type == "stop_call":
                    await _cancel_current_turn()
                    await manager.send_json(session_id, {"type": "status", "message": "call_ended"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS call ended session={session_id}"})
                    break

                    elif msg_type == "stop_playback":
                    await _cancel_current_turn()
                    await manager.send_json(session_id, {"type": "status", "message": "playback_stopped"})
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS playback stopped session={session_id}"})

                    elif msg_type == "stop_listening":
                    await manager.send_json(session_id, {"type": "status", "message": "processing"})
                    await manager.send_json(session_id, {"type": "status", "message": "transcribing"})
                    audio_data = vad.flush()
                    if not audio_data:
                        await manager.send_json(session_id, {"type": "status", "message": "idle"})
                        continue
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS flush session={session_id} audio_len={len(audio_data)}"})
                    wav_audio = pcm_to_wav(audio_data, sample_rate=settings.audio_sample_rate)
                    try:
                        stt_start = time.perf_counter()
                        user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
                        stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)
                    except asyncio.TimeoutError:
                        await manager.send_json(session_id, {"type": "error", "message": "stt_timeout"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS STT timeout session={session_id}"})
                        continue
                    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS STT session={session_id} text={user_text} latency_ms={stt_latency_ms}"})
                    await manager.send_json(session_id, {"type": "status", "message": "transcribed"})
                    if not user_text or is_noisy_transcription(user_text):
                        await manager.send_json(session_id, {"type": "error", "message": "empty_transcript"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS empty transcript session={session_id}"})
                        continue
                    await manager.send_json(session_id, {"type": "transcript", "role": "user", "text": user_text})
                    if recording_start_time is None:
                        recording_start_time = time.perf_counter()
                    user_recording_start_ms = int((time.perf_counter() - recording_start_time) * 1000)
                    current_user_message_id = await save_turn(
                        db_session_id,
                        "user",
                        user_text,
                        latency_ms=0,
                        stt_latency_ms=stt_latency_ms,
                        recording_start_ms=user_recording_start_ms,
                    )
                    current_turn_task_ref["task"] = asyncio.create_task(
                        start_turn_with_filler(
                            session_id,
                            user_text,
                            conversation_mgr,
                            voice_id,
                            db_session_id,
                            stt_latency_ms=stt_latency_ms,
                            filler_threshold_ms=settings.filler_threshold_ms,
                            user_message_id=current_user_message_id,
                        )
                    )
                    current_turn_task_ref["task"].add_done_callback(_on_turn_done)
                    try:
                        await asyncio.wait_for(current_turn_task_ref["task"], timeout=60)
                    except asyncio.TimeoutError:
                        await manager.send_json(session_id, {"type": "error", "message": "llm_timeout"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS LLM timeout session={session_id}"})
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        await manager.send_json(session_id, {"type": "error", "message": f"turn_failed:{type(exc).__name__}"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS turn failed session={session_id} error={exc}"})

                    elif msg_type == "transcript":
                    user_text = data.get("text", "")
                    if not user_text:
                        continue
                    if _is_duplicate_turn(conversation_mgr, "user", user_text):
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS duplicate transcript skipped session={session_id} text={user_text}"})
                        continue
                    await _cancel_current_turn()
                    await manager.send_json(session_id, {"type": "transcript", "role": "user", "text": user_text})
                    if recording_start_time is None:
                        recording_start_time = time.perf_counter()
                    user_recording_start_ms = int((time.perf_counter() - recording_start_time) * 1000)
                    current_user_message_id = await save_turn(
                        db_session_id,
                        "user",
                        user_text,
                        latency_ms=0,
                        recording_start_ms=user_recording_start_ms,
                    )
                    current_turn_task_ref["task"] = asyncio.create_task(
                        start_turn_with_filler(
                            session_id,
                            user_text,
                            conversation_mgr,
                            voice_id,
                            persona_id,
                            db_session_id,
                            stt_latency_ms=None,
                            filler_threshold_ms=settings.filler_threshold_ms,
                            user_message_id=current_user_message_id,
                        )
                    )
                    current_turn_task_ref["task"].add_done_callback(_on_turn_done)
                    try:
                        await asyncio.wait_for(current_turn_task_ref["task"], timeout=60)
                    except asyncio.TimeoutError:
                        await manager.send_json(session_id, {"type": "error", "message": "llm_timeout"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS LLM timeout session={session_id}"})
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        await manager.send_json(session_id, {"type": "error", "message": f"turn_failed:{type(exc).__name__}"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS turn failed session={session_id} error={exc}"})

                    elif msg_type == "ping":
                    try:
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    except Exception:
                        break'''

new_block = '''                    elif msg_type == "voice_select":
                        voice_id = data.get("voice_id", voice_id)
                        await manager.send_json(session_id, {"type": "status", "message": f"voice_selected:{voice_id}"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS voice selected session={session_id} voice={voice_id}"})
                        try:
                            supabase = get_supabase()
                            supabase.table("sessions").update({"selected_voice": voice_id}).eq("id", db_session_id).execute()
                        except Exception:
                            pass

                    elif msg_type == "stop_call":
                        await _cancel_current_turn()
                        await manager.send_json(session_id, {"type": "status", "message": "call_ended"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS call ended session={session_id}"})
                        break

                    elif msg_type == "stop_playback":
                        await _cancel_current_turn()
                        await manager.send_json(session_id, {"type": "status", "message": "playback_stopped"})
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS playback stopped session={session_id}"})

                    elif msg_type == "stop_listening":
                        await manager.send_json(session_id, {"type": "status", "message": "processing"})
                        await manager.send_json(session_id, {"type": "status", "message": "transcribing"})
                        audio_data = vad.flush()
                        if not audio_data:
                            await manager.send_json(session_id, {"type": "status", "message": "idle"})
                            continue
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS flush session={session_id} audio_len={len(audio_data)}"})
                        wav_audio = pcm_to_wav(audio_data, sample_rate=settings.audio_sample_rate)
                        try:
                            stt_start = time.perf_counter()
                            user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
                            stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)
                        except asyncio.TimeoutError:
                            await manager.send_json(session_id, {"type": "error", "message": "stt_timeout"})
                            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS STT timeout session={session_id}"})
                            continue
                        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS STT session={session_id} text={user_text} latency_ms={stt_latency_ms}"})
                        await manager.send_json(session_id, {"type": "status", "message": "transcribed"})
                        if not user_text or is_noisy_transcription(user_text):
                            await manager.send_json(session_id, {"type": "error", "message": "empty_transcript"})
                            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS empty transcript session={session_id}"})
                            continue
                        await manager.send_json(session_id, {"type": "transcript", "role": "user", "text": user_text})
                        if recording_start_time is None:
                            recording_start_time = time.perf_counter()
                        user_recording_start_ms = int((time.perf_counter() - recording_start_time) * 1000)
                        current_user_message_id = await save_turn(
                            db_session_id,
                            "user",
                            user_text,
                            latency_ms=0,
                            stt_latency_ms=stt_latency_ms,
                            recording_start_ms=user_recording_start_ms,
                        )
                        current_turn_task_ref["task"] = asyncio.create_task(
                            start_turn_with_filler(
                                session_id,
                                user_text,
                                conversation_mgr,
                                voice_id,
                                db_session_id,
                                stt_latency_ms=stt_latency_ms,
                                filler_threshold_ms=settings.filler_threshold_ms,
                                user_message_id=current_user_message_id,
                            )
                        )
                        current_turn_task_ref["task"].add_done_callback(_on_turn_done)
                        try:
                            await asyncio.wait_for(current_turn_task_ref["task"], timeout=60)
                        except asyncio.TimeoutError:
                            await manager.send_json(session_id, {"type": "error", "message": "llm_timeout"})
                            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS LLM timeout session={session_id}"})
                        except asyncio.CancelledError:
                            pass
                        except Exception as exc:
                            await manager.send_json(session_id, {"type": "error", "message": f"turn_failed:{type(exc).__name__}"})
                            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS turn failed session={session_id} error={exc}"})

                    elif msg_type == "transcript":
                        user_text = data.get("text", "")
                        if not user_text:
                            continue
                        if _is_duplicate_turn(conversation_mgr, "user", user_text):
                            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "warning", "msg": f"WS duplicate transcript skipped session={session_id} text={user_text}"})
                            continue
                        await _cancel_current_turn()
                        await manager.send_json(session_id, {"type": "transcript", "role": "user", "text": user_text})
                        if recording_start_time is None:
                            recording_start_time = time.perf_counter()
                        user_recording_start_ms = int((time.perf_counter() - recording_start_time) * 1000)
                        current_user_message_id = await save_turn(
                            db_session_id,
                            "user",
                            user_text,
                            latency_ms=0,
                            recording_start_ms=user_recording_start_ms,
                        )
                        current_turn_task_ref["task"] = asyncio.create_task(
                            start_turn_with_filler(
                                session_id,
                                user_text,
                                conversation_mgr,
                                voice_id,
                                persona_id,
                                db_session_id,
                                stt_latency_ms=None,
                                filler_threshold_ms=settings.filler_threshold_ms,
                                user_message_id=current_user_message_id,
                            )
                        )
                        current_turn_task_ref["task"].add_done_callback(_on_turn_done)
                        try:
                            await asyncio.wait_for(current_turn_task_ref["task"], timeout=60)
                        except asyncio.TimeoutError:
                            await manager.send_json(session_id, {"type": "error", "message": "llm_timeout"})
                            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS LLM timeout session={session_id}"})
                        except asyncio.CancelledError:
                            pass
                        except Exception as exc:
                            await manager.send_json(session_id, {"type": "error", "message": f"turn_failed:{type(exc).__name__}"})
                            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS turn failed session={session_id} error={exc}"})

                    elif msg_type == "ping":
                        try:
                            await websocket.send_text(json.dumps({"type": "pong"}))
                        except Exception:
                            break'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('app/websocket/handler.py', 'w') as f:
        f.write(content)
    print('Fixed all elif blocks')
else:
    print('Pattern not found')
