import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  Bot,
  Compass,
  FolderGit2,
  GitBranch,
  Layers,
  Plus,
  ShieldCheck,
} from 'lucide-react';
import { healthApi } from '../api/health';
import { projectsApi } from '../api/projects';
import { OperationStatusBadge } from '../components/badges/OperationStatusBadge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { Spinner } from '../components/common/Spinner';
import { useProject } from '../context/ProjectContext';
import { DetailedHealthResponse } from '../types/health';
import { Operation } from '../types/projects';

export const DashboardPage: React.FC = () => {
  const { projects, activeProject, isLoading: isProjectsLoading } = useProject();
  const [health, setHealth] = useState<DetailedHealthResponse | null>(null);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [isLoadingOps, setIsLoadingOps] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    healthApi.checkDetails().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (activeProject) {
      setIsLoadingOps(true);
      projectsApi
        .listOperations(activeProject.project_id)
        .then((res) => setOperations(res?.operations || []))
        .catch(() => setOperations([]))
        .finally(() => setIsLoadingOps(false));
    } else {
      setOperations([]);
    }
  }, [activeProject]);


  const activeProjectsCount = projects.filter((p) => p.status === 'ACTIVE').length;

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Developer Intelligence Dashboard</h2>
          <p className="page-subtitle">
            Autonomous codebase exploration, static relationship graphs, and AI-assisted workflows.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => navigate('/projects/new')}
          leftIcon={<Plus size={16} />}
        >
          Add Project
        </Button>
      </div>

      {/* Top Metrics Cards */}
      <div className="grid-cards" style={{ marginBottom: '2rem' }}>
        <Card
          title="Total Projects"
          subtitle="Registered codebases"
          action={<Compass size={20} color="var(--accent-blue)" />}
        >
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            {isProjectsLoading ? <Spinner size="sm" /> : projects.length}
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--accent-emerald)' }}>
            {activeProjectsCount} Active
          </span>
        </Card>

        <Card
          title="System Health"
          subtitle="Subsystem diagnostics"
          action={<FolderGit2 size={20} color="var(--accent-cyan)" />}
        >
          <div style={{ fontSize: '1.25rem', fontWeight: 700, color: health?.status === 'ok' ? 'var(--accent-emerald)' : 'var(--accent-amber)' }}>
            {health ? health.status.toUpperCase() : 'CHECKING...'}
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Git: {health?.git.available ? 'Ready' : 'Unavailable'} | Storage: {health?.storage.available ? 'Mounted' : 'Missing'}
          </span>
        </Card>

        <Card
          title="AI Agent Subsystem"
          subtitle="LLM inference orchestration"
          action={<Bot size={20} color="var(--accent-purple)" />}
        >
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {health?.llm.provider.toUpperCase() || 'GROQ'}
          </div>
          <span style={{ fontSize: '0.8rem', color: health?.llm.api_key_configured ? 'var(--accent-emerald)' : 'var(--accent-amber)' }}>
            {health?.llm.api_key_configured ? '● Key Configured' : '○ Missing API Key'}
          </span>
        </Card>

        <Card
          title="Target Repository"
          subtitle="Current active focus"
          action={<GitBranch size={20} color="var(--accent-emerald)" />}
        >
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {activeProject ? activeProject.name : 'None selected'}
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Branch: {activeProject?.default_branch || 'main'}
          </span>
        </Card>
      </div>

      {/* Quick Launchpad & Recent Operations */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
        <Card title="Intelligence Capabilities" subtitle="Launch tools on active project">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            <Button
              variant="secondary"
              leftIcon={<Layers size={16} />}
              onClick={() => activeProject && navigate(`/projects/${activeProject.project_id}/graph`)}
              disabled={!activeProject}
            >
              Dependency Graph
            </Button>
            <Button
              variant="secondary"
              leftIcon={<Bot size={16} />}
              onClick={() => activeProject && navigate(`/projects/${activeProject.project_id}/agent`)}
              disabled={!activeProject}
            >
              AI Agent Chat
            </Button>
            <Button
              variant="secondary"
              leftIcon={<ShieldCheck size={16} />}
              onClick={() => activeProject && navigate(`/projects/${activeProject.project_id}/review`)}
              disabled={!activeProject}
            >
              Code Review
            </Button>
            <Button
              variant="secondary"
              leftIcon={<GitBranch size={16} />}
              onClick={() => activeProject && navigate(`/projects/${activeProject.project_id}/git`)}
              disabled={!activeProject}
            >
              Git History
            </Button>
          </div>
        </Card>

        <Card
          title="Recent Project Operations"
          subtitle={activeProject ? `Recorded actions for ${activeProject.name}` : 'Select a project to view'}
          action={
            <Button variant="ghost" size="sm" onClick={() => navigate('/operations')}>
              View All
            </Button>
          }
        >
          {isLoadingOps ? (
            <Spinner label="Loading operations..." />
          ) : operations.length === 0 ? (
            <EmptyState
              title="No Operations Recorded"
              description="Run a scan, graph build, or review to record operations."
            />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {operations.slice(0, 5).map((op) => (
                <div
                  key={op.operation_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.6rem 0.8rem',
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: '0.85rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    <Activity size={15} color="var(--accent-blue)" />
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {op.operation_type.toUpperCase()}
                      </div>
                      <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)' }}>
                        {new Date(op.started_at).toLocaleTimeString()}
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
    </div>
  );
};
