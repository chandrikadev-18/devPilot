import { apiClient } from './client';
import {
  GitBlameResponse,
  GitCommitDetail,
  GitHistoryResponse,
  GitLastChangeResponse,
} from '../types/git';

export const gitApi = {
  getLastChange: async (symbol: string, projectDir?: string): Promise<GitLastChangeResponse> => {
    return apiClient<GitLastChangeResponse>('/api/git/last-change', {
      params: { symbol, project_dir: projectDir },
    });
  },

  getHistory: async (
    symbol: string,
    limit: number = 10,
    projectDir?: string
  ): Promise<GitHistoryResponse> => {
    return apiClient<GitHistoryResponse>('/api/git/history', {
      params: { symbol, limit, project_dir: projectDir },
    });
  },

  getBlame: async (
    symbol: string,
    startLine?: number,
    endLine?: number,
    projectDir?: string
  ): Promise<GitBlameResponse> => {
    return apiClient<GitBlameResponse>('/api/git/blame', {
      params: {
        symbol,
        start_line: startLine,
        end_line: endLine,
        project_dir: projectDir,
      },
    });
  },

  getCommit: async (commit: string, projectDir?: string): Promise<GitCommitDetail> => {
    return apiClient<GitCommitDetail>(`/api/git/commit/${encodeURIComponent(commit)}`, {
      params: { project_dir: projectDir },
    });
  },
};
