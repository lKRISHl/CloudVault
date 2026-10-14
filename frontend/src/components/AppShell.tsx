import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { Icon } from './ui/Icon';

export function AppShell() {
  const { user, logout } = useAuth();
  return <div className="vault-shell">
    <a href="#workspace-content" className="skip-link">Skip to content</a>
    <aside className="vault-sidebar">
      <NavLink to="/app" className="vault-brand"><span className="brand-mark"><Icon name="vault" /></span>CloudVault<span className="brand-dot">.</span></NavLink>
      <div className="workspace-label"><span className="workspace-monogram">{user?.tenant?.name.slice(0, 1).toUpperCase() ?? 'W'}</span><div><small>YOUR WORKSPACE</small><strong>{user?.tenant?.name ?? 'Select a workspace'}</strong></div></div>
      <p className="nav-caption">WORKSPACE</p>
      <nav aria-label="Main navigation" className="vault-nav">
        <NavLink end to="/app"><Icon name="grid" />Overview</NavLink>
        <NavLink to="/app/folders"><Icon name="folder" />Files & folders</NavLink>
        <NavLink to="/app/settings"><Icon name="settings" />Workspace settings</NavLink>
        <NavLink to="/app/security"><Icon name="shield" />Account security</NavLink>
      </nav>
      <div className="sidebar-note"><Icon name="vault" /><strong>A home for your work.</strong><p>Keep your files organized in one workspace.</p></div>
      <div className="sidebar-account"><span className="account-avatar">{user?.full_name.slice(0, 1).toUpperCase()}</span><div><strong>{user?.full_name}</strong><small>{user?.role ?? 'Account'}</small></div><button onClick={() => void logout()} aria-label="Sign out">↗</button></div>
    </aside>
    <div className="vault-main"><header className="vault-topbar"><span>Workspace / <strong>{user?.tenant?.name ?? 'Overview'}</strong></span><span className="identity-chip">{user?.email_verified ? 'Email verified' : 'Verify your email'}</span></header><div id="workspace-content" tabIndex={-1} className="vault-content"><Outlet /></div></div>
  </div>;
}
