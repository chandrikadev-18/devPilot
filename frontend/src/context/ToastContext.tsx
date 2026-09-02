import React, { createContext, useContext, useState } from 'react';
import { AlertCircle, CheckCircle, Info, X } from 'lucide-react';

export interface Toast {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  message: string;
}

interface ToastContextType {
  toasts: Toast[];
  showToast: (message: string, type?: Toast['type']) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = (message: string, type: Toast['type'] = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => {
      removeToast(id);
    }, 4500);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ toasts, showToast, removeToast }}>
      {children}
      <div
        style={{
          position: 'fixed',
          bottom: '1.5rem',
          right: '1.5rem',
          zIndex: 100,
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
          maxWidth: '380px',
        }}
      >
        {toasts.map((toast) => {
          const getBg = () => {
            switch (toast.type) {
              case 'success': return 'var(--accent-emerald)';
              case 'error': return 'var(--accent-rose)';
              case 'warning': return 'var(--accent-amber)';
              default: return 'var(--accent-blue)';
            }
          };
          return (
            <div
              key={toast.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.65rem',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-secondary)',
                border: `1px solid ${getBg()}`,
                color: 'var(--text-primary)',
                boxShadow: 'var(--shadow-lg)',
                fontSize: '0.875rem',
              }}
            >
              {toast.type === 'success' && <CheckCircle size={16} color="var(--accent-emerald)" />}
              {toast.type === 'error' && <AlertCircle size={16} color="var(--accent-rose)" />}
              {toast.type === 'warning' && <AlertCircle size={16} color="var(--accent-amber)" />}
              {toast.type === 'info' && <Info size={16} color="var(--accent-blue)" />}
              <span style={{ flex: 1 }}>{toast.message}</span>
              <button onClick={() => removeToast(toast.id)} style={{ color: 'var(--text-muted)' }}>
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used within ToastProvider');
  return context;
};
