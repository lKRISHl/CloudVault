import { HealthStatus } from '../components/ui/HealthStatus';
import { useAuth } from '../auth/AuthContext';
import { Link } from 'react-router-dom';
import { WorkspaceSwitcher } from '../features/organizations/WorkspaceSwitcher';
import { Icon } from '../components/ui/Icon';

export function HomePage() {
  const { user } = useAuth();
  return <main>
    <div className="overview-hero"><div><span className="eyebrow">A SPACE TO MAKE THINGS HAPPEN</span><h1>Welcome, {user?.full_name.split(' ')[0]}.</h1><p>Your files and your team, with a little more room to breathe. Pick up where you left off.</p></div><Link className="primary-button" aria-label="Browse folders" to="/app/folders">Browse folders →</Link></div>
    <div className="overview-grid"><div className="space-y-5"><WorkspaceSwitcher /><HealthStatus /></div><div className="space-y-4">
      <Link className="quick-link" to="/app/folders"><span className="folder-icon"><Icon name="folder" /></span><div><strong>Your workspace library</strong><small>Organize folders and upload your files</small></div><span>↗</span></Link>
      <Link className="quick-link" aria-label="Profile and organization" to="/app/settings"><span className="file-icon"><Icon name="settings" /></span><div><strong>Profile and organization</strong><small>Manage your workspace and its members</small></div><span>↗</span></Link>
      <Link className="quick-link" aria-label="Account security and email" to="/app/security"><span className="upload-icon"><Icon name="shield" /></span><div><strong>Account security and email</strong><small>Verification, sessions and recovery</small></div><span>↗</span></Link>
      <p className="muted-copy">Signed in as {user?.full_name} · {user?.tenant?.name ?? 'No workspace selected'}</p>
    </div></div>
  </main>;
}
