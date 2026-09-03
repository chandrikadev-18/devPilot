export interface GraphInfoResponse {
  total_nodes: number;
  total_edges: number;
  files: number;
  classes: number;
  functions: number;
  methods: number;
  modules?: number;
  calls: number;
  imports?: number;
  contains?: number;
  defines?: number;
  belongs_to?: number;
}

export interface CallerInfo {
  id?: string;
  name?: string;
  qualified_name?: string;
  caller_name?: string;
  caller_file?: string;
  caller_line?: number;
  file_path?: string;
  start_line?: number;
  end_line?: number;
  call_line?: number;
  call_type?: string;
  target_symbol?: string;
}

export interface GraphCallersResponse {
  symbol: string;
  total_callers: number;
  callers: CallerInfo[];
}

export interface CalleeInfo {
  id?: string;
  name?: string;
  qualified_name?: string;
  callee_name?: string;
  callee_file?: string;
  callee_line?: number;
  file_path?: string;
  start_line?: number;
  end_line?: number;
  call_line?: number;
  call_type?: string;
  caller_symbol?: string;
}

export interface GraphCalleesResponse {
  symbol: string;
  total_callees: number;
  callees: CalleeInfo[];
}

export interface DependencyItem {
  id?: string;
  name?: string;
  qualified_name?: string;
  target?: string;
  file?: string;
  file_path?: string;
  start_line?: number;
  end_line?: number;
  call_line?: number;
  depth: number;
  type?: string;
  caller?: string;
  call_path?: string;
}

export interface GraphDependenciesResponse {
  symbol: string;
  depth: number;
  total_dependencies: number;
  dependencies: DependencyItem[];
}

export interface DependentItem {
  id?: string;
  name?: string;
  source?: string;
  file?: string;
  file_path?: string;
  start_line?: number;
  end_line?: number;
  call_line?: number;
  depth: number;
  type?: string;
  calls_target?: string;
  dependent_path?: string;
}

export interface GraphDependentsResponse {
  symbol: string;
  depth: number;
  total_dependents: number;
  dependents: DependentItem[];
}

export interface GraphImpactItem {
  id?: string;
  name?: string;
  file_path?: string;
  node_type?: string;
  start_line?: number;
  end_line?: number;
  call_line?: number;
  calls_target?: string;
  depth?: number;
}

export interface GraphImpactResponse {
  symbol: string;
  depth: number;
  analysis_type: string;
  total_impacted: number;
  direct_callers: (GraphImpactItem | string)[];
  indirect_callers: (GraphImpactItem | string)[];
  direct_dependents?: (GraphImpactItem | string)[];
  indirect_dependents?: (GraphImpactItem | string)[];
  impacted_files: string[];
}

export interface GraphFileDependenciesResponse {
  file_path: string;
  imports_files?: string[];
  imports_modules?: string[];
  imports?: string[];
  imported_by: string[];
  defined_symbols?: any[];
  total_imports?: number;
  total_imported_by?: number;
}

