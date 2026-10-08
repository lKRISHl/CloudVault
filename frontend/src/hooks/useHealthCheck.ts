import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';

export function useHealthCheck() {
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: api.getHealth,
    refetchInterval: 30000,
    retry: false,
  });

  const readinessQuery = useQuery({
    queryKey: ['readiness'],
    queryFn: api.getReadiness,
    refetchInterval: 30000,
    retry: false,
  });

  const isLoading = healthQuery.isLoading || readinessQuery.isLoading;
  const isError = healthQuery.isError || readinessQuery.isError;
  const isHealthy = healthQuery.data?.status === 'ok' && readinessQuery.data?.status === 'ok';

  return {
    health: healthQuery.data,
    readiness: readinessQuery.data,
    isLoading,
    isError,
    isHealthy,
  };
}
