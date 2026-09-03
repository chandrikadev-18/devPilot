import React, { useEffect, useState } from 'react';
import { Activity, Filter, RefreshCw } from 'lucide-react';
import { projectsApi } from '../api/projects';
import { OperationStatusBadge } from '../components/badges/OperationStatusBadge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { CodeBlock } from '../components/common/CodeBlock';
import { EmptyState } from '../components/common/EmptyState';
import { Modal } from '../components/common/Modal';
import { Spinner } from '../components/common/Spinner';
import { Table } from '../components/common/Table';
import { useProject } from '../context/ProjectContext';
import { useToast } from '../context/ToastContext';
import { Operation } from '../types/projects';

export const OperationsPage: React.FC = () => {
  const { activeProject } = useProject();
  const [operations, setOperations] = useState<Operation[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [selectedOp, setSelectedOp] = useState<Operation | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const { showToast } = useToast();

  const loadOperations = async () => {
    if (!activeProject) {
      setIsLoading(false);
      return;
    }
    try {
      setIsLoading(true);
      const filter = statusFilter === 'ALL' ? undefined : statusFilter;
      const res = await projectsApi.listOperations(activeProject.project_id, filter);
      setOperations(res.operations);
    } catch (err: any) {
      showToast(err.message || 'Failed to load operations', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadOperations();
  }, [activeProject, statusFilter]);

  const filteredOps = operations.filter((op) => {
    if (statusFilter === 'ALL') return true;
    return op.status.toUpperCase() === statusFilter.toUpperCase();
  });

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Operation Records & Telemetry</h2>
          <p className="page-subtitle">
            Inspection logs for scans, dependency graph builds, reviews, and autonomous agent queries.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={loadOperations}
          isLoading={isLoading}
          leftIcon={<RefreshCw size={14} />}
        >
          Refresh
        </Button>
      </div>

      <Card padding="md">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Filter size={15} color="var(--text-muted)" />
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Status:</span>
            {['ALL', 'SUCCESS', 'RUNNING', 'FAILED', 'PENDING'].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                style={{
                  padding: '0.25rem 0.6rem',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.775rem',
                  fontWeight: 600,
                  backgroundColor: statusFilter === st ? 'var(--accent-blue)' : 'rgba(255, 255, 255, 0.04)',
                  color: statusFilter === st ? '#ffffff' : 'var(--text-secondary)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                {st}
              </button>
            ))}
          </div>

          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Showing {filteredOps.length} operations
          </span>
        </div>

        {!activeProject ? (
          <EmptyState
            title="No Active Project Selected"
            description="Select a project from the top header to inspect recorded operations."
          />
        ) : isLoading ? (
          <Spinner label="Loading project operation logs..." />
        ) : filteredOps.length === 0 ? (
          <EmptyState
            title="No Operations Recorded"
            description={`No operations matching "${statusFilter}" have been recorded for ${activeProject.name}.`}
          />
        ) : (
          <Table<Operation>
            keyExtractor={(op) => op.operation_id}
            onRowClick={(op) => setSelectedOp(op)}
            columns={[
              {
                header: 'Operation Type',
                accessor: (op) => (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Activity size={15} color="var(--accent-blue)" />
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {op.operation_type.toUpperCase()}
                    </span>
                  </div>
                ),
              },
              {
                header: 'Operation ID',
                accessor: (op) => (
                  <code style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {op.operation_id}
                  </code>
                ),
              },
              {
                header: 'Status',
                accessor: (op) => <OperationStatusBadge status={op.status} />,
                width: '120px',
              },
              {
                header: 'Started At',
                accessor: (op) => (
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {new Date(op.started_at).toLocaleString()}
                  </span>
                ),
              },
              {
                header: 'Duration',
                accessor: (op) => (
                  <span style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)' }}>
                    {op.result?.duration_ms ? `${op.result.duration_ms} ms` : '—'}
                  </span>
                ),
                width: '100px',
              },
            ]}
            data={filteredOps}
          />
        )}
      </Card>

      {/* Operation Details Modal */}
      {selectedOp && (
        <Modal
          isOpen={!!selectedOp}
          onClose={() => setSelectedOp(null)}
          title={`Operation: ${selectedOp.operation_type.toUpperCase()}`}
          maxWidth="700px"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
            <div><strong>Operation ID:</strong> <code>{selectedOp.operation_id}</code></div>
            <div><strong>Status:</strong> <OperationStatusBadge status={selectedOp.status} /></div>
            <div><strong>Started:</strong> {new Date(selectedOp.started_at).toLocaleString()}</div>
            {selectedOp.completed_at && (
              <div><strong>Completed:</strong> {new Date(selectedOp.completed_at).toLocaleString()}</div>
            )}
            {selectedOp.error && (
              <div style={{ color: 'var(--accent-rose)' }}>
                <strong>Error:</strong> {selectedOp.error}
              </div>
            )}
            {selectedOp.result && (
              <div>
                <strong>Result Payload:</strong>
                <CodeBlock code={JSON.stringify(selectedOp.result, null, 2)} language="json" maxHeight="350px" />
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
};
