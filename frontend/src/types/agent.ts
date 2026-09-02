export interface ToolExecution {
  tool: string;
  status: string;
  duration_ms: number;
  args?: Record<string, any>;
}

export interface AgentAskRequest {
  question: string;
  project_dir?: string;
  provider?: string;
  model?: string;
}

export interface AgentAskResponse {
  question: string;
  answer: string;
  tools_used: string[];
  sources: string[];
  metadata: {
    iterations: number;
    stopped_reason?: string;
    timing?: Record<string, number>;
    tool_executions?: ToolExecution[];
  };
  iterations?: number;
  timing?: Record<string, number>;
}
