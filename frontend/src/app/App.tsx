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
import { ApiRequestError } from '../services/api';

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
        <BrowserRouter>
          <Routes>
            <Route path="/account/recover" element={<RecoveryPage />} />
            <Route path="/account/action" element={<AccountActionPage />} />
            <Route path="/join" element={<JoinPage />} />
            <Route element={<GuestRoute />}>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
            </Route>
            <Route element={<ProtectedRoute />}>
              <Route path="/app" element={<HomePage />} />
              <Route path="/app/settings" element={<SettingsPage />} />
              <Route path="/app/security" element={<SecurityPage />} />
              <Route path="/app/folders" element={<FoldersPage />} />
            </Route>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
