import React from 'react';
import { Badge } from '../common/Badge';

export interface OperationStatusBadgeProps {
  status: string;
}

export const OperationStatusBadge: React.FC<OperationStatusBadgeProps> = ({ status }) => {
  const norm = (status || '').toUpperCase();

  switch (norm) {
    case 'SUCCESS':
    case 'COMPLETED':
      return <Badge variant="success">Completed</Badge>;
    case 'RUNNING':
      return <Badge variant="warning">Running</Badge>;
    case 'STARTED':
    case 'PENDING':
      return <Badge variant="cyan">{norm === 'STARTED' ? 'Started' : 'Pending'}</Badge>;
    case 'ROLLED_BACK':
      return <Badge variant="purple">Rolled Back</Badge>;
    case 'FAILED':
      return <Badge variant="danger">Failed</Badge>;
    default:
      return <Badge variant="default">{status}</Badge>;
  }
};
