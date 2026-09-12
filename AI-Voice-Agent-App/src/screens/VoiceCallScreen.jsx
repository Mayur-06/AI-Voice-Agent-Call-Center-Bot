import { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, buttonVariants } from '@/components/ui/button';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Separator } from '@/components/ui/separator';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Toast, ToastClose, ToastDescription, ToastTitle } from '@/components/ui/toast';
import { useVoiceCall } from '@/hooks/useVoiceCall';
import useCallStore from '@/store/callStore';
import { cn } from '@/lib/utils';

const PERSONAS = [
  {
    id: 'neha',
    name: 'Neha',
    initials: 'NP',
    role: 'Support Advisor',
    description: 'Empathetic, patient and solution-oriented. Helps you work through issues with warmth and clarity.',
    avatarUrl: 'https://res.cloudinary.com/ejpx0qht/image/upload/v1788858004/aura-avatars/neha.png',
  },
  {
    id: 'alena',
    name: 'Alena',
    initials: 'AV',
    role: 'Technical Advisor',
    description: 'Precise, knowledgeable and step-by-step. Breaks down complex topics into actionable guidance.',
    avatarUrl: 'https://res.cloudinary.com/ejpx0qht/image/upload/v1788858005/aura-avatars/alena.png',
  },
  {
    id: 'sora',
    name: 'Sora',
    initials: 'ST',
    role: 'Sales Partner',
    description: 'Friendly, persuasive and feature-focused. Helps align solutions with your needs and next steps.',
    avatarUrl: 'https://res.cloudinary.com/ejpx0qht/image/upload/v1788858006/aura-avatars/sora.png',
  },
  {
    id: 'aria',
    name: 'Aria',
    initials: 'AS',
    role: 'General Assistant',
    description: 'Balanced and helpful. Adapts to your intent and keeps conversations useful, direct, and supportive.',
    avatarUrl: 'https://res.cloudinary.com/ejpx0qht/image/upload/v1788858007/aura-avatars/aria.png',
  },
];

function getPersona(id) {
  return PERSONAS.find((p) => p.id === id) || null;
}

function isMicError(message) {
  if (!message || typeof message !== 'string') return false;
  const lower = message.toLowerCase();
  return lower.includes('microphone') || lower.includes('worklet') || lower.includes('getusermedia');
}

function MicIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </svg>
  );
}

function MicOffIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="2" y1="2" x2="22" y2="22" />
      <path d="M18.89 13.23A7.12 7.12 0 0 0 19 12v-2" />
      <path d="M5 10v2a7 7 0 0 0 12 5" />
      <path d="M15 9.34V5a3 3 0 0 0-5.68-1.33" />
      <path d="M9 9v3a3 3 0 0 0 4.26 2.5" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </svg>
  );
}

function EndCallIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.362 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.338 1.85.573 2.81.7A2 2 0 0 1 22 16.92Z" transform="rotate(135 12 12)" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="5 12 12 5 19 12" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function TabIcon({ tab }) {
  if (tab === 'call') {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3Z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="22" />
      </svg>
    );
  }
  if (tab === 'transcript') {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    );
  }
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

