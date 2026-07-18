import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectCardsPage } from './pages/ProjectCardsPage';
import { KnowledgeSourcesPage } from './pages/KnowledgeSourcesPage';
import { KnowledgeSyncPage } from './pages/KnowledgeSyncPage';
import { LogsPage } from './pages/LogsPage';
import { ConversationsPage } from './pages/ConversationsPage';
import { AdminLayout } from './components/AdminLayout';

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AdminLayout />}>
            <Route path="/" element={<Navigate to="/system" replace />} />
            <Route path="/system" element={<DashboardPage />} />
            <Route path="/content/cards" element={<ProjectCardsPage />} />
            <Route path="/content/sources" element={<KnowledgeSourcesPage />} />
            <Route path="/content/sync" element={<KnowledgeSyncPage />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/conversations" element={<ConversationsPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}

export default App;
