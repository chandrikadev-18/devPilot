import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  Bot,
  Compass,
  FileCode2,
  FolderGit2,
  GitBranch,
  GitPullRequest,
  Layers,
  LayoutDashboard,
  Settings,
  ShieldCheck,
  Wrench,
} from 'lucide-react';
import { useProject } from '../context/ProjectContext';

export const Sidebar: React.FC = () => {
  const { activeProject } = useProject();
  const projectId = activeProject?.project_id;

  const navItems = [
    { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={18} /> },
    { to: '/tasks', label: 'Task Workspace', icon: <Wrench size={18} /> },
    { to: '/projects', label: 'Projects', icon: <Compass size={18} /> },
    {
      to: projectId ? `/projects/${projectId}/explorer` : '/projects',
      label: 'Code Explorer',
      icon: <FileCode2 size={18} />,
      disabled: !projectId,
    },
    {
      to: projectId ? `/projects/${projectId}/graph` : '/projects',
      label: 'Dependency Graph',
      icon: <Layers size={18} />,
      disabled: !projectId,
    },
    {
      to: projectId ? `/projects/${projectId}/agent` : '/projects',
      label: 'AI Agent',
      icon: <Bot size={18} />,
      disabled: !projectId,
    },
    {
      to: projectId ? `/projects/${projectId}/review` : '/projects',
      label: 'Code Review',
      icon: <ShieldCheck size={18} />,
      disabled: !projectId,
    },
    {
      to: projectId ? `/projects/${projectId}/changes` : '/projects',
      label: 'Changes',
      icon: <GitPullRequest size={18} />,
      disabled: !projectId,
    },
    {
      to: projectId ? `/projects/${projectId}/fix` : '/projects',
      label: 'Safe Fix Loop',
      icon: <Wrench size={18} />,
      disabled: !projectId,
    },
    {
      to: projectId ? `/projects/${projectId}/git` : '/projects',
      label: 'Git / PR',
      icon: <GitBranch size={18} />,
      disabled: !projectId,
    },
    { to: '/operations', label: 'Operations', icon: <Activity size={18} /> },
    { to: '/health', label: 'System Health', icon: <FolderGit2 size={18} /> },
    { to: '/settings', label: 'Settings', icon: <Settings size={18} /> },
  ];

  return (
    <aside
      style={{
        width: 'var(--sidebar-width)',
        backgroundColor: 'var(--bg-secondary)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        position: 'sticky',
        top: 0,
        flexShrink: 0,
        zIndex: 20,
      }}
    >
      {/* Brand Header */}
      <div
        style={{
          padding: '1.25rem 1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <div
          style={{
            width: '32px',
            height: '32px',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--accent-blue)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#ffffff',
            boxShadow: 'var(--shadow-glow)',
          }}
        >
          <Bot size={20} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#ffffff', letterSpacing: '-0.02em' }}>
            DevPilot
          </h1>
          <span style={{ fontSize: '0.675rem', color: 'var(--accent-cyan)', fontWeight: 600 }}>
            v3.0 ENTERPRISE
          </span>
        </div>
      </div>

      {/* Navigation list */}
      <nav style={{ flex: 1, padding: '1rem 0.75rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
        {navItems.map((item) => (
          <NavLink
            key={item.to + item.label}
            to={item.to}
            end={item.to === '/dashboard' || item.to === '/projects'}
            style={({ isActive }) => ({
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '0.6rem 0.85rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.875rem',
              fontWeight: isActive ? 600 : 500,
              color: isActive ? '#ffffff' : 'var(--text-secondary)',
              backgroundColor: isActive ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
              borderLeft: isActive ? '3px solid var(--accent-blue)' : '3px solid transparent',
              transition: 'all 0.15s ease',
              opacity: item.disabled ? 0.45 : 1,
              pointerEvents: item.disabled ? 'none' : 'auto',
            })}
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Active Project Footer Indicator */}
      {activeProject && (
        <div
          style={{
            padding: '0.85rem 1.25rem',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'rgba(0, 0, 0, 0.2)',
          }}
        >
          <div style={{ fontSize: '0.725rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>
            Target Codebase
          </div>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {activeProject.name}
          </div>
        </div>
      )}
    </aside>
  );
};
