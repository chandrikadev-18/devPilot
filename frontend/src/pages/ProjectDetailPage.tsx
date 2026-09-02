import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Activity,
  ArrowLeft,
  Bot,
  Compass,
  FileCode2,
  GitBranch,
  Layers,
  Play,
  ShieldCheck,
} from 'lucide-react';
import { projectsApi } from '../api/projects';
import { OperationStatusBadge } from '../components/badges/OperationStatusBadge';
import { StatusBadge } from '../components/badges/StatusBadge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { ErrorState } from '../components/common/ErrorState';
import { Spinner } from '../components/common/Spinner';
import { useToast } from '../context/ToastContext';
import { Operation, Project } from '../types/projects';

export const ProjectDetailPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { showToast } = useToast();
  const navigate = useNavigate();

  const loadData = async () => {
    if (!projectId) return;
    try {
      setIsLoading(true);
      setError(null);
      const [projData, opsData] = await Promise.all([
        projectsApi.get(projectId),
        projectsApi.listOperations(projectId).catch(() => ({ operations: [], total: 0 })),
      ]);
      setProject(projData);
      setOperations(opsData.operations);
    } catch (err: any) {
      setError(err.message || 'Failed to load project details');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [projectId]);

  const handleScan = async () => {
    if (!projectId) return;
    try {
      setActionLoading('scan');
      const res = await projectsApi.scan(projectId);
      showToast(`Scan complete: ${res.total_files} files discovered`, 'success');
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Scan failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleBuildGraph = async () => {
    if (!projectId) return;
    try {
      setActionLoading('graph');
      const res = await projectsApi.buildGraph(projectId);
      showToast(`Graph built: ${res.total_nodes} nodes, ${res.total_edges} edges`, 'success');
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Graph build failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  if (isLoading) return <Spinner label="Loading project overview..." />;
  if (error || !project) return <ErrorState message={error || 'Project not found'} onRetry={loadData} />;

  return (
    <div className="page-wrapper">
      <div style={{ marginBottom: '1rem' }}>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/projects')}
          leftIcon={<ArrowLeft size={16} />}
        >
          Back to Projects
        </Button>
      </div>

      {/* Header Overview */}
      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h2 className="page-title">{project.name}</h2>
            <StatusBadge status={project.status} />
          </div>
          <p className="page-subtitle">
            <code>{project.path}</code>
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleScan}
            isLoading={actionLoading === 'scan'}
            leftIcon={<Play size={14} />}
          >
            Scan Files
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleBuildGraph}
            isLoading={actionLoading === 'graph'}
            leftIcon={<Layers size={14} />}
          >
            Build Graph
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate(`/projects/${project.project_id}/review`)}
            leftIcon={<ShieldCheck size={14} />}
          >
            Run Review
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate(`/projects/${project.project_id}/agent`)}
            leftIcon={<Bot size={14} />}
          >
            Launch Agent
          </Button>
        </div>
      </div>

      {/* Metadata cards */}
      <div className="grid-cards" style={{ marginBottom: '2rem' }}>
        <Card title="Repository Info">
          <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
            <div><strong>Default Branch:</strong> {project.default_branch}</div>
            <div><strong>Repository:</strong> {project.repository || 'Local only (Git)'}</div>
            <div><strong>Project ID:</strong> <code>{project.project_id}</code></div>
          </div>
        </Card>

        <Card title="Quick Navigation">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            <Button
              variant="ghost"
              size="sm"
              style={{ justifyContent: 'flex-start' }}
              leftIcon={<FileCode2 size={16} />}
              onClick={() => navigate(`/projects/${project.project_id}/explorer`)}
            >
              Explore Code Files
            </Button>
            <Button
              variant="ghost"
              size="sm"
              style={{ justifyContent: 'flex-start' }}
              leftIcon={<Layers size={16} />}
              onClick={() => navigate(`/projects/${project.project_id}/graph`)}
            >
              Inspect Relationship Graph
            </Button>
            <Button
              variant="ghost"
              size="sm"
              style={{ justifyContent: 'flex-start' }}
              leftIcon={<GitBranch size={16} />}
              onClick={() => navigate(`/projects/${project.project_id}/git`)}
            >
              Git History & Blame
            </Button>
          </div>
        </Card>
      </div>

      {/* Operations History */}
      <Card title="Operation Lifecycle Records" subtitle="Tracked execution for this codebase">
        {operations.length === 0 ? (
          <EmptyState
            title="No Operations Recorded"
            description="Trigger a file scan or build graph to record operational metrics."
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {operations.map((op) => (
              <div
                key={op.operation_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.75rem 1rem',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.875rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <Activity size={16} color="var(--accent-blue)" />
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {op.operation_type.toUpperCase()}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Started: {new Date(op.started_at).toLocaleString()}
                      {op.result?.duration_ms && ` • ${op.result.duration_ms}ms`}
                    </div>
                  </div>
                </div>
                <OperationStatusBadge status={op.status} />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
