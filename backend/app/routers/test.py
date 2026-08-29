from fastapi import APIRouter
from fastapi.responses import HTMLResponse, StreamingResponse
import json
import asyncio

router = APIRouter(tags=["test"])

TEST_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Voice WebSocket Test</title>
    <style>
        body { font-family: monospace; padding: 20px; max-width: 800px; margin: 0 auto; }
        .log { background: #f0f0f0; padding: 10px; margin: 5px 0; border-radius: 4px; white-space: pre-wrap; word-break: break-all; }
        .sent { background: #d4edda; }
        .received { background: #d1ecf1; }
        .error { background: #f8d7da; }
        input, button { margin: 5px; padding: 8px; }
        .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>Voice WebSocket Test</h1>

    <div class="section">
        <h3>Connection</h3>
        <input type="text" id="sessionId" placeholder="Session ID" value="">
        <input type="text" id="token" placeholder="Access Token" value="">
        <button onclick="connect()">Connect</button>
        <button onclick="disconnect()">Disconnect</button>
        <div id="status">Disconnected</div>
    </div>

    <div class="section">
        <h3>Auth</h3>
        <input type="text" id="personaId" placeholder="Persona ID" value="">
        <input type="text" id="voiceId" placeholder="Voice ID" value="en-IN-NeerjaNeural">
        <button onclick="sendAuth()">Send Auth</button>
        <button onclick="sendVoiceSelect()">Send Voice Select</button>
    </div>

    <div class="section">
        <h3>Send Message</h3>
        <input type="text" id="messageText" placeholder="Message text" value="Hello, test message" style="width: 400px;">
        <button onclick="sendTranscript()">Send Transcript</button>
        <button onclick="sendStopPlayback()">Stop Playback</button>
    </div>

    <div class="section">
        <h3>Logs</h3>
        <button onclick="clearLogs()">Clear Logs</button>
        <div id="logs"></div>
    </div>

    <script>
        let ws = null;

        function log(message, type = '') {
            const logs = document.getElementById('logs');
            const div = document.createElement('div');
            div.className = 'log ' + type;
            div.textContent = new Date().toLocaleTimeString() + ' - ' + message;
            logs.appendChild(div);
            logs.scrollTop = logs.scrollHeight;
        }

        function clearLogs() {
            document.getElementById('logs').innerHTML = '';
        }

        function connect() {
            const sessionId = document.getElementById('sessionId').value.trim();
            const token = document.getElementById('token').value.trim();
            if (!sessionId || !token) {
                alert('Please enter Session ID and Access Token');
                return;
            }
            const url = `ws://${window.location.host}/ws/voice/${sessionId}?token=${token}`;
            log('Connecting to: ' + url, 'sent');
            ws = new WebSocket(url);

            ws.onopen = () => {
                log('Connected', 'sent');
                document.getElementById('status').textContent = 'Connected';
            };

            ws.onmessage = (e) => {
                if (e.data instanceof Blob) {
                    log('Received binary data: ' + e.data.size + ' bytes', 'received');
                } else {
                    try {
                        const data = JSON.parse(e.data);
                        log('Received: ' + JSON.stringify(data), 'received');
                    } catch (err) {
                        log('Received: ' + e.data, 'received');
                    }
                }
            };

            ws.onerror = (e) => {
                log('Error occurred', 'error');
            };

            ws.onclose = (e) => {
                log('Disconnected: code=' + e.code + ', reason=' + e.reason, 'error');
                document.getElementById('status').textContent = 'Disconnected';
            };
        }

        function disconnect() {
            if (ws) {
                ws.close();
                ws = null;
            }
        }

        function sendAuth() {
            const personaId = document.getElementById('personaId').value.trim();
            const voiceId = document.getElementById('voiceId').value.trim();
            if (!personaId) {
                alert('Please enter Persona ID');
                return;
            }
            const msg = { type: 'auth', persona_id: personaId, voice_id: voiceId || 'en-IN-NeerjaNeural' };
            sendJson(msg);
        }

        function sendVoiceSelect() {
            const voiceId = document.getElementById('voiceId').value.trim();
            if (!voiceId) {
                alert('Please enter Voice ID');
                return;
            }
            const msg = { type: 'voice_select', voice_id: voiceId };
            sendJson(msg);
        }

        function sendTranscript() {
            const text = document.getElementById('messageText').value.trim();
            if (!text) {
                alert('Please enter message text');
                return;
            }
            const msg = { type: 'transcript', text: text };
            sendJson(msg);
        }

        function sendStopPlayback() {
            const msg = { type: 'stop_playback' };
            sendJson(msg);
        }

        function sendJson(data) {
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                alert('WebSocket is not connected');
                return;
            }
            const json = JSON.stringify(data);
            ws.send(json);
            log('Sent: ' + json, 'sent');
        }
    </script>
</body>
</html>"""

PIPELINE_HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Pipeline End-to-End Test</title>
    <style>
        body { font-family: monospace; padding: 20px; max-width: 900px; margin: 0 auto; }
        .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 4px; }
        .log { background: #f0f0f0; padding: 10px; margin: 5px 0; border-radius: 4px; white-space: pre-wrap; word-break: break-all; }
        .sent { background: #d4edda; }
        .received { background: #d1ecf1; }
        .error { background: #f8d7da; }
        input, button { margin: 5px; padding: 8px; }
        audio { width: 100%; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>Pipeline End-to-End Test</h1>

    <div class="section">
        <h3>Connection</h3>
        <input type="text" id="sessionId" placeholder="Session ID" value="e2e-test">
        <input type="text" id="token" placeholder="Access Token" value="">
        <button onclick="connect()">Connect</button>
        <button onclick="disconnect()">Disconnect</button>
        <div id="status">Disconnected</div>
    </div>

    <div class="section">
        <h3>Auth</h3>
        <input type="text" id="personaId" placeholder="Persona ID" value="default">
        <input type="text" id="voiceId" placeholder="Voice ID" value="en-IN-NeerjaNeural">
        <button onclick="sendAuth()">Send Auth</button>
    </div>

    <div class="section">
        <h3>Upload Audio</h3>
        <input type="file" id="audioFile" accept="audio/wav,audio/x-wav,audio/mpeg,audio/mp3">
        <button onclick="sendAudio()">Send Audio</button>
        <div id="uploadStatus"></div>
    </div>

    <div class="section">
        <h3>Pipeline Status</h3>
        <div id="pipelineStatus" style="font-size: 18px; font-weight: bold; padding: 10px; background: #e0e0e0; border-radius: 4px;">Idle</div>
    </div>

    <div class="section">
        <h3>Response Audio</h3>
        <audio id="responseAudio" controls style="display:none;"></audio>
        <div id="audioStatus">No response yet</div>
    </div>

    <div class="section">
        <h3>Backend Logs</h3>
        <div id="backendLogs"></div>
    </div>

    <div class="section">
        <h3>Client Logs</h3>
        <button onclick="clearLogs()">Clear Logs</button>
        <div id="logs"></div>
    </div>

    <script>
        let ws = null;
        let eventSource = null;

        function log(message, type = '') {
            const logs = document.getElementById('logs');
            const div = document.createElement('div');
            div.className = 'log ' + type;
            div.textContent = new Date().toLocaleTimeString() + ' - ' + message;
            logs.appendChild(div);
            logs.scrollTop = logs.scrollHeight;
        }

        function clearLogs() {
            document.getElementById('logs').innerHTML = '';
        }

        function connect() {
            const sessionId = document.getElementById('sessionId').value.trim();
            const token = document.getElementById('token').value.trim();
            if (!sessionId || !token) {
                alert('Please enter Session ID and Access Token');
                return;
            }
            const wsUrl = `ws://${window.location.host}/ws/voice/${sessionId}?token=${token}`;
            log('Connecting WebSocket: ' + wsUrl, 'sent');
            ws = new WebSocket(wsUrl);

            ws.binaryType = 'arraybuffer';

            ws.onopen = () => {
                log('WebSocket connected', 'sent');
                document.getElementById('status').textContent = 'Connected';
            };

            ws.onmessage = (e) => {
                if (typeof e.data === 'string') {
                    try {
                        const data = JSON.parse(e.data);
                        log('Received: ' + JSON.stringify(data), 'received');
                        if (data.type === 'status') {
                            const statusEl = document.getElementById('pipelineStatus');
                            statusEl.textContent = data.message || data.text || 'Processing';
                            if (data.message === 'response_ready' || data.message === 'response_audio') {
                                statusEl.style.background = '#d4edda';
                            } else if (data.message && data.message.includes('error')) {
                                statusEl.style.background = '#f8d7da';
                            } else {
                                statusEl.style.background = '#d1ecf1';
                            }
                        }
                    } catch (err) {
                        log('Received: ' + e.data, 'received');
                    }
                } else {
                    const byteLength = e.data instanceof Blob ? e.data.size : e.data.byteLength;
                    log('Received binary audio: ' + byteLength + ' bytes, type=' + (e.data.constructor && e.data.constructor.name), 'received');
                    const blob = e.data instanceof Blob ? e.data : new Blob([e.data], { type: 'audio/wav' });
                    const url = URL.createObjectURL(blob);
                    const audio = document.getElementById('responseAudio');
                    if (!audio) {
                        log('Audio element not found', 'error');
                        return;
                    }
                    audio.src = url;
                    audio.style.display = 'block';
                    document.getElementById('audioStatus').textContent = 'Response audio ready (' + byteLength + ' bytes)';
                    audio.load();
                    audio.play().catch(err => log('Autoplay blocked: ' + err.message, 'error'));
                }
            };

            ws.onerror = (e) => {
                log('WebSocket error', 'error');
            };

            ws.onclose = (e) => {
                log('WebSocket closed: code=' + e.code + ', reason=' + e.reason, 'error');
                document.getElementById('status').textContent = 'Disconnected';
            };

            const logUrl = `/test/logs?session=${encodeURIComponent(sessionId)}`;
            eventSource = new EventSource(logUrl);
            eventSource.onmessage = (e) => {
                const backendLogs = document.getElementById('backendLogs');
                const div = document.createElement('div');
                div.className = 'log';
                div.textContent = new Date().toLocaleTimeString() + ' - ' + e.data;
                backendLogs.appendChild(div);
                backendLogs.scrollTop = backendLogs.scrollHeight;
            };
            eventSource.onerror = () => {
                log('Log stream closed or errored', 'error');
            };
            log('Connecting to log stream: ' + logUrl, 'sent');
        }

        function disconnect() {
            if (ws) {
                ws.close();
                ws = null;
            }
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
        }

        function sendAuth() {
            const personaId = document.getElementById('personaId').value.trim();
            const voiceId = document.getElementById('voiceId').value.trim();
            if (!personaId) {
                alert('Please enter Persona ID');
                return;
            }
            const msg = { type: 'auth', persona_id: personaId, voice_id: voiceId || 'en-IN-NeerjaNeural' };
            sendJson(msg);
        }

        async function sendAudio() {
            const fileInput = document.getElementById('audioFile');
            const file = fileInput.files[0];
            if (!file) {
                alert('Please select a WAV file');
                return;
            }
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                alert('WebSocket is not connected');
                return;
            }
            document.getElementById('uploadStatus').textContent = 'Uploading: ' + file.name + ' (' + file.size + ' bytes)';
            const arrayBuffer = await file.arrayBuffer();
            ws.send(arrayBuffer);
            log('Sent audio file: ' + file.name + ' (' + file.size + ' bytes)', 'sent');
            document.getElementById('uploadStatus').textContent = 'Uploaded: ' + file.name;
        }

        function sendJson(data) {
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                alert('WebSocket is not connected');
                return;
            }
            const json = JSON.stringify(data);
            ws.send(json);
            log('Sent: ' + json, 'sent');
        }
    </script>
</body>
</html>"""


@router.get("/test/voice", response_class=HTMLResponse)
async def voice_test_page():
    return TEST_HTML


@router.get("/test/pipeline", response_class=HTMLResponse)
async def pipeline_test_page():
    return PIPELINE_HTML


@router.get("/test/logs")
async def stream_logs(session: str = "global"):
    async def event_generator():
        from app.websocket.handler import _stream_session_logs
        async for line in _stream_session_logs(session):
            yield line

    return StreamingResponse(event_generator(), media_type="text/event-stream")
