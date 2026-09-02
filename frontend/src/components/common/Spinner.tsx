import React from 'react';

export interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

export const Spinner: React.FC<SpinnerProps> = ({ size = 'md', label }) => {
  const getDimensions = () => {
    switch (size) {
      case 'sm': return '16px';
      case 'lg': return '36px';
      case 'md':
      default: return '24px';
    }
  };

  const dim = getDimensions();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', padding: '1rem' }}>
      <div
        style={{
          width: dim,
          height: dim,
          border: '3px solid rgba(59, 130, 246, 0.2)',
          borderTopColor: 'var(--accent-blue)',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }}
      />
      {label && <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{label}</span>}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};
