import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Calendar,
  Clock,
  ExternalLink,
  GitBranch,
  GitCommit,
  Search,
  User,
} from 'lucide-react';
import { gitApi } from '../api/git';
import { projectsApi } from '../api/projects';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { CodeBlock } from '../components/common/CodeBlock';
import { EmptyState } from '../components/common/EmptyState';
import { Input } from '../components/common/Input';
import { Modal } from '../components/common/Modal';
import { Spinner } from '../components/common/Spinner';
import { Tabs } from '../components/common/Tabs';
import { useToast } from '../context/ToastContext';
import { GitBlameResponse, GitCommitDetail, GitHistoryResponse, GitLastChangeResponse } from '../types/git';
import { Project } from '../types/projects';

export const GitIntelligencePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [activeTab, setActiveTab] = useState('history');

  const [historyData, setHistoryData] = useState<GitHistoryResponse | null>(null);
  const [lastChangeData, setLastChangeData] = useState<GitLastChangeResponse | null>(null);
  const [blameData, setBlameData] = useState<GitBlameResponse | null>(null);

  // Commit Details Modal State
  const [selectedCommitDetail, setSelectedCommitDetail] = useState<GitCommitDetail | null>(null);
  const [isLoadingCommit, setIsLoadingCommit] = useState(false);

  const [isLoading, setIsLoading] = useState(true);
  const [isQuerying, setIsQuerying] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    if (!projectId) return;
    setIsLoading(true);
    projectsApi
      .get(projectId)
      .then((proj) => setProject(proj))
      .catch((err) => showToast(err.message || 'Failed to load project', 'error'))
      .finally(() => setIsLoading(false));
  }, [projectId]);

  const runQueryForTab = async (tab: string, sym: string) => {
    if (!sym.trim() || !project) return;
    try {
      setIsQuerying(true);
      const s = sym.trim();
      const pPath = project.path;

      if (tab === 'history') {
        const res = await gitApi.getHistory(s, 15, pPath);
        setHistoryData(res);
      } else if (tab === 'lastChange') {
        const res = await gitApi.getLastChange(s, pPath);
        setLastChangeData(res);
      } else if (tab === 'blame') {
        const res = await gitApi.getBlame(s, undefined, undefined, pPath);
        setBlameData(res);
      }
    } catch (err: any) {
      showToast(err.message || 'Git inspection failed', 'error');
    } finally {
      setIsQuerying(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    runQueryForTab(activeTab, symbolQuery);
  };

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    if (symbolQuery.trim()) {
      runQueryForTab(tab, symbolQuery);
    }
  };

  const inspectCommit = async (commitHash: string) => {
    if (!commitHash || !project) return;
    try {
      setIsLoadingCommit(true);
      const detail = await gitApi.getCommit(commitHash, project.path);
      setSelectedCommitDetail(detail);
    } catch (err: any) {
      showToast(err.message || `Failed to fetch commit ${commitHash}`, 'error');
    } finally {
      setIsLoadingCommit(false);
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Git Intelligence & History</h2>
          <p className="page-subtitle">
            Commit attribution, symbol evolution history, and line-level blame analysis for {project?.name}.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1000px' }}>
        {/* Project Branch & Repository Header */}
        <Card title="Repository Overview">
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', fontSize: '0.875rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <GitBranch size={16} color="var(--accent-blue)" />
              <span><strong>Default Branch:</strong> {project?.default_branch || 'main'}</span>
            </div>
            <div>
              <strong>Path:</strong> <code>{project?.path}</code>
            </div>
          </div>
        </Card>

        {/* Search Panel */}
        <Card padding="md">
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
            <div style={{ flex: 1 }}>
              <Input
                placeholder="Enter symbol (e.g. GraphBuilder.build) or file path (e.g. app/main.py)..."
                value={symbolQuery}
                onChange={(e) => setSymbolQuery(e.target.value)}
                leftIcon={<Search size={16} />}
                required
              />
            </div>
            <Button variant="primary" type="submit" isLoading={isQuerying} leftIcon={<GitCommit size={15} />}>
              Inspect Git
            </Button>
          </form>

          <Tabs
            tabs={[
              { id: 'history', label: 'Commit History', icon: <GitCommit size={15} /> },
              { id: 'lastChange', label: 'Last Change', icon: <Clock size={15} /> },
              { id: 'blame', label: 'Line Blame', icon: <User size={15} /> },
            ]}
            activeTab={activeTab}
            onChange={handleTabChange}
          />

          {/* Results view */}
          <div style={{ marginTop: '1.25rem' }}>
            {isQuerying ? (
              <Spinner label="Querying repository history..." />
            ) : activeTab === 'history' ? (
              historyData ? (
                <div>
                  <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>History for <code>{historyData.symbol || historyData.symbol_or_file || symbolQuery}</code>:</span>
                    <Badge variant="primary">{historyData.total_commits} commits</Badge>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {historyData.commits.map((c, idx) => {
                      const author = c.author_name || c.author || 'Unknown';
                      const dateStr = c.date ? new Date(c.date).toLocaleString() : '';
                      return (
                        <div
                          key={idx}
                          style={{
                            padding: '0.75rem 1rem',
                            backgroundColor: 'rgba(255, 255, 255, 0.02)',
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--border-subtle)',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '0.9rem' }}>
                              {c.message}
                            </span>
                            <button
                              onClick={() => inspectCommit(c.commit_hash || c.short_hash)}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.25rem',
                                fontSize: '0.75rem',
                                color: 'var(--accent-blue)',
                                padding: '0.15rem 0.45rem',
                                borderRadius: 'var(--radius-sm)',
                                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                              }}
                              title="Click to inspect commit details"
                            >
                              <code>{c.short_hash}</code>
                              <ExternalLink size={11} />
                            </button>
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                            Author: {author} {dateStr && `• ${dateStr}`}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <EmptyState title="Search Symbol or File" description="Inspect chronological commits touching a specific symbol or file." />
              )
            ) : activeTab === 'lastChange' ? (
              lastChangeData ? (
                <div style={{ padding: '1rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <h4 style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
                      {lastChangeData.message || lastChangeData.commit_message || 'Commit Details'}
                    </h4>
                    {(lastChangeData.commit_hash || lastChangeData.short_hash) && (
                      <button
                        onClick={() => inspectCommit(lastChangeData.commit_hash || lastChangeData.short_hash)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                          fontSize: '0.75rem',
                          color: 'var(--accent-blue)',
                          padding: '0.15rem 0.45rem',
                          borderRadius: 'var(--radius-sm)',
                          backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        }}
                      >
                        <code>{lastChangeData.short_hash || (lastChangeData.commit_hash ? lastChangeData.commit_hash.substring(0, 7) : 'HEAD')}</code>
                        <ExternalLink size={11} />
                      </button>
                    )}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.35rem', marginTop: '0.5rem' }}>
                    <div>
                      <strong>Author:</strong> {lastChangeData.author || lastChangeData.author_name || 'Unknown'}
                      {lastChangeData.author_email && ` (${lastChangeData.author_email})`}
                    </div>
                    <div>
                      <strong>Date:</strong> {lastChangeData.date || lastChangeData.authored_date ? new Date(lastChangeData.date || lastChangeData.authored_date || '').toLocaleString() : 'N/A'}
                    </div>
                    {lastChangeData.file && (
                      <div>
                        <strong>File:</strong> <code>{lastChangeData.file}</code>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <EmptyState title="Inspect Last Change" description="Finds the most recent commit affecting the symbol or file." />
              )
            ) : activeTab === 'blame' ? (
              blameData ? (
                <div>
                  <div style={{ marginBottom: '0.75rem', fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Blame for <code>{blameData.symbol || blameData.symbol_or_file || symbolQuery}</code> ({blameData.total_lines} lines):</span>
                    {blameData.primary_contributor && (
                      <Badge variant="cyan">Top Contributor: {blameData.primary_contributor}</Badge>
                    )}
                  </div>
                  <div style={{ maxHeight: '400px', overflowY: 'auto', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>
                      <tbody>
                        {blameData.lines.map((line, idx) => (
                          <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                            <td style={{ padding: '0.2rem 0.5rem', color: 'var(--text-muted)', width: '40px', textAlign: 'right' }}>
                              {line.line_number}
                            </td>
                            <td style={{ padding: '0.2rem 0.5rem', color: 'var(--accent-cyan)', width: '80px' }}>
                              <button
                                onClick={() => inspectCommit(line.commit_hash || line.short_hash)}
                                style={{ color: 'var(--accent-cyan)', textDecoration: 'underline', cursor: 'pointer' }}
                              >
                                {line.short_hash}
                              </button>
                            </td>
                            <td style={{ padding: '0.2rem 0.5rem', color: 'var(--text-secondary)', width: '130px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {line.author || line.author_name || 'Unknown'}
                            </td>
                            <td style={{ padding: '0.2rem 0.5rem', color: 'var(--text-primary)' }}>
                              {line.content ?? line.line_content ?? ''}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <EmptyState title="Blame Analysis" description="Inspect line-level author and commit attribution for a symbol or file." />
              )
            ) : null}
          </div>
        </Card>
      </div>

      {/* Commit Detail Modal */}
      {selectedCommitDetail && (
        <Modal
          isOpen={!!selectedCommitDetail}
          onClose={() => setSelectedCommitDetail(null)}
          title={`Commit: ${selectedCommitDetail.short_hash || selectedCommitDetail.commit_hash.substring(0, 7)}`}
          maxWidth="700px"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
            <div><strong>Message:</strong> {selectedCommitDetail.message}</div>
            <div><strong>Author:</strong> {selectedCommitDetail.author} &lt;{selectedCommitDetail.author_email}&gt;</div>
            <div><strong>Date:</strong> {new Date(selectedCommitDetail.date).toLocaleString()}</div>
            <div><strong>SHA:</strong> <code>{selectedCommitDetail.commit_hash}</code></div>
            <div><strong>Changed Files:</strong> {selectedCommitDetail.files_changed?.length || 0}</div>
            {(selectedCommitDetail.diff_patch || selectedCommitDetail.diff_summary) && (
              <div>
                <strong>Diff Preview:</strong>
                <CodeBlock
                  code={selectedCommitDetail.diff_patch || selectedCommitDetail.diff_summary || ''}
                  language="diff"
                  maxHeight="300px"
                />
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
};
