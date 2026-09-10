import { useEffect, useRef, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { API_BASE, apiFetch } from '@/config';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { ChartContainer, ChartTooltip, ChartTooltipContent } from '@/components/ui/chart';
import { Separator } from '@/components/ui/separator';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip';
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

const sentimentChartConfig = {
  score: {
    label: 'Sentiment',
    color: '#03191e',
  },
};

function formatTime(seconds) {
  if (!seconds || !isFinite(seconds)) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function PostCallReviewScreen() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [summary, setSummary] = useState('');
  const [summaryObj, setSummaryObj] = useState(null);
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [sentiment, setSentiment] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [copied, setCopied] = useState(false);
  const [waitingForEnd, setWaitingForEnd] = useState(false);
  const [reviewProgress, setReviewProgress] = useState(0);
  const audioRef = useRef(null);
  const recordingUrlRef = useRef(recordingUrl);

  const [exportError, setExportError] = useState(null);
  const [exportLoading, setExportLoading] = useState(false);

  useEffect(() => {
    recordingUrlRef.current = recordingUrl;
  }, [recordingUrl]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [sessionRes, summaryRes, sentimentRes, metricsRes] = await Promise.all([
          apiFetch(`${API_BASE}/api/sessions/${sessionId}`),
          apiFetch(`${API_BASE}/api/sessions/${sessionId}/summary`),
          apiFetch(`${API_BASE}/api/sessions/${sessionId}/sentiment`),
          apiFetch(`${API_BASE}/api/sessions/${sessionId}/metrics`),
        ]);

        if (!sessionRes.ok) {
          throw new Error('Failed to load session');
        }
        const sessionData = await sessionRes.json();
        if (cancelled) return;
        setSession(sessionData);

        const sessionHasEnded = sessionData.status === 'ended' || !!sessionData.ended_at;
        setWaitingForEnd(!sessionHasEnded);

        if (summaryRes.ok) {
          const summaryData = await summaryRes.json();
          if (!cancelled) {
            const raw = summaryData.summary || '';
            setSummary(raw);
            try {
              setSummaryObj(JSON.parse(raw));
            } catch {
              setSummaryObj(null);
            }
          }
        }

        if (sentimentRes.ok) {
          const sentimentData = await sentimentRes.json();
          if (!cancelled) setSentiment(Array.isArray(sentimentData) ? sentimentData : []);
        }

        if (metricsRes.ok) {
          const metricsData = await metricsRes.json();
          if (!cancelled) setMetrics(metricsData);
        }

        const recordingRes = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/recording`);
        if (recordingRes.ok) {
          const blob = await recordingRes.blob();
          if (!cancelled) {
            const url = URL.createObjectURL(blob);
            setRecordingUrl(url);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load review data');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
      if (recordingUrlRef.current) URL.revokeObjectURL(recordingUrlRef.current);
    };
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;

    if (!waitingForEnd) {
      setReviewProgress(100);
      return;
    }

    setReviewProgress(15);
    const start = Date.now();
    const timer = setInterval(() => {
      const elapsed = Date.now() - start;
      const nextProgress = Math.min(95, 15 + Math.round((elapsed / 9000) * 80));
      setReviewProgress(nextProgress);
    }, 250);

    return () => clearInterval(timer);
  }, [sessionId, waitingForEnd]);

  useEffect(() => {
    if (!sessionId || !waitingForEnd) return;
    let cancelled = false;
    let timer = null;

    async function poll() {
      try {
        const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        setSession(data);

        if (data.status === 'ended' || data.ended_at) {
          setWaitingForEnd(false);

          const [summaryRes, sentimentRes, metricsRes] = await Promise.all([
            apiFetch(`${API_BASE}/api/sessions/${sessionId}/summary`),
            apiFetch(`${API_BASE}/api/sessions/${sessionId}/sentiment`),
            apiFetch(`${API_BASE}/api/sessions/${sessionId}/metrics`),
          ]);

          if (summaryRes.ok) {
            const summaryData = await summaryRes.json();
            const raw = summaryData.summary || '';
            setSummary(raw);
            try {
              setSummaryObj(JSON.parse(raw));
            } catch {
              setSummaryObj(null);
            }
          }

          if (sentimentRes.ok) {
            const sentimentData = await sentimentRes.json();
            setSentiment(Array.isArray(sentimentData) ? sentimentData : []);
          }

          if (metricsRes.ok) {
            const metricsData = await metricsRes.json();
            setMetrics(metricsData);
          }

          const recordingRes = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/recording`);
          if (recordingRes.ok) {
            const blob = await recordingRes.blob();
            const url = URL.createObjectURL(blob);
            setRecordingUrl(url);
          }

          if (timer) clearTimeout(timer);
        }
      } catch {
        // ignore poll errors
      }
    }

    timer = setInterval(poll, 1500);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [sessionId, waitingForEnd]);

  const togglePlay = () => {
    if (!audioRef.current || !recordingUrl) return;
    if (audioRef.current.paused) {
      audioRef.current.play();
      setPlaying(true);
    } else {
      audioRef.current.pause();
      setPlaying(false);
    }
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration || 0);
    }
  };

  const handleEnded = () => {
    setPlaying(false);
    setCurrentTime(0);
  };

  const seekTo = (seconds) => {
    if (!audioRef.current) return;
    audioRef.current.currentTime = seconds;
    setCurrentTime(seconds);
  };

  const triggerDownload = async (url, fallbackFilename) => {
    const response = await apiFetch(url);
    if (!response.ok) {
      throw new Error('Export request failed');
    }

    const blob = await response.blob();
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename\s*=\s*"?([^";]+)"?/i);
    const filename = match ? decodeURIComponent(match[1]) : fallbackFilename;

    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  };

  const handleExportTranscript = async (format) => {
    setExportLoading(true);
    setExportError(null);
    try {
      const url = `${API_BASE}/api/sessions/${sessionId}/export/transcript?format=${format}`;
      await triggerDownload(url, `session-${sessionId}-transcript.${format}`);
    } catch {
      setExportError('Failed to export transcript');
    } finally {
      setExportLoading(false);
    }
  };

  const handleExportRecording = async (format) => {
    setExportLoading(true);
    setExportError(null);
    try {
      const url = `${API_BASE}/api/sessions/${sessionId}/export/recording?format=${format}`;
      await triggerDownload(url, `session-${sessionId}-recording.${format}`);
    } catch {
      setExportError('Failed to export recording');
    } finally {
      setExportLoading(false);
    }
  };

  const handleExportSummary = async (format) => {
    setExportLoading(true);
    setExportError(null);
    try {
      const url = `${API_BASE}/api/sessions/${sessionId}/export/summary?format=${format}`;
      await triggerDownload(url, `session-${sessionId}-summary.${format}`);
    } catch {
      setExportError('Failed to export summary');
    } finally {
      setExportLoading(false);
    }
  };

  const handleCopyJson = async () => {
    try {
      const res = await apiFetch(`${API_BASE}/api/sessions/${sessionId}/transcript`);
      if (!res.ok) {
        setExportError('Failed to copy transcript');
        return;
      }
      const data = await res.json();
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setExportError('Failed to copy transcript');
    }
  };

  const sentimentChartData = useMemo(() => {
    if (!sentiment || !session?.messages) return [];
    const byId = new Map(session.messages.map(m => [m.id, m]));
    return sentiment
      .map(s => {
        const msg = byId.get(s.message_id);
        return {
          time: msg ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '',
          score: s.score,
          message_id: s.message_id,
        };
      })
      .filter(s => s.time)
      .sort((a, b) => {
        const ta = session.messages.find(m => m.id === a.message_id);
        const tb = session.messages.find(m => m.id === b.message_id);
        if (!ta || !tb) return 0;
        return new Date(ta.timestamp) - new Date(tb.timestamp);
      });
  }, [sentiment, session]);

  const timelineMarkers = useMemo(() => {
    if (!session?.messages) return [];
    const markers = [];
    const msgMap = new Map(session.messages.map(m => [m.id, m]));

    if (session.messages.length > 0) {
      markers.push({
        label: 'Intro',
        time: session.messages[0].timestamp,
        message_id: session.messages[0].id,
      });
    }

    sentiment.forEach(s => {
      const msg = msgMap.get(s.message_id);
      if (msg && msg.latency_ms > 2000) {
        markers.push({
          label: 'Latency Clarification',
          time: msg.timestamp,
          message_id: s.message_id,
        });
      }
    });

    session.messages.forEach(msg => {
      if (msg.interrupted) {
        markers.push({
          label: 'Buffer Inquiry',
          time: msg.timestamp,
          message_id: msg.id,
        });
      }
    });

    if (session.messages.length > 0) {
      markers.push({
        label: 'Active Playhead',
        time: session.messages[session.messages.length - 1].timestamp,
        message_id: session.messages[session.messages.length - 1].id,
      });
    }

    return markers.sort((a, b) => new Date(a.time) - new Date(b.time));
  }, [session, sentiment]);

  const currentMessageId = useMemo(() => {
    if (!session?.messages || !audioRef.current) return null;
    const currentMs = currentTime * 1000;
    let activeId = null;
    for (const msg of session.messages) {
      if (msg.recording_start_ms != null && msg.recording_start_ms <= currentMs) {
        activeId = msg.id;
      }
    }
    return activeId;
  }, [currentTime, session]);

  const turnCountAtPlayhead = useMemo(() => {
    if (!session?.messages) return 0;
    const currentMs = currentTime * 1000;
    return session.messages.filter(m => m.recording_start_ms != null && m.recording_start_ms <= currentMs).length;
  }, [currentTime, session]);

  const filteredMessages = useMemo(() => {
    if (!searchQuery.trim()) return session?.messages || [];
    const q = searchQuery.toLowerCase();
    return (session?.messages || []).filter(m => m.text.toLowerCase().includes(q));
  }, [searchQuery, session]);

  const startedAt = session?.started_at ? new Date(session.started_at) : null;
  const endedAt = session?.ended_at ? new Date(session.ended_at) : null;
  const sessionDate = startedAt ? startedAt.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : 'N/A';
  const sessionDuration = metrics?.total_duration ? `${metrics.total_duration.toFixed(1)}s` : `${session?.duration ? session.duration.toFixed(1) : 0}s`;
  const personaName = session?.persona_name || 'Unknown';
  const personaDomain = session?.persona_domain || 'General';

  const dialogueFlow = summaryObj?.dialogue_flow || [];
  const decisions = summaryObj?.decisions_made || [];
  const actionItems = summaryObj?.action_items || [];
  const keyTopics = summaryObj?.key_topics || [];

  if (loading && !session) {
    return (
      <div className="post-call-screen">
        <header className="session-setup-header">
          <div className="session-setup-header-brand">
            <div className="session-setup-header-avatar" aria-hidden="true">A</div>
            <span className="session-setup-header-title">Aura</span>
          </div>
          <div className="session-setup-header-nav">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/session')}
              className="text-xs font-medium"
              style={{ color: 'rgba(251, 251, 255, 0.8)' }}
            >
              Sessions
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled
              className="text-xs font-medium opacity-50 cursor-not-allowed"
              style={{ color: 'rgba(251, 251, 255, 0.8)' }}
            >
              Analytics
            </Button>
          </div>
        </header>

        <main className="post-call-main post-call-main--centered">
          <div className="post-call-loading-card">
            <h2 className="post-call-loading-title">Preparing your review</h2>
            <p className="post-call-loading-text">
              We&apos;re finalizing your session details and gathering the latest insights.
            </p>
            <Progress value={reviewProgress} className="post-call-progress" />
          </div>
        </main>
      </div>
    );
  }

  if (error) return <div className="p-6 text-red-500">{error}</div>;
  if (!session) return <div className="p-6">Session not found.</div>;

  if (waitingForEnd) {
    return (
      <div className="post-call-screen">
        <header className="session-setup-header">
          <div className="session-setup-header-brand">
            <div className="session-setup-header-avatar" aria-hidden="true">A</div>
            <span className="session-setup-header-title">Aura</span>
          </div>
          <div className="session-setup-header-nav">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/session')}
              className="text-xs font-medium"
              style={{ color: 'rgba(251, 251, 255, 0.8)' }}
            >
              Sessions
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled
              className="text-xs font-medium opacity-50 cursor-not-allowed"
              style={{ color: 'rgba(251, 251, 255, 0.8)' }}
            >
              Analytics
            </Button>
          </div>
        </header>

        <main className="post-call-main post-call-main--centered">
          <div className="post-call-loading-card">
            <h2 className="post-call-loading-title">Preparing your review</h2>
            <p className="post-call-loading-text">
              We&apos;re finalizing your session details and gathering the latest insights.
            </p>
            <Progress value={reviewProgress} className="post-call-progress" />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="post-call-screen">
      <header className="session-setup-header">
        <div className="session-setup-header-brand">
          <div className="session-setup-header-avatar" aria-hidden="true">A</div>
          <span className="session-setup-header-title">Aura</span>
        </div>
        <div className="session-setup-header-nav">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/session')}
            className="text-xs font-medium"
            style={{ color: 'rgba(251, 251, 255, 0.8)' }}
          >
            Sessions
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled
            className="text-xs font-medium opacity-50 cursor-not-allowed"
            style={{ color: 'rgba(251, 251, 255, 0.8)' }}
          >
            Analytics
          </Button>
        </div>
      </header>

      <div className="post-call-main">
        <div className="post-call-intro">
          <span className="session-setup-intro-label">Understand</span>
          <h1 className="session-setup-intro-title">Session Debrief</h1>
          <p className="session-setup-intro-desc">
            Replay the call, inspect how the conversation unfolded, and review the decisions and metrics generated from the session.
          </p>
        </div>

        {/* Header */}
        <header className="post-call-header">
          <div className="post-call-header-left">
            <h2 className="post-call-title">Post-Call Review</h2>
            <div className="post-call-header-meta">
              <span className="post-call-session-title">Session with {personaName}</span>
              <span className="post-call-meta-sep">·</span>
              <span className="post-call-meta-text">{sessionDate}</span>
              <span className="post-call-meta-sep">·</span>
              <span className="post-call-meta-text">{sessionDuration}</span>
            </div>
            {waitingForEnd && (
              <div className="post-call-finalizing">Finalizing session...</div>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate('/session')}
            className="post-call-header-button"
          >
            New Session
          </Button>
        </header>

        {/* Playback Module */}
        <Card>
          <CardHeader>
            <div className="post-call-playback-header">
              <div>
                <CardTitle>Playback</CardTitle>
                <CardDescription>Review the call recording and transcript</CardDescription>
              </div>
              <div className="post-call-playback-meta">
                <Badge variant="secondary">{turnCountAtPlayhead} / {session.messages?.length || 0} turns</Badge>
                <Badge variant="secondary">{formatTime(currentTime)} / {formatTime(duration)}</Badge>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {recordingUrl ? (
              <div className="post-call-playback">
                <div className="post-call-playback-controls">
                  <Button size="icon-sm" variant="outline" onClick={togglePlay} aria-label={playing ? 'Pause' : 'Play'}>
                    {playing ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" /></svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.14v14l11-7-11-7z" /></svg>
                    )}
                  </Button>
                  <input
                    type="range"
                    min={0}
                    max={duration || 0}
                    step={0.1}
                    value={currentTime}
                    onChange={(e) => seekTo(parseFloat(e.target.value))}
                    className="post-call-seek"
                  />
                </div>
                <audio
                  ref={audioRef}
                  src={recordingUrl}
                  onTimeUpdate={handleTimeUpdate}
                  onLoadedMetadata={handleLoadedMetadata}
                  onEnded={handleEnded}
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                  className="hidden"
                />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No recording available</p>
            )}
          </CardContent>
        </Card>

        {/* Sentiment & Engagement Flow */}
        <Card className="post-call-section-card">
          <CardHeader>
            <CardTitle>Sentiment & Engagement Flow</CardTitle>
            <CardDescription>Timeline markers highlight key moments</CardDescription>
          </CardHeader>
          <CardContent>
            {sentimentChartData.length > 0 ? (
              <>
                <ChartContainer config={sentimentChartConfig} style={{ width: '100%', height: 220 }}>
                  <LineChart data={sentimentChartData} margin={{ left: 12, right: 12 }}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis dataKey="time" tickLine={false} axisLine={false} tickMargin={8} />
                    <YAxis domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} tickLine={false} axisLine={false} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Line dataKey="score" stroke="var(--color-score)" strokeWidth={2} dot />
                  </LineChart>
                </ChartContainer>
                <div className="post-call-timeline-markers">
                  {timelineMarkers.map((marker, idx) => (
                    <Tooltip key={idx}>
                      <TooltipTrigger asChild>
                        <Badge variant="outline" className="post-call-marker">
                          {marker.label}
                        </Badge>
                      </TooltipTrigger>
                      <TooltipContent>
                        {new Date(marker.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </TooltipContent>
                    </Tooltip>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No sentiment data available</p>
            )}
          </CardContent>
        </Card>

        {/* Meeting Overview */}
        <Card className="post-call-section-card">
          <CardHeader>
            <CardTitle>Meeting Overview</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="post-call-overview-grid">
              <div>
                <span className="post-call-overview-label">Purpose</span>
                <p className="post-call-overview-value">{personaDomain}</p>
              </div>
              <div>
                <span className="post-call-overview-label">Participants</span>
                <p className="post-call-overview-value">You · {personaName}</p>
              </div>
              <div>
                <span className="post-call-overview-label">Duration</span>
                <p className="post-call-overview-value">{sessionDuration}</p>
              </div>
              <div>
                <span className="post-call-overview-label">Date</span>
                <p className="post-call-overview-value">{sessionDate}</p>
              </div>
            </div>
            {dialogueFlow.length > 0 && (
              <>
                <Separator className="post-call-separator" />
                <div>
                  <span className="post-call-overview-label">Dialogue Flow</span>
                  <div className="post-call-flow-list">
                    {dialogueFlow.map((step, idx) => (
                      <div key={idx} className="post-call-flow-item">
                        <span className="post-call-flow-index">{idx + 1}</span>
                        <span className="post-call-flow-text">{step}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Key Takeaways & Agreed Decisions */}
        <Card className="post-call-section-card">
          <CardHeader>
            <CardTitle>Key Takeaways & Agreed Decisions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="post-call-takeaways">
              {keyTopics.length > 0 && (
                <div className="post-call-takeaway-section">
                  <span className="post-call-takeaway-label">Key Topics</span>
                  <ul className="post-call-takeaway-list">
                    {keyTopics.map((topic, idx) => (
                      <li key={idx} className="post-call-takeaway-item">{topic}</li>
                    ))}
                  </ul>
                </div>
              )}
              {decisions.length > 0 && (
                <div className="post-call-takeaway-section">
                  <span className="post-call-takeaway-label">Decisions Made</span>
                  <ul className="post-call-takeaway-list">
                    {decisions.map((item, idx) => (
                      <li key={idx} className="post-call-takeaway-item">{item}</li>
                    ))}
                  </ul>
                </div>
              )}
              {actionItems.length > 0 && (
                <div className="post-call-takeaway-section">
                  <span className="post-call-takeaway-label">Action Items</span>
                  <ul className="post-call-takeaway-list">
                    {actionItems.map((item, idx) => (
                      <li key={idx} className="post-call-takeaway-item">{item}</li>
                    ))}
                  </ul>
                </div>
              )}
              {keyTopics.length === 0 && decisions.length === 0 && actionItems.length === 0 && (
                <p className="text-sm text-muted-foreground">No key takeaways recorded</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Call Metrics */}
        <Card className="post-call-section-card">
          <CardHeader>
            <CardTitle>Call Metrics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="post-call-metrics-grid">
              <div>
                <span className="post-call-metric-label">Duration</span>
                <p className="post-call-metric-value">{metrics ? `${metrics.total_duration?.toFixed(1) ?? 0}s` : '—'}</p>
              </div>
              <div>
                <span className="post-call-metric-label">Dialogue Turns</span>
                <p className="post-call-metric-value">{metrics ? (metrics.turn_count ?? 0) : '—'}</p>
              </div>
              <div>
                <span className="post-call-metric-label">Avg Latency</span>
                <p className="post-call-metric-value">{metrics ? `${Math.round(metrics.average_latency ?? 0)} ms` : '—'}</p>
              </div>
              <div>
                <span className="post-call-metric-label">P95 Latency</span>
                <p className="post-call-metric-value">{metrics && metrics.p95_latency != null ? `${Math.round(metrics.p95_latency)} ms` : '—'}</p>
              </div>
              <div>
                <span className="post-call-metric-label">Stream Status</span>
                <p className="post-call-metric-value capitalize">{metrics ? (metrics.stream_status || 'unknown') : '—'}</p>
              </div>
              <div>
                <span className="post-call-metric-label">Sentiment Score</span>
                <p className="post-call-metric-value">{metrics ? (metrics.sentiment_score ?? 0).toFixed(2) : '—'}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Conversation Transcript */}
        <Card className="post-call-section-card">
          <CardHeader>
            <div className="post-call-transcript-header">
              <div>
                <CardTitle>Conversation Transcript</CardTitle>
                <CardDescription>{session.messages?.length || 0} turns</CardDescription>
              </div>
              <div className="post-call-transcript-search">
                <input
                  type="text"
                  placeholder="Search transcript..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="post-call-search-input"
                />
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {filteredMessages.length === 0 ? (
              <p className="text-sm text-muted-foreground">No messages in this session.</p>
            ) : (
              <div className="post-call-transcript-list">
                {filteredMessages.map((msg) => {
                  const isActive = msg.id === currentMessageId;
                  return (
                    <div
                      key={msg.id}
                      className={cn(
                        'post-call-transcript-row',
                        isActive && 'post-call-transcript-row--active'
                      )}
                      onClick={() => {
                        if (msg.recording_start_ms != null) {
                          seekTo(msg.recording_start_ms / 1000);
                        }
                      }}
                    >
                      <div className="post-call-transcript-meta">
                        <Avatar size="sm" className="post-call-transcript-avatar">
                          {msg.speaker === 'user' ? (
                            <>
                              <AvatarImage src="https://res.cloudinary.com/ejpx0qht/image/upload/v1788858007/aura-avatars/aria.png" alt="You" />
                              <AvatarFallback>You</AvatarFallback>
                            </>
                          ) : (
                            <>
                              <AvatarImage src={`https://res.cloudinary.com/ejpx0qht/image/upload/v1788858004/aura-avatars/${session.persona_name?.toLowerCase() || 'aria'}.png`} alt={session.persona_name || 'Aura'} />
                              <AvatarFallback>{session.persona_name?.[0] || 'A'}</AvatarFallback>
                            </>
                          )}
                        </Avatar>
                        <span className="post-call-transcript-name">{msg.speaker === 'user' ? 'You' : session.persona_name || 'Aura'}</span>
                        <span className="post-call-transcript-time">
                          {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                        </span>
                      </div>
                      <p className="post-call-transcript-text">{msg.text}</p>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Export */}
        <Card className="post-call-section-card">
          <CardHeader>
            <CardTitle>Export</CardTitle>
          </CardHeader>
          <CardContent>
            {exportError && (
              <p className="text-sm text-red-600 mb-3">{exportError}</p>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" disabled={exportLoading}>
                  {exportLoading ? 'Exporting...' : 'Export'}
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="ml-2">
                    <path d="M6 9l6 6 6-6" />
                  </svg>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuItem onSelect={() => handleExportTranscript('txt')}>
                  <FileTextIcon /> TXT Transcript
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => handleExportTranscript('json')}>
                  <FileJsonIcon /> JSON Transcript
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => handleExportSummary('pdf')}>
                  <FileTextIcon /> PDF Summary
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => handleExportRecording('mp3')}>
                  <FileAudioIcon /> MP3 Full Audio
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => handleExportRecording('wav')}>
                  <FileAudioIcon /> WAV Full Audio
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={handleCopyJson}>
                  <FileJsonIcon /> {copied ? 'Copied!' : 'Copy JSON Content'}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FileTextIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

function FileAudioIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18V5l12-2v13" />
      <circle cx="6" cy="18" r="3" />
      <circle cx="18" cy="16" r="3" />
    </svg>
  );
}

function FileJsonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <path d="M8 13h2" />
      <path d="M8 17h2" />
      <path d="M14 13h2" />
      <path d="M14 17h2" />
    </svg>
  );
}
