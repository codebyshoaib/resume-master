import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { JdGapPanel } from '@/components/builder/jd-gap-panel';
import type { JdMatchResult, RequirementCoverage } from '@/lib/api/resume';

vi.mock('@/lib/i18n', () => ({
  useTranslations: () => ({
    // Echo the key plus any params so assertions can see interpolation happened.
    t: (key: string, params?: Record<string, string | number>) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
  }),
}));

function coverage(overrides: Partial<RequirementCoverage>[]): RequirementCoverage[] {
  return overrides.map((o) => ({
    requirement: 'Python',
    kind: 'required',
    status: 'covered',
    evidence: '',
    gap_note: '',
    ...o,
  }));
}

function match(overrides: Partial<JdMatchResult> = {}): JdMatchResult {
  return {
    score: 55.4,
    coverage: coverage([
      { requirement: 'Python', status: 'covered', evidence: 'built Python APIs' },
      { requirement: 'Kubernetes', status: 'missing', gap_note: 'no orchestration shown' },
      { requirement: 'Terraform', status: 'partial', kind: 'preferred', gap_note: 'no IaC depth' },
    ]),
    highlight_keywords: ['Python'],
    cached: false,
    truncated: false,
    ...overrides,
  };
}

const noop = () => {};

describe('JdGapPanel', () => {
  it('shows the rounded semantic score', () => {
    render(
      <JdGapPanel
        match={match()}
        status="ready"
        error={null}
        isFixing={false}
        onReanalyze={noop}
        onImproveMatch={noop}
      />
    );
    expect(screen.getByText('55%')).toBeTruthy();
  });

  it('counts only missing and partial requirements as open', () => {
    render(
      <JdGapPanel
        match={match()}
        status="ready"
        error={null}
        isFixing={false}
        onReanalyze={noop}
        onImproveMatch={noop}
      />
    );
    // 2 of 3 open — the covered one must not be counted.
    expect(screen.getByText(/semanticScoreExplainer.*"total":3.*"open":2/)).toBeTruthy();
  });

  it('renders gap notes for open requirements and evidence for covered ones', () => {
    render(
      <JdGapPanel
        match={match()}
        status="ready"
        error={null}
        isFixing={false}
        onReanalyze={noop}
        onImproveMatch={noop}
      />
    );
    expect(screen.getByText('no orchestration shown')).toBeTruthy();
    expect(screen.getByText('no IaC depth')).toBeTruthy();
    expect(screen.getByText(/built Python APIs/)).toBeTruthy();
  });

  it('fires the improve handler when gaps are open', () => {
    const onImproveMatch = vi.fn();
    render(
      <JdGapPanel
        match={match()}
        status="ready"
        error={null}
        isFixing={false}
        onReanalyze={noop}
        onImproveMatch={onImproveMatch}
      />
    );
    fireEvent.click(screen.getByText('builder.jdMatch.improveMatch'));
    expect(onImproveMatch).toHaveBeenCalledTimes(1);
  });

  it('disables improve when every requirement is covered', () => {
    const fullyCovered = match({
      score: 100,
      coverage: coverage([{ status: 'covered', evidence: 'x' }]),
    });
    render(
      <JdGapPanel
        match={fullyCovered}
        status="ready"
        error={null}
        isFixing={false}
        onReanalyze={noop}
        onImproveMatch={noop}
      />
    );
    const button = screen.getByText('builder.jdMatch.improveMatch').closest('button');
    expect(button?.disabled).toBe(true);
    expect(screen.getByText('builder.jdMatch.allCovered')).toBeTruthy();
  });

  it('disables improve while a fix is in flight', () => {
    render(
      <JdGapPanel
        match={match()}
        status="ready"
        error={null}
        isFixing={true}
        onReanalyze={noop}
        onImproveMatch={noop}
      />
    );
    const button = screen.getByText('builder.jdMatch.improving').closest('button');
    expect(button?.disabled).toBe(true);
  });

  it('surfaces the error and offers a retry', () => {
    const onReanalyze = vi.fn();
    render(
      <JdGapPanel
        match={null}
        status="error"
        error="boom"
        isFixing={false}
        onReanalyze={onReanalyze}
        onImproveMatch={noop}
      />
    );
    expect(screen.getByText('builder.jdMatch.analysisFailed')).toBeTruthy();
    expect(screen.getByText('boom')).toBeTruthy();
    fireEvent.click(screen.getByText('builder.jdMatch.reanalyze'));
    expect(onReanalyze).toHaveBeenCalledTimes(1);
  });

  it('shows the loading state instead of a stale score', () => {
    render(
      <JdGapPanel
        match={match()}
        status="loading"
        error={null}
        isFixing={false}
        onReanalyze={noop}
        onImproveMatch={noop}
      />
    );
    expect(screen.getByText('builder.jdMatch.analyzing')).toBeTruthy();
    expect(screen.queryByText('55%')).toBeNull();
  });

  it('warns when the posting had more requirements than were graded', () => {
    render(
      <JdGapPanel
        match={match({ truncated: true })}
        status="ready"
        error={null}
        isFixing={false}
        onReanalyze={noop}
        onImproveMatch={noop}
      />
    );
    expect(screen.getByText('builder.jdMatch.truncatedNotice')).toBeTruthy();
  });
});
