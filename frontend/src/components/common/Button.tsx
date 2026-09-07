import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'danger' | 'ghost' | 'success';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  className = '',
  disabled,
  ...props
}) => {
  const getVariantStyles = (): React.CSSProperties => {
    switch (variant) {
      case 'primary':
        return {
          backgroundColor: 'var(--accent-blue)',
          color: '#080C0A',
          fontWeight: 600,
          border: '1px solid rgba(255, 255, 255, 0.1)',
          boxShadow: 'var(--shadow-sm)',
        };
      case 'secondary':
        return {
          backgroundColor: 'var(--bg-tertiary)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-subtle)',
        };
      case 'outline':
        return {
          backgroundColor: 'transparent',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-medium)',
        };
      case 'danger':
        return {
          backgroundColor: 'var(--accent-rose)',
          color: '#ffffff',
          fontWeight: 600,
          border: '1px solid rgba(255, 255, 255, 0.1)',
        };
      case 'success':
        return {
          backgroundColor: 'var(--accent-emerald)',
          color: '#080C0A',
          fontWeight: 600,
          border: '1px solid rgba(255, 255, 255, 0.1)',
        };
      case 'ghost':
        return {
          backgroundColor: 'transparent',
          color: 'var(--text-secondary)',
          border: '1px solid transparent',
        };
      default:
        return {};
    }
  };

  const getSizeStyles = (): React.CSSProperties => {
    switch (size) {
      case 'sm':
        return { padding: '0.35rem 0.65rem', fontSize: '0.8rem', borderRadius: 'var(--radius-sm)' };
      case 'lg':
        return { padding: '0.75rem 1.5rem', fontSize: '1rem', borderRadius: 'var(--radius-md)' };
      case 'md':
      default:
        return { padding: '0.5rem 1rem', fontSize: '0.875rem', borderRadius: 'var(--radius-md)' };
    }
  };

  return (
    <button
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.5rem',
        fontWeight: 500,
        transition: 'all 0.15s ease',
        cursor: disabled || isLoading ? 'not-allowed' : 'pointer',
        opacity: disabled || isLoading ? 0.6 : 1,
        ...getVariantStyles(),
        ...getSizeStyles(),
      }}
      disabled={disabled || isLoading}
      className={className}
      {...props}
    >
      {isLoading && (
        <span
          style={{
            display: 'inline-block',
            width: '14px',
            height: '14px',
            border: '2px solid rgba(255,255,255,0.3)',
            borderTopColor: '#ffffff',
            borderRadius: '50%',
            animation: 'spin 0.6s linear infinite',
          }}
        />
      )}
      {!isLoading && leftIcon}
      {children}
      {!isLoading && rightIcon}
    </button>
  );
};
