import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Calendar,
  Clock,
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
import { EmptyState } from '../components/common/EmptyState';
import { Input } from '../components/common/Input';
import { Spinner } from '../components/common/Spinner';
import { Tabs } from '../components/common/Tabs';
import { useToast } from '../context/ToastContext';
import { GitBlameResponse, GitHistoryResponse, GitLastChangeResponse } from '../types/git';
import { Project } from '../types/projects';

export const GitIntelligencePage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [activeTab, setActiveTab] = useState('history');

  const [historyData, setHistoryData] = useState<GitHistoryResponse | null>(null);
  const [lastChangeData, setLastChangeData] = useState<GitLastChangeResponse | null>(null);
  const [blameData, setBlameData] = useState<GitBlameResponse | null>(null);

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

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbolQuery.trim() || !project) return;

    try {
      setIsQuerying(true);
      const sym = symbolQuery.trim();
      const pPath = project.path;

      if (activeTab === 'history') {
        const res = await gitApi.getHistory(sym, 10, pPath);
        setHistoryData(res);
      } else if (activeTab === 'lastChange') {
        const res = await gitApi.getLastChange(sym, pPath);
        setLastChangeData(res);
      } else if (activeTab === 'blame') {
        const res = await gitApi.getBlame(sym, undefined, undefined, pPath);
        setBlameData(res);
      }
    } catch (err: any) {
      showToast(err.message || 'Git inspection failed', 'error');
    } finally {
      setIsQuerying(false);
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
            onChange={(tab) => setActiveTab(tab)}
          />

          {/* Results view */}
          <div style={{ marginTop: '1.25rem' }}>
            {isQuerying ? (
              <Spinner label="Querying repository history..." />
            ) : activeTab === 'history' ? (
              historyData ? (
                <div>
                  <div style={{ marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>History for <code>{historyData.symbol_or_file}</code>:</span>
                    <Badge variant="primary">{historyData.total_commits} commits</Badge>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {historyData.commits.map((c, idx) => (
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
                          <code style={{ fontSize: '0.75rem', color: 'var(--accent-blue)' }}>{c.short_hash}</code>
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                          Author: {c.author} • {new Date(c.date).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <EmptyState title="Search Symbol or File" description="Inspect chronological commits touching a specific symbol or file." />
              )
            ) : activeTab === 'lastChange' ? (
              lastChangeData ? (
                <div style={{ padding: '1rem', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                  <h4 style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
                    {lastChangeData.commit_message}
                  </h4>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    <div><strong>Author:</strong> {lastChangeData.author_name} ({lastChangeData.author_email})</div>
                    <div><strong>Date:</strong> {new Date(lastChangeData.authored_date).toLocaleString()}</div>
                    <div><strong>Commit:</strong> <code>{lastChangeData.short_hash}</code></div>
                  </div>
                </div>
              ) : (
                <EmptyState title="Inspect Last Change" description="Finds the most recent commit affecting the symbol or file." />
              )
            ) : activeTab === 'blame' ? (
              blameData ? (
                <div>
                  <div style={{ marginBottom: '0.75rem', fontWeight: 600 }}>
                    Blame for <code>{blameData.symbol_or_file}</code> ({blameData.total_lines} lines):
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
                              {line.short_hash}
                            </td>
                            <td style={{ padding: '0.2rem 0.5rem', color: 'var(--text-secondary)', width: '120px' }}>
                              {line.author_name}
                            </td>
                            <td style={{ padding: '0.2rem 0.5rem', color: 'var(--text-primary)' }}>
                              {line.line_content}
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
    </div>
  );
};
