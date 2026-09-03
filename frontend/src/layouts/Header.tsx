import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Activity, FolderCode, Plus, RefreshCw } from 'lucide-react';
import { healthApi } from '../api/health';
import { Button } from '../components/common/Button';
import { useProject } from '../context/ProjectContext';
import { DetailedHealthResponse } from '../types/health';

export const Header: React.FC = () => {
  const { projects, activeProject, selectProjectById, refreshProjects, isLoading } = useProject();
  const [health, setHealth] = useState<DetailedHealthResponse | null>(null);
  const navigate = useNavigate();
  const location = useLocation();

  const handleProjectChange = (newProjectId: string) => {
    selectProjectById(newProjectId);
    const match = location.pathname.match(/^\/projects\/([^\/]+)(\/.*)?$/);
    if (match) {
      const subpath = match[2] || '';
      navigate(`/projects/${newProjectId}${subpath}`);
    }
  };

  const fetchHealth = async () => {
    try {
      const data = await healthApi.checkDetails();
      setHealth(data);
    } catch {
      setHealth(null);
    }
  };

  useEffect(() => {
    fetchHealth();
    const timer = setInterval(fetchHealth, 30000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header
      style={{
        height: 'var(--header-height)',
        backgroundColor: 'rgba(15, 23, 42, 0.75)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 2rem',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      {/* Left: Project Selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FolderCode size={18} color="var(--accent-blue)" />
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
            Active Project:
          </span>
        </div>

        {projects.length > 0 ? (
          <select
            value={activeProject?.project_id || ''}
            onChange={(e) => handleProjectChange(e.target.value)}
            style={{
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '0.4rem 0.75rem',
              color: 'var(--text-primary)',
              fontSize: '0.875rem',
              outline: 'none',
              cursor: 'pointer',
              minWidth: '180px',
            }}
          >
            {projects.map((p) => (
              <option key={p.project_id} value={p.project_id}>
                {p.name} ({p.status})
              </option>
            ))}
          </select>
        ) : (
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No projects loaded</span>
        )}

        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/projects/new')}
          leftIcon={<Plus size={14} />}
          title="Register new project"
        >
          New
        </Button>
      </div>

      {/* Right: Quick Refresh & Health Status Pill */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            refreshProjects();
            fetchHealth();
          }}
          isLoading={isLoading}
          leftIcon={<RefreshCw size={14} />}
          title="Refresh projects & health status"
        >
          Sync
        </Button>

        {/* Subsystem Health Indicator */}
        <div
          onClick={() => navigate('/health')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.35rem 0.75rem',
            borderRadius: 'var(--radius-full)',
            backgroundColor: health?.status === 'ok' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)',
            border: `1px solid ${health?.status === 'ok' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
            cursor: 'pointer',
            fontSize: '0.775rem',
            fontWeight: 600,
            color: health?.status === 'ok' ? '#34d399' : '#fbbf24',
          }}
        >
          <Activity size={13} />
          <span>{health ? `Backend ${health.status.toUpperCase()}` : 'Connecting...'}</span>
        </div>
      </div>
    </header>
  );
};
