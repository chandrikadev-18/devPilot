import { apiClient } from './client';
import {
  ChangeProposal,
  PlanChangeResponse,
  ReviewChangeResponse,
} from '../types/changes';

export const changesApi = {
  analyze: async (commit?: string, projectDir?: string): Promise<any> => {
    return apiClient<any>('/api/changes/analyze', {
      params: { commit, project_dir: projectDir },
    });
  },

  plan: async (request: string, projectDir?: string): Promise<PlanChangeResponse> => {
    return apiClient<PlanChangeResponse>('/api/changes/plan', {
      method: 'POST',
      body: JSON.stringify({ change_request: request, project_dir: projectDir }),
    });
  },

  propose: async (request: string, projectDir?: string): Promise<ChangeProposal> => {
    return apiClient<ChangeProposal>('/api/changes/propose', {
      method: 'POST',
      body: JSON.stringify({ request, project_dir: projectDir }),
    });
  },

  approveProposal: async (proposalId: string, projectDir?: string, force: boolean = true): Promise<ChangeProposal> => {
    return apiClient<ChangeProposal>(`/api/changes/proposals/${proposalId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ project_dir: projectDir, force }),
      params: { project_dir: projectDir },
    });
  },

  rejectProposal: async (proposalId: string, reason?: string, projectDir?: string): Promise<ChangeProposal> => {
    return apiClient<ChangeProposal>(`/api/changes/proposals/${proposalId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason, project_dir: projectDir }),
      params: { project_dir: projectDir },
    });
  },

  executeProposal: async (proposalId: string, projectDir?: string): Promise<any> => {
    return apiClient<any>(`/api/changes/proposals/${proposalId}/execute`, {
      method: 'POST',
      body: JSON.stringify({ project_dir: projectDir }),
      params: { project_dir: projectDir },
    });
  },

  review: async (baseBranch?: string, projectDir?: string): Promise<ReviewChangeResponse> => {
    return apiClient<ReviewChangeResponse>('/api/changes/review', {
      params: { base_branch: baseBranch, project_dir: projectDir },
    });
  },

  fix: async (request: string, projectDir?: string): Promise<any> => {
    return apiClient<any>('/api/changes/fix', {
      method: 'POST',
      body: JSON.stringify({ request, project_dir: projectDir }),
    });
  },

  fixLoop: async (request: string, maxIterations: number = 3, projectDir?: string): Promise<any> => {
    return apiClient<any>('/api/changes/fix-loop', {
      method: 'POST',
      body: JSON.stringify({ request, max_iterations: maxIterations, project_dir: projectDir }),
    });
  },

  getSummary: async (baseBranch?: string, projectDir?: string): Promise<any> => {
    return apiClient<any>('/api/changes/git-intelligence', {
      params: { base_branch: baseBranch, project_dir: projectDir },
    });
  },
};

