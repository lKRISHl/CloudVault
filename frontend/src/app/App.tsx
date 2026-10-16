import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from '../auth/AuthContext';
import { HomePage } from '../pages/HomePage';
import { LoginPage } from '../pages/LoginPage';
import { RegisterPage } from '../pages/RegisterPage';
import { SettingsPage } from '../features/organizations/SettingsPage';
import { JoinPage } from '../features/organizations/JoinPage';
import { SecurityPage } from '../features/accounts/SecurityPage';
import { RecoveryPage } from '../features/accounts/RecoveryPage';
import { AccountActionPage } from '../features/accounts/AccountActionPage';
import { FoldersPage } from '../features/folders/FoldersPage';
import { FileSearchPage } from '../features/search/FileSearchPage';
import { PublicSharePage, ShareManagementPage } from '../features/sharing/SharingPages';
import { GroupsPage } from '../features/organizations/GroupsPage';
import { PermissionsPage } from '../features/permissions/PermissionsPage';
import { TrashPage } from '../features/trash/TrashPage';
import { VersionsPage } from '../features/versions/VersionsPage';
import { PreviewPage } from '../features/previews/PreviewPage';
import { AppShell } from '../components/AppShell';
import { ApiRequestError } from '../services/api';
import { RealtimeProvider } from '../realtime/RealtimeProvider';

function ProtectedRoute() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">
        Restoring session…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

function GuestRoute() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-gray-500">
        Restoring session…
      </div>
    );
  }

  if (user) {
    return <Navigate to="/app" replace />;
  }

  return <Outlet />;
}

function App() {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: {
    retry: (count, error) => count < 2 && !(error instanceof ApiRequestError && error.status < 500),
  } } }));
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RealtimeProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/share" element={<PublicSharePage />} />
            <Route path="/account/recover" element={<RecoveryPage />} />
            <Route path="/account/action" element={<AccountActionPage />} />
            <Route path="/join" element={<JoinPage />} />
            <Route element={<GuestRoute />}>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
            </Route>
            <Route element={<ProtectedRoute />}>
              <Route element={<AppShell />}>
              <Route path="/app" element={<HomePage />} />
              <Route path="/app/settings" element={<SettingsPage />} />
              <Route path="/app/security" element={<SecurityPage />} />
              <Route path="/app/folders" element={<FoldersPage />} />
              <Route path="/app/search" element={<FileSearchPage />} />
              <Route path="/app/files/:fileId/shares" element={<ShareManagementPage />} />
              <Route path="/app/folders/:folderId/shares" element={<ShareManagementPage />} />
              <Route path="/app/groups" element={<GroupsPage />} />
              <Route path="/app/permissions/:kind/:id" element={<PermissionsPage />} />
              <Route path="/app/trash" element={<TrashPage />} />
              <Route path="/app/files/:fileId/versions" element={<VersionsPage />} />
              <Route path="/app/files/:fileId/preview" element={<PreviewPage />} />
              </Route>
            </Route>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
        </RealtimeProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
