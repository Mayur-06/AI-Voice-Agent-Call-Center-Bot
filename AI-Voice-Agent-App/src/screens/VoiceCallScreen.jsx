import { useEffect, useRef, useCallback, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useVoiceCall } from '@/hooks/useVoiceCall';

const STATUS_LABELS = {
  idle: 'Idle',
  listening: 'Listening',
  processing: 'Processing',
  speaking: 'Speaking',
};

const VOICES = [
  { id: 'en-IN-NeerjaNeural', name: 'Neerja (Female)' },
  { id: 'en-US-GuyNeural', name: 'Guy (Male)' },
];

function VisualizerCanvas({ analyser }) {
  const canvasRef = useRef(null);
  const animationRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      const width = canvas.width = canvas.clientWidth * window.devicePixelRatio;
      const height = canvas.height = canvas.clientHeight * window.devicePixelRatio;
      ctx.clearRect(0, 0, width, height);

      if (analyser) {
        const bufferLength = analyser.fftSize;
        const dataArray = new Uint8Array(bufferLength);
        analyser.getByteTimeDomainData(dataArray);

        ctx.lineWidth = 2;
        ctx.strokeStyle = '#0f172a';
        ctx.beginPath();

        const sliceWidth = width / bufferLength;
        let x = 0;
        for (let i = 0; i < bufferLength; i++) {
          const v = dataArray[i] / 128.0;
          const y = (v * height) / 2;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
          x += sliceWidth;
        }
        ctx.lineTo(width, height / 2);
        ctx.stroke();
      } else {
        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, height / 2);
        ctx.lineTo(width, height / 2);
        ctx.stroke();
      }
      animationRef.current = requestAnimationFrame(draw);
    };

    animationRef.current = requestAnimationFrame(draw);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [analyser]);

  return <canvas ref={canvasRef} className="visualizer-canvas" />;
}

