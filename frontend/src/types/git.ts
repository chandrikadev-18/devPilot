export interface GitCommitDetail {
  commit_hash: string;
  short_hash: string;
  author: string;
  email: string;
  date: string;
  message: string;
  files_changed: string[];
  stats?: {
    insertions: number;
    deletions: number;
    files: number;
  };
  diff_patch?: string;
}

export interface GitLastChangeResponse {
  symbol_or_file: string;
  commit_hash: string;
  short_hash: string;
  author_name: string;
  author_email: string;
  authored_date: string;
  commit_message: string;
}

export interface GitHistoryItem {
  commit_hash: string;
  short_hash: string;
  author: string;
  date: string;
  message: string;
}

export interface GitHistoryResponse {
  symbol_or_file: string;
  total_commits: number;
  commits: GitHistoryItem[];
}

export interface BlameLineItem {
  line_number: number;
  line_content: string;
  commit_hash: string;
  short_hash: string;
  author_name: string;
  authored_date: string;
}

export interface GitBlameResponse {
  symbol_or_file: string;
  lines: BlameLineItem[];
  total_lines: number;
}
