import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle, Info } from 'lucide-react';

export interface AlertProps {
  type?: 'info' | 'success' | 'warning' | 'error';
  title?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}

export const Alert: React.FC<AlertProps> = ({
  type = 'info',
  title,
  children,
  action,
}) => {
  const getConfig = () => {
    switch (type) {
      case 'success':
        return {
          icon: <CheckCircle size={18} color="var(--accent-emerald)" />,
          bg: 'rgba(16, 185, 129, 0.08)',
          border: 'rgba(16, 185, 129, 0.25)',
        };
      case 'warning':
        return {
          icon: <AlertTriangle size={18} color="var(--accent-amber)" />,
          bg: 'rgba(245, 158, 11, 0.08)',
          border: 'rgba(245, 158, 11, 0.25)',
        };
      case 'error':
        return {
          icon: <AlertCircle size={18} color="var(--accent-rose)" />,
          bg: 'rgba(244, 63, 94, 0.08)',
          border: 'rgba(244, 63, 94, 0.25)',
        };
      case 'info':
      default:
        return {
          icon: <Info size={18} color="var(--accent-blue)" />,
          bg: 'rgba(59, 130, 246, 0.08)',
          border: 'rgba(59, 130, 246, 0.25)',
        };
    }
  };

  const config = getConfig();

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem',
        padding: '0.85rem 1rem',
        borderRadius: 'var(--radius-md)',
        backgroundColor: config.bg,
        border: `1px solid ${config.border}`,
        fontSize: '0.875rem',
      }}
    >
      <div style={{ flexShrink: 0, marginTop: '2px' }}>{config.icon}</div>
      <div style={{ flex: 1 }}>
        {title && (
          <h4 style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
            {title}
          </h4>
        )}
        <div style={{ color: 'var(--text-secondary)', lineHeight: 1.4 }}>{children}</div>
      </div>
      {action && <div>{action}</div>}
    </div>
  );
};
