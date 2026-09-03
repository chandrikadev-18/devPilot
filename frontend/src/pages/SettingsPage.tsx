import React, { useEffect, useState } from 'react';
import { Activity, CheckCircle2, RefreshCw, Server, ShieldCheck, XCircle } from 'lucide-react';
import { healthApi } from '../api/health';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { Spinner } from '../components/common/Spinner';
import { DetailedHealthResponse } from '../types/health';

export const SettingsPage: React.FC = () => {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
  const [health, setHealth] = useState<DetailedHealthResponse | null>(null);
  const [pingMs, setPingMs] = useState<number | null>(null);
  const [isPinging, setIsPinging] = useState(false);

  const pingBackend = async () => {
    setIsPinging(true);
    const start = performance.now();
    try {
      const data = await healthApi.checkDetails();
      const elapsed = Math.round(performance.now() - start);
      setHealth(data);
      setPingMs(elapsed);
    } catch {
      setHealth(null);
      setPingMs(null);
    } finally {
      setIsPinging(false);
    }
  };

  useEffect(() => {
    pingBackend();
  }, []);

  return (
    <div className="page-wrapper" style={{ maxWidth: '850px' }}>
      <div className="page-header">
        <div>
          <h2 className="page-title">Settings & System Configuration</h2>
          <p className="page-subtitle">
            DevPilot frontend connection parameters, diagnostics, and security guardrails.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={pingBackend}
          isLoading={isPinging}
          leftIcon={<RefreshCw size={14} />}
        >
          Test Connection
        </Button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <Card title="API Gateway Configuration" subtitle="Target backend service connection">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.875rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <strong>Backend REST Base URL:</strong>
                <div style={{ marginTop: '0.25rem' }}>
                  <code style={{ fontSize: '0.85rem', color: 'var(--accent-cyan)' }}>{apiUrl}</code>
                </div>
              </div>
              <div>
                {isPinging ? (
                  <Spinner size="sm" label="Testing latency..." />
                ) : health ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Badge variant="success">Connected</Badge>
                    {pingMs !== null && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--accent-emerald)', fontWeight: 600 }}>
                        {pingMs}ms latency
                      </span>
                    )}
                  </div>
                ) : (
                  <Badge variant="danger">Disconnected</Badge>
                )}
              </div>
            </div>

            {health && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                  gap: '0.75rem',
                  padding: '0.75rem',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.8rem',
                }}
              >
                <div><strong>Service:</strong> {health.service}</div>
                <div><strong>Version:</strong> {health.version}</div>
                <div><strong>Environment:</strong> <code>{health.environment}</code></div>
                <div><strong>LLM Provider:</strong> {health.llm.provider.toUpperCase()}</div>
              </div>
            )}

            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              To configure a custom backend URL or proxy, adjust <code>VITE_API_URL</code> in <code>frontend/.env</code>.
            </p>
          </div>
        </Card>

        <Card title="Architecture Guardrails" subtitle="DevPilot Enterprise Principles">
          <ul style={{ paddingLeft: '1.25rem', fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <li><strong>Strict Read-Only Intelligence:</strong> Code exploration, AST graph queries, and reviews never modify source files.</li>
            <li><strong>Explicit Approval Required:</strong> Patch proposals are never executed or applied automatically without manual confirmation.</li>
            <li><strong>Zero Secret Leakage:</strong> Credentials, Bearer tokens, and API keys are redacted automatically at the network and log level.</li>
            <li><strong>Deterministic AST Resolution:</strong> Tree-sitter powered syntax modeling ensures resilient parsing across modern Python versions.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
};
