export type ProjectStatus = 'ACTIVE' | 'ARCHIVED' | 'ERROR';

export interface Project {
  project_id: string;
  name: string;
  path: string;
  repository: string | null;
  default_branch: string;
  status: ProjectStatus | string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, any>;
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

export interface CreateProjectRequest {
  name?: string;
  path: string;
  repository?: string;
  default_branch?: string;
  metadata?: Record<string, any>;
}

export interface ProjectScanResponse {
  operation: Operation;
  project_name: string;
  project_path: string;
  total_files: number;
  total_dirs: number;
  extensions: Record<string, number>;
  files_count: number;
}

export interface ProjectGraphBuildResponse {
  operation: Operation;
  project_id: string;
  total_nodes: number;
  total_edges: number;
  files: number;
  classes: number;
  functions: number;
}

export interface ProjectReviewResponse {
  operation: Operation;
  review: Record<string, any>;
}

export interface ProjectAgentRequest {
  question: string;
  provider?: string;
  model?: string;
}

export interface ProjectAgentResponse {
  operation: Operation;
  project_id: string;
  question: string;
  answer: string;
  tool_calls: any[];
  iterations: number;
}

export interface Operation {
  operation_id: string;
  project_id: string;
  operation_type: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | string;
  started_at: string;
  completed_at: string | null;
  result: Record<string, any> | null;
  error: string | null;
}

export interface OperationListResponse {
  operations: Operation[];
  total: number;
}

export interface ApiResponse<T = any> {
  status: 'success' | 'error';
  data: T;
  message?: string;
  error?: {
    code: string;
    message: string;
  };
}
