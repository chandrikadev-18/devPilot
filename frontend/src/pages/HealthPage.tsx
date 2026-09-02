import React, { useEffect, useState } from 'react';
import {
  Activity,
  Bot,
  CheckCircle2,
  Database,
  FolderGit2,
  GitBranch,
  Layers,
  RefreshCw,
  Server,
  XCircle,
} from 'lucide-react';
import { healthApi } from '../api/health';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { Spinner } from '../components/common/Spinner';
import { useToast } from '../context/ToastContext';
import { DetailedHealthResponse } from '../types/health';

export const HealthPage: React.FC = () => {
  const [health, setHealth] = useState<DetailedHealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { showToast } = useToast();

  const loadHealth = async () => {
    try {
      setIsLoading(true);
      const data = await healthApi.checkDetails();
      setHealth(data);
    } catch (err: any) {
      showToast(err.message || 'Failed to connect to backend', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadHealth();
  }, []);

  return (
    <div className="page-wrapper" style={{ maxWidth: '900px' }}>
      <div className="page-header">
        <div>
          <h2 className="page-title">System Diagnostics & Health</h2>
          <p className="page-subtitle">
            Subsystem availability, filesystem storage, Git integration, and LLM orchestration status.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={loadHealth} isLoading={isLoading} leftIcon={<RefreshCw size={14} />}>
          Refresh Diagnostics
        </Button>
      </div>

      {isLoading ? (
        <Spinner label="Probing backend subsystems..." />
      ) : !health ? (
        <Card>
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <XCircle size={40} color="var(--accent-rose)" style={{ margin: '0 auto 1rem auto' }} />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--accent-rose)' }}>
              Backend Unreachable
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginTop: '0.25rem' }}>
              Ensure the DevPilot backend server is running on <code>http://127.0.0.1:8000</code>.
            </p>
          </div>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Overall status banner */}
          <Card padding="md">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <CheckCircle2 size={24} color="var(--accent-emerald)" />
                <div>
                  <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {health.service} Backend is {health.status.toUpperCase()}
                  </h3>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Version {health.version} • Environment: <code>{health.environment}</code>
                  </p>
                </div>
              </div>
              <Badge variant={health.status === 'ok' ? 'success' : 'warning'}>{health.status}</Badge>
            </div>
          </Card>

          {/* Subsystem grid */}
          <div className="grid-cards">
            {/* Git Subsystem */}
            <Card
              title="Git Intelligence Subsystem"
              action={
                <Badge variant={health.git.available ? 'success' : 'danger'}>
                  {health.git.available ? 'Available' : 'Unavailable'}
                </Badge>
              }
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <GitBranch size={16} color="var(--accent-blue)" />
                <span>{health.git.version || 'Git CLI mounted'}</span>
              </div>
            </Card>

            {/* Storage Subsystem */}
            <Card
              title="Project Storage Subsystem"
              action={
                <Badge variant={health.storage.available ? 'success' : 'danger'}>
                  {health.storage.available ? 'Available' : 'Unavailable'}
                </Badge>
              }
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <Database size={16} color="var(--accent-emerald)" />
                <span>Writable: {health.storage.writable ? 'Yes (.devpilot/)' : 'Read-only'}</span>
              </div>
            </Card>

            {/* Graph Subsystem */}
            <Card
              title="Static Dependency Graph"
              action={
                <Badge variant={health.graph.available ? 'success' : 'danger'}>
                  {health.graph.available ? 'Available' : 'Unavailable'}
                </Badge>
              }
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <Layers size={16} color="var(--accent-purple)" />
                <span>Tree-sitter AST & Callgraph Engine</span>
              </div>
            </Card>

            {/* LLM Subsystem */}
            <Card
              title="LLM Orchestration Subsystem"
              action={
                <Badge variant={health.llm.api_key_configured ? 'success' : 'warning'}>
                  {health.llm.api_key_configured ? 'Configured' : 'Missing Key'}
                </Badge>
              }
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <div><strong>Provider:</strong> {health.llm.provider.toUpperCase()}</div>
                <div><strong>Model:</strong> <code>{health.llm.model}</code></div>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
};
