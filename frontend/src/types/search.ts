export interface SymbolMatchItem {
  file_path: string;
  symbol_name: string;
  symbol_type?: string;
  parent_symbol?: string;
  start_line?: number;
  end_line?: number;
  code?: string;
  chunk_id?: string;
}

export interface SymbolSearchResponse {
  query: string;
  total_matches: number;
  matches: SymbolMatchItem[];
}

export interface SemanticSearchResultItem {
  symbol: string;
  file: string;
  start_line: number;
  end_line: number;
  score: number;
  reason?: string;
  symbol_type?: string;
  parent_symbol?: string;
  related_symbols?: string[];
}

export interface SemanticSearchResponse {
  query: string;
  total_results: number;
  results: SemanticSearchResultItem[];
}
