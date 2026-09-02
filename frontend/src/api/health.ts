import { apiClient } from './client';
import { DetailedHealthResponse, HealthResponse } from '../types/health';

export const healthApi = {
  check: async (): Promise<HealthResponse> => {
    return apiClient<HealthResponse>('/health');
  },

  checkDetails: async (): Promise<DetailedHealthResponse> => {
    return apiClient<DetailedHealthResponse>('/health/details');
  },
};
