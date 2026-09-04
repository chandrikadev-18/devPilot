import { apiClient } from './client';
import { DetailedHealthResponse, HealthResponse, ReadinessResponse } from '../types/health';

export const healthApi = {
  check: async (): Promise<HealthResponse> => {
    return apiClient<HealthResponse>('/health');
  },

  checkReadiness: async (): Promise<ReadinessResponse> => {
    return apiClient<ReadinessResponse>('/health/ready');
  },

  checkDetails: async (): Promise<DetailedHealthResponse> => {
    return apiClient<DetailedHealthResponse>('/health/details');
  },
};

