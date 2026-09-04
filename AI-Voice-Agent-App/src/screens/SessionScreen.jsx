import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useVoiceCall } from '@/hooks/useVoiceCall';
import useCallStore from '@/store/callStore';
import { Button } from '@/components/ui/button';
import { API_BASE } from '@/config';

const PERSONAS = [
  {
    id: 'customer-support',
    name: 'Customer Support',
    description: 'Empathetic, patient and solution-oriented.',
    icon: '💬',
  },
  {
    id: 'technical-expert',
    name: 'Technical Expert',
    description: 'Precise, knowledgeable and step-by-step.',
    icon: '🔧',
  },
  {
    id: 'sales-assistant',
    name: 'Sales Assistant',
    description: 'Friendly, persuasive and feature-focused.',
    icon: '📈',
  },
  {
    id: 'general-assistant',
    name: 'General Assistant',
    description: 'Balanced and helpful.',
    icon: '🤖',
  },
];

const ACCEPTED_TYPES = ['.pdf', '.docx', '.txt', '.md', '.csv'];

function useVoicePreview() {
  const [previewingVoiceId, setPreviewingVoiceId] = useState(null);
  const audioRef = useRef(null);

  const playPreview = useCallback(async (voiceId) => {
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

    try {
      const res = await fetch(`${API_BASE}/api/voices/${voiceId}/preview`);
      if (!res.ok) throw new Error('Preview not available');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        setPreviewingVoiceId(null);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setPreviewingVoiceId(null);
        URL.revokeObjectURL(url);
      };
      await audio.play();
    } catch {
      setPreviewingVoiceId(null);
    }
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

export default function SessionScreen() {
  const navigate = useNavigate();
  const {
    selectedPersona,
    selectedVoiceId,
    setSelectedPersona,
    setSelectedVoiceId,
    startCall,
    error,
    setError,
    sessionId,
  } = useVoiceCall();

  const [isStarting, setIsStarting] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [voices, setVoices] = useState([]);
  const [voicesLoading, setVoicesLoading] = useState(true);
  const [pastSessions, setPastSessions] = useState([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const fileInputRef = useRef(null);
  const dragCounterRef = useRef(0);
  const uploadedDocuments = useCallStore((s) => s.uploadedDocuments);
  const setUploadedDocuments = useCallStore((s) => s.setUploadedDocuments);
  const { previewingVoiceId, playPreview } = useVoicePreview();

  useEffect(() => {
    let cancelled = false;
    const loadSessions = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/sessions`);
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
        const res = await fetch(`${API_BASE}/api/voices`);
        if (!cancelled && res.ok) {
          const data = await res.json();
          setVoices(data || []);
        }
      } catch {
        if (!cancelled) {
          setVoices([]);
        }
      } finally {
        if (!cancelled) {
          setVoicesLoading(false);
        }
      }
    };
    loadVoices();
    return () => {
      cancelled = true;
    };
  }, []);

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
      if (sessionId) {
        url.searchParams.set('session_id', sessionId);
      }
      const res = await fetch(url.toString(), {
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
  }, [setUploadedDocuments]);

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
      await startCall();
      const currentSessionId = useCallStore.getState().sessionId;
      if (currentSessionId) {
        navigate(`/call/${currentSessionId}`);
      }
    } finally {
      setIsStarting(false);
    }
  }, [selectedPersona, startCall, navigate]);

  const canStart = Boolean(selectedPersona) && !isStarting;

  const hasDocuments = uploadedDocuments.length > 0;

  return (
    <div className="session-screen">
      <div className="session-container">
        <div className="session-header">
          <div className="session-header-top">
            <div>
              <h1 className="session-title">AI Voice Agent</h1>
              <p className="session-subtitle">Select a persona, choose a voice, upload documents and start your session.</p>
            </div>
            <div className="session-nav">
              <Button variant="outline" size="sm" onClick={() => navigate('/analytics')}>
                Analytics Dashboard
              </Button>
            </div>
          </div>
        </div>

        {error && (
          <div className="vc-error-banner">
            <span className="vc-error-icon">!</span>
            <span className="vc-error-text">{error}</span>
            <button className="vc-error-dismiss" onClick={() => setError(null)}>x</button>
          </div>
        )}

        <div className="session-body">
          <section className="session-section">
            <h2 className="session-section-title">Persona</h2>
            <div className="persona-grid">
              {PERSONAS.map((persona) => {
                const isSelected = selectedPersona === persona.id;
                return (
                  <button
                    key={persona.id}
                    type="button"
                    className={`persona-card ${isSelected ? 'persona-card--selected' : ''}`}
                    onClick={() => setSelectedPersona(persona.id)}
                  >
                    <span className="persona-icon" aria-hidden="true">{persona.icon}</span>
                    <span className="persona-name">{persona.name}</span>
                    <span className="persona-description">{persona.description}</span>
                  </button>
                );
              })}
            </div>
          </section>

          <section className="session-section">
            <h2 className="session-section-title">Voice</h2>
            {voicesLoading ? (
              <p className="voice-loading">Loading voices...</p>
            ) : (
              <div className="voice-list">
                {voices.map((voice) => {
                  const isSelected = selectedVoiceId === voice.voice_id;
                  const isPreviewing = previewingVoiceId === voice.id;
                  return (
                    <div
                      key={voice.id}
                      className={`voice-card ${isSelected ? 'voice-card--selected' : ''}`}
                    >
                      <button
                        type="button"
                        className={`voice-radio ${isSelected ? 'voice-radio--checked' : ''}`}
                        onClick={() => setSelectedVoiceId(voice.voice_id)}
                        aria-pressed={isSelected}
                      >
                        <span className="voice-radio-indicator" />
                      </button>
                      <div className="voice-info">
                        <span className="voice-name">{voice.name}</span>
                        <span className="voice-id">{voice.id}</span>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => playPreview(voice.id)}
                        disabled={isPreviewing}
                      >
                        {isPreviewing ? 'Playing...' : 'Preview'}
                      </Button>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="session-section">
            <h2 className="session-section-title">Documents</h2>
            <div
              className={`document-drop-zone ${isDragging ? 'document-drop-zone--active' : ''}`}
              onDragEnter={onDragEnter}
              onDragLeave={onDragLeave}
              onDragOver={onDragOver}
              onDrop={onDrop}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={ACCEPTED_TYPES.join(',')}
                className="document-input"
                onChange={onFileChange}
              />
              <div className="document-drop-content">
                <span className="document-drop-icon" aria-hidden="true">📄</span>
                <p className="document-drop-text">
                  Drag &amp; drop files here, or{' '}
                  <button
                    type="button"
                    className="document-drop-link"
                    onClick={openFilePicker}
                  >
                    browse
                  </button>
                </p>
                <span className="document-hint">Supported: PDF, DOCX, TXT, MD, CSV</span>
              </div>
            </div>

            {isUploading && (
              <p className="document-status">Uploading documents...</p>
            )}

            {uploadError && (
              <p className="document-error">{uploadError}</p>
            )}

            {hasDocuments && (
              <div className="document-list-wrapper">
                <div className="document-list-header">
                  <span className="document-list-count">{uploadedDocuments.length} document{uploadedDocuments.length === 1 ? '' : 's'} uploaded</span>
                  <button
                    type="button"
                    className="document-clear-button"
                    onClick={clearAll}
                  >
                    Clear all
                  </button>
                </div>
                <ul className="document-list">
                  {uploadedDocuments.map((doc, idx) => {
                    const id = doc?.id != null ? String(doc.id) : String(idx);
                    const filename = typeof doc?.filename === 'string' ? doc.filename : (typeof doc?.name === 'string' ? doc.name : `Document ${idx + 1}`);
                    return (
                      <li key={id} className="document-item">
                        <span className="document-item-name">{filename}</span>
                        <button
                          type="button"
                          className="document-item-remove"
                          onClick={() => removeDocument(idx)}
                          aria-label={`Remove ${filename}`}
                        >
                          ×
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </section>

          {!sessionsLoading && pastSessions.length > 0 && (
            <section className="session-section">
              <h2 className="session-section-title">Past Sessions</h2>
              <div className="past-sessions-list">
                {pastSessions.map((session) => (
                  <button
                    key={session.id}
                    type="button"
                    className="past-session-item"
                    onClick={() => navigate(`/review/${session.id}`)}
                  >
                    <span className="past-session-id">{session.id}</span>
                    <span className="past-session-meta">
                      {session.status || 'completed'} · {session.started_at ? new Date(session.started_at).toLocaleString() : 'no date'}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="session-footer">
          <Button
            size="lg"
            onClick={handleStartSession}
            disabled={!canStart}
            className="session-start-button"
          >
            {isStarting ? 'Starting...' : 'Start Session'}
          </Button>
        </div>
      </div>
    </div>
  );
}
