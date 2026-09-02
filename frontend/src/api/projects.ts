import { apiClient } from './client';
import {
  CreateProjectRequest,
  Operation,
  OperationListResponse,
  Project,
  ProjectAgentRequest,
  ProjectAgentResponse,
  ProjectGraphBuildResponse,
  ProjectListResponse,
  ProjectReviewResponse,
  ProjectScanResponse,
} from '../types/projects';

export const projectsApi = {
  list: async (status?: string): Promise<ProjectListResponse> => {
    return apiClient<ProjectListResponse>('/projects', {
      params: { status },
    });
  },

  get: async (projectId: string): Promise<Project> => {
    return apiClient<Project>(`/projects/${projectId}`);
  },

  create: async (data: CreateProjectRequest): Promise<Project> => {
    return apiClient<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  delete: async (projectId: string): Promise<void> => {
    return apiClient<void>(`/projects/${projectId}`, {
      method: 'DELETE',
    });
  },

  scan: async (projectId: string): Promise<ProjectScanResponse> => {
    return apiClient<ProjectScanResponse>(`/projects/${projectId}/scan`, {
      method: 'POST',
    });
  },

  buildGraph: async (projectId: string): Promise<ProjectGraphBuildResponse> => {
    return apiClient<ProjectGraphBuildResponse>(`/projects/${projectId}/graph/build`, {
      method: 'POST',
    });
  },

  review: async (projectId: string): Promise<ProjectReviewResponse> => {
    return apiClient<ProjectReviewResponse>(`/projects/${projectId}/review`, {
      method: 'POST',
    });
  },

  askAgent: async (projectId: string, data: ProjectAgentRequest): Promise<ProjectAgentResponse> => {
    return apiClient<ProjectAgentResponse>(`/projects/${projectId}/agent`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  listOperations: async (projectId: string, status?: string): Promise<OperationListResponse> => {
    return apiClient<OperationListResponse>(`/projects/${projectId}/operations`, {
      params: { status },
    });
  },

  getOperation: async (operationId: string): Promise<Operation> => {
    return apiClient<Operation>(`/operations/${operationId}`);
  },
};
