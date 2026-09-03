import React, { createContext, useContext, useEffect, useState } from 'react';
import { projectsApi } from '../api/projects';
import { Project } from '../types/projects';

interface ProjectContextType {
  projects: Project[];
  activeProject: Project | null;
  isLoading: boolean;
  error: string | null;
  setActiveProject: (project: Project | null) => void;
  selectProjectById: (projectId: string) => void;
  refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextType | undefined>(undefined);

const STORAGE_KEY = 'devpilot_active_project_id';

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProjectState] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const setActiveProject = (proj: Project | null) => {
    setActiveProjectState(proj);
    if (proj) {
      localStorage.setItem(STORAGE_KEY, proj.project_id);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  const refreshProjects = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const res = await projectsApi.list();
      setProjects(res.projects);

      const savedId = localStorage.getItem(STORAGE_KEY);
      if (savedId) {
        const found = res.projects.find((p) => p.project_id === savedId);
        if (found) {
          setActiveProjectState(found);
          return;
        }
      }

      if (!activeProject && res.projects.length > 0) {
        setActiveProjectState(res.projects[0]);
        localStorage.setItem(STORAGE_KEY, res.projects[0].project_id);
      } else if (activeProject) {
        const updated = res.projects.find((p) => p.project_id === activeProject.project_id);
        if (updated) setActiveProjectState(updated);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch projects');
    } finally {
      setIsLoading(false);
    }
  };

  const selectProjectById = (projectId: string) => {
    const found = projects.find((p) => p.project_id === projectId);
    if (found) {
      setActiveProject(found);
    } else if (projectId) {
      projectsApi.get(projectId).then((p) => {
        setActiveProject(p);
      }).catch(() => {});
    }
  };

  useEffect(() => {
    refreshProjects();
  }, []);

  return (
    <ProjectContext.Provider
      value={{
        projects,
        activeProject,
        isLoading,
        error,
        setActiveProject,
        selectProjectById,
        refreshProjects,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
};

export const useProject = () => {
  const context = useContext(ProjectContext);
  if (!context) throw new Error('useProject must be used within ProjectProvider');
  return context;
};
