import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ExternalLink,
  Layers,
  Play,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { projectsApi } from '../api/projects';
import { StatusBadge } from '../components/badges/StatusBadge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { Input } from '../components/common/Input';
import { Spinner } from '../components/common/Spinner';
import { Table } from '../components/common/Table';
import { useProject } from '../context/ProjectContext';
import { useToast } from '../context/ToastContext';
import { Project } from '../types/projects';

export const ProjectsPage: React.FC = () => {
  const { projects, isLoading, refreshProjects, selectProjectById } = useProject();
  const [searchTerm, setSearchTerm] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const filteredProjects = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.path.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (p.repository && p.repository.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  const handleScan = async (p: Project, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setActionLoading(`scan-${p.project_id}`);
      const res = await projectsApi.scan(p.project_id);
      showToast(`Scanned ${res.total_files} files in ${p.name}`, 'success');
      refreshProjects();
    } catch (err: any) {
      showToast(err.message || 'Scan failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleBuildGraph = async (p: Project, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      setActionLoading(`graph-${p.project_id}`);
      const res = await projectsApi.buildGraph(p.project_id);
      showToast(`Built graph: ${res.total_nodes} nodes, ${res.total_edges} edges`, 'success');
      refreshProjects();
    } catch (err: any) {
      showToast(err.message || 'Graph build failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReview = (p: Project, e: React.MouseEvent) => {
    e.stopPropagation();
    selectProjectById(p.project_id);
    navigate(`/projects/${p.project_id}/review`);
  };

  const handleDelete = async (p: Project, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`Are you sure you want to delete ${p.name}?`)) return;
    try {
      await projectsApi.delete(p.project_id);
      showToast(`Project ${p.name} deleted`, 'info');
      refreshProjects();
    } catch (err: any) {
      showToast(err.message || 'Delete failed', 'error');
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Project Management</h2>
          <p className="page-subtitle">
            Register and manage local codebases, repositories, and dependency indices.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => navigate('/projects/new')}
          leftIcon={<Plus size={16} />}
        >
          Register Project
        </Button>
      </div>

      <Card padding="md">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', marginBottom: '1rem' }}>
          <div style={{ maxWidth: '350px', width: '100%' }}>
            <Input
              placeholder="Search by name, path, or repo..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              leftIcon={<Search size={16} />}
            />
          </div>
        </div>

        {isLoading ? (
          <Spinner label="Loading registered projects..." />
        ) : filteredProjects.length === 0 ? (
          <EmptyState
            title="No Projects Found"
            description={
              searchTerm
                ? 'No projects match your search query.'
                : 'No projects registered yet. Click "Register Project" to get started.'
            }
            action={
              !searchTerm && (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => navigate('/projects/new')}
                  leftIcon={<Plus size={14} />}
                >
                  Add Your First Project
                </Button>
              )
            }
          />
        ) : (
          <Table<Project>
            keyExtractor={(p) => p.project_id}
            onRowClick={(p) => {
              selectProjectById(p.project_id);
              navigate(`/projects/${p.project_id}`);
            }}
            columns={[
              {
                header: 'Project Name',
                accessor: (p) => (
                  <div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{p.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      <code>{p.project_id}</code>
                    </div>
                  </div>
                ),
              },
              {
                header: 'Local Path',
                accessor: (p) => (
                  <code style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)' }}>{p.path}</code>
                ),
              },
              {
                header: 'Branch / Repo',
                accessor: (p) => (
                  <div style={{ fontSize: '0.8rem' }}>
                    <span style={{ color: 'var(--text-primary)' }}>{p.default_branch}</span>
                    {p.repository && (
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.725rem' }}>{p.repository}</div>
                    )}
                  </div>
                ),
              },
              {
                header: 'Status',
                accessor: (p) => <StatusBadge status={p.status} />,
                width: '110px',
              },
              {
                header: 'Actions',
                accessor: (p) => (
                  <div style={{ display: 'flex', gap: '0.4rem' }} onClick={(e) => e.stopPropagation()}>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={(e) => handleScan(p, e)}
                      isLoading={actionLoading === `scan-${p.project_id}`}
                      title="Scan codebase files"
                    >
                      <Play size={13} /> Scan
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={(e) => handleBuildGraph(p, e)}
                      isLoading={actionLoading === `graph-${p.project_id}`}
                      title="Build static dependency graph"
                    >
                      <Layers size={13} /> Graph
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={(e) => handleReview(p, e)}
                      title="Review working tree changes"
                    >
                      <ShieldCheck size={13} /> Review
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => handleDelete(p, e)}
                      title="Delete project registration"
                    >
                      <Trash2 size={13} color="var(--accent-rose)" />
                    </Button>
                  </div>
                ),
                width: '280px',
              },
            ]}
            data={filteredProjects}
          />
        )}
      </Card>
    </div>
  );
};
