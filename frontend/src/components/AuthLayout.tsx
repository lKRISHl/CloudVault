import type { ReactNode } from 'react';
import { Icon } from './ui/Icon';

export function AuthLayout({ children }: { children: ReactNode }) {
  return <div className="auth-layout"><aside className="auth-story">
    <div className="vault-brand"><span className="brand-mark"><Icon name="vault" /></span>CloudVault<span className="brand-dot">.</span></div>
    <div className="auth-story-copy"><span className="eyebrow">LESS CLUTTER. MORE CLARITY.</span><h2>Your work.<br />In its own<br /><em>space.</em></h2><p>A considered home for your files, your team, and everything you’re building.</p>
    <div className="auth-art" aria-hidden="true"><div className="art-folder"><Icon name="folder" /><span>Project workspace</span><span className="art-pill">Organized</span></div><div className="art-file"><Icon name="file" /><div><strong>Everything in its place</strong><small>Files · Folders · Workspaces</small></div><span>✓</span></div></div></div>
    <small className="auth-footer">Built for the way you work.</small>
  </aside><main className="auth-form-side">{children}</main></div>;
}
