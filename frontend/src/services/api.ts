import type { HealthResponse, ReadinessResponse } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';
const API_V1 = `${API_BASE}/api/v1`;

async function fetchApi<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Accept': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorDetail = `API error: ${response.status}`;
    try {
      const errorData = await response.json();
      errorDetail = errorData.detail || errorDetail;
    } catch {
      // Response body is not JSON
    }
    throw new Error(errorDetail);
  }

  return response.json();
}

export const api = {
  getHealth: () => fetchApi<HealthResponse>(`${API_V1}/health`),
  getReadiness: () => fetchApi<ReadinessResponse>(`${API_V1}/health/ready`),
};
