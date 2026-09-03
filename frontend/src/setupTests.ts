import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Global mock for fetch supporting all DevPilot v3.0 endpoints
(globalThis as any).fetch = vi.fn().mockImplementation((url: string, options: any = {}) => {
  const method = (options.method || 'GET').toUpperCase();

  if (url.includes('/health/details')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          status: 'ok',
          service: 'DevPilot',
          version: '3.0',
          environment: 'test',
          git: { available: true, version: '2.40.0' },
          storage: { available: true, writable: true },
          graph: { available: true },
          llm: { provider: 'groq', model: 'llama-3.3-70b', api_key_configured: true },
        }),
    });
  }

  if (url.includes('/health')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ status: 'ok', service: 'DevPilot', version: '3.0' }),
    });
  }

  if (url.includes('/api/graph/info') || url.includes('/graph/info')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          total_nodes: 42,
          files: 5,
          classes: 8,
          functions: 14,
          methods: 12,
          modules: 3,
          total_edges: 38,
          calls: 20,
          imports: 10,
          contains: 5,
          defines: 3,
          belongs_to: 0,
        }),
    });
  }

  if (url.includes('/api/graph/callers') || url.includes('/graph/callers')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          symbol: 'GraphBuilder.build',
          total_callers: 2,
          callers: ['app.main.run_graph', 'app.projects.service.build_graph'],
        }),
    });
  }

  if (url.includes('/api/graph/callees') || url.includes('/graph/callees')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          symbol: 'GraphBuilder.build',
          total_callees: 3,
          callees: ['ASTExtractor.extract', 'GraphStore.add_node', 'GraphStore.add_edge'],
        }),
    });
  }

  if (url.includes('/api/graph/dependencies') || url.includes('/graph/dependencies')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          symbol: 'GraphBuilder.build',
          depth: 2,
          total_dependencies: 3,
          dependencies: ['ASTExtractor.extract', 'GraphStore.add_node', 'GraphStore.add_edge'],
        }),
    });
  }

  if (url.includes('/api/graph/dependents') || url.includes('/graph/dependents')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          symbol: 'GraphBuilder.build',
          depth: 2,
          total_dependents: 2,
          dependents: ['app.main.run_graph', 'app.projects.service.build_graph'],
        }),
    });
  }

  if (url.includes('/api/graph/impact') || url.includes('/graph/impact')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          symbol: 'GraphBuilder.build',
          depth: 2,
          analysis_type: 'STATIC DEPENDENCY IMPACT',
          total_impacted: 4,
          direct_callers: ['app.main.run_graph'],
          indirect_callers: ['app.cli.main'],
          direct_dependents: ['app.main.run_graph'],
          indirect_dependents: ['app.cli.main'],
          impacted_files: ['app/main.py', 'app/cli.py'],
        }),
    });
  }

  if (url.includes('/api/graph/file-dependencies')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          file_path: 'app/main.py',
          imports_files: ['app/graph/builder.py', 'app/projects/service.py'],
          imported_by: [],
          defined_symbols: [],
        }),
    });
  }

  if (url.includes('/api/search/symbol')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          query: 'GraphBuilder',
          total_matches: 1,
          matches: [
            {
              file_path: 'app/graph/builder.py',
              symbol_name: 'GraphBuilder',
              symbol_type: 'class',
              start_line: 12,
              end_line: 95,
              code: 'class GraphBuilder:\n    def build(self, path): pass',
            },
          ],
        }),
    });
  }

  if (url.includes('/api/search/semantic')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          query: 'build graph',
          total_results: 1,
          results: [
            {
              symbol: 'GraphBuilder.build',
              file: 'app/graph/builder.py',
              start_line: 25,
              end_line: 60,
              score: 0.92,
              reason: 'Constructs AST graph from files',
              symbol_type: 'method',
            },
          ],
        }),
    });
  }

  if (url.includes('/api/git/last-change')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          symbol: 'GraphBuilder.build',
          commit: 'a1b2c3d4e5f6789012345678901234567890abcd',
          short_hash: 'a1b2c3d',
          author: 'DevPilot Engineer',
          date: '2026-09-01T10:00:00Z',
          message: 'feat: AST relationship graph builder',
          file: 'app/graph/builder.py',
          line_start: 25,
          line_end: 60,
        }),
    });
  }

  if (url.includes('/api/git/history')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          symbol: 'GraphBuilder.build',
          total_commits: 1,
          commits: [
            {
              commit: 'a1b2c3d4e5f6789012345678901234567890abcd',
              short_hash: 'a1b2c3d',
              author: 'DevPilot Engineer',
              date: '2026-09-01T10:00:00Z',
              message: 'feat: AST relationship graph builder',
            },
          ],
        }),
    });
  }

  if (url.includes('/api/git/blame')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          symbol: 'GraphBuilder.build',
          file: 'app/graph/builder.py',
          lines: [
            {
              line_number: 25,
              commit_hash: 'a1b2c3d',
              author: 'DevPilot Engineer',
              date: '2026-09-01',
              code: '    def build(self, root):',
            },
          ],
        }),
    });
  }

  if (url.includes('/api/git/commit/')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          commit: 'a1b2c3d4e5f6789012345678901234567890abcd',
          short_hash: 'a1b2c3d',
          author: 'DevPilot Engineer',
          date: '2026-09-01T10:00:00Z',
          message: 'feat: AST relationship graph builder',
          stats: { insertions: 50, deletions: 2, files_changed: 3 },
          diff: 'diff --git a/app/graph/builder.py b/app/graph/builder.py\n+class GraphBuilder:\n',
        }),
    });
  }

  if (url.includes('/api/changes/plan')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          change_request: 'Add validation to build',
          target: 'GraphBuilder.build',
          target_symbol: 'GraphBuilder.build',
          target_file: 'app/graph/builder.py',
          target_lines: '25-60',
          affected_files: ['app/graph/builder.py', 'app/main.py'],
          affected_symbols: ['GraphBuilder.build', 'run_graph'],
          relevant_tests: ['tests/test_graph_builder.py'],
          recommended_order: ['1. Update GraphBuilder.build', '2. Run test_graph_builder'],
          risk: 'LOW',
          reason: 'Localized modification with verified test coverage',
          evidence: [],
          unverified: [],
        }),
    });
  }

  if (url.includes('/api/changes/propose')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          proposal_id: 'prop_test_456',
          request: 'Add validation to build',
          target_symbol: 'GraphBuilder.build',
          target_file: 'app/graph/builder.py',
          target_lines: '25-60',
          change_summary: 'Add root directory existence check in build()',
          affected_files: ['app/graph/builder.py'],
          affected_symbols: ['GraphBuilder.build'],
          proposed_changes: ['Add path validation check'],
          patch: '--- a/app/graph/builder.py\n+++ b/app/graph/builder.py\n@@ -25,2 +25,4 @@\n+    if not root.exists():\n+        raise ValueError("Invalid root")\n',
          tests_to_update: [],
          tests_to_add: ['tests/test_graph_builder.py'],
          risk: 'LOW',
          reasoning: 'Non-breaking defensive check',
          confidence: 0.95,
          warnings: [],
          unverified_assumptions: [],
          status: 'PENDING_APPROVAL',
        }),
    });
  }

  if (url.includes('/approve')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          proposal_id: 'prop_test_456',
          request: 'Add validation to build',
          status: 'APPROVED',
          risk: 'LOW',
          patch: '--- a/app/graph/builder.py\n+++ b/app/graph/builder.py\n+    pass\n',
        }),
    });
  }

  if (url.includes('/reject')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          proposal_id: 'prop_test_456',
          request: 'Add validation to build',
          status: 'REJECTED',
          risk: 'LOW',
        }),
    });
  }

  if (url.includes('/execute')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          execution_id: 'exec_789',
          proposal_id: 'prop_test_456',
          status: 'SUCCESS',
          changed_files: ['app/graph/builder.py'],
          diff: '--- a/app/graph/builder.py\n+++ b/app/graph/builder.py\n',
        }),
    });
  }

  if (url.includes('/api/changes/review')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          branch: 'main',
          is_clean: false,
          status: { modified_files: ['app/graph/builder.py'], staged_files: [], unstaged_files: ['app/graph/builder.py'] },
          changed_files: ['app/graph/builder.py'],
          changed_symbols: [{ name: 'GraphBuilder.build', file: 'app/graph/builder.py', change_type: 'modified', symbol_type: 'method' }],
          impact: { direct: ['run_graph'], indirect: [], files: ['app/main.py'], total_affected_symbols: 1 },
          risk: { score: 15, level: 'LOW', reasons: ['Localized changes with existing test suite'] },
          recommended_tests: ['tests/test_graph_builder.py'],
          test_recommendations: [{ test_target: 'tests/test_graph_builder.py', file_path: 'tests/test_graph_builder.py', reason: 'Covers GraphBuilder' }],
          diff_stats: { insertions: 4, deletions: 1 },
          review_notes: ['Ensure input path is resolved'],
          summary: 'Defensive validation added to GraphBuilder.build without breaking callers.',
        }),
    });
  }

  if (url.includes('/api/changes/fix-loop')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          loop_id: 'fix_loop_123',
          request: 'Fix ValueError on empty symbol',
          status: 'SUCCESS',
          current_iteration: 1,
          max_iterations: 3,
          iterations: [
            {
              iteration_id: 'iter_1',
              iteration_number: 1,
              status: 'SUCCESS',
              proposed_fix_summary: 'Add empty string guard',
              patch: '--- a/app/graph/queries.py\n+++ b/app/graph/queries.py\n+if not symbol: return []',
            },
          ],
          message: 'Autonomous fix completed and verified against test suite.',
        }),
    });
  }

  if (url.includes('/agent')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          project_id: 'proj_test_123',
          question: 'What does GraphBuilder.build depend on?',
          answer: 'GraphBuilder.build depends on ASTExtractor to parse Python syntax and GraphStore to persist nodes and edges.',
          tool_calls: [{ tool: 'get_symbol_dependencies', status: 'success', duration_ms: 15.2 }],
          iterations: 1,
          operation: {
            operation_id: 'op_agent_1',
            project_id: 'proj_test_123',
            operation_type: 'agent',
            status: 'COMPLETED',
            started_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            result: {},
            error: null,
          },
        }),
    });
  }

  if (url.includes('/projects/proj_test_123/scan')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          project_name: 'Test Project',
          project_path: '/tmp/test-project',
          total_files: 25,
          total_dirs: 6,
          extensions: { '.py': 20, '.json': 3, '.md': 2 },
          files_count: 25,
          operation: {
            operation_id: 'op_scan_1',
            project_id: 'proj_test_123',
            operation_type: 'scan',
            status: 'COMPLETED',
            started_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            result: { total_files: 25 },
            error: null,
          },
        }),
    });
  }

  if (url.includes('/projects/proj_test_123/graph/build')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          project_id: 'proj_test_123',
          total_nodes: 50,
          total_edges: 45,
          files: 10,
          classes: 15,
          functions: 25,
          operation: {
            operation_id: 'op_graph_1',
            project_id: 'proj_test_123',
            operation_type: 'graph_build',
            status: 'COMPLETED',
            started_at: new Date().toISOString(),
            completed_at: new Date().toISOString(),
            result: { total_nodes: 50 },
            error: null,
          },
        }),
    });
  }

  if (url.includes('/operations')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          operations: [
            {
              operation_id: 'op_123',
              project_id: 'proj_test_123',
              operation_type: 'scan',
              status: 'COMPLETED',
              started_at: new Date().toISOString(),
              completed_at: new Date().toISOString(),
              result: { total_files: 10, duration_ms: 12.3 },
              error: null,
            },
          ],
          total: 1,
        }),
    });
  }

  if (url.includes('/projects')) {
    if (method === 'POST') {
      return Promise.resolve({
        ok: true,
        status: 201,
        json: () =>
          Promise.resolve({
            project_id: 'proj_new_999',
            name: 'New Registered Project',
            path: '/tmp/new-project',
            repository: 'https://github.com/org/new',
            default_branch: 'main',
            status: 'ACTIVE',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            metadata: {},
          }),
      });
    }

    if (url.match(/\/projects\/[^\/]+$/) && method === 'GET') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            project_id: 'proj_test_123',
            name: 'Test Project',
            path: '/tmp/test-project',
            repository: 'https://github.com/org/repo',
            default_branch: 'main',
            status: 'ACTIVE',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            metadata: {},
          }),
      });
    }

    return Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          projects: [
            {
              project_id: 'proj_test_123',
              name: 'Test Project',
              path: '/tmp/test-project',
              repository: 'https://github.com/org/repo',
              default_branch: 'main',
              status: 'ACTIVE',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              metadata: {},
            },
          ],
          total: 1,
        }),
    });
  }

  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ status: 'ok' }),
  });
});