function SessionContextContent({ persona, docs }) {
  return (
    <div className="vc-context-body">
      {/* Persona */}
      {persona && (
        <div className="vc-persona-card">
          <div className="vc-persona-row">
            <div className="vc-persona-avatar">
              <Avatar size="lg" className="h-10 w-10">
                {persona.avatarUrl ? (
                  <AvatarImage src={persona.avatarUrl} alt={persona.name} />
                ) : null}
                <AvatarFallback>{persona.initials}</AvatarFallback>
              </Avatar>
            </div>
            <div className="vc-persona-meta">
              <h3 className="vc-persona-name">{persona.name}</h3>
              <p className="vc-persona-role">{persona.role}</p>
            </div>
          </div>
          <p className="vc-persona-desc">{persona.description}</p>
        </div>
      )}

      <Separator className="vc-context-separator" />

      {/* Referenced Docs */}
      <div className="vc-docs-section">
        <div className="vc-docs-header">
          <span className="vc-docs-title">Referenced in Call</span>
          <span className="vc-docs-count">{docs.length} topic{docs.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="vc-docs-list">
          {docs.length > 0 ? docs.map((doc, idx) => {
            const id = doc?.id != null ? String(doc.id) : String(idx);
            const filename = typeof doc?.filename === 'string' ? doc.filename : `Document ${idx + 1}`;
            const pageCount = typeof doc?.page_count === 'number' ? `${doc.page_count} pages` : null;
            const meta = pageCount || null;
            return (
              <div key={id} className="vc-doc-item">
                <div className="vc-doc-icon" aria-hidden="true">
                  <FileIcon />
                </div>
                <div className="vc-doc-body">
                  <p className="vc-doc-name">{filename}</p>
                  {meta && <p className="vc-doc-meta">{meta}</p>}
                </div>
              </div>
            );
          }) : (
            <p className="vc-docs-empty">No reference files attached</p>
          )}
        </div>
      </div>
    </div>
  );
}

function AuraVisualizer({ state, muted, isCapturing, onToggleCapture }) {
  const auraState = (muted || !isCapturing) ? 'aura-muted'
    : state === 'listening' ? 'aura-listening'
    : state === 'speaking' ? 'aura-speaking'
    : state === 'processing' ? 'aura-thinking'
    : state === 'idle' ? 'aura-idle'
    : 'aura-muted';

  const lineElements = [
    { x1: 100, y1: 24, x2: 100, y2: 38, stroke: '#03191e', width: 2 },
    { x1: 118, y1: 26, x2: 114, y2: 40, stroke: '#ebe1c1', width: 2 },
    { x1: 135, y1: 33, x2: 128, y2: 46, stroke: '#03191e', width: 2 },
    { x1: 150, y1: 45, x2: 140, y2: 56, stroke: '#ebe1c1', width: 2.5 },
    { x1: 162, y1: 60, x2: 150, y2: 69, stroke: '#03191e', width: 2 },
    { x1: 170, y1: 78, x2: 156, y2: 84, stroke: '#ebe1c1', width: 2.5 },
    { x1: 174, y1: 100, x2: 158, y2: 100, stroke: '#03191e', width: 2.5 },
    { x1: 170, y1: 122, x2: 156, y2: 116, stroke: '#ebe1c1', width: 2.5 },
    { x1: 162, y1: 140, x2: 150, y2: 131, stroke: '#03191e', width: 2.5 },
    { x1: 150, y1: 155, x2: 140, y2: 144, stroke: '#ebe1c1', width: 2.5 },
    { x1: 135, y1: 167, x2: 128, y2: 154, stroke: '#03191e', width: 2 },
    { x1: 118, y1: 174, x2: 114, y2: 160, stroke: '#03191e', width: 2.5 },
    { x1: 100, y1: 176, x2: 100, y2: 162, stroke: '#03191e', width: 2 },
    { x1: 82, y1: 174, x2: 86, y2: 160, stroke: '#ebe1c1', width: 2.5 },
    { x1: 65, y1: 167, x2: 72, y2: 154, stroke: '#03191e', width: 2 },
    { x1: 50, y1: 155, x2: 60, y2: 144, stroke: '#ebe1c1', width: 2.5 },
    { x1: 38, y1: 140, x2: 50, y2: 131, stroke: '#03191e', width: 2.5 },
    { x1: 30, y1: 122, x2: 44, y2: 116, stroke: '#ebe1c1', width: 2.5 },
    { x1: 26, y1: 100, x2: 42, y2: 100, stroke: '#03191e', width: 2.5 },
    { x1: 30, y1: 78, x2: 44, y2: 84, stroke: '#03191e', width: 2.5 },
    { x1: 38, y1: 60, x2: 50, y2: 69, stroke: '#ebe1c1', width: 2.5 },
    { x1: 50, y1: 45, x2: 60, y2: 56, stroke: '#03191e', width: 2 },
    { x1: 65, y1: 33, x2: 72, y2: 46, stroke: '#03191e', width: 2 },
    { x1: 82, y1: 26, x2: 86, y2: 40, stroke: '#ebe1c1', width: 2.5 },
  ];

  return (
    <div className={`vc-aura-visualizer ${auraState}`}>
      <svg className="vc-aura-svg" viewBox="0 0 200 200" aria-hidden="true">
        <defs>
          <radialGradient id="gentleSunGlow" cx="50%" cy="50%" fx="50%" fy="50%" r="50%">
            <stop offset="0%" stopColor="#ebe1c1" stopOpacity={auraState === 'aura-speaking' ? 0.7 : 0.4} />
            <stop offset="60%" stopColor="#ebe1c1" stopOpacity={auraState === 'aura-speaking' ? 0.25 : 0.12} />
            <stop offset="100%" stopColor="#faf9fb" stopOpacity={0} />
          </radialGradient>
        </defs>
        <circle cx="100" cy="100" fill="url(#gentleSunGlow)" r="82" />
        {lineElements.map((line, i) => (
          <line
            key={i}
            x1={line.x1}
            x2={line.x2}
            y1={line.y1}
            y2={line.y2}
            stroke={line.stroke}
            strokeLinecap="round"
            strokeWidth={line.width}
            className="vc-aura-line"
            style={{ animationDelay: `${i * 0.06}s` }}
          />
        ))}
      </svg>
      <div className="vc-aura-orb-wrapper">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className={cn(
                'vc-aura-mic-btn',
                !isCapturing && 'vc-aura-mic-btn--muted'
              )}
              aria-label={isCapturing ? 'Turn off microphone' : 'Turn on microphone'}
              onClick={onToggleCapture}
            >
              <span className="vc-aura-mic-icon">
                {isCapturing ? <MicIcon /> : <MicOffIcon />}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">
            {isCapturing ? 'Turn off microphone' : 'Turn on microphone'}
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}

export default function VoiceCallScreen() {
  const { sessionId: routeSessionId } = useParams();
  const navigate = useNavigate();

  const {
    status,
    connectionStatus,
    transcript,
    selectedPersona,
    muted,
    error,
    filler,
    isCapturing,
    startCall,
    stopCall,
    sendTextFallback,
    setError,
    toggleCapture,
  } = useVoiceCall();

  const uploadedDocuments = useCallStore((s) => s.uploadedDocuments);
  const setUploadedDocuments = useCallStore((s) => s.setUploadedDocuments);
  const [textInput, setTextInput] = useState('');
  const [activeTab, setActiveTab] = useState('call'); // 'call' | 'transcript'
  const [isContextDrawerOpen, setIsContextDrawerOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const initializedRef = useRef(false);
  const transcriptEndRef = useRef(null);

  // Auto-close context drawer if screen is resized to desktop (>= 1024px)
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1024) {
        setIsContextDrawerOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Close context drawer on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isContextDrawerOpen) {
        setIsContextDrawerOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isContextDrawerOpen]);

  useEffect(() => {
    if (!initializedRef.current && routeSessionId && status === 'idle') {
      initializedRef.current = true;
      const doInit = async () => {
        await startCall(routeSessionId);
      };
      doInit();
    }
  }, [routeSessionId, startCall, status]);

  useEffect(() => {
    if (transcriptEndRef.current) {
      transcriptEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [transcript, filler]);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 4000);
    return () => clearTimeout(t);
  }, [error, setError]);

  const handleEndCall = useCallback(() => {
    stopCall();
    setUploadedDocuments([]);
    if (routeSessionId) {
      navigate(`/review/${routeSessionId}`, { replace: true });
    } else {
      navigate('/session');
    }
  }, [stopCall, navigate, routeSessionId, setUploadedDocuments]);

  const handleSendText = useCallback(() => {
    const trimmed = textInput.trim();
    if (!trimmed) return;
    sendTextFallback(trimmed);
    setTextInput('');
  }, [textInput, sendTextFallback]);

  const handleToggleCapture = useCallback(() => {
    console.info('[voice] toggleCapture click; isCapturing=', isCapturing, 'status=', status);
    toggleCapture();
  }, [toggleCapture, isCapturing, status]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendText();
    }
  }, [handleSendText]);

  const handleCopyTranscript = useCallback(() => {
    if (!transcript || transcript.length === 0) return;
    const text = transcript
      .map((t) => `[${new Date(t.timestamp).toLocaleTimeString()}] ${t.role === 'user' ? 'You' : 'Aura'}: ${t.text}`)
      .join('\n\n');
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch((err) => {
      console.error('Failed to copy', err);
    });
  }, [transcript]);

  const handleExportTranscript = useCallback(() => {
    if (!transcript || transcript.length === 0) return;
    const personaObj = getPersona(selectedPersona);
    const personaTitle = personaObj?.name ? `Session with ${personaObj.name}` : 'Voice Session';
    const header = `${personaTitle}\nDate: ${new Date().toLocaleString()}\nSession ID: ${routeSessionId || 'N/A'}\n${'='.repeat(40)}\n\n`;
    const body = transcript
      .map((t) => `[${new Date(t.timestamp).toLocaleTimeString()}] ${t.role === 'user' ? 'You' : 'Aura'}:\n${t.text}`)
      .join('\n\n');
    const blob = new Blob([header + body], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `aura-session-${routeSessionId || 'transcript'}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [transcript, selectedPersona, routeSessionId]);

  const isAiSpeaking = status === 'speaking';
  const isProcessing = status === 'processing';
  const isListening = status === 'listening';
  const isConnected = connectionStatus === 'connected' || connectionStatus === 'authenticated';

  const connectionLabel = connectionStatus === 'connected' && 'Connected'
    || connectionStatus === 'connecting' && 'Connecting...'
    || connectionStatus === 'authenticated' && 'Authenticated'
    || connectionStatus === 'error' && 'Connection error'
    || connectionStatus === 'disconnected' && 'Disconnected'
    || 'Unknown';

  const persona = getPersona(selectedPersona);
  const docs = uploadedDocuments || [];

  const latestMessage = useMemo(() => {
    if (filler) {
      return { role: 'assistant', text: filler, isFiller: true };
    }
    if (transcript && transcript.length > 0) {
      return transcript[transcript.length - 1];
    }
    return null;
  }, [transcript, filler]);

  return (
    <div className="voice-call-screen">
      {/* ─── Top App Bar ─────────────────────────────────────────────── */}
      <header className="vc-app-bar">
        <div className="vc-app-bar-inner">
          <div className="vc-app-bar-left">
            <div className="vc-app-bar-brand">
              <div className="vc-app-bar-logo" aria-hidden="true">A</div>
              <span className="vc-app-bar-title">Aura</span>
            </div>
            {persona && (
              <button
                type="button"
                onClick={() => setIsContextDrawerOpen(true)}
                className="vc-app-bar-persona hidden sm:flex lg:pointer-events-none items-center gap-1.5 text-xs text-white/70 pl-3 border-l border-white/10 hover:text-white transition-colors cursor-pointer lg:cursor-default"
                title="View persona details"
              >
                <span className="font-semibold text-white/90">{persona.name}</span>
                <span className="text-white/40">•</span>
                <span className="text-white/60">{persona.role}</span>
              </button>
            )}
          </div>
          <div className="vc-app-bar-right">
            {/* Context side bar toggle button: active for all screens except desktop (lg:hidden) */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsContextDrawerOpen(true)}
              className="vc-context-toggle-btn"
              aria-label="Open session context sidebar"
            >
              <InfoIcon />
              <span>Context</span>
              {docs.length > 0 && (
                <span className="vc-context-toggle-badge">{docs.length}</span>
              )}
            </Button>

            <div className="vc-connection-indicator">
              <span className={`vc-connection-dot ${connectionStatus}`} />
              <span className="vc-connection-label">{connectionLabel}</span>
            </div>
          </div>
        </div>
      </header>

      {/* ─── Mobile View Tabs (Visible only on < 768px) ────────────── */}
      <nav className="vc-mobile-nav" aria-label="Call views">
        <div className="vc-mobile-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'call'}
            className={cn('vc-mobile-tab-btn', activeTab === 'call' && 'vc-mobile-tab-btn--active')}
            onClick={() => setActiveTab('call')}
          >
            <TabIcon tab="call" />
            <span>Call</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'transcript'}
            className={cn('vc-mobile-tab-btn', activeTab === 'transcript' && 'vc-mobile-tab-btn--active')}
            onClick={() => setActiveTab('transcript')}
          >
            <TabIcon tab="transcript" />
            <span>Transcript</span>
            {transcript.length > 0 && (
              <span className="vc-mobile-tab-badge">{transcript.length}</span>
            )}
          </button>
          <button
            type="button"
            role="button"
            aria-label="Open session context sidebar"
            className={cn('vc-mobile-tab-btn', isContextDrawerOpen && 'vc-mobile-tab-btn--active')}
            onClick={() => setIsContextDrawerOpen(true)}
          >
            <TabIcon tab="context" />
            <span>Context</span>
            {docs.length > 0 && (
              <span className="vc-mobile-tab-badge">{docs.length}</span>
            )}
          </button>
        </div>
      </nav>

      {/* ─── Toast Layer ───────────────────────────────────────────── */}
      {error && isMicError(error) && (
        <Toast>
          <ToastTitle>Unable to continue</ToastTitle>
          <ToastDescription>{error}</ToastDescription>
          <ToastClose onClick={() => setError(null)} />
        </Toast>
      )}

      {/* ─── Main Workspace ─────────────────────────────────────────── */}
      <main className="vc-main">
        {/* ─── LEFT: Transcript ─────────────────────────────────────── */}
        <section className={cn('vc-transcript-column', activeTab === 'transcript' && 'vc-pane--active')}>
          <div className="vc-transcript-header">
            <div className="vc-transcript-header-left">
              <span className="vc-column-title">Conversation</span>
              <span className="vc-column-sep">•</span>
              <span className="vc-column-subtitle">Notes &amp; Flow</span>
            </div>
            <div className="vc-transcript-header-right">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }), "vc-icon-btn")}
                    aria-label="Copy conversation"
                    onClick={handleCopyTranscript}
                    disabled={transcript.length === 0}
                  >
                    {copied ? (
                      <CheckIcon />
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                      </svg>
                    )}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">{copied ? 'Copied to clipboard!' : 'Copy conversation'}</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }), "vc-icon-btn")}
                    aria-label="Export notes"
                    onClick={handleExportTranscript}
                    disabled={transcript.length === 0}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="18" cy="5" r="3" />
                      <circle cx="6" cy="12" r="3" />
                      <circle cx="18" cy="19" r="3" />
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
                    </svg>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">Export notes</TooltipContent>
              </Tooltip>
            </div>
          </div>
          <div className="vc-transcript-scroll">
            {transcript.length === 0 && !filler && (
              <div className="vc-transcript-empty">
                <p>No messages yet. Start speaking or type below.</p>
              </div>
            )}
            {filler && (
              <div className="vc-chat-bubble vc-chat-bubble--filler">
                <div className="vc-chat-meta">
                  <span className="vc-chat-name">Aura</span>
                  <span className="vc-chat-time">
                    {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
                <div className="vc-chat-body vc-chat-body--filler">
                  {filler}
                  <span className="vc-chat-cursor" aria-hidden="true" />
                </div>
              </div>
            )}
            {transcript.map((entry) => (
              <div
                key={entry.id}
                className={`vc-chat-bubble ${entry.role === 'user' ? 'vc-chat-bubble--user' : 'vc-chat-bubble--assistant'}`}
              >
                <div className="vc-chat-meta">
                  <span className="vc-chat-name">
                    {entry.role === 'user' ? 'You' : 'Aura'}
                  </span>
                  <span className="vc-chat-time">
                    {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </span>
                </div>
                <div className={`vc-chat-body ${entry.role === 'user' ? 'vc-chat-body--user' : 'vc-chat-body--assistant'}`}>
                  {entry.text}
                </div>
              </div>
            ))}
            <div ref={transcriptEndRef} />
          </div>
        </section>

        {/* ─── CENTER: Aura Visualizer ──────────────────────────────── */}
        <section className={cn('vc-aura-column', activeTab === 'call' && 'vc-pane--active')}>
          <div className="vc-aura-wrapper">
            {/* Soft ambient backdrop */}
            <div className="vc-aura-backdrop-outer" aria-hidden="true" />
            <div className="vc-aura-backdrop-inner" aria-hidden="true" />
            <AuraVisualizer 
              state={muted || !isCapturing ? 'muted' : status} 
              muted={muted || !isCapturing}
              isCapturing={isCapturing}
              onToggleCapture={handleToggleCapture}
            />
          </div>

          {/* Status indicator */}
          <div className="vc-status-chip">
            <div className="vc-wave-bars" aria-hidden="true">
              {(isAiSpeaking || isListening || isProcessing) && (
                <>
                  <span className="vc-wave-bar vc-wave-bar-1" />
                  <span className="vc-wave-bar vc-wave-bar-2" />
                  <span className="vc-wave-bar vc-wave-bar-3" />
                  <span className="vc-wave-bar vc-wave-bar-4" />
                  <span className="vc-wave-bar vc-wave-bar-5" />
                </>
              )}
            </div>
            <span className="vc-status-text">
              {isAiSpeaking && 'Aura is speaking...'}
              {isProcessing && !isAiSpeaking && 'Processing...'}
              {isListening && isCapturing && 'Listening...'}
              {!isAiSpeaking && !isProcessing && !isListening && !isConnected && 'Disconnected'}
              {!isAiSpeaking && !isProcessing && !isListening && isConnected && !isCapturing && 'idle'}
            </span>
          </div>

          <p className="vc-aura-hint">
            Click the orb to speak, then turn off to proceed
          </p>

          {/* Mobile Live Floating Caption */}
          {latestMessage && (
            <div
              className="vc-mobile-caption"
              onClick={() => setActiveTab('transcript')}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && setActiveTab('transcript')}
              aria-label="View message in transcript"
            >
              <div className="vc-mobile-caption-meta">
                <span className="vc-mobile-caption-role">{latestMessage.role === 'user' ? 'You' : 'Aura'}</span>
                <span className="vc-mobile-caption-link">View all ({transcript.length}) →</span>
              </div>
              <p className="vc-mobile-caption-text">
                {latestMessage.text}
                {latestMessage.isFiller && <span className="vc-chat-cursor" aria-hidden="true" />}
              </p>
            </div>
          )}
        </section>

        {/* ─── RIGHT: Session Context (Permanent sidebar on desktop only) ─── */}
        <section className="vc-context-column">
          <div className="vc-context-card">
            <div className="vc-context-header">
              <span className="vc-context-header-title">Session Context</span>
            </div>
            <SessionContextContent persona={persona} docs={docs} />
          </div>
        </section>
      </main>

      {/* ─── Tablet / Mobile Context Drawer ───────────────────────── */}
      {isContextDrawerOpen && (
        <>
          <div
            className="vc-drawer-backdrop"
            onClick={() => setIsContextDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="vc-drawer-panel" role="dialog" aria-modal="true" aria-label="Session Context">
            <div className="vc-drawer-header">
              <h2 className="vc-drawer-title">Session Context</h2>
              <button
                type="button"
                className="vc-drawer-close"
                onClick={() => setIsContextDrawerOpen(false)}
                aria-label="Close session context"
              >
                <CloseIcon />
              </button>
            </div>
            <SessionContextContent persona={persona} docs={docs} />
          </div>
        </>
      )}

      {/* ─── Bottom Control Dock ─────────────────────────────────────── */}
      <footer className="vc-controls-bar">
        <div className="vc-controls-inner">
          {/* Left spacer for symmetry on large screens */}
          <div className="vc-controls-left" />

          {/* Center: Fallback Text Input */}
          <div className="vc-controls-center">
            <div className="vc-text-input-wrapper">
              <input
                type="text"
                className="vc-text-input"
                placeholder="Type a message or note for Aura..."
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={!isConnected}
              />
              <Button
                size="icon-sm"
                onClick={handleSendText}
                disabled={!isConnected || !textInput.trim()}
                aria-label="Send note"
                className="vc-send-btn"
              >
                <SendIcon />
              </Button>
            </div>
          </div>

          {/* Right: Call Actions */}
          <div className="vc-controls-right">
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <button
                  type="button"
                  className={cn(buttonVariants({ variant: "destructive", size: "default" }), "vc-end-call-btn")}
                  aria-label="End call"
                >
                  <EndCallIcon />
                  <span className="hidden sm:inline">End Call</span>
                  <span className="sm:hidden">End</span>
                </button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>End this call?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will disconnect the voice session and return you to the setup screen. Any unsaved context will be cleared.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleEndCall}>End Call</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </footer>
    </div>
  );
}
