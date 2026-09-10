import { useEffect, useState } from 'react';
import { API_BASE } from '@/config';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Legend, PieChart, Pie, Cell,
} from 'recharts';

const COLORS = ['#22c55e', '#eab308', '#ef4444', '#a855f7', '#3b82f6'];

export default function AnalyticsDashboard() {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/analytics/`);
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

  if (loading) return <div className="p-6">Loading analytics...</div>;
  if (error) return <div className="p-6 text-red-500">{error}</div>;
  if (!analytics) return <div className="p-6">No analytics available.</div>;

  const sentimentEntries = Object.entries(analytics.sentiment_breakdown || {});
  const sentimentPieData = sentimentEntries.map(([name, value]) => ({ name, value }));
  const callsOverTime = analytics.calls_over_time || [];
  const perPersona = analytics.per_persona_stats || [];

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Analytics Dashboard</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500">Total Sessions</h2>
          <p className="text-2xl font-semibold">{analytics.total_sessions ?? 0}</p>
        </div>
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500">Total Messages</h2>
          <p className="text-2xl font-semibold">{analytics.total_messages ?? 0}</p>
        </div>
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500">Avg Latency</h2>
          <p className="text-2xl font-semibold">{Math.round(analytics.avg_latency_ms ?? 0)} ms</p>
        </div>
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500">Avg Session Duration</h2>
          <p className="text-2xl font-semibold">{Math.round(analytics.avg_session_duration_s ?? 0)} s</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Calls Over Time</h2>
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
        </div>

        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Sentiment Breakdown</h2>
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
        </div>
      </div>

      <div className="border rounded-lg p-4">
        <h2 className="font-medium text-gray-500 mb-2">Per-Persona Performance</h2>
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
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Sentiment Counts</h2>
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
        </div>
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Interruptions</h2>
          <p className="text-2xl font-semibold">{analytics.interruption_count ?? 0}</p>
        </div>
      </div>

      {analytics.anomalies && analytics.anomalies.length > 0 && (
        <div className="border rounded-lg p-4">
          <h2 className="font-medium text-gray-500 mb-2">Anomalies</h2>
          <ul className="list-disc pl-5 text-sm space-y-1">
            {analytics.anomalies.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}