export default function VoiceCallScreen() {
  const { sessionId: routeSessionId } = useParams();
  const navigate = useNavigate();

  const {
    status,
    connectionStatus,
    transcript,
    sessionId,
    selectedPersona,
    selectedVoiceId,
    muted,
    error,
    latencies,
    startCall,
    stopCall,
    sendTextFallback,
    toggleMute,
    setSelectedPersona,
    selectVoice,
    setStatus,
  } = useVoiceCall();

  const [textInput, setTextInput] = useState('');
  const [isStarting, setIsStarting] = useState(false);
  const analyserRef = useRef(null);
  const stopCallRef = useRef(null);
  stopCallRef.current = stopCall;

  const initializedRef = useRef(false);

  useEffect(() => {
    if (!initializedRef.current && routeSessionId && status === 'idle') {
      initializedRef.current = true;
      const doInit = async () => {
        setIsStarting(true);
        await startCall();
        setIsStarting(false);
      };
      doInit();
    }
  }, [routeSessionId, startCall, status]);

  useEffect(() => {
    return () => {
      stopCallRef.current();
    };
  }, []);

  const handleEndCall = useCallback(() => {
    stopCall();
    navigate('/session');
  }, [stopCall, navigate]);

  const handleSendText = useCallback(() => {
    const trimmed = textInput.trim();
    if (!trimmed) return;
    sendTextFallback(trimmed);
    setTextInput('');
  }, [textInput, sendTextFallback]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendText();
    }
  }, [handleSendText]);

  const statusClass = status === 'listening' ? 'status-listening'
    : status === 'processing' ? 'status-processing'
    : status === 'speaking' ? 'status-speaking'
    : '';

  const isActive = connectionStatus === 'connected' || connectionStatus === 'authenticated' || status === 'listening' || status === 'processing' || status === 'speaking';

  return (
    <div className="voice-call-screen">
      <div className="vc-header">
        <div className="vc-header-left">
          <h2 className="vc-title">Voice Call</h2>
          <span className={`vc-status-badge ${statusClass}`}>
            {STATUS_LABELS[status] ?? status}
          </span>
        </div>
        <div className="vc-header-right">
          <span className={`vc-connection-dot ${connectionStatus}`} />
          <span className="vc-connection-label">
            {connectionStatus === 'connected' && 'Connected'}
            {connectionStatus === 'connecting' && 'Connecting...'}
            {connectionStatus === 'authenticated' && 'Authenticated'}
            {connectionStatus === 'error' && 'Connection error'}
            {connectionStatus === 'disconnected' && 'Disconnected'}
          </span>
        </div>
      </div>

      {error && (
        <div className="vc-error-banner">
          <span className="vc-error-icon">!</span>
          <span className="vc-error-text">{error}</span>
          <button className="vc-error-dismiss" onClick={() => setStatus('idle')}>x</button>
        </div>
      )}

      <div className="vc-body">
        <div className="vc-visualizer-section">
          <VisualizerCanvas analyser={analyserRef.current} />
          <div className="vc-latency-row">
            {latencies.stt !== null && (
              <span className="vc-latency-badge">STT: {latencies.stt}ms</span>
            )}
            {latencies.llm !== null && (
              <span className="vc-latency-badge">LLM: {latencies.llm}ms</span>
            )}
            {latencies.ttsFirstAudio !== null && (
              <span className="vc-latency-badge">TTS: {latencies.ttsFirstAudio}ms</span>
            )}
            {latencies.total !== null && (
              <span className="vc-latency-badge vc-latency-badge--total">Total: {latencies.total}ms</span>
            )}
          </div>
        </div>

        <div className="vc-controls-section">
          <div className="vc-voice-selector">
            <label className="vc-label">Voice</label>
            <select
              className="vc-select"
              value={selectedVoiceId ?? ''}
              onChange={(e) => selectVoice(e.target.value)}
              disabled={!isActive}
            >
              {VOICES.map((voice) => (
                <option key={voice.id} value={voice.id}>{voice.name}</option>
              ))}
            </select>
          </div>

          <div className="vc-mic-row">
            <button
              className={`vc-mic-button ${status === 'listening' && !muted ? 'vc-mic-button--active' : ''} ${muted ? 'vc-mic-button--muted' : ''}`}
              onClick={toggleMute}
              disabled={!isActive}
              aria-label={muted ? 'Unmute microphone' : 'Mute microphone'}
              title={muted ? 'Unmute' : 'Mute'}
            >
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3Z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="22" />
              </svg>
            </button>

            <button
              className="vc-end-button"
              onClick={handleEndCall}
              aria-label="End call"
              title="End call"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.362 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.338 1.85.573 2.81.7A2 2 0 0 1 22 16.92Z" transform="rotate(135 12 12)" />
              </svg>
            </button>
          </div>
        </div>

        <div className="vc-transcript-section">
          <h3 className="vc-section-title">Transcript</h3>
          <div className="vc-transcript-scroll">
            {transcript.length === 0 && (
              <p className="vc-transcript-empty">No messages yet. Start speaking or type below.</p>
            )}
            {transcript.map((entry) => (
              <div
                key={entry.id}
                className={`vc-transcript-entry ${entry.role === 'user' ? 'vc-transcript-entry--user' : 'vc-transcript-entry--assistant'}`}
              >
                <span className="vc-transcript-role">
                  {entry.role === 'user' ? 'You' : 'Assistant'}
                </span>
                <p className="vc-transcript-text">{entry.text}</p>
                <span className="vc-transcript-time">
                  {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              </div>
            ))}
            <div ref={(el) => {
              if (el) el.scrollIntoView({ behavior: 'smooth' });
            }} />
          </div>
        </div>

        <div className="vc-fallback-section">
          <div className="vc-fallback-row">
            <input
              type="text"
              className="vc-fallback-input"
              placeholder="Type a message as a fallback..."
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!isActive}
            />
            <Button
              size="sm"
              onClick={handleSendText}
              disabled={!isActive || !textInput.trim()}
              aria-label="Send text message"
            >
              Send
            </Button>
          </div>
          <p className="vc-fallback-hint">Use text input if your microphone is unavailable.</p>
        </div>
      </div>
    </div>
  );
}
