import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertCircle,
  CheckCircle2,
  FileCode2,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { changesApi } from '../api/changes';
import { projectsApi } from '../api/projects';
import { RiskBadge } from '../components/badges/RiskBadge';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { Spinner } from '../components/common/Spinner';
import { FindingCard } from '../components/review/FindingCard';
import { useToast } from '../context/ToastContext';
import { ReviewChangeResponse } from '../types/changes';
import { Project } from '../types/projects';

export const CodeReviewPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [review, setReview] = useState<ReviewChangeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isReviewing, setIsReviewing] = useState(false);
  const { showToast } = useToast();

  const loadReview = async () => {
    if (!projectId) return;
    try {
      setIsLoading(true);
      const proj = await projectsApi.get(projectId);
      setProject(proj);
      const data = await changesApi.review(undefined, proj.path);
      setReview(data);
    } catch (err: any) {
      showToast(err.message || 'Failed to review code', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadReview();
  }, [projectId]);

  const handleRunReview = async () => {
    if (!project) return;
    try {
      setIsReviewing(true);
      const data = await changesApi.review(undefined, project.path);
      setReview(data);
      showToast('Code review updated', 'success');
    } catch (err: any) {
      showToast(err.message || 'Review execution failed', 'error');
    } finally {
      setIsReviewing(false);
    }
  };

  return (
    <div className="page-wrapper">
      <div className="page-header">
        <div>
          <h2 className="page-title">Working Tree Code Review</h2>
          <p className="page-subtitle">
            Automated AST change detection, risk scoring, and blast radius impact assessment for {project?.name}.
          </p>
        </div>
        <Button
          variant="primary"
          onClick={handleRunReview}
          isLoading={isReviewing}
          leftIcon={<Play size={16} />}
        >
          Run Review
        </Button>
      </div>

      {isLoading ? (
        <Spinner label="Analyzing working tree modifications..." />
      ) : !review ? (
        <EmptyState
          title="No Review Data"
          description="Click 'Run Review' to analyze working tree changes."
        />
      ) : review.is_clean ? (
        <Card>
          <div style={{ textAlign: 'center', padding: '2rem 1rem' }}>
            <CheckCircle2 size={42} color="var(--accent-emerald)" style={{ margin: '0 auto 1rem auto' }} />
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.4rem' }}>
              Working Tree is Clean
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              No modified or uncommitted local changes detected in <code>{project?.path}</code>.
            </p>
          </div>
        </Card>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Top Risk & Blast Radius Cards */}
          <div className="grid-cards">
            <Card title="Risk Evaluation" subtitle="Heuristic risk score">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.25rem' }}>
                <RiskBadge level={review.risk?.level || 'LOW'} score={review.risk?.score} />
              </div>
              {review.risk?.reasons && review.risk.reasons.length > 0 && (
                <ul style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', paddingLeft: '1.2rem', marginTop: '0.5rem' }}>
                  {review.risk.reasons.map((r, idx) => (
                    <li key={idx}>{r}</li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Impact & Blast Radius" subtitle="Static dependency callgraph">
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                {review.impact?.total_affected_symbols ?? 0} Affected Symbols
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                Direct Callers: {review.impact?.direct.length ?? 0} | Impacted Files: {review.impact?.files.length ?? 0}
              </div>
            </Card>

            <Card title="Changed Files" subtitle="Local modifications">
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                {review.changed_files?.length ?? 0} Files
              </div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                Altered Symbols: {review.changed_symbols?.length ?? 0}
              </div>
            </Card>
          </div>

          {/* Review Narrative Summary */}
          {review.summary && (
            <Card title="Review Summary" subtitle="Working tree change assessment">
              <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                {review.summary}
              </p>
            </Card>
          )}

          {/* Review Notes / Findings */}
          {review.review_notes && review.review_notes.length > 0 && (
            <Card title={`Review Notes (${review.review_notes.length})`} subtitle="Actionable notices & constraints">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {review.review_notes.map((note, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '0.5rem 0.75rem',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'rgba(255, 255, 255, 0.02)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '0.85rem',
                      color: 'var(--text-secondary)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <AlertCircle size={14} color="var(--accent-amber)" />
                    <span>{note}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Changed Symbols Breakdown */}
          {review.changed_symbols && review.changed_symbols.length > 0 && (
            <Card title="Altered Code Symbols" subtitle="Syntactic units detected by Tree-sitter">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {review.changed_symbols.map((sym, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '0.4rem 0.65rem',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'rgba(255, 255, 255, 0.03)',
                      border: '1px solid var(--border-subtle)',
                      fontSize: '0.825rem',
                    }}
                  >
                    <code style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{sym.name}</code>
                    <span style={{ fontSize: '0.725rem', color: 'var(--accent-cyan)', marginLeft: '0.4rem' }}>
                      ({sym.change_type})
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Review Findings if structured */}
          {review.findings && review.findings.length > 0 && (
            <Card title={`Review Findings (${review.findings.length})`} subtitle="Actionable code review notices">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {review.findings.map((f, idx) => (
                  <FindingCard key={idx} finding={f} />
                ))}
              </div>
            </Card>
          )}

          {/* Detailed Test Recommendations */}
          {review.test_recommendations && review.test_recommendations.length > 0 && (
            <Card title={`Recommended Tests (${review.test_recommendations.length})`} subtitle="Targeted tests based on altered symbols">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {review.test_recommendations.map((t, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: '0.6rem 0.85rem',
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'rgba(59, 130, 246, 0.04)',
                      border: '1px solid rgba(59, 130, 246, 0.2)',
                      fontSize: '0.85rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.2rem' }}>
                      <code style={{ color: '#93c5fd', fontWeight: 600 }}>{t.test_target}</code>
                      {t.symbol_name && <span style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)' }}>for {t.symbol_name}</span>}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{t.reason}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Fallback Simple Recommended Tests */}
          {(!review.test_recommendations || review.test_recommendations.length === 0) &&
            review.recommended_tests &&
            review.recommended_tests.length > 0 && (
              <Card title="Recommended Validation Tests" subtitle="Targeted tests based on altered symbols">
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  {review.recommended_tests.map((test, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '0.5rem 0.75rem',
                        borderRadius: 'var(--radius-sm)',
                        backgroundColor: 'rgba(59, 130, 246, 0.05)',
                        border: '1px solid rgba(59, 130, 246, 0.2)',
                        fontSize: '0.85rem',
                        color: '#93c5fd',
                      }}
                    >
                      <code>{test}</code>
                    </div>
                  ))}
                </div>
              </Card>
            )}
        </div>
      )}
    </div>
  );
};
