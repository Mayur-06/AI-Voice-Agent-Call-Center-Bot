import React, { useEffect, useRef, useCallback, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Separator } from '@/components/ui/separator';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useVoiceCall } from '@/hooks/useVoiceCall';
import useCallStore from '@/store/callStore';
import { cn } from '@/lib/utils';

export const PERSONAS = [
  {
    id: 'neha',
    name: 'Neha',
    initials: 'NP',
    role: 'Support Advisor',
    description: 'Empathetic, patient and solution-oriented. Helps you work through issues with warmth and clarity.',
    avatarUrl: 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&auto=format&fit=crop&q=80',
  },
  {
    id: 'alena',
    name: 'Alena',
    initials: 'AV',
    role: 'Technical Advisor',
    description: 'Precise, knowledgeable and step-by-step. Breaks down complex topics into actionable guidance.',
    avatarUrl: 'https://images.unsplash.com/photo-1580489944761-15a19d654956?w=150&auto=format&fit=crop&q=80',
  },
  {
    id: 'sora',
    name: 'Sora',
    initials: 'ST',
    role: 'Sales Partner',
    description: 'Friendly, persuasive and feature-focused. Helps align solutions with your needs and next steps.',
    avatarUrl: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
  },
  {
    id: 'aria',
    name: 'Aria',
    initials: 'AS',
    role: 'General Assistant',
    description: 'Balanced and helpful. Adapts to your intent and keeps conversations useful, direct, and supportive.',
    avatarUrl: 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=150&auto=format&fit=crop&q=80',
  },
];

