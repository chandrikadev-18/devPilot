export interface GraphInfoResponse {
  total_nodes: number;
  total_edges: number;
  files: number;
  classes: number;
  functions: number;
  methods: number;
  calls: number;
}

export interface CallerInfo {
  caller_name: string;
  caller_file: string;
  caller_line: number;
  call_type?: string;
}

export interface GraphCallersResponse {
  symbol: string;
  total_callers: number;
  callers: CallerInfo[];
}

export interface CalleeInfo {
  callee_name: string;
  callee_file?: string;
  callee_line?: number;
  call_type?: string;
}

export interface GraphCalleesResponse {
  symbol: string;
  total_callees: number;
  callees: CalleeInfo[];
}

export interface DependencyItem {
  target: string;
  file?: string;
  depth: number;
  type?: string;
}

export interface GraphDependenciesResponse {
  symbol: string;
  depth: number;
  total_dependencies: number;
  dependencies: DependencyItem[];
}

export interface DependentItem {
  source: string;
  file?: string;
  depth: number;
  type?: string;
}

export interface GraphDependentsResponse {
  symbol: string;
  depth: number;
  total_dependents: number;
  dependents: DependentItem[];
}

export interface GraphImpactResponse {
  symbol: string;
  depth: number;
  analysis_type: string;
  total_impacted: number;
  direct_callers: string[];
  indirect_callers: string[];
  impacted_files: string[];
}

export interface GraphFileDependenciesResponse {
  file_path: string;
  imports: string[];
  imported_by: string[];
  total_imports: number;
  total_imported_by: number;
}
