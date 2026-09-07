import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Activity, ChevronDown, FolderCode, Plus, RefreshCw } from 'lucide-react';
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
        backgroundColor: 'var(--bg-secondary)',
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
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FolderCode size={16} color="var(--accent-blue)" />
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
            Project:
          </span>
        </div>

        {projects.length > 0 ? (
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <select
              value={activeProject?.project_id || ''}
              onChange={(e) => handleProjectChange(e.target.value)}
              style={{
                backgroundColor: 'var(--bg-input)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '0.35rem 2rem 0.35rem 0.75rem',
                color: 'var(--text-primary)',
                fontSize: '0.825rem',
                fontWeight: 500,
                outline: 'none',
                cursor: 'pointer',
                minWidth: '200px',
                appearance: 'none',
                transition: 'border-color 0.15s ease',
              }}
            >
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name} ({p.status})
                </option>
              ))}
            </select>
            <ChevronDown
              size={13}
              style={{
                position: 'absolute',
                right: '0.65rem',
                color: 'var(--text-muted)',
                pointerEvents: 'none',
              }}
            />
          </div>
        ) : (
          <span style={{ fontSize: '0.825rem', color: 'var(--text-muted)' }}>No projects loaded</span>
        )}

        <Button
          variant="secondary"
          size="sm"
          onClick={() => navigate('/projects/new')}
          leftIcon={<Plus size={13} />}
          title="Register new project"
        >
          New Project
        </Button>
      </div>

      {/* Right: Quick Refresh & Health Status Pill */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            refreshProjects();
            fetchHealth();
          }}
          isLoading={isLoading}
          leftIcon={<RefreshCw size={13} />}
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
            padding: '0.25rem 0.65rem',
            borderRadius: 'var(--radius-full)',
            backgroundColor: health?.status === 'ok' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
            border: `1px solid ${health?.status === 'ok' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(245, 158, 11, 0.25)'}`,
            cursor: 'pointer',
            fontSize: '0.75rem',
            fontWeight: 500,
            color: health?.status === 'ok' ? '#34d399' : '#fbbf24',
          }}
        >
          <div
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: health?.status === 'ok' ? '#34d399' : '#fbbf24',
            }}
          />
          <span>{health ? `System ${health.status.toUpperCase()}` : 'Connecting...'}</span>
        </div>
      </div>
    </header>
  );
};
