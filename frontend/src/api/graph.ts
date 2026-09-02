import { apiClient } from './client';
import {
  GraphCalleesResponse,
  GraphCallersResponse,
  GraphDependenciesResponse,
  GraphDependentsResponse,
  GraphFileDependenciesResponse,
  GraphImpactResponse,
  GraphInfoResponse,
} from '../types/graph';

export const graphApi = {
  getInfo: async (projectDir?: string): Promise<GraphInfoResponse> => {
    return apiClient<GraphInfoResponse>('/api/graph/info', {
      params: { project_dir: projectDir },
    });
  },

  getCallers: async (symbol: string, projectDir?: string): Promise<GraphCallersResponse> => {
    return apiClient<GraphCallersResponse>('/api/graph/callers', {
      params: { symbol, project_dir: projectDir },
    });
  },

  getCallees: async (symbol: string, projectDir?: string): Promise<GraphCalleesResponse> => {
    return apiClient<GraphCalleesResponse>('/api/graph/callees', {
      params: { symbol, project_dir: projectDir },
    });
  },

  getDependencies: async (
    symbol: string,
    depth: number = 1,
    projectDir?: string
  ): Promise<GraphDependenciesResponse> => {
    return apiClient<GraphDependenciesResponse>('/api/graph/dependencies', {
      params: { symbol, depth, project_dir: projectDir },
    });
  },

  getDependents: async (
    symbol: string,
    depth: number = 1,
    projectDir?: string
  ): Promise<GraphDependentsResponse> => {
    return apiClient<GraphDependentsResponse>('/api/graph/dependents', {
      params: { symbol, depth, project_dir: projectDir },
    });
  },

  getImpact: async (
    symbol: string,
    depth: number = 2,
    projectDir?: string
  ): Promise<GraphImpactResponse> => {
    return apiClient<GraphImpactResponse>('/api/graph/impact', {
      params: { symbol, depth, project_dir: projectDir },
    });
  },

  getFileDependencies: async (
    filePath: string,
    projectDir?: string
  ): Promise<GraphFileDependenciesResponse> => {
    return apiClient<GraphFileDependenciesResponse>('/api/graph/file-dependencies', {
      params: { file_path: filePath, project_dir: projectDir },
    });
  },

  build: async (directory?: string): Promise<GraphInfoResponse> => {
    return apiClient<GraphInfoResponse>('/api/graph/build', {
      method: 'POST',
      params: { directory },
    });
  },
};
