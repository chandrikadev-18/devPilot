import React from 'react';
import { Badge } from '../common/Badge';

export interface StatusBadgeProps {
  status: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const norm = (status || '').toUpperCase();

  switch (norm) {
    case 'ACTIVE':
    case 'COMPLETED':
    case 'SUCCESS':
    case 'APPROVED':
    case 'OK':
      return <Badge variant="success">{status}</Badge>;
    case 'RUNNING':
    case 'PENDING':
    case 'PROPOSED':
    case 'DEGRADED':
      return <Badge variant="warning">{status}</Badge>;
    case 'ERROR':
    case 'FAILED':
    case 'REJECTED':
      return <Badge variant="danger">{status}</Badge>;
    case 'ARCHIVED':
      return <Badge variant="default">{status}</Badge>;
    default:
      return <Badge variant="primary">{status}</Badge>;
  }
};
