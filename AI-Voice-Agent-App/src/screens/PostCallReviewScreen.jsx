import { useEffect, useRef, useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { API_BASE } from '@/config';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts';
import { Button } from '@/components/ui/button';

const COLORS = ['#22c55e', '#eab308', '#ef4444', '#a855f7'];

export default function PostCallReviewScreen() {
  const { sessionId } = useParams();
  const [session, setSession] = useState(null);
  const [summary, setSummary] = useState('');
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [sentiment, setSentiment] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const audioRef = useRef(null);
  const recordingUrlRef = useRef(recordingUrl);

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
          fetch(`${API_BASE}/api/sessions/${sessionId}`),
          fetch(`${API_BASE}/api/sessions/${sessionId}/summary`),
          fetch(`${API_BASE}/api/sessions/${sessionId}/sentiment`),
          fetch(`${API_BASE}/api/sessions/${sessionId}/metrics`),
        ]);

        if (!sessionRes.ok) {
          throw new Error('Failed to load session');
        }
        const sessionData = await sessionRes.json();
        if (!cancelled) setSession(sessionData);

        if (summaryRes.ok) {
          const summaryData = await summaryRes.json();
          if (!cancelled) setSummary(summaryData.summary || '');
        }

        if (sentimentRes.ok) {
          const sentimentData = await sentimentRes.json();
          if (!cancelled) setSentiment(Array.isArray(sentimentData) ? sentimentData : []);
        }

        if (metricsRes.ok) {
          const metricsData = await metricsRes.json();
          if (!cancelled) setMetrics(metricsData);
        }

        const recordingRes = await fetch(`${API_BASE}/api/sessions/${sessionId}/recording`);
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
      setDuration(audioRef.current.duration);
    }
  };

  const handleEnded = () => {
    setPlaying(false);
    setCurrentTime(0);
  };

  const seekTo = (ms) => {
    if (!audioRef.current) return;
    const seconds = ms / 1000;
    audioRef.current.currentTime = seconds;
    setCurrentTime(seconds);
  };

  const handleDownloadTranscript = (format) => {
    const url = `${API_BASE}/api/sessions/${sessionId}/export/transcript?format=${format}`;
    window.open(url, '_blank');
  };

  const handleDownloadRecording = () => {
    const url = `${API_BASE}/api/sessions/${sessionId}/export/recording?format=wav`;
    window.open(url, '_blank');
  };

  const handleDownloadSummary = (format) => {
    const url = `${API_BASE}/api/sessions/${sessionId}/export/summary?format=${format}`;
    window.open(url, '_blank');
  };

  const sentimentTimeline = useMemo(() => {
    if (!sentiment || !session?.messages) return [];
    const byId = new Map(session.messages.map(m => [m.id, m]));
    return sentiment.map(s => {
      const msg = byId.get(s.message_id);
      return {
        ...s,
        timestamp: msg?.timestamp || s.created_at,
        score: s.score,
      };
    }).filter(s => s.timestamp).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  }, [sentiment, session]);

  const sentimentPieData = useMemo(() => {
    if (!session?.messages) return [];
    const counts = {};
    session.messages.forEach(m => {
      if (m.speaker === 'user' && m.sentiment) {
        counts[m.sentiment] = (counts[m.sentiment] || 0) + 1;
      }
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value }));
  }, [session]);

  if (loading) return <div className="p-6">Loading review...</div>;
  if (error) return <div className="p-6 text-red-500">{error}</div>;
  if (!session) return <div className="p-6">Session not found.</div>;

  const messages = session.messages || [];
  const startedAt = session.started_at ? new Date(session.started_at).toLocaleString() : 'N/A';
  const endedAt = session.ended_at ? new Date(session.ended_at).toLocaleString() : 'In progress';

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Post-Call Review</h1>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500">Session</h2>
          <p className="font-mono text-sm">{session.id}</p>
          <p className="text-sm">Started: {startedAt}</p>
          <p className="text-sm">Ended: {endedAt}</p>
          <p className="text-sm">Status: {session.status}</p>
        </div>
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500">Persona</h2>
          <p className="text-sm">{session.persona_id || 'N/A'}</p>
          <p className="text-sm">Voice: {session.selected_voice || 'N/A'}</p>
        </div>
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500">Recording</h2>
          {recordingUrl ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={togglePlay}>
                  {playing ? 'Pause' : 'Play'}
                </Button>
                <span className="text-xs text-gray-500">
                  {Math.floor(currentTime)}s / {Math.floor(duration)}s
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={duration || 0}
                step={0.1}
                value={currentTime}
                onChange={(e) => seekTo(parseFloat(e.target.value) * 1000)}
                className="w-full"
              />
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
            <p className="text-sm text-gray-500">No recording available</p>
          )}
        </div>
      </div>

      {metrics && (
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Call Metrics</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-gray-500">Total Duration</p>
              <p className="text-lg font-semibold">{metrics.total_duration?.toFixed(1) ?? 0}s</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">User Speaking</p>
              <p className="text-lg font-semibold">{metrics.user_speaking_time?.toFixed(1) ?? 0}s</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Agent Speaking</p>
              <p className="text-lg font-semibold">{metrics.agent_speaking_time?.toFixed(1) ?? 0}s</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Turns</p>
              <p className="text-lg font-semibold">{metrics.turn_count ?? 0}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Avg Latency</p>
              <p className="text-lg font-semibold">{Math.round(metrics.average_latency ?? 0)} ms</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Sentiment Score</p>
              <p className="text-lg font-semibold">{(metrics.sentiment_score ?? 0).toFixed(2)}</p>
            </div>
            <div className="md:col-span-2">
              <p className="text-xs text-gray-500">Resolution</p>
              <p className="text-lg font-semibold capitalize">{(metrics.resolution_status || 'unknown').replace(/_/g, ' ')}</p>
            </div>
          </div>
        </div>
      )}

      {sentimentPieData.length > 0 && (
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Sentiment Breakdown</h2>
          <div className="flex flex-col md:flex-row items-center gap-4">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={sentimentPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {sentimentPieData.map((entry, index) => (
                    <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {sentimentTimeline.length > 0 && (
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Sentiment Timeline</h2>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={sentimentTimeline}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" tickFormatter={(v) => new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} />
              <YAxis domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} />
              <Tooltip labelFormatter={(v) => new Date(v).toLocaleTimeString()} formatter={(value) => [value, 'score']} />
              <Line type="monotone" dataKey="score" stroke="#2563eb" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {summary && (
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Summary</h2>
          <p className="text-sm whitespace-pre-wrap">{summary}</p>
        </div>
      )}

      <div className="border rounded-lg p-4">
        <h2 className="font-medium text-gray-500 mb-2">Transcript</h2>
        {messages.length === 0 ? (
          <p className="text-sm text-gray-500">No messages in this session.</p>
        ) : (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {messages.map((msg) => {
              return (
                <div key={msg.id} className="text-sm">
                  <span className="font-medium">{msg.speaker === 'user' ? 'You' : 'Assistant'}</span>
                  <span className="text-gray-400 text-xs ml-2">
                    {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                  </span>
                  {msg.recording_start_ms != null && (
                    <button
                      type="button"
                      className="ml-2 text-xs text-blue-600 underline"
                      onClick={() => seekTo(msg.recording_start_ms)}
                    >
                      Jump to audio
                    </button>
                  )}
                  <p className="mt-0.5">{msg.text}</p>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="border rounded-lg p-4">
        <h2 className="font-medium text-gray-500 mb-2">Export</h2>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => handleDownloadTranscript('txt')}>Transcript TXT</Button>
          <Button size="sm" variant="outline" onClick={() => handleDownloadTranscript('json')}>Transcript JSON</Button>
          <Button size="sm" variant="outline" onClick={handleDownloadRecording}>Recording WAV</Button>
          <Button size="sm" variant="outline" onClick={() => handleDownloadSummary('txt')}>Summary TXT</Button>
          <Button size="sm" variant="outline" onClick={() => handleDownloadSummary('json')}>Summary JSON</Button>
        </div>
      </div>
    </div>
  );
}