import React from 'react';
import { AlertCircle, AlertTriangle, Info, ShieldAlert } from 'lucide-react';
import { ReviewFinding } from '../../types/changes';
import { Badge } from '../common/Badge';

export interface FindingCardProps {
  finding: ReviewFinding;
}

export const FindingCard: React.FC<FindingCardProps> = ({ finding }) => {
  const getSeverityConfig = () => {
    switch (finding.severity.toLowerCase()) {
      case 'critical':
        return {
          icon: <ShieldAlert size={18} color="var(--accent-rose)" />,
          badgeVariant: 'danger' as const,
          border: '1px solid rgba(244, 63, 94, 0.3)',
          bg: 'rgba(244, 63, 94, 0.05)',
        };
      case 'high':
        return {
          icon: <AlertCircle size={18} color="var(--accent-rose)" />,
          badgeVariant: 'danger' as const,
          border: '1px solid rgba(244, 63, 94, 0.25)',
          bg: 'rgba(244, 63, 94, 0.04)',
        };
      case 'medium':
        return {
          icon: <AlertTriangle size={18} color="var(--accent-amber)" />,
          badgeVariant: 'warning' as const,
          border: '1px solid rgba(245, 158, 11, 0.25)',
          bg: 'rgba(245, 158, 11, 0.04)',
        };
      case 'low':
      default:
        return {
          icon: <Info size={18} color="var(--accent-blue)" />,
          badgeVariant: 'primary' as const,
          border: '1px solid var(--border-subtle)',
          bg: 'rgba(59, 130, 246, 0.04)',
        };
    }
  };

  const config = getSeverityConfig();

  return (
    <div
      style={{
        padding: '1rem',
        borderRadius: 'var(--radius-md)',
        backgroundColor: config.bg,
        border: config.border,
        display: 'flex',
        flexDirection: 'column',
        gap: '0.6rem',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {config.icon}
          <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
            {finding.category || 'General Finding'}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
          <Badge variant={config.badgeVariant}>{finding.severity}</Badge>
          {finding.confidence && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {Math.round(finding.confidence * 100)}% conf
            </span>
          )}
        </div>
      </div>

      <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
        {finding.description}
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '0.75rem',
          fontSize: '0.785rem',
          color: 'var(--text-muted)',
          backgroundColor: 'rgba(0, 0, 0, 0.2)',
          padding: '0.4rem 0.6rem',
          borderRadius: 'var(--radius-sm)',
        }}
      >
        <span><strong>File:</strong> <code>{finding.file}</code></span>
        {finding.line && <span><strong>Line:</strong> {finding.line}</span>}
        {finding.symbol && <span><strong>Symbol:</strong> <code>{finding.symbol}</code></span>}
      </div>

      {finding.recommendation && (
        <div style={{ fontSize: '0.825rem', color: 'var(--accent-cyan)', marginTop: '0.2rem' }}>
          💡 <strong>Recommendation:</strong> {finding.recommendation}
        </div>
      )}
    </div>
  );
};
