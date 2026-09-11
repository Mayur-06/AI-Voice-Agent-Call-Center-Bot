import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE, apiFetch } from '@/config';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Legend, PieChart, Pie, Cell,
} from 'recharts';

const COLORS = ['#22c55e', '#eab308', '#ef4444', '#a855f7', '#3b82f6'];

export default function AnalyticsDashboard() {
  const navigate = useNavigate();
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await apiFetch(`${API_BASE}/api/analytics`);
        if (!res.ok) throw new Error('Failed to load analytics');
        const data = await res.json();
        if (!cancelled) setAnalytics(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load analytics');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!loading) {
      setProgress(100);
      return;
    }

    setProgress(15);
    const start = Date.now();
    const timer = setInterval(() => {
      const elapsed = Date.now() - start;
      const nextProgress = Math.min(95, 15 + Math.round((elapsed / 9000) * 80));
      setProgress(nextProgress);
    }, 250);

    return () => clearInterval(timer);
  }, [loading]);

  if (loading) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center p-6">
        <div className="post-call-loading-card">
          <h2 className="post-call-loading-title">Loading analytics</h2>
          <p className="post-call-loading-text">
            We&apos;re gathering the latest session insights and trends.
          </p>
          <Progress value={progress} className="post-call-progress" />
        </div>
      </div>
    );
  }
  if (error) return <div className="p-6 text-red-500">{error}</div>;
  if (!analytics) return <div className="p-6">No analytics available.</div>;

  const sentimentEntries = Object.entries(analytics.sentiment_breakdown || {});
  const sentimentPieData = sentimentEntries.map(([name, value]) => ({ name, value }));
  const callsOverTime = analytics.calls_over_time || [];
  const perPersona = analytics.per_persona_stats || [];

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
            onClick={() => navigate('/analytics')}
            className="text-xs font-medium"
            style={{ color: 'rgba(251, 251, 255, 0.8)' }}
          >
            Analytics
          </Button>
        </div>
      </header>

      <main className="post-call-main">
        <div className="post-call-intro">
          <span className="session-setup-intro-label">Analytics</span>
          <h1 className="session-setup-intro-title">Analytics Dashboard</h1>
          <p className="session-setup-intro-desc">
            Session insights and performance trends across all conversations.
          </p>
        </div>

        <div className="space-y-4 sm:space-y-6">

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <Card className="analytics-section-card">
          <CardContent className="p-4">
            <h2 className="font-medium text-gray-500 text-sm">Total Sessions</h2>
            <p className="text-xl sm:text-2xl font-semibold truncate">{analytics.total_sessions ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="analytics-section-card">
          <CardContent className="p-4">
            <h2 className="font-medium text-gray-500 text-sm">Total Messages</h2>
            <p className="text-xl sm:text-2xl font-semibold truncate">{analytics.total_messages ?? 0}</p>
          </CardContent>
        </Card>
        <Card className="analytics-section-card">
          <CardContent className="p-4">
            <h2 className="font-medium text-gray-500 text-sm">Avg Latency</h2>
            <p className="text-xl sm:text-2xl font-semibold truncate">{Math.round(analytics.avg_latency_ms ?? 0)} ms</p>
          </CardContent>
        </Card>
        <Card className="analytics-section-card">
          <CardContent className="p-4">
            <h2 className="font-medium text-gray-500 text-sm">Avg Session Duration</h2>
            <p className="text-xl sm:text-2xl font-semibold truncate">{Math.round(analytics.avg_session_duration_s ?? 0)} s</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
        <Card className="analytics-section-card">
          <CardHeader>
            <CardTitle>Calls Over Time</CardTitle>
            <CardDescription>Session volume trends</CardDescription>
          </CardHeader>
          <CardContent>
            {callsOverTime.length === 0 ? (
              <p className="text-sm text-gray-500">No call history yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={callsOverTime}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tickFormatter={(v) => v.slice(5)} />
                  <YAxis allowDecimals={false} />
                  <Tooltip labelFormatter={(v) => v} formatter={(value) => [value, 'calls']} />
                  <Line type="monotone" dataKey="count" stroke="#2563eb" strokeWidth={2} dot />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card className="analytics-section-card">
          <CardHeader>
            <CardTitle>Sentiment Breakdown</CardTitle>
            <CardDescription>Distribution of sentiment scores</CardDescription>
          </CardHeader>
          <CardContent>
            {sentimentPieData.length === 0 ? (
              <p className="text-sm text-gray-500">No sentiment data yet.</p>
            ) : (
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
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="analytics-section-card">
        <CardHeader>
          <CardTitle>Per-Persona Performance</CardTitle>
          <CardDescription>Session metrics by conversation partner</CardDescription>
        </CardHeader>
        <CardContent>
          {perPersona.length === 0 ? (
            <p className="text-sm text-gray-500">No persona data yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={perPersona}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="persona" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="sessions" fill="#3b82f6" name="Sessions" />
                <Bar dataKey="avg_latency_ms" fill="#f59e0b" name="Avg Latency ms" />
                <Bar dataKey="avg_duration_s" fill="#10b981" name="Avg Duration s" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
        <Card className="analytics-section-card">
          <CardHeader>
            <CardTitle>Sentiment Counts</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {sentimentEntries.length === 0 ? (
                <p className="text-sm text-gray-500">No sentiment data yet.</p>
              ) : (
                sentimentEntries.map(([label, count]) => (
                  <div key={label} className="flex justify-between text-sm">
                    <span className="capitalize">{label}</span>
                    <span className="font-medium">{count}</span>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
        <Card className="analytics-section-card">
          <CardHeader>
            <CardTitle>Interruptions</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xl sm:text-2xl font-semibold">{analytics.interruption_count ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      {analytics.anomalies && analytics.anomalies.length > 0 && (
        <Card className="analytics-section-card">
          <CardHeader>
            <CardTitle>Anomalies</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc pl-5 text-sm space-y-1">
              {analytics.anomalies.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
      </main>
    </div>
  );
}