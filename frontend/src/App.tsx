import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ProjectProvider } from './context/ProjectContext';
import { ToastProvider } from './context/ToastContext';
import { AppLayout } from './layouts/AppLayout';
import { AIAgentPage } from './pages/AIAgentPage';
import { ChangesPage } from './pages/ChangesPage';
import { CodeExplorerPage } from './pages/CodeExplorerPage';
import { CodeReviewPage } from './pages/CodeReviewPage';
import { DashboardPage } from './pages/DashboardPage';
import { DependencyGraphPage } from './pages/DependencyGraphPage';
import { GitIntelligencePage } from './pages/GitIntelligencePage';
import { HealthPage } from './pages/HealthPage';
import { OperationsPage } from './pages/OperationsPage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { ProjectNewPage } from './pages/ProjectNewPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { SafeFixPage } from './pages/SafeFixPage';
import { SettingsPage } from './pages/SettingsPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <ToastProvider>
        <ProjectProvider>
          <Routes>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/projects" element={<ProjectsPage />} />
              <Route path="/projects/new" element={<ProjectNewPage />} />
              <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
              <Route path="/projects/:projectId/explorer" element={<CodeExplorerPage />} />
              <Route path="/projects/:projectId/graph" element={<DependencyGraphPage />} />
              <Route path="/projects/:projectId/agent" element={<AIAgentPage />} />
              <Route path="/projects/:projectId/review" element={<CodeReviewPage />} />
              <Route path="/projects/:projectId/changes" element={<ChangesPage />} />
              <Route path="/projects/:projectId/fix" element={<SafeFixPage />} />
              <Route path="/projects/:projectId/git" element={<GitIntelligencePage />} />
              <Route path="/operations" element={<OperationsPage />} />
              <Route path="/health" element={<HealthPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Route>
          </Routes>
        </ProjectProvider>
      </ToastProvider>
    </BrowserRouter>
  );
};
