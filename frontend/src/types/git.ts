export interface GitCommitDetail {
  commit_hash: string;
  short_hash: string;
  author_name?: string;
  author?: string;
  author_email?: string;
  email?: string;
  date: string;
  message: string;
  files_changed: string[];
  additions?: number;
  deletions?: number;
  diff_summary?: string;
  diff_patch?: string;
  stats?: {
    insertions: number;
    deletions: number;
    files: number;
  };
}

export interface GitLastChangeResponse {
  symbol?: string;
  symbol_or_file?: string;
  commit?: string;
  commit_hash?: string;
  short_hash: string;
  author?: string;
  author_name?: string;
  author_email?: string;
  date?: string;
  authored_date?: string;
  message?: string;
  commit_message?: string;
  file?: string;
  line?: number;
  end_line?: number;
}

export interface GitHistoryItem {
  commit_hash: string;
  short_hash: string;
  author?: string;
  author_name?: string;
  author_email?: string;
  date: string;
  message: string;
  files_changed?: string[];
}

export interface GitHistoryResponse {
  symbol?: string;
  symbol_or_file?: string;
  file?: string;
  line?: number;
  total_commits: number;
  commits: GitHistoryItem[];
}

export interface BlameLineItem {
  line_number: number;
  commit_hash: string;
  short_hash: string;
  author?: string;
  author_name?: string;
  date?: string;
  authored_date?: string;
  content?: string;
  line_content?: string;
}

export interface GitBlameResponse {
  symbol?: string;
  symbol_or_file?: string;
  file?: string;
  start_line?: number;
  end_line?: number;
  total_lines: number;
  primary_contributor?: string;
  contributors?: string[];
  lines: BlameLineItem[];
}

