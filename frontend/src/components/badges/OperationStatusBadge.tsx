import React from 'react';
import { Badge } from '../common/Badge';

export interface OperationStatusBadgeProps {
  status: string;
}

export const OperationStatusBadge: React.FC<OperationStatusBadgeProps> = ({ status }) => {
  const norm = (status || '').toUpperCase();

  switch (norm) {
    case 'COMPLETED':
      return <Badge variant="success">Completed</Badge>;
    case 'RUNNING':
      return <Badge variant="warning">Running</Badge>;
    case 'PENDING':
      return <Badge variant="cyan">Pending</Badge>;
    case 'FAILED':
      return <Badge variant="danger">Failed</Badge>;
    default:
      return <Badge variant="default">{status}</Badge>;
  }
};
