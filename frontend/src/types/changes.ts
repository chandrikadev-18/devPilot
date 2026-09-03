export interface ChangedSymbolItem {
  name: string;
  file: string;
  change_type: string;
  symbol_type?: string;
  line_start?: number;
  line_end?: number;
}

export interface ChangeImpactItem {
  direct: string[];
  indirect: string[];
  files: string[];
  total_affected_symbols: number;
}

export interface ChangeRiskItem {
  score: number;
  level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  reasons: string[];
}

export interface ReviewFinding {
  severity: 'low' | 'medium' | 'high' | 'critical' | string;
  category: string;
  file: string;
  line?: number;
  symbol?: string;
  description: string;
  evidence?: string;
  recommendation?: string;
  confidence?: number;
}

export interface TestRecommendationItem {
  test_target: string;
  file_path: string;
  reason: string;
  symbol_name?: string;
}

export interface ReviewChangeResponse {
  branch?: string;
  base_branch?: string;
  is_clean: boolean;
  status?: {
    staged?: string[];
    unstaged?: string[];
    untracked?: string[];
    modified_files?: string[];
    added_files?: string[];
    deleted_files?: string[];
  };
  changed_files?: string[];
  changed_symbols?: ChangedSymbolItem[];
  impact?: ChangeImpactItem;
  risk?: ChangeRiskItem;
  findings?: ReviewFinding[];
  review_notes?: string[];
  test_recommendations?: TestRecommendationItem[];
  recommended_tests?: string[];
  summary?: string;
  diff_stats?: Record<string, any>;
  diff_summary?: string;
  duration_ms?: number;
}

export interface ChangeProposal {
  proposal_id: string;
  request: string;
  status: 'PENDING_APPROVAL' | 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'APPLIED' | 'EXECUTED' | 'FAILED' | string;
  risk?: string;
  risk_level?: string;
  created_at?: string;
  updated_at?: string;
  approved_at?: string;
  rejected_at?: string;
  applied_at?: string;
  executed_at?: string;
  patch?: string;
  diff?: string;
  target_file?: string;
  target_symbol?: string;
  target_lines?: string;
  change_summary?: string;
  affected_files?: string[];
  affected_symbols?: string[];
  proposed_changes?: string[];
  tests?: string[];
  tests_to_update?: string[];
  tests_to_add?: string[];
  reason?: string;
  reasoning?: string;
  confidence?: number;
  warnings?: string[];
}

export interface ChangePlanEvidenceItem {
  file: string;
  symbol: string;
  lines: string;
  relationship: string;
}

export interface PlanChangeResponse {
  change_request?: string;
  request?: string;
  target?: string;
  target_symbol?: string;
  target_file?: string;
  target_lines?: string;
  target_files?: string[];
  target_symbols?: string[];
  affected_files?: string[];
  affected_symbols?: string[];
  direct_dependencies?: string[];
  relevant_tests?: string[];
  recommended_order?: string[];
  risk?: string;
  reason?: string;
  plan?: string;
  risk_assessment?: ChangeRiskItem;
  evidence?: ChangePlanEvidenceItem[];
  unverified?: string[];
}

