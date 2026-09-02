import { apiClient } from './client';
import { AgentAskRequest, AgentAskResponse } from '../types/agent';

export const agentApi = {
  ask: async (data: AgentAskRequest): Promise<AgentAskResponse> => {
    return apiClient<AgentAskResponse>('/api/agent/ask', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  askLegacy: async (data: AgentAskRequest): Promise<AgentAskResponse> => {
    return apiClient<AgentAskResponse>('/api/ask', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
