import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

function bytes(value: number) {
  return `${(value / 1024 ** 2).toLocaleString(undefined, { maximumFractionDigits: 2 })} MiB`;
}

export function StorageUsagePanel() {
  const { user } = useAuth();
  const enabled = user?.email_verified && !!user.tenant && ['owner', 'admin'].includes(user.role ?? '');
  const usage = useQuery({
    queryKey: ['storage-usage', user?.id, user?.tenant?.id],
    queryFn: api.storageUsage, enabled: !!enabled, refetchInterval: 15000,
  });
  if (!enabled) return null;
  return <section className="content-card p-5 space-y-3" aria-label="Workspace storage">
    <h2 className="section-title">Workspace storage</h2>
    {usage.isPending && <p>Loading storage usage…</p>}
    {usage.error && <p role="alert">Storage usage unavailable. <button onClick={() => void usage.refetch()}>Retry</button></p>}
    {usage.data && <>
      <p>{usage.data.plan === 'free' ? 'Free' : 'Team'} allocation: {bytes(usage.data.allocated_bytes)} of {bytes(usage.data.limit_bytes)}</p>
      <progress aria-label="Allocated storage" max={Math.max(1, usage.data.limit_bytes)} value={Math.min(usage.data.allocated_bytes, Math.max(1, usage.data.limit_bytes))} />
      <ul>
        <li>Retained files and versions: {bytes(usage.data.retained_bytes)}</li>
        <li>Upload reservations: {bytes(usage.data.reserved_bytes)}</li>
        <li>Preview allocation: {bytes(usage.data.derivative_bytes)}</li>
        <li>Other observed storage: {bytes(usage.data.orphan_bytes)}</li>
      </ul>
      <p>History, trash and quarantined content count toward storage. Cancelled or expired uploads keep their reservation until cleanup confirms reclamation.</p>
      {usage.data.over_quota && <p role="alert">This workspace is over quota. Existing content remains available; new uploads and previews need free space.</p>}
      {usage.data.reconciliation_required && <p role="alert">Storage accounting needs an operator check. New allocations are paused; existing downloads and cleanup remain available.</p>}
    </>}
  </section>;
}
