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

export interface ReviewChangeResponse {
  branch?: string;
  base_branch?: string;
  is_clean: boolean;
  status?: {
    staged: string[];
    unstaged: string[];
    untracked: string[];
  };
  changed_files?: string[];
  changed_symbols?: ChangedSymbolItem[];
  impact?: ChangeImpactItem;
  risk?: ChangeRiskItem;
  findings?: ReviewFinding[];
  recommended_tests?: string[];
  summary?: string;
  diff_summary?: string;
  duration_ms?: number;
}

export interface ChangeProposal {
  proposal_id: string;
  request: string;
  status: 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED' | string;
  risk_level: string;
  created_at: string;
  approved_at?: string;
  rejected_at?: string;
  executed_at?: string;
  diff?: string;
  affected_files?: string[];
  affected_symbols?: string[];
  tests?: string[];
  reason?: string;
}

export interface PlanChangeResponse {
  request: string;
  plan: string;
  target_files: string[];
  target_symbols: string[];
  risk_assessment: ChangeRiskItem;
}
