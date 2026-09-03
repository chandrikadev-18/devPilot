import React, { useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Check,
  CheckCircle,
  FileDiff,
  GitPullRequest,
  Play,
  Send,
  ShieldAlert,
  X,
} from 'lucide-react';
import { changesApi } from '../api/changes';
import { projectsApi } from '../api/projects';
import { RiskBadge } from '../components/badges/RiskBadge';
import { StatusBadge } from '../components/badges/StatusBadge';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { CodeBlock } from '../components/common/CodeBlock';
import { EmptyState } from '../components/common/EmptyState';
import { Input } from '../components/common/Input';
import { Spinner } from '../components/common/Spinner';
import { useToast } from '../context/ToastContext';
import { ChangeProposal, PlanChangeResponse } from '../types/changes';

export const ChangesPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<any | null>(null);
  const [requestText, setRequestText] = useState('');
  const [isPlanning, setIsPlanning] = useState(false);
  const [isProposing, setIsProposing] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const [plan, setPlan] = useState<PlanChangeResponse | null>(null);
  const [proposal, setProposal] = useState<ChangeProposal | null>(null);
  const [executionResult, setExecutionResult] = useState<any | null>(null);

  const { showToast } = useToast();

  React.useEffect(() => {
    if (!projectId) return;
    projectsApi.get(projectId).then(setProject).catch(() => {});
  }, [projectId]);

  const handlePlan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!requestText.trim() || !projectId) return;

    try {
      setIsPlanning(true);
      const proj = project || (await projectsApi.get(projectId));
      setProject(proj);
      const res = await changesApi.plan(requestText.trim(), proj.path);
      setPlan(res);
      showToast('Change plan created', 'success');
    } catch (err: any) {
      showToast(err.message || 'Planning failed', 'error');
    } finally {
      setIsPlanning(false);
    }
  };

  const handlePropose = async () => {
    if (!requestText.trim() || !projectId) return;

    try {
      setIsProposing(true);
      const proj = project || (await projectsApi.get(projectId));
      setProject(proj);
      const res = await changesApi.propose(requestText.trim(), proj.path);
      setProposal(res);
      showToast(`Proposal ${res.proposal_id} created`, 'success');
    } catch (err: any) {
      showToast(err.message || 'Propose failed', 'error');
    } finally {
      setIsProposing(false);
    }
  };

  const handleApprove = async () => {
    if (!proposal) return;
    try {
      setActionLoading('approve');
      const res = await changesApi.approveProposal(proposal.proposal_id, project?.path, true);
      setProposal(res);
      showToast('Proposal approved', 'success');
    } catch (err: any) {
      showToast(err.message || 'Approval failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async () => {
    if (!proposal) return;
    try {
      setActionLoading('reject');
      const res = await changesApi.rejectProposal(proposal.proposal_id, 'Rejected by user', project?.path);
      setProposal(res);
      showToast('Proposal rejected', 'info');
    } catch (err: any) {
      showToast(err.message || 'Rejection failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const handleExecute = async () => {
    if (!proposal) return;
    try {
      setActionLoading('execute');
      const res = await changesApi.executeProposal(proposal.proposal_id, project?.path);
      setExecutionResult(res);
      setProposal((prev) => (prev ? { ...prev, status: 'EXECUTED' } : null));
      showToast('Proposal applied and validated successfully', 'success');
    } catch (err: any) {
      showToast(err.message || 'Execution failed', 'error');
    } finally {
      setActionLoading(null);
    }
  };

  const planFiles = plan?.affected_files || plan?.target_files || (plan?.target_file ? [plan.target_file] : []);
  const planSymbols = plan?.affected_symbols || plan?.target_symbols || (plan?.target_symbol ? [plan.target_symbol] : []);
  const riskLevel = typeof plan?.risk === 'string' ? plan.risk : plan?.risk_assessment?.level || 'LOW';

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Change Proposals & Safe Execution</h2>
          <p className="page-subtitle">
            Plan changes, inspect risk, approve proposals, and execute patches safely with automated validation.
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1.5rem', maxWidth: '900px' }}>
        {/* Request Input Form */}
        <Card title="Describe Desired Change" subtitle="Enter natural language specification">
          <form onSubmit={handlePlan} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <Input
              placeholder="e.g. Add input validation to register_project and log structured warning..."
              value={requestText}
              onChange={(e) => setRequestText(e.target.value)}
              required
            />
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <Button
                variant="secondary"
                type="submit"
                isLoading={isPlanning}
                disabled={!requestText.trim()}
                leftIcon={<Play size={15} />}
              >
                Plan Change
              </Button>
              <Button
                variant="primary"
                type="button"
                onClick={handlePropose}
                isLoading={isProposing}
                disabled={!requestText.trim()}
                leftIcon={<GitPullRequest size={15} />}
              >
                Generate Proposal
              </Button>
            </div>
          </form>
        </Card>

        {/* Plan Assessment View */}
        {plan && (
          <Card title="Change Plan & Risk Assessment">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Risk Level:</span>
                <RiskBadge level={riskLevel} score={plan.risk_assessment?.score} />
              </div>

              {(planFiles.length > 0 || planSymbols.length > 0) && (
                <div>
                  <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Target Files & Symbols:
                  </h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.25rem' }}>
                    {planFiles.map((f, idx) => (
                      <Badge key={idx} variant="primary"><code>{f}</code></Badge>
                    ))}
                    {planSymbols.map((s, idx) => (
                      <Badge key={idx} variant="cyan"><code>{s}</code></Badge>
                    ))}
                  </div>
                </div>
              )}

              {plan.reason && (
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  <strong>Reasoning:</strong> {plan.reason}
                </div>
              )}

              {plan.recommended_order && plan.recommended_order.length > 0 && (
                <div>
                  <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
                    Recommended Steps:
                  </h4>
                  <ol style={{ fontSize: '0.85rem', paddingLeft: '1.2rem', marginTop: '0.25rem', color: 'var(--text-primary)' }}>
                    {plan.recommended_order.map((step, idx) => (
                      <li key={idx} style={{ marginBottom: '0.2rem' }}>{step}</li>
                    ))}
                  </ol>
                </div>
              )}

              {plan.plan && (
                <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', lineHeight: 1.5, backgroundColor: 'rgba(0,0,0,0.2)', padding: '0.75rem', borderRadius: 'var(--radius-sm)' }}>
                  {plan.plan}
                </div>
              )}
            </div>
          </Card>
        )}

        {/* Active Proposal View */}
        {proposal && (
          <Card
            title={`Proposal: ${proposal.proposal_id}`}
            subtitle={`Status: ${proposal.status}`}
            action={<StatusBadge status={proposal.status} />}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {proposal.change_summary && (
                <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                  <strong>Summary:</strong> {proposal.change_summary}
                </div>
              )}

              {(proposal.patch || proposal.diff) && (
                <div>
                  <h4 style={{ fontSize: '0.875rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                    Proposed Diff:
                  </h4>
                  <CodeBlock code={proposal.patch || proposal.diff || ''} language="diff" maxHeight="300px" />
                </div>
              )}

              {/* Proposal Actions */}
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
                {(proposal.status === 'PENDING_APPROVAL' || proposal.status === 'PROPOSED') && (
                  <>
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={handleReject}
                      isLoading={actionLoading === 'reject'}
                      leftIcon={<X size={14} />}
                    >
                      Reject
                    </Button>
                    <Button
                      variant="success"
                      size="sm"
                      onClick={handleApprove}
                      isLoading={actionLoading === 'approve'}
                      leftIcon={<Check size={14} />}
                    >
                      Approve Proposal
                    </Button>
                  </>
                )}

                {proposal.status === 'APPROVED' && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleExecute}
                    isLoading={actionLoading === 'execute'}
                    leftIcon={<Play size={14} />}
                  >
                    Apply & Validate Patch
                  </Button>
                )}
              </div>
            </div>
          </Card>
        )}

        {/* Execution Result */}
        {executionResult && (
          <Card title="Execution & Validation Outcome">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
              <CheckCircle size={18} />
              <span>Patch applied and test suite validated successfully!</span>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};
