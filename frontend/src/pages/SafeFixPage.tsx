import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  CheckCircle2,
  Clock,
  RotateCcw,
  ShieldAlert,
  Wrench,
  XCircle,
  Zap,
} from 'lucide-react';
import { changesApi } from '../api/changes';
import { projectsApi } from '../api/projects';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { CodeBlock } from '../components/common/CodeBlock';
import { Input } from '../components/common/Input';
import { Spinner } from '../components/common/Spinner';
import { useToast } from '../context/ToastContext';

export const SafeFixPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [fixRequest, setFixRequest] = useState('');
  const [maxIterations, setMaxIterations] = useState(3);
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<any | null>(null);

  const { showToast } = useToast();

  const phases = [
    { name: 'Plan & Analysis', desc: 'Identify affected AST symbols and blast radius' },
    { name: 'Change Proposal', desc: 'Generate validated unified diff patch' },
    { name: 'Automated Review', desc: 'Verify safety, security, and rule constraints' },
    { name: 'Patch Application', desc: 'Apply patch to working tree' },
    { name: 'Test Suite Validation', desc: 'Run automated regression test suite' },
    { name: 'Rollback Protection', desc: 'Auto-revert modifications on test failure' },
  ];

  const handleRunFixLoop = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fixRequest.trim() || !projectId) return;

    try {
      setIsRunning(true);
      setResult(null);
      const proj = await projectsApi.get(projectId);
      const res = await changesApi.fixLoop(fixRequest.trim(), maxIterations, proj.path);
      setResult(res);
      const isSuccess = res.status === 'SUCCESS' || res.is_success === true;
      if (isSuccess) {
        showToast('Autonomous Fix Loop completed successfully!', 'success');
      } else {
        showToast(res.message || 'Fix Loop could not converge cleanly. State reverted.', 'warning');
      }
    } catch (err: any) {
      showToast(err.message || 'Fix Loop failed', 'error');
    } finally {
      setIsRunning(false);
    }
  };

  const isSuccess = result && (result.status === 'SUCCESS' || result.is_success === true);
  const isFailed = result && !isSuccess;
  const iterationsCount = result
    ? result.current_iteration || (Array.isArray(result.iterations) ? result.iterations.length : result.iterations) || 1
    : 1;
  const patchDiff = result?.final_result?.diff || (Array.isArray(result?.iterations) && result.iterations.length > 0 ? result.iterations[result.iterations.length - 1].patch : undefined) || result?.diff;

  return (
    <div className="page-wrapper" style={{ maxWidth: '900px' }}>
      <div className="page-header">
        <div>
          <h2 className="page-title">Safe Fix & Repair Loop</h2>
          <p className="page-subtitle">
            Autonomous patch planning, test validation, and zero-risk rollback loop.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {/* Request Input */}
        <Card title="Autonomous Fix Specification" subtitle="Describe the issue, bug, or modification to repair">
          <form onSubmit={handleRunFixLoop} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <Input
              placeholder="e.g. Fix ValueError when empty string is passed to hash_password..."
              value={fixRequest}
              onChange={(e) => setFixRequest(e.target.value)}
              disabled={isRunning}
              required
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Max Iterations:</span>
                <select
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(Number(e.target.value))}
                  disabled={isRunning}
                  style={{
                    backgroundColor: 'var(--bg-input)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '0.25rem 0.5rem',
                    color: 'var(--text-primary)',
                  }}
                >
                  <option value={1}>1 iteration</option>
                  <option value={2}>2 iterations</option>
                  <option value={3}>3 iterations (recommended)</option>
                  <option value={5}>5 iterations</option>
                </select>
              </div>

              <Button
                variant="primary"
                type="submit"
                isLoading={isRunning}
                disabled={!fixRequest.trim()}
                leftIcon={<Wrench size={15} />}
              >
                Start Autonomous Fix Loop
              </Button>
            </div>
          </form>
        </Card>

        {/* Phase Timeline Workflow */}
        <Card title="Safety Guardrails & Phase Pipeline">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {phases.map((phase, idx) => {
              return (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.6rem 0.85rem',
                    backgroundColor: 'rgba(255, 255, 255, 0.02)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div
                      style={{
                        width: '24px',
                        height: '24px',
                        borderRadius: '50%',
                        backgroundColor: 'var(--bg-tertiary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        color: 'var(--text-primary)',
                      }}
                    >
                      {idx + 1}
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                        {phase.name}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{phase.desc}</div>
                    </div>
                  </div>

                  <div>
                    {isRunning ? (
                      <Badge variant="warning">Running</Badge>
                    ) : isSuccess ? (
                      <Badge variant="success">Passed</Badge>
                    ) : isFailed ? (
                      <Badge variant="danger">Reverted</Badge>
                    ) : (
                      <Badge variant="default">Idle</Badge>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Result view */}
        {result && (
          <Card
            title={isSuccess ? 'Fix Loop Succeeded' : 'Fix Loop Failed / Reverted'}
            action={
              isSuccess ? (
                <Badge variant="success">SUCCESS</Badge>
              ) : (
                <Badge variant="danger">FAILED</Badge>
              )
            }
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
              <div><strong>Iterations Run:</strong> {iterationsCount}</div>
              <div><strong>Status:</strong> {result.status || (isSuccess ? 'SUCCESS' : 'FAILED')}</div>
              <div>
                <strong>Summary:</strong> {result.message || result.summary || (isSuccess ? 'All tests passed with patch.' : 'Tests failed or fix did not converge, modifications rolled back safely.')}
              </div>
              {result.errors && result.errors.length > 0 && (
                <div style={{ color: 'var(--accent-rose)' }}>
                  <strong>Errors:</strong> {result.errors.join(', ')}
                </div>
              )}
              {patchDiff && (
                <div>
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem' }}>Patch Diff:</h4>
                  <CodeBlock code={patchDiff} language="diff" />
                </div>
              )}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};
