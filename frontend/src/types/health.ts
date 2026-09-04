export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface ReadinessResponse {
  status: 'healthy' | 'degraded' | 'unavailable' | string;
  service: string;
  version: string;
  ready: boolean;
  checks: Record<string, { status: string; detail?: string; [key: string]: any }>;
}

export interface DetailedHealthResponse {
  status: 'ok' | 'degraded' | 'error' | string;
  service: string;
  version: string;
  environment: string;
  git: {
    available: boolean;
    version?: string;
  };
  storage: {
    available: boolean;
    writable: boolean;
  };
  graph: {
    available: boolean;
  };
  llm: {
    provider: string;
    model: string;
    api_key_configured: boolean;
  };
}

