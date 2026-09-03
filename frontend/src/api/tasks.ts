import { apiClient } from './client';

export interface TaskPlanStep {
  step_number: number;
  file: string;
  symbol: string;
  operation: string;
  reason: string;
  risk: string;
  expected_result: string;
}

export interface RootCauseEvidence {
  confidence: string;
  summary: string;
  culprit_file?: string;
  culprit_symbol?: string;
  evidence_points: string[];
  call_chain: string[];
  related_tests: string[];
}

export interface EngineeringTask {
  task_id: string;
  title: string;
  description: string;
  project_id: string;
  project_root: string;
  status: string;
  priority: string;
  task_type: string;
  target_files: string[];
  target_symbols: string[];
  discovered_symbols: string[];
  affected_files: string[];
  root_cause?: RootCauseEvidence;
  impact: Record<string, any>;
  implementation_plan: TaskPlanStep[];
  patch?: string;
  proposal_id?: string;
  tests_discovered: string[];
  tests_generated: string[];
  validation_results: Record<string, any>;
  review_results: Record<string, any>;
  pr_summary?: string;
  risk: string;
  iteration_count: number;
  max_iterations: number;
  checkpoint_id?: string;
  error_message?: string;
  decision_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface TaskListResponse {
  success: boolean;
  total: number;
  tasks: EngineeringTask[];
}

export interface TaskResponse {
  success: boolean;
  task: EngineeringTask;
}

export const tasksApi = {
  createTask: (title: string, description: string = '', task_type?: string, priority?: string, project_id?: string) =>
    apiClient<TaskResponse>('/tasks', {
      method: 'POST',
      body: JSON.stringify({ title, description, task_type, priority, project_id }),
    }),

  listTasks: (status?: string, task_type?: string, priority?: string) =>
    apiClient<TaskListResponse>('/tasks', {
      params: { status, task_type, priority },
    }),

  getTask: (taskId: string) =>
    apiClient<TaskResponse>(`/tasks/${taskId}`),

  analyzeTask: (taskId: string) =>
    apiClient<TaskResponse>(`/tasks/${taskId}/analyze`, {
      method: 'POST',
    }),

  planTask: (taskId: string) =>
    apiClient<TaskResponse>(`/tasks/${taskId}/plan`, {
      method: 'POST',
    }),

  approveTask: (taskId: string, reason?: string, force: boolean = false) =>
    apiClient<TaskResponse>(`/tasks/${taskId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ reason, force }),
    }),

  rejectTask: (taskId: string, reason?: string) =>
    apiClient<TaskResponse>(`/tasks/${taskId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  executeTask: (taskId: string, runTests: boolean = true) =>
    apiClient<TaskResponse>(`/tasks/${taskId}/execute`, {
      method: 'POST',
      body: JSON.stringify({ run_tests: runTests }),
    }),

  rollbackTask: (taskId: string) =>
    apiClient<TaskResponse>(`/tasks/${taskId}/rollback`, {
      method: 'POST',
    }),

  getTaskDiff: (taskId: string) =>
    apiClient<{ success: boolean; task_id: string; patch: string }>(`/tasks/${taskId}/diff`),

  getTaskReport: (taskId: string) =>
    apiClient<{ success: boolean; task_id: string; title: string; status: string; pr_summary: string }>(`/tasks/${taskId}/report`),
};
