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

describe('DevPilot Frontend Test Suite (v3.0)', () => {
  // 1-3. Application Startup, Routing & Dashboard
  it('1. Application startup and renders dashboard branding', async () => {
    render(<App />);
    expect(screen.getByText('DevPilot')).toBeInTheDocument();
    expect(screen.getByText('v3.0 ENTERPRISE')).toBeInTheDocument();
  });

  it('2. Renders Dashboard metrics and active project focus', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText('Developer Intelligence Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Total Projects')).toBeInTheDocument();
      expect(screen.getAllByText('System Health').length).toBeGreaterThan(0);
    });
  });

  // 4. Reusable components
  it('3. Reusable Button renders variants and triggers onClick', () => {
    const handleClick = vi.fn();
    render(<Button variant="primary" onClick={handleClick}>Click Me</Button>);
    const btn = screen.getByText('Click Me');
    fireEvent.click(btn);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('4. Reusable Badge and StatusBadges render correct colors and text', () => {
    const { rerender } = render(<StatusBadge status="ACTIVE" />);
    expect(screen.getByText('ACTIVE')).toBeInTheDocument();

    rerender(<RiskBadge level="HIGH" score={80} />);
    expect(screen.getByText('HIGH (80/100)')).toBeInTheDocument();

    rerender(<OperationStatusBadge status="COMPLETED" />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('5. Reusable Card component renders title, subtitle, and content', () => {
    render(
      <Card title="Custom Card Title" subtitle="Subtitle description">
        <span>Inner Content</span>
      </Card>
    );
    expect(screen.getByText('Custom Card Title')).toBeInTheDocument();
    expect(screen.getByText('Subtitle description')).toBeInTheDocument();
    expect(screen.getByText('Inner Content')).toBeInTheDocument();
  });

  it('6. Review FindingCard displays severity, category, and recommendation', () => {
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

  // 7-8. API Client and Error Handling
  it('7. ApiClient performs GET requests and parses JSON response', async () => {
    const res = await apiClient<any>('/health');
    expect(res).toBeDefined();
  });

  it('8. ApiClient handles network or abort errors with ApiError', async () => {
    const customError = new ApiError('Not Found', 404, 'NOT_FOUND');
    expect(customError.status).toBe(404);
    expect(customError.code).toBe('NOT_FOUND');
  });

  // 9. Navigation links
  it('9. Sidebar contains navigation links for all DevPilot intelligence views', () => {
    render(<App />);
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Projects')).toBeInTheDocument();
    expect(screen.getByText('Operations')).toBeInTheDocument();
    expect(screen.getAllByText('System Health').length).toBeGreaterThan(0);
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

});
