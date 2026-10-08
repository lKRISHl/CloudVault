export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
}

export interface ReadinessResponse {
  status: string;
  version: string;
  timestamp: string;
  checks: {
    database: {
      status: string;
      latency_ms?: number;
    };
  };
}

export interface ApiError {
  detail: string;
  status_code: number;
}
