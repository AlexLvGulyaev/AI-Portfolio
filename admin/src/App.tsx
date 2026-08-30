import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectCardsPage } from './pages/ProjectCardsPage';
import { AdmissionConsolePage } from './pages/AdmissionConsolePage';
import { DocumentsPage } from './pages/DocumentsPage';
import { RetrievalSettingsPage } from './pages/RetrievalSettingsPage';
import { AiSettingsPage } from './pages/AiSettingsPage';
import { LogsPage } from './pages/LogsPage';
import { AuditPage } from './pages/AuditPage';
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
            <Route path="/content/sources" element={<AdmissionConsolePage />} />
            <Route path="/content/documents" element={<DocumentsPage />} />
            <Route path="/system/retrieval" element={<RetrievalSettingsPage />} />
            <Route path="/system/ai" element={<AiSettingsPage />} />
            {/* Легаси-роут страницы «Синхронизация»: синк переехал в консоль допуска. */}
            <Route path="/content/sync" element={<Navigate to="/content/sources" replace />} />
            <Route path="/logs" element={<LogsPage />} />
            <Route path="/conversations" element={<ConversationsPage />} />
            <Route path="/audit" element={<AuditPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}

export default App;
