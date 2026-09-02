import React from 'react';
import { Badge } from '../common/Badge';

export interface RiskBadgeProps {
  level: string;
  score?: number;
}

export const RiskBadge: React.FC<RiskBadgeProps> = ({ level, score }) => {
  const norm = (level || '').toUpperCase();
  const label = score !== undefined ? `${level} (${score}/100)` : level;

  switch (norm) {
    case 'LOW':
      return <Badge variant="success">{label}</Badge>;
    case 'MEDIUM':
      return <Badge variant="warning">{label}</Badge>;
    case 'HIGH':
      return <Badge variant="danger">{label}</Badge>;
    case 'CRITICAL':
      return <Badge variant="danger">{label}</Badge>;
    default:
      return <Badge variant="default">{label}</Badge>;
  }
};
