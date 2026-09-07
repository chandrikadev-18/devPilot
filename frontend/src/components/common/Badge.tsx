import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'purple' | 'cyan';
  size?: 'sm' | 'md';
}

export const Badge: React.FC<BadgeProps> = ({ children, variant = 'default', size = 'sm' }) => {
  const getStyles = (): React.CSSProperties => {
    switch (variant) {
      case 'primary':
        return { backgroundColor: 'var(--accent-blue-subtle)', color: '#a5b4fc', border: '1px solid rgba(99, 102, 241, 0.25)' };
      case 'success':
        return { backgroundColor: 'var(--accent-emerald-subtle)', color: '#67e8f9', border: '1px solid rgba(34, 211, 238, 0.25)' };
      case 'warning':
        return { backgroundColor: 'var(--accent-amber-subtle)', color: '#fde047', border: '1px solid rgba(245, 158, 11, 0.25)' };
      case 'danger':
        return { backgroundColor: 'var(--accent-rose-subtle)', color: '#fda4af', border: '1px solid rgba(244, 63, 94, 0.25)' };
      case 'purple':
        return { backgroundColor: 'var(--accent-purple-subtle)', color: '#d8b4fe', border: '1px solid rgba(139, 92, 246, 0.25)' };
      case 'cyan':
        return { backgroundColor: 'var(--accent-cyan-subtle)', color: '#22d3ee', border: '1px solid rgba(6, 182, 212, 0.25)' };
      case 'default':
      default:
        return { backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' };
    }
  };

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem',
        fontWeight: 500,
        borderRadius: 'var(--radius-sm)',
        padding: size === 'sm' ? '0.125rem 0.45rem' : '0.2rem 0.6rem',
        fontSize: size === 'sm' ? '0.725rem' : '0.8rem',
        letterSpacing: '0.02em',
        ...getStyles(),
      }}
    >
      {children}
    </span>
  );
};
