import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { StorageUsagePanel } from '../features/organizations/StorageUsagePanel';
import { api } from '../services/api';

const auth = vi.hoisted(() => ({ user: { id: 'owner', tenant: { id: 'tenant' },
  email_verified: true, role: 'owner' } }));
vi.mock('../auth/AuthContext', () => ({ useAuth: () => auth }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); auth.user.role = 'owner'; });

it('shows retained and reserved storage and safe over-quota behavior', async () => {
  vi.spyOn(api, 'storageUsage').mockResolvedValue({
    plan: 'free', limit_bytes: 100, retained_bytes: 100, reserved_bytes: 6,
    derivative_bytes: 0, orphan_bytes: 0, allocated_bytes: 106, available_bytes: 0,
    unresolved_references: 1, over_quota: true, reconciliation_required: true,
  });
  render(<QueryClientProvider client={new QueryClient()}><StorageUsagePanel /></QueryClientProvider>);
  expect(await screen.findByText(/This workspace is over quota/)).toBeInTheDocument();
  expect(screen.getByText(/History, trash and quarantined/)).toBeInTheDocument();
  expect(screen.getByText(/Storage accounting needs an operator/)).toBeInTheDocument();
});

it('does not fetch organization-wide private accounting for members', () => {
  auth.user.role = 'member';
  const read = vi.spyOn(api, 'storageUsage');
  render(<QueryClientProvider client={new QueryClient()}><StorageUsagePanel /></QueryClientProvider>);
  expect(read).not.toHaveBeenCalled();
  expect(screen.queryByLabelText('Workspace storage')).not.toBeInTheDocument();
});
