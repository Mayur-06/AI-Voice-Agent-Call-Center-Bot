import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import SessionScreen from './screens/SessionScreen';
import VoiceCallScreen from './screens/VoiceCallScreen';
import PostCallReviewScreen from './screens/PostCallReviewScreen';
import AnalyticsDashboard from './screens/AnalyticsDashboard';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/session" replace />} />
        <Route path="/session" element={<SessionScreen />} />
        <Route path="/call/:sessionId" element={<VoiceCallScreen />} />
        <Route path="/review/:sessionId" element={<PostCallReviewScreen />} />
        <Route path="/analytics" element={<AnalyticsDashboard />} />
      </Routes>
    </BrowserRouter>
  );
}
