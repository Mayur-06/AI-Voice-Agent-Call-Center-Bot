import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useVoiceCall } from '@/hooks/useVoiceCall';
import useCallStore from '@/store/callStore';
import { Button } from '@/components/ui/button';
import { API_BASE, apiFetch } from '@/config';

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

const VOICE_STYLES = [
  {
    id: 'en-IN-NeerjaNeural',
    name: 'Neerja',
    description: 'Warm, natural Indian voice — articulate and empathetic',
    previewUrl: 'https://res.cloudinary.com/ejpx0qht/video/upload/v1788860561/voice-previews/en-IN-NeerjaNeural.mp3',
  },
  {
    id: 'en-US-JennyNeural',
    name: 'Jenny',
    description: 'Calm, clear US English voice — steady and professional',
    previewUrl: 'https://res.cloudinary.com/ejpx0qht/video/upload/v1788860562/voice-previews/en-US-JennyNeural.mp3',
  },
];

const ACCEPTED_TYPES = ['.pdf', '.doc', '.docx', '.txt', '.md', '.csv'];

function useVoicePreview() {
  const [previewingVoiceId, setPreviewingVoiceId] = useState(null);
  const audioRef = useRef(null);

  const playPreview = useCallback((voiceId, previewUrl) => {
    if (previewingVoiceId === voiceId && audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
      setPreviewingVoiceId(null);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    setPreviewingVoiceId(voiceId);

    const url = previewUrl || `${API_BASE}/api/voices/${voiceId}/preview`;
    const audio = new Audio(url);
    audioRef.current = audio;
    audio.onended = () => {
      setPreviewingVoiceId(null);
    };
    audio.onerror = () => {
      setPreviewingVoiceId(null);
    };
    audio.play().catch(() => {
      setPreviewingVoiceId(null);
    });
  }, [previewingVoiceId]);

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  return { previewingVoiceId, playPreview };
}

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5.14v14l11-7-11-7z" />
    </svg>
  );
}

function UploadFileIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  );
}

function DescriptionFileIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function CallIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.362 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.338 1.85.573 2.81.7A2 2 0 0 1 22 16.92Z" transform="rotate(135 12 12)" />
    </svg>
  );
}

