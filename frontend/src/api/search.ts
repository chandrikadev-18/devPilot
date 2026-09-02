import { apiClient } from './client';
import { SemanticSearchResponse, SymbolSearchResponse } from '../types/search';

export const searchApi = {
  searchSymbol: async (
    query: string,
    projectDir?: string,
    strict: boolean = false
  ): Promise<SymbolSearchResponse> => {
    return apiClient<SymbolSearchResponse>('/api/search/symbol', {
      params: { query, project_dir: projectDir, strict },
    });
  },

  semanticSearch: async (
    query: string,
    topK: number = 5,
    projectDir?: string
  ): Promise<SemanticSearchResponse> => {
    return apiClient<SemanticSearchResponse>('/api/search/semantic', {
      params: { query, top_k: topK, project_dir: projectDir },
    });
  },
};
