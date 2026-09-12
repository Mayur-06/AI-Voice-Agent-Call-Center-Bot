import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import SessionScreen from './screens/SessionScreen';
import VoiceCallScreen from './screens/VoiceCallScreen';
import PostCallReviewScreen from './screens/PostCallReviewScreen';
import AnalyticsDashboard from './screens/AnalyticsDashboard';
import { ErrorBoundary } from './components/ErrorBoundary';
import { API_BASE, apiFetch } from './config';

// The call screen starts microphone capture as soon as it mounts. Validate the
// session before mounting it so an ended call cannot be reopened by browser
// history, a refresh, or a pasted URL.
function ActiveCallRoute() {
  const { sessionId } = useParams();
  const [sessionState, setSessionState] = useState('checking');

  useEffect(() => {
    let cancelled = false;

    async function validateSession() {
      try {
        const response = await apiFetch(`${API_BASE}/api/sessions/${sessionId}`);
        if (!response.ok) {
          if (!cancelled) setSessionState('missing');
          return;
        }

        const session = await response.json();
        if (!cancelled) {
          setSessionState(session.status === 'ended' || session.ended_at ? 'ended' : 'active');
        }
      } catch {
        // Fail closed: without a successful validation, do not mount a route
        // that can open a microphone or reconnect a call.
        if (!cancelled) setSessionState('missing');
      }
    }

    validateSession();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  if (sessionState === 'checking') return null;
  if (sessionState === 'ended') return <Navigate to={`/review/${sessionId}`} replace />;
  if (sessionState !== 'active') return <Navigate to="/session" replace />;
  return <VoiceCallScreen />;
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Navigate to="/session" replace />} />
          <Route path="/session" element={<SessionScreen />} />
          <Route path="/call/:sessionId" element={<ActiveCallRoute />} />
          <Route path="/review/:sessionId" element={<PostCallReviewScreen />} />
          <Route path="/analytics" element={<AnalyticsDashboard />} />
        </Routes>
      </ErrorBoundary>
    </BrowserRouter>
  );
}
