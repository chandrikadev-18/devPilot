import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, FolderPlus } from 'lucide-react';
import { projectsApi } from '../api/projects';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { Input } from '../components/common/Input';
import { useProject } from '../context/ProjectContext';
import { useToast } from '../context/ToastContext';

export const ProjectNewPage: React.FC = () => {
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [repository, setRepository] = useState('');
  const [defaultBranch, setDefaultBranch] = useState('main');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { refreshProjects, selectProjectById } = useProject();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!path.trim()) {
      setError('Project filesystem path is required.');
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      const created = await projectsApi.create({
        name: name.trim() || undefined,
        path: path.trim(),
        repository: repository.trim() || undefined,
        default_branch: defaultBranch.trim() || 'main',
      });

      showToast(`Registered project: ${created.name}`, 'success');
      await refreshProjects();
      selectProjectById(created.project_id);
      navigate(`/projects/${created.project_id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to create project');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="page-wrapper" style={{ maxWidth: '650px' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/projects')}
          leftIcon={<ArrowLeft size={16} />}
        >
          Back to Projects
        </Button>
      </div>

      <Card
        title="Register New Codebase"
        subtitle="Connect a local directory to DevPilot's intelligence engine"
      >
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <Input
            label="Project Name (Optional)"
            placeholder="e.g. My Backend Service"
            helperText="If omitted, DevPilot will infer the name from the directory."
            value={name}
            onChange={(e) => setName(e.target.value)}
          />

          <Input
            label="Local Filesystem Path *"
            placeholder="e.g. d:\Projects\my-app or /home/user/my-app"
            helperText="Must be an existing accessible directory on the server."
            value={path}
            onChange={(e) => setPath(e.target.value)}
            required
          />

          <Input
            label="Repository URL (Optional)"
            placeholder="e.g. https://github.com/org/repo"
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
          />

          <Input
            label="Default Branch"
            placeholder="main"
            value={defaultBranch}
            onChange={(e) => setDefaultBranch(e.target.value)}
          />

          {error && (
            <div
              style={{
                padding: '0.75rem',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'rgba(244, 63, 94, 0.1)',
                border: '1px solid var(--accent-rose)',
                color: 'var(--accent-rose)',
                fontSize: '0.85rem',
              }}
            >
              {error}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '0.5rem' }}>
            <Button variant="outline" type="button" onClick={() => navigate('/projects')}>
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              isLoading={isSubmitting}
              leftIcon={<FolderPlus size={16} />}
            >
              Register Codebase
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};