export function getPersona(id) {
  return PERSONAS.find((p) => p.id === id) || PERSONAS[0];
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
      <svg className="vc-mobile-tab-icon shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3Z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="22" />
      </svg>
    );
  }
  if (tab === 'transcript') {
    return (
      <svg className="vc-mobile-tab-icon shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    );
  }
  return (
    <svg className="vc-mobile-tab-icon shrink-0" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

function SessionContextContent({ persona, docs }) {
  return (
    <div className="vc-context-body">
      {/* Persona card */}
      {persona && (
        <div className="vc-persona-card">
          <div className="vc-persona-row">
            <div className="vc-persona-avatar">
              <Avatar size="lg" className="h-10 w-10 border border-[#03191e]/15">
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
          {docs.length > 0 ? (
            docs.map((doc, idx) => {
              const id = doc?.id != null ? String(doc.id) : String(idx);
              const filename = typeof doc?.filename === 'string' ? doc.filename : `Document ${idx + 1}`;
              const pageCount = typeof doc?.page_count === 'number' ? `${doc.page_count} pages` : null;
              const meta = pageCount || 'Attached reference';
              return (
                <div key={id} className="vc-doc-item">
                  <div className="vc-doc-icon" aria-hidden="true">
                    <FileIcon />
                  </div>
                  <div className="vc-doc-body">
                    <p className="vc-doc-name" title={filename}>{filename}</p>
                    {meta && <p className="vc-doc-meta">{meta}</p>}
                  </div>
                </div>
              );
            })
          ) : (
            <p className="vc-docs-empty">No reference files attached</p>
          )}
        </div>
      </div>
    </div>
  );
}

function AuraVisualizer({
  state,
  muted,
  isCapturing,
  onToggleCapture,
}) {
  const auraState =
    muted || !isCapturing
      ? 'aura-muted'
      : state === 'listening'
      ? 'aura-listening'
      : state === 'speaking'
      ? 'aura-speaking'
      : state === 'processing'
      ? 'aura-thinking'
      : state === 'idle'
      ? 'aura-idle'
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
    <div className={`vc-aura-visualizer ${auraState}`} aria-hidden="true">
      <svg className="vc-aura-svg" viewBox="0 0 200 200">
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
              aria-label={isCapturing ? 'Mute microphone' : 'Unmute microphone'}
              onClick={onToggleCapture}
            >
              <span className="vc-aura-mic-icon">
                {isCapturing ? <MicIcon /> : <MicOffIcon />}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="top">
            {isCapturing ? 'Mute microphone' : 'Unmute microphone'}
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}

export default function VoiceCallScreen({
  onEndCallCallback,
}) {
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
  const [textInput, setTextInput] = useState('');
  const [activeTab, setActiveTab] = useState('call');
  const [isContextDrawerOpen, setIsContextDrawerOpen] = useState(false);

  const initializedRef = useRef(false);
  const transcriptEndRef = useRef(null);

  // Auto-close context drawer if screen is resized to desktop (>= 1024px) where right sidebar is permanently visible
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
    if (!initializedRef.current && status === 'idle') {
      initializedRef.current = true;
      startCall();
    }
  }, [startCall, status]);

  useEffect(() => {
    if (transcriptEndRef.current) {
      transcriptEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [transcript, filler]);

  const handleEndCall = useCallback(() => {
    stopCall();
    onEndCallCallback?.();
  }, [stopCall, onEndCallCallback]);

  const handleSendText = useCallback(() => {
    const trimmed = textInput.trim();
    if (!trimmed) return;
    sendTextFallback(trimmed);
    setTextInput('');
  }, [textInput, sendTextFallback]);

  const handleToggleCapture = useCallback(() => {
    toggleCapture();
  }, [toggleCapture]);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendText();
      }
    },
    [handleSendText]
  );

  const isAiSpeaking = status === 'speaking';
  const isProcessing = status === 'processing';
  const isListening = status === 'listening';
  const isConnected = connectionStatus === 'connected' || connectionStatus === 'authenticated';

  const connectionLabel =
    (connectionStatus === 'connected' && 'Connected') ||
    (connectionStatus === 'connecting' && 'Connecting...') ||
    (connectionStatus === 'authenticated' && 'Authenticated') ||
    (connectionStatus === 'error' && 'Connection error') ||
    (connectionStatus === 'disconnected' && 'Disconnected') ||
    'Unknown';

  const persona = getPersona(selectedPersona);
  const docs = uploadedDocuments || [];

  return (
    <div className="voice-call-screen">
      {/* ─── Top App Bar ─────────────────────────────────────────────── */}
      <header className="vc-app-bar">
        <div className="vc-app-bar-inner">
          <div className="vc-app-bar-left">
            <div className="vc-app-bar-brand">
              <div className="vc-app-bar-logo" aria-hidden="true">
                A
              </div>
              <span className="vc-app-bar-title">Aura</span>
            </div>
            {persona && (
              <button
                type="button"
                onClick={() => {
                  if (window.innerWidth < 1024) {
                    setIsContextDrawerOpen(true);
                  }
                }}
                className="vc-app-bar-persona hidden sm:flex lg:pointer-events-none items-center gap-1.5 text-xs text-white/75 hover:text-white transition-colors cursor-pointer lg:cursor-default"
                title="Persona details (visible in right sidebar on desktop, or tap to open)"
              >
                <span className="font-semibold text-white/95">{persona.name}</span>
                <span className="text-white/35">•</span>
                <span className="text-white/60 truncate max-w-[120px] sm:max-w-[160px]">{persona.role}</span>
              </button>
            )}
          </div>
          <div className="vc-app-bar-right">
            {/* Context button: visible and active on tablet (700px - 1023px) to open session context drawer. Hidden on mobile (< 700px) and desktop (>= 1024px) */}
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsContextDrawerOpen(true)}
              className="vc-context-toggle-btn"
              aria-label="Open session context sidebar from right"
            >
              <InfoIcon />
              <span className="hidden sm:inline">Context</span>
              {docs.length > 0 && (
                <span className="vc-context-toggle-badge">{docs.length}</span>
              )}
            </Button>

            <div className="vc-connection-indicator">
              <span className={`vc-connection-dot ${connectionStatus}`} />
              <span className="vc-connection-label hidden sm:inline">{connectionLabel}</span>
            </div>
          </div>
        </div>
      </header>

      {/* ─── Mobile View Tabs (Visible only on < 700px) ────────────── */}
      <nav className="vc-mobile-nav" aria-label="Call views">
        <div className="vc-mobile-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'call'}
            className={cn('vc-mobile-tab-btn', activeTab === 'call' && 'vc-mobile-tab-btn--active')}
            onClick={() => {
              setActiveTab('call');
              setIsContextDrawerOpen(false);
            }}
          >
            <TabIcon tab="call" />
            <span className="vc-mobile-tab-label">Voice Call</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'transcript'}
            className={cn('vc-mobile-tab-btn', activeTab === 'transcript' && 'vc-mobile-tab-btn--active')}
            onClick={() => {
              setActiveTab('transcript');
              setIsContextDrawerOpen(false);
            }}
          >
            <TabIcon tab="transcript" />
            <span className="vc-mobile-tab-label">Transcript</span>
            {transcript.length > 0 && (
              <span className="vc-mobile-tab-badge">{transcript.length}</span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'context'}
            className={cn('vc-mobile-tab-btn', activeTab === 'context' && 'vc-mobile-tab-btn--active')}
            onClick={() => {
              setActiveTab('context');
              setIsContextDrawerOpen(false);
            }}
          >
            <TabIcon tab="context" />
            <span className="vc-mobile-tab-label">Context</span>
            {docs.length > 0 && (
              <span className="vc-mobile-tab-badge">{docs.length}</span>
            )}
          </button>
        </div>
      </nav>

      {/* ─── Error Banner ───────────────────────────────────────────── */}
      {error && (
        <div className="vc-error-banner" role="alert">
          <span className="vc-error-icon">!</span>
          <span className="vc-error-text">{error}</span>
          <button className="vc-error-dismiss" onClick={() => setError(null)} aria-label="Dismiss error">
            ×
          </button>
        </div>
      )}

      {/* ─── Main Workspace ─────────────────────────────────────────── */}
      <main className="vc-main">
        {/* ─── LEFT: Transcript Column ─────────────────────────────────────── */}
        <section
          className={cn(
            'vc-transcript-column',
            activeTab !== 'transcript' && 'vc-mobile-hidden'
          )}
        >
          <div className="vc-transcript-header">
            <div className="vc-transcript-header-left">
              <span className="vc-column-title">Live Transcription</span>
              <span className="vc-column-sep">•</span>
              <span className="vc-column-subtitle">Conversation &amp; Notes</span>
            </div>
            {transcript.length > 0 && (
              <span className="vc-context-toggle-badge">{transcript.length}</span>
            )}
          </div>
          <div className="vc-transcript-scroll">
            {transcript.length === 0 && !filler && (
              <div className="vc-transcript-empty">
                <p className="font-semibold text-xs text-[#03191e]/80 mb-1">Live Transcript Active</p>
                <p>Spoken dialogue and user notes will stream here in real time as you speak.</p>
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
                className={cn(
                  'vc-chat-bubble',
                  entry.role === 'user' ? 'vc-chat-bubble--user' : 'vc-chat-bubble--assistant'
                )}
              >
                <div className="vc-chat-meta">
                  <span className="vc-chat-name">{entry.role === 'user' ? 'You' : 'Aura'}</span>
                  <span className="vc-chat-time">
                    {new Date(entry.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>
                <div
                  className={cn(
                    'vc-chat-body',
                    entry.role === 'user' ? 'vc-chat-body--user' : 'vc-chat-body--assistant'
                  )}
                >
                  {entry.text}
                </div>
              </div>
            ))}
            <div ref={transcriptEndRef} />
          </div>
        </section>

        {/* ─── CENTER: Aura Visualizer Column ──────────────────────────────── */}
        <section
          className={cn(
            'vc-aura-column',
            activeTab !== 'call' && 'vc-mobile-hidden'
          )}
        >
          <div className="vc-aura-wrapper">
            {/* Ambient soft glow rings */}
            <div className="vc-aura-backdrop-outer" aria-hidden="true" />
            <div className="vc-aura-backdrop-inner" aria-hidden="true" />
            <AuraVisualizer
              state={muted || !isCapturing ? 'muted' : status}
              muted={muted || !isCapturing}
              isCapturing={isCapturing}
              onToggleCapture={handleToggleCapture}
            />
          </div>

          {/* Real-time status indicator */}
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
              {isProcessing && !isAiSpeaking && 'Processing thought...'}
              {isListening && isCapturing && 'Listening to you...'}
              {!isAiSpeaking && !isProcessing && !isListening && !isConnected && 'Disconnected'}
              {!isAiSpeaking && !isProcessing && !isListening && isConnected && !isCapturing && 'Microphone muted'}
              {!isAiSpeaking && !isProcessing && !isListening && isConnected && isCapturing && 'Ready & listening'}
            </span>
          </div>

          {/* Microphone Status Pill */}
          <button
            type="button"
            onClick={handleToggleCapture}
            className={cn(
              'vc-mic-status-pill',
              isCapturing && !muted ? 'vc-mic-status-pill--active' : 'vc-mic-status-pill--muted'
            )}
            title={isCapturing && !muted ? 'Click to mute microphone' : 'Click to unmute microphone'}
          >
            <span className={cn('w-2 h-2 rounded-full', isCapturing && !muted ? 'bg-emerald-500' : 'bg-red-500 animate-pulse')} />
            <span>{isCapturing && !muted ? 'Microphone Active' : 'Microphone Muted (Tap to speak)'}</span>
          </button>

          <p className="vc-aura-hint">
            Tap the orb or mic status to toggle speech, or type notes below.
          </p>
        </section>

        {/* ─── RIGHT: Session Context (Permanent sidebar on right) ─── */}
        <section
          className={cn(
            'vc-context-column',
            activeTab !== 'context' && 'vc-mobile-hidden'
          )}
        >
          <div className="vc-context-card">
            <div className="vc-context-header flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="vc-context-header-title">Session Context</span>
                <span className="vc-column-sep">•</span>
                <span className="vc-column-subtitle">Briefs &amp; Documents</span>
              </div>
              <span className="vc-context-toggle-badge">{docs.length}</span>
            </div>
            <SessionContextContent persona={persona} docs={docs} />
          </div>
        </section>
      </main>

      {/* ─── Tablet / Mobile Context Slide-over Drawer ───────────────────────── */}
      {isContextDrawerOpen && (
        <>
          <div
            className="vc-drawer-backdrop"
            onClick={() => setIsContextDrawerOpen(false)}
            aria-hidden="true"
          />
          <div
            className="vc-drawer-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Session Context"
          >
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
          {/* Center: Note Input */}
          <div className="vc-controls-center">
            {/* Note / Text Fallback Input */}
            <div className="vc-text-input-wrapper">
              <input
                type="text"
                className="vc-text-input"
                placeholder="Type note or message for Aura..."
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
                <Button
                  variant="destructive"
                  size="default"
                  className="vc-end-call-btn"
                  aria-label="End call"
                >
                  <EndCallIcon />
                  <span className="hidden sm:inline">End Call</span>
                  <span className="sm:hidden">End</span>
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>End this call?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will disconnect the voice session and wrap up the call. Your transcript and references will be archived into your session debrief.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Resume Call</AlertDialogCancel>
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
