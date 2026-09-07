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
  Terminal,
  Wrench,
} from 'lucide-react';
import { useProject } from '../context/ProjectContext';

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

export const Sidebar: React.FC = () => {
  const { activeProject } = useProject();
  const projectId = activeProject?.project_id;

  const sections: NavSection[] = [
    {
      title: 'WORKSPACE',
      items: [
        { to: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
        { to: '/tasks', label: 'Task Workspace', icon: <Wrench size={16} /> },
        { to: '/projects', label: 'Projects', icon: <Compass size={16} /> },
      ],
    },
    {
      title: 'CODE INTELLIGENCE',
      items: [
        {
          to: projectId ? `/projects/${projectId}/explorer` : '/projects',
          label: 'Code Explorer',
          icon: <FileCode2 size={16} />,
          disabled: !projectId,
        },
        {
          to: projectId ? `/projects/${projectId}/graph` : '/projects',
          label: 'Dependency Graph',
          icon: <Layers size={16} />,
          disabled: !projectId,
        },
        {
          to: projectId ? `/projects/${projectId}/agent` : '/projects',
          label: 'AI Agent',
          icon: <Bot size={16} />,
          disabled: !projectId,
        },
      ],
    },
    {
      title: 'REVIEW & REPAIR',
      items: [
        {
          to: projectId ? `/projects/${projectId}/review` : '/projects',
          label: 'Code Review',
          icon: <ShieldCheck size={16} />,
          disabled: !projectId,
        },
        {
          to: projectId ? `/projects/${projectId}/changes` : '/projects',
          label: 'Changes',
          icon: <GitPullRequest size={16} />,
          disabled: !projectId,
        },
        {
          to: projectId ? `/projects/${projectId}/fix` : '/projects',
          label: 'Safe Fix Loop',
          icon: <Wrench size={16} />,
          disabled: !projectId,
        },
        {
          to: projectId ? `/projects/${projectId}/git` : '/projects',
          label: 'Git / PR',
          icon: <GitBranch size={16} />,
          disabled: !projectId,
        },
      ],
    },
    {
      title: 'MANAGEMENT',
      items: [
        { to: '/operations', label: 'Operations', icon: <Activity size={16} /> },
        { to: '/health', label: 'System Health', icon: <FolderGit2 size={16} /> },
        { to: '/settings', label: 'Settings', icon: <Settings size={16} /> },
      ],
    },
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
          height: 'var(--header-height)',
          padding: '0 1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-sm)',
              backgroundColor: 'var(--accent-blue)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
            }}
          >
            <Terminal size={16} />
          </div>
          <span style={{ fontSize: '1rem', fontWeight: 700, color: '#ffffff', letterSpacing: '-0.02em' }}>
            DevPilot
          </span>
        </div>
      </div>

      {/* Navigation list */}
      <nav
        style={{
          flex: 1,
          padding: '1rem 0.65rem',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '1.25rem',
        }}
      >
        {sections.map((sec) => (
          <div key={sec.title}>
            <div
              style={{
                fontSize: '0.675rem',
                fontWeight: 600,
                letterSpacing: '0.06em',
                color: 'var(--text-muted)',
                padding: '0 0.6rem 0.4rem 0.6rem',
              }}
            >
              {sec.title}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
              {sec.items.map((item) => (
                <NavLink
                  key={item.to + item.label}
                  to={item.to}
                  end={item.to === '/dashboard' || item.to === '/projects'}
                  style={({ isActive }) => ({
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.65rem',
                    padding: '0.45rem 0.65rem',
                    borderRadius: 'var(--radius-md)',
                    fontSize: '0.825rem',
                    fontWeight: isActive ? 600 : 500,
                    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                    backgroundColor: isActive ? 'var(--bg-tertiary)' : 'transparent',
                    border: `1px solid ${isActive ? 'var(--border-subtle)' : 'transparent'}`,
                    transition: 'all 0.12s ease',
                    opacity: item.disabled ? 0.5 : 1,
                  })}
                >
                  <span style={{ display: 'flex', alignItems: 'center', opacity: 0.9 }}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* Active Project Footer Indicator */}
      {activeProject && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'rgba(0, 0, 0, 0.25)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.65rem',
          }}
        >
          <div
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: 'var(--accent-emerald)',
              flexShrink: 0,
            }}
          />
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontSize: '0.675rem', color: 'var(--text-muted)', fontWeight: 600 }}>
              ACTIVE REPOSITORY
            </div>
            <div
              style={{
                fontSize: '0.8rem',
                fontWeight: 600,
                color: 'var(--text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {activeProject.name}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};
