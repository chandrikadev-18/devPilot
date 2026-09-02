import React from 'react';
import { Card } from '../components/common/Card';

export const SettingsPage: React.FC = () => {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

  return (
    <div className="page-wrapper" style={{ maxWidth: '800px' }}>
      <div className="page-header">
        <div>
          <h2 className="page-title">Settings & Configuration</h2>
          <p className="page-subtitle">
            Frontend connection parameters and environment specifications.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <Card title="API Configuration" subtitle="Target backend service connection">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
            <div>
              <strong>Backend Endpoint (VITE_API_URL):</strong>
              <div style={{ marginTop: '0.25rem' }}>
                <code>{apiUrl}</code>
              </div>
            </div>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              To change this URL, update the <code>VITE_API_URL</code> key in <code>frontend/.env</code>.
            </p>
          </div>
        </Card>

        <Card title="Architecture Guardrails" subtitle="DevPilot Enterprise Principles">
          <ul style={{ paddingLeft: '1.25rem', fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            <li><strong>Strict Read-Only Intelligence:</strong> Code exploration, AST graph queries, and reviews never modify source files.</li>
            <li><strong>Explicit Approval Required:</strong> Patch proposals are never executed or applied automatically without manual confirmation.</li>
            <li><strong>Zero Secret Leakage:</strong> Credentials, Bearer tokens, and API keys are redacted automatically at the network and log level.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
};