export default function SessionScreen() {
  const navigate = useNavigate();
  const {
    selectedPersona,
    selectedVoiceId,
    setSelectedPersona,
    setSelectedVoiceId,
    error,
    setError,
  } = useVoiceCall();

  const setCallSessionId = useCallStore((s) => s.setSessionId);
  const setCallStatus = useCallStore((s) => s.setStatus);
  const setCallConnectionStatus = useCallStore((s) => s.setConnectionStatus);
  const setCallTranscript = useCallStore((s) => s.setTranscript);
  const setCallFiller = useCallStore((s) => s.setFiller);
  const setCallLatencies = useCallStore((s) => s.setLatencies);

  const [isStarting, setIsStarting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [voices, setVoices] = useState([]);
  const [pastSessions, setPastSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [isPastSessionsDrawerOpen, setIsPastSessionsDrawerOpen] = useState(false);
  const fileInputRef = useRef(null);
  const dragCounterRef = useRef(0);
  const uploadedDocuments = useCallStore((s) => s.uploadedDocuments);
  const setUploadedDocuments = useCallStore((s) => s.setUploadedDocuments);
  const { previewingVoiceId, playPreview } = useVoicePreview();

  useEffect(() => {
    let cancelled = false;
    const loadSessions = async () => {
      try {
        const res = await apiFetch(`${API_BASE}/api/sessions`);
        if (!cancelled && res.ok) {
          const data = await res.json();
          setPastSessions(Array.isArray(data) ? data.slice(0, 20) : []);
        }
      } catch {
        if (!cancelled) {
          setPastSessions([]);
        }
      } finally {
        if (!cancelled) {
          setSessionsLoading(false);
        }
      }
    };
    loadSessions();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadVoices = async () => {
      try {
        const res = await apiFetch(`${API_BASE}/api/voices`);
        if (!cancelled && res.ok) {
          const data = await res.json();
          setVoices(data || []);
        }
      } catch {
        if (!cancelled) {
          setVoices([]);
        }
      }
    };
    loadVoices();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 1024) {
        setIsPastSessionsDrawerOpen(false);
      }
    };

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isPastSessionsDrawerOpen) {
        setIsPastSessionsDrawerOpen(false);
      }
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('keydown', handleKeyDown);

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isPastSessionsDrawerOpen]);

  const handleFiles = useCallback(async (files) => {
    const fileArray = Array.from(files).filter((file) => {
      const ext = '.' + file.name.split('.').pop().toLowerCase();
      return ACCEPTED_TYPES.includes(ext);
    });

    if (!fileArray.length) {
      setUploadError('No supported files selected. Accepted: PDF, DOCX, TXT, MD, CSV.');
      return;
    }

    setUploadError(null);
    setIsUploading(true);

    const formData = new FormData();
    fileArray.forEach((file) => formData.append('files', file));

    try {
      const url = new URL(`${API_BASE}/api/documents/upload`);
      url.searchParams.set('persona_id', selectedPersona);
      const res = await apiFetch(url.toString(), {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error('Upload failed');
      const data = await res.json();
      const docs = Array.isArray(data.documents) ? data.documents : [];
      setUploadedDocuments((prev) => [...prev, ...docs]);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }, [setUploadedDocuments, selectedPersona]);

  const onDragEnter = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current += 1;
    if (dragCounterRef.current === 1) {
      setIsDragging(true);
    }
  }, []);

  const onDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0;
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
      e.dataTransfer.clearData();
    }
  }, [handleFiles]);

  const openFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const onFileChange = useCallback((e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFiles(e.target.files);
    }
  }, [handleFiles]);

  const removeDocument = useCallback((index) => {
    setUploadedDocuments((prev) => prev.filter((_, i) => i !== index));
  }, [setUploadedDocuments]);

  const clearAll = useCallback(() => {
    setUploadedDocuments([]);
  }, [setUploadedDocuments]);

  const handleStartSession = useCallback(async () => {
    if (!selectedPersona) return;
    setIsStarting(true);
    try {
      const response = await apiFetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          persona_id: selectedPersona,
          selected_voice: selectedVoiceId || null,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create session');
      }

      const data = await response.json();
      const newSessionId = data.id;
      setCallSessionId(newSessionId);
      setCallStatus('idle');
      setCallConnectionStatus('disconnected');
      setCallTranscript([]);
      setError(null);
      setCallFiller(null);
      setCallLatencies({ stt: null, llm: null, ttsFirstAudio: null, total: null });
      navigate(`/call/${newSessionId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session');
      setCallStatus('idle');
      setCallConnectionStatus('disconnected');
    } finally {
      setIsStarting(false);
    }
  }, [selectedPersona, selectedVoiceId, setCallSessionId, setCallStatus, setCallConnectionStatus, setCallTranscript, setError, setCallFiller, setCallLatencies, navigate]);

  const selectedPersonaData = PERSONAS.find((p) => p.id === selectedPersona);
  const selectedVoice = voices.find((v) => v.voice_id === selectedVoiceId);
  const selectedVoiceName = selectedVoice?.name || selectedVoiceId;
  const hasDocuments = uploadedDocuments.length > 0;
  const canStart = Boolean(selectedPersona) && Boolean(selectedVoiceId) && !isStarting;

  const getPersonaInitials = (persona) => {
    if (persona.initials) return persona.initials;
    return persona.name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
  };

  return (
    <div className="session-setup-screen">
      {/* ─── Header ─────────────────────────────────────────────────── */}
      <header className="session-setup-header">
        <div className="session-setup-header-brand">
          <div className="session-setup-header-avatar" aria-hidden="true">A</div>
          <span className="session-setup-header-title">Aura</span>
        </div>
        <div className="session-setup-header-nav">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsPastSessionsDrawerOpen(true)}
            className="text-xs font-medium"
            style={{ color: 'rgba(251, 251, 255, 0.8)' }}
          >
            Sessions
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/analytics')}
            className="text-xs font-medium"
            style={{ color: 'rgba(251, 251, 255, 0.8)' }}
          >
            Analytics
          </Button>
          {/* <div className="session-setup-header-avatar-user" aria-label="Profile" role="button" tabIndex={0}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(251,251,255,0.7)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div> */}
        </div>
      </header>

      {/* ─── Main Content ───────────────────────────────────────────── */}
      <main className="session-setup-main">
        {error && (
          <div className="session-error-banner" role="alert">
            <span className="session-error-icon">!</span>
            <span className="session-error-text">{error}</span>
            <button className="session-error-dismiss" onClick={() => setError(null)} aria-label="Dismiss error">×</button>
          </div>
        )}

        {/* Page intro */}
        <div className="session-setup-intro">
          <span className="session-setup-intro-label">Voice Conversation</span>
          <h1 className="session-setup-intro-title">Choose Conversation partner</h1>
          <p className="session-setup-intro-desc">
            Select who you&apos;d like to speak with, pick a voice style, and attach any reference notes before beginning the conversation.
          </p>
        </div>

        {/* Two-column layout */}
        <div className="session-setup-grid">
          {/* ─── LEFT: Personas + Past Sessions ─────────────────────── */}
          <div className="session-setup-left-column">
            <section className="session-setup-persona-section">
              <div className="session-setup-section-header">
                <h2 className="session-setup-section-title">Our Experts</h2>
                <span className="session-setup-section-hint">Click to select partner</span>
              </div>
              <div className="persona-grid">
                {PERSONAS.map((persona) => {
                  const isSelected = selectedPersona === persona.id;
                  return (
                    <button
                      key={persona.id}
                      type="button"
                      className={`persona-card${isSelected ? ' persona-card--selected' : ''}`}
                      onClick={() => setSelectedPersona(persona.id)}
                      aria-pressed={isSelected}
                    >
                      <div className="persona-card-top">
                        <div className="persona-avatar" aria-hidden="true">
                          {persona.avatarUrl ? (
                            <img src={persona.avatarUrl} alt={persona.name} loading="lazy" />
                          ) : (
                            getPersonaInitials(persona)
                          )}
                        </div>
                        <span
                          className={
                            isSelected
                              ? 'persona-select-badge persona-select-badge--selected'
                              : 'persona-select-badge persona-select-badge--unselected'
                          }
                        >
                          {isSelected && (
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          )}
                          {isSelected ? 'Selected' : 'Select'}
                        </span>
                      </div>
                      <h3 className="persona-name">{persona.name}</h3>
                      <p className="persona-role">{persona.role}</p>
                      <p className="persona-description">{persona.description}</p>
                    </button>
                  );
                })}
              </div>
            </section>

          </div>

          {/* ─── RIGHT: Voice + Reference Notes ─────────────────────── */}
          <div className="session-setup-right-column">
            {/* Voice Style */}
            <div className="voice-style-card">
              <div className="voice-style-header">
                <h2 className="voice-style-title">Voice Style</h2>
                <span className="voice-style-hint">Select Tone &amp; Delivery</span>
              </div>
              <div className="voice-list">
                {VOICE_STYLES.map((voice) => {
                  const isSelected = selectedVoiceId === voice.id;
                  const isPreviewing = previewingVoiceId === voice.id;
                  const voiceApiData = voices.find((v) => v.voice_id === voice.id);

                  return (
                    <div
                      key={voice.id}
                      className={`voice-card${isSelected ? ' voice-card--selected' : ''}`}
                      onClick={() => setSelectedVoiceId(voice.id)}
                      role="button"
                      tabIndex={0}
                      aria-pressed={isSelected}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setSelectedVoiceId(voice.id);
                        }
                      }}
                    >
                      <button
                        type="button"
                        className="voice-preview-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          playPreview(voiceApiData?.id || voice.id, voice.previewUrl);
                        }}
                        disabled={isPreviewing}
                        aria-label={isPreviewing ? `Playing ${voice.name} preview` : `Preview ${voice.name} voice`}
                        title={isPreviewing ? 'Playing...' : `Preview ${voice.name}`}
                      >
                        {isPreviewing ? (
                          <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14">
                            <rect x="6" y="4" width="4" height="16" rx="1" />
                            <rect x="14" y="4" width="4" height="16" rx="1" />
                          </svg>
                        ) : (
                          <PlayIcon />
                        )}
                      </button>
                      <div className="voice-info">
                        <span className="voice-name">{voice.name}</span>
                        <span className="voice-description">{voice.description}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Reference Notes */}
            <div className="reference-notes-card">
              <div className="reference-notes-header">
                <h2 className="reference-notes-title">Reference Notes</h2>
                {hasDocuments && (
                  <span className="reference-notes-count">
                    {uploadedDocuments.length} attached
                  </span>
                )}
              </div>

              <div
                className={`drop-zone${isDragging ? ' drop-zone--active' : ''}`}
                onDragEnter={onDragEnter}
                onDragLeave={onDragLeave}
                onDragOver={onDragOver}
                onDrop={onDrop}
                onClick={openFilePicker}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openFilePicker();
                  }
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={ACCEPTED_TYPES.join(',')}
                  className="drop-zone-input"
                  onChange={onFileChange}
                />
                <div className="drop-zone-icon" aria-hidden="true">
                  <UploadFileIcon />
                </div>
                <p className="drop-zone-title">Drop reference notes or slides</p>
                <p className="drop-zone-hint">PDF, Word, or plain text up to 25MB</p>
              </div>

              {isUploading && (
                <p className="document-status">Uploading documents…</p>
              )}
              {uploadError && !isUploading && (
                <p className="document-error-msg">{uploadError}</p>
              )}

              {hasDocuments && (
                <ul className="document-list">
                  {uploadedDocuments.map((doc, idx) => {
                    const id = doc?.id != null ? String(doc.id) : String(idx);
                    const filename = typeof doc?.filename === 'string' ? doc.filename : `Document ${idx + 1}`;
                    const fileSize = typeof doc?.file_size === 'number'
                      ? `${(doc.file_size / 1024).toFixed(1)} KB`
                      : null;
                    const pageCount = typeof doc?.page_count === 'number'
                      ? `${doc.page_count} pages`
                      : null;
                    const meta = [fileSize, pageCount].filter(Boolean).join(' · ');

                    return (
                      <li key={id} className="document-item">
                        <div className="document-item-icon" aria-hidden="true">
                          <DescriptionFileIcon />
                        </div>
                        <div className="document-item-body">
                          <span className="document-item-name">{filename}</span>
                          {meta && <span className="document-item-meta">{meta}</span>}
                        </div>
                        <button
                          type="button"
                          className="document-item-remove"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeDocument(idx);
                          }}
                          aria-label={`Remove ${filename}`}
                          title={`Remove ${filename}`}
                        >
                          <CloseIcon />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}

              {hasDocuments && (
                <div style={{ marginTop: '0.625rem', textAlign: 'right' }}>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      clearAll();
                    }}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      fontSize: '0.75rem',
                      fontWeight: 500,
                      color: '#ef4444',
                      cursor: 'pointer',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '0.25rem',
                      transition: 'background-color 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.08)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    Clear all
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {isPastSessionsDrawerOpen && (
        <>
          <div
            className="vc-drawer-backdrop"
            onClick={() => setIsPastSessionsDrawerOpen(false)}
            aria-hidden="true"
          />
          <aside className="session-past-drawer-panel" role="dialog" aria-modal="true" aria-label="Past Sessions">
            <div className="vc-drawer-header">
              <h2 className="vc-drawer-title">Past Sessions</h2>
              <button
                type="button"
                className="vc-drawer-close"
                onClick={() => setIsPastSessionsDrawerOpen(false)}
                aria-label="Close past sessions"
              >
                <CloseIcon />
              </button>
            </div>
            <div className="session-past-drawer-scroll" style={{ padding: '1rem', overflowY: 'auto' }}>
              {sessionsLoading ? (
                <div className="session-past-drawer-loading">
                  <div className="vc-loader-spinner" aria-label="Loading sessions" />
                </div>
              ) : pastSessions.length === 0 ? (
                <div style={{ fontSize: '0.875rem', color: 'rgba(3, 25, 30, 0.6)', padding: '0.75rem 0' }}>
                  No past sessions yet.
                </div>
              ) : (
                <div className="past-sessions-list">
                  {pastSessions.map((session) => (
                    <button
                      key={session.id}
                      type="button"
                      className="past-session-item"
                      onClick={() => {
                        setIsPastSessionsDrawerOpen(false);
                        navigate(`/review/${session.id}`);
                      }}
                    >
                      <span className="past-session-id">{session.id}</span>
                      <span className="past-session-meta">
                        {session.persona_name || 'Unknown'} · {session.selected_voice_name || 'Default'} · {session.status || 'completed'}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </aside>
        </>
      )}

      {/* ─── Sticky Footer Dock ─────────────────────────────────────── */}
      <footer className="session-setup-dock">
        <div className="session-setup-dock-inner">
          <div className="session-setup-dock-summary">
            <div className="session-setup-dock-dot" aria-hidden="true" />
            <div className="session-setup-dock-text">
              <span className="session-setup-dock-persona">
                {selectedPersonaData
                  ? `${selectedPersonaData.name} · ${selectedPersonaData.role}`
                  : 'Select a conversation partner'}
              </span>
              <span className="session-setup-dock-detail">
                {selectedPersona
                  ? `Voice: ${selectedVoiceName}${hasDocuments ? ` · ${uploadedDocuments.length} document${uploadedDocuments.length === 1 ? '' : 's'} attached` : ''}`
                  : 'Choose a persona to begin setup'}
              </span>
            </div>
          </div>
          <div className="session-setup-dock-actions">
            <Button
              size="default"
              onClick={handleStartSession}
              disabled={!canStart}
              className="session-start-button inline-flex items-center gap-2 font-semibold"
              style={{
                backgroundColor: 'var(--ink-black)',
                color: 'var(--ghost-white)',
                borderRadius: '9999px',
                paddingLeft: '1.5rem',
                paddingRight: '1.5rem',
                minHeight: '2.5rem',
              }}
            >
              <CallIcon />
              {isStarting ? 'Starting…' : 'Start Call'}
            </Button>
          </div>
        </div>
      </footer>
    </div>
  );
}
