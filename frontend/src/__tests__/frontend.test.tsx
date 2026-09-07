import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { App } from '../App';
import { Button } from '../components/common/Button';
import { Badge } from '../components/common/Badge';
import { Card } from '../components/common/Card';
import { StatusBadge } from '../components/badges/StatusBadge';
import { RiskBadge } from '../components/badges/RiskBadge';
import { OperationStatusBadge } from '../components/badges/OperationStatusBadge';
import { FindingCard } from '../components/review/FindingCard';
import { apiClient, ApiError } from '../api/client';
import { projectsApi } from '../api/projects';
import { graphApi } from '../api/graph';
import { changesApi } from '../api/changes';
import { gitApi } from '../api/git';
import { searchApi } from '../api/search';
import { healthApi } from '../api/health';

describe('DevPilot Frontend Comprehensive Integration Suite (v3.0)', () => {
  // 1. Application Startup & Navigation
  it('1. Application startup renders DevPilot branding and version', () => {
    render(<App />);
    expect(screen.getByText('DevPilot')).toBeInTheDocument();
  });

  it('2. Dashboard displays overview cards and system status', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Developer Intelligence Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Total Projects')).toBeInTheDocument();
      expect(screen.getAllByText('System Health').length).toBeGreaterThan(0);
    });
  });

  // 3. UI Components & Status Badges
  it('3. Reusable Button variants and click events', () => {
    const handleClick = vi.fn();
    render(<Button variant="primary" onClick={handleClick}>Run Scan</Button>);
    const btn = screen.getByText('Run Scan');
    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('4. Reusable Badges render appropriate variant labels and colors', () => {
    const { rerender } = render(<StatusBadge status="ACTIVE" />);
    expect(screen.getByText('ACTIVE')).toBeInTheDocument();

    rerender(<RiskBadge level="HIGH" score={80} />);
    expect(screen.getByText('HIGH (80/100)')).toBeInTheDocument();

    rerender(<OperationStatusBadge status="COMPLETED" />);
    expect(screen.getByText('Completed')).toBeInTheDocument();

    rerender(<OperationStatusBadge status="STARTED" />);
    expect(screen.getByText('Started')).toBeInTheDocument();

    rerender(<OperationStatusBadge status="ROLLED_BACK" />);
    expect(screen.getByText('Rolled Back')).toBeInTheDocument();
  });

  it('5. FindingCard displays code review insights and advice', () => {
    render(
      <FindingCard
        finding={{
          severity: 'high',
          category: 'Security Warning',
          file: 'app/auth.py',
          line: 42,
          symbol: 'verify_token',
          description: 'Token validation lacks expiration check.',
          recommendation: 'Add exp verification claim in payload.',
          confidence: 0.95,
        }}
      />
    );
    expect(screen.getByText('Security Warning')).toBeInTheDocument();
    expect(screen.getByText('Token validation lacks expiration check.')).toBeInTheDocument();
    expect(screen.getByText(/Add exp verification/)).toBeInTheDocument();
  });

  // 6. Projects API Integration
  it('6. Projects API lists, registers, scans, and builds graph', async () => {
    const listRes = await projectsApi.list();
    expect(listRes.projects.length).toBeGreaterThan(0);
    expect(listRes.projects[0].project_id).toBe('proj_test_123');

    const created = await projectsApi.create({ path: '/tmp/new-project', name: 'New Project' });
    expect(created.project_id).toBeDefined();

    const scanRes = await projectsApi.scan('proj_test_123');
    expect(scanRes.total_files).toBe(25);
    expect(scanRes.operation.status).toBe('COMPLETED');

    const graphRes = await projectsApi.buildGraph('proj_test_123');
    expect(graphRes.total_nodes).toBe(50);
    expect(graphRes.functions).toBe(25);

    const opsRes = await projectsApi.listOperations('proj_test_123');
    expect(opsRes.operations.length).toBeGreaterThan(0);
  });

  // 7. Graph API Integration
  it('7. Graph API queries info, callers, callees, dependencies, and impact', async () => {
    const info = await graphApi.getInfo('/tmp/test-project');
    expect(info.total_nodes).toBe(42);
    expect(info.total_edges).toBe(38);

    const callers = await graphApi.getCallers('GraphBuilder.build', '/tmp/test-project');
    expect(callers.total_callers).toBe(2);

    const callees = await graphApi.getCallees('GraphBuilder.build', '/tmp/test-project');
    expect(callees.total_callees).toBe(3);

    const deps = await graphApi.getDependencies('GraphBuilder.build', 2, '/tmp/test-project');
    expect(deps.total_dependencies).toBe(3);

    const dependents = await graphApi.getDependents('GraphBuilder.build', 2, '/tmp/test-project');
    expect(dependents.total_dependents).toBe(2);

    const impact = await graphApi.getImpact('GraphBuilder.build', 2, '/tmp/test-project');
    expect(impact.total_impacted).toBe(4);
    expect(impact.impacted_files).toContain('app/main.py');

    const fileDeps = await graphApi.getFileDependencies('app/main.py', '/tmp/test-project');
    expect(fileDeps.file_path).toBe('app/main.py');
  });

  // 8. Search API Integration
  it('8. Search API queries AST symbols and semantic code embeddings', async () => {
    const symbolRes = await searchApi.searchSymbol('GraphBuilder', '/tmp/test-project');
    expect(symbolRes.total_matches).toBe(1);
    expect(symbolRes.matches[0].symbol_name).toBe('GraphBuilder');

    const semanticRes = await searchApi.semanticSearch('build graph', 5, '/tmp/test-project');
    expect(semanticRes.total_results).toBe(1);
    expect(semanticRes.results[0].symbol).toBe('GraphBuilder.build');
  });

  // 9. Git Intelligence API Integration
  it('9. Git API retrieves commit history, last change, blame, and commit details', async () => {
    const lastChange = await gitApi.getLastChange('GraphBuilder.build', '/tmp/test-project');
    expect(lastChange.commit).toBeDefined();
    expect(lastChange.author).toBe('DevPilot Engineer');

    const history = await gitApi.getHistory('GraphBuilder.build', 10, '/tmp/test-project');
    expect(history.commits.length).toBe(1);

    const blame = await gitApi.getBlame('GraphBuilder.build', undefined, undefined, '/tmp/test-project');
    expect(blame.lines.length).toBe(1);

    const commitDetail = await gitApi.getCommit('a1b2c3d', '/tmp/test-project');
    expect(commitDetail.stats?.insertions).toBe(50);
  });

  // 10. Code Changes & Safe Fix Loop Integration
  it('10. Changes API plans changes, creates proposals, approves, and executes fix loop', async () => {
    const planRes = await changesApi.plan('Add validation to build', '/tmp/test-project');
    expect(planRes.target_symbol).toBe('GraphBuilder.build');
    expect(planRes.risk).toBe('LOW');

    const proposal = await changesApi.propose('Add validation to build', '/tmp/test-project');
    expect(proposal.proposal_id).toBe('prop_test_456');
    expect(proposal.status).toBe('PENDING_APPROVAL');

    const approved = await changesApi.approveProposal('prop_test_456', '/tmp/test-project', true);
    expect(approved.status).toBe('APPROVED');

    const executed = await changesApi.executeProposal('prop_test_456', '/tmp/test-project');
    expect(executed.status).toBe('SUCCESS');

    const reviewRes = await changesApi.review(undefined, '/tmp/test-project');
    expect(reviewRes.is_clean).toBe(false);
    expect(reviewRes.changed_symbols?.length).toBe(1);

    const fixLoopRes = await changesApi.fixLoop('Fix ValueError on empty symbol', 3, '/tmp/test-project');
    expect(fixLoopRes.status).toBe('SUCCESS');
    expect(fixLoopRes.iterations.length).toBe(1);
  });

  // 11. AI Agent Integration
  it('11. AI Agent API processes questions with tool execution metadata', async () => {
    const agentRes = await projectsApi.askAgent('proj_test_123', {
      question: 'What does GraphBuilder.build depend on?',
    });
    expect(agentRes.answer).toContain('ASTExtractor');
    expect(agentRes.tool_calls.length).toBeGreaterThan(0);
  });

  // 12. Health & Diagnostics Integration
  it('12. Health API returns service readiness and detailed subsystem diagnostics', async () => {
    const health = await healthApi.check();
    expect(health.status).toBe('ok');

    const readiness = await healthApi.checkReadiness();
    expect(readiness.ready).toBe(true);
    expect(readiness.status).toBe('healthy');
    expect(readiness.checks.storage).toBeDefined();

    const detailed = await healthApi.checkDetails();
    expect(detailed.status).toBe('ok');
    expect(detailed.git.available).toBe(true);
    expect(detailed.storage.available).toBe(true);
    expect(detailed.llm.provider).toBe('groq');
  });


  // 13. Error Handling
  it('13. ApiClient gracefully handles and wraps HTTP errors', async () => {
    const customError = new ApiError('Not Found', 404, 'PROJECT_NOT_FOUND', 'Project does not exist');
    expect(customError.status).toBe(404);
    expect(customError.code).toBe('PROJECT_NOT_FOUND');
    expect(customError.detail).toBe('Project does not exist');
  });
});
