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
        return { backgroundColor: 'var(--accent-blue-subtle)', color: '#4ade80', border: '1px solid rgba(34, 197, 94, 0.25)' };
      case 'success':
        return { backgroundColor: 'var(--accent-emerald-subtle)', color: '#bef264', border: '1px solid rgba(132, 204, 22, 0.25)' };
      case 'warning':
        return { backgroundColor: 'var(--accent-amber-subtle)', color: '#fde047', border: '1px solid rgba(234, 179, 8, 0.25)' };
      case 'danger':
        return { backgroundColor: 'var(--accent-rose-subtle)', color: '#fda4af', border: '1px solid rgba(244, 63, 94, 0.25)' };
      case 'purple':
        return { backgroundColor: 'var(--accent-purple-subtle)', color: '#d8b4fe', border: '1px solid rgba(168, 85, 247, 0.25)' };
      case 'cyan':
        return { backgroundColor: 'var(--accent-cyan-subtle)', color: '#5eead4', border: '1px solid rgba(20, 184, 166, 0.25)' };
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
