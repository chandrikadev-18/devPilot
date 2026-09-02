import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Global mock for fetch
(globalThis as any).fetch = vi.fn().mockImplementation((url: string) => {

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

  if (url.includes('/projects')) {
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

  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ status: 'ok' }),
  });
});
