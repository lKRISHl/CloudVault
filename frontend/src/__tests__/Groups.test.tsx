import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { GroupsPage } from '../features/organizations/GroupsPage';
import { api } from '../services/api';

const auth = vi.hoisted(() => ({ role: 'owner' }));
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'me', tenant: { id: 'workspace' }, email_verified: true, role: auth.role } }) }));
afterEach(() => { vi.restoreAllMocks(); auth.role = 'owner'; });
function show() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><GroupsPage /></MemoryRouter></QueryClientProvider>); }

it('creates a group and adds only a selected verified workspace member', async () => {
  vi.spyOn(api, 'groups').mockResolvedValue({ items: [], offset: 0, has_more: false });
  vi.spyOn(api, 'createGroup').mockResolvedValue({ id: 'design', name: 'Design' });
  vi.spyOn(api, 'groupMembers').mockImplementation(async (_id, _q, offset, candidates) => ({ items: candidates ? [{ user_id: 'member', full_name: 'Team Member', email: 'member@example.com' }] : [], offset, has_more: false }));
  vi.spyOn(api, 'setGroupMember').mockResolvedValue();
  show(); const user = userEvent.setup();
  await user.type(screen.getByLabelText('New group name'), 'Design');
  await user.click(screen.getByRole('button', { name: 'Create group' }));
  await screen.findByRole('option', { name: 'Team Member · member@example.com' });
  await user.selectOptions(screen.getByLabelText('Add verified member'), 'member');
  await user.click(screen.getByRole('button', { name: 'Add group member' }));
  await waitFor(() => expect(api.setGroupMember).toHaveBeenCalledWith('design', 'member', true));
});

it('does not load group administration for ordinary members', () => {
  auth.role = 'member'; const listing = vi.spyOn(api, 'groups');
  show(); expect(screen.getByRole('alert')).toHaveTextContent('Workspace owner or admin required');
  expect(listing).not.toHaveBeenCalled();
});
