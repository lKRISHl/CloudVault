import { useHealthCheck } from '../../hooks/useHealthCheck';

export function HealthStatus() {
  const { health, readiness, isLoading, isError, isHealthy } = useHealthCheck();

  if (isLoading) {
    return (
      <div className="flex items-center space-x-2 text-yellow-600 bg-yellow-50 p-4 rounded-lg shadow-sm border border-yellow-200">
        <div className="w-3 h-3 bg-yellow-500 rounded-full animate-pulse"></div>
        <span className="font-medium text-sm">Checking system health...</span>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center space-x-2 text-red-600 bg-red-50 p-4 rounded-lg shadow-sm border border-red-200">
        <div className="w-3 h-3 bg-red-500 rounded-full"></div>
        <span className="font-medium text-sm">Unable to connect to server</span>
      </div>
    );
  }

  const dbStatus = readiness?.checks?.database?.status ?? 'unknown';
  const dbLatency = readiness?.checks?.database?.latency_ms;
  const statusColor = isHealthy ? 'green' : 'red';

  return (
    <div className="flex flex-col space-y-2 bg-white p-4 rounded-lg shadow-sm border border-gray-100 min-w-64">
      <div className={`flex items-center space-x-2 text-${statusColor}-700`}>
        <div className={`w-3 h-3 bg-${statusColor}-500 rounded-full shadow-[0_0_8px_rgba(34,197,94,0.5)]`}></div>
        <span className="font-semibold">
          {isHealthy ? 'System Operational' : 'System Degraded'}
        </span>
      </div>

      <div className="text-xs text-gray-500 mt-2 space-y-1">
        <div className="flex justify-between">
          <span>Version:</span>
          <span className="font-mono bg-gray-100 px-1 rounded">{health?.version ?? 'unknown'}</span>
        </div>
        <div className="flex justify-between">
          <span>Database:</span>
          <span className={`font-mono ${dbStatus === 'up' ? 'text-green-600' : 'text-red-500'}`}>
            {dbStatus}
          </span>
        </div>
        {dbLatency !== undefined && (
          <div className="flex justify-between">
            <span>DB Latency:</span>
            <span className="font-mono">{dbLatency}ms</span>
          </div>
        )}
        <div className="flex justify-between pt-1 border-t border-gray-100 mt-1">
          <span>Last Checked:</span>
          <span>{new Date().toLocaleTimeString()}</span>
        </div>
      </div>
    </div>
  );
}
