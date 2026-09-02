import React from 'react';

export interface CardProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode;

  subtitle?: string;
  action?: React.ReactNode;
  padding?: 'none' | 'sm' | 'md' | 'lg';
}

export const Card: React.FC<CardProps> = ({
  children,
  title,
  subtitle,
  action,
  padding = 'md',
  className = '',
  style,
  ...props
}) => {
  const getPadding = () => {
    switch (padding) {
      case 'none': return '0';
      case 'sm': return '0.75rem';
      case 'lg': return '1.5rem';
      case 'md':
      default: return '1.25rem';
    }
  };

  return (
    <div
      className={`glass-panel ${className}`}
      style={{
        padding: getPadding(),
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem',
        ...style,
      }}
      {...props}
    >
      {(title || action) && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            borderBottom: subtitle || children ? '1px solid var(--border-subtle)' : 'none',
            paddingBottom: subtitle || children ? '0.75rem' : '0',
            marginBottom: '0.25rem',
          }}
        >
          <div>
            {typeof title === 'string' ? (
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {title}
              </h3>
            ) : (
              title
            )}
            {subtitle && (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                {subtitle}
              </p>
            )}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
};
