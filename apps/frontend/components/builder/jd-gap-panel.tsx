'use client';

import { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { useTranslations } from '@/lib/i18n';
import type { JdMatchResult, RequirementCoverage } from '@/lib/api/resume';
import type { JdMatchStatus } from '@/hooks/use-jd-match';
import { AlertTriangle, CheckCircle, Loader2, RefreshCw, Sparkles, XCircle } from 'lucide-react';

interface JdGapPanelProps {
  match: JdMatchResult | null;
  status: JdMatchStatus;
  error: string | null;
  isFixing: boolean;
  onReanalyze: () => void;
  onImproveMatch: () => void;
}

const STATUS_ORDER: RequirementCoverage['status'][] = ['missing', 'partial', 'covered'];

/**
 * Requirement-by-requirement coverage for the JD Match tab, plus the action that
 * closes the gaps.
 *
 * This replaced a static list of tips. The gaps ARE the tips, and unlike the
 * old advice they are specific to this posting and this resume.
 */
export function JdGapPanel({
  match,
  status,
  error,
  isFixing,
  onReanalyze,
  onImproveMatch,
}: JdGapPanelProps) {
  const { t } = useTranslations();

  const grouped = useMemo(() => {
    const buckets: Record<RequirementCoverage['status'], RequirementCoverage[]> = {
      missing: [],
      partial: [],
      covered: [],
    };
    for (const item of match?.coverage ?? []) {
      buckets[item.status].push(item);
    }
    return buckets;
  }, [match]);

  const openCount = grouped.missing.length + grouped.partial.length;

  if (status === 'loading') {
    return (
      <div className="flex items-center gap-2 border border-black bg-white p-4 font-mono text-xs">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('builder.jdMatch.analyzing')}
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="border border-black bg-white p-4">
        <div className="flex items-center gap-2 font-mono text-xs text-destructive">
          <AlertTriangle className="h-4 w-4" />
          {t('builder.jdMatch.analysisFailed')}
        </div>
        {error && <p className="mt-2 break-words font-mono text-[10px] text-ink-soft">{error}</p>}
        <Button variant="outline" size="sm" className="mt-3" onClick={onReanalyze}>
          <RefreshCw className="h-4 w-4" />
          {t('builder.jdMatch.reanalyze')}
        </Button>
      </div>
    );
  }

  if (!match) return null;

  return (
    <div className="space-y-4">
      {/* Score */}
      <div className="border border-black bg-white p-4 shadow-sw-xs">
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
            {t('builder.jdMatch.semanticScoreLabel')}
          </span>
          <span className={`font-serif text-3xl font-bold ${scoreColor(match.score)}`}>
            {Math.round(match.score)}%
          </span>
        </div>
        <p className="mt-2 font-mono text-[10px] leading-relaxed text-ink-soft">
          {t('builder.jdMatch.semanticScoreExplainer', {
            total: match.coverage.length,
            open: openCount,
          })}
        </p>
        {match.truncated && (
          <p className="mt-2 font-mono text-[10px] text-warning">
            {t('builder.jdMatch.truncatedNotice')}
          </p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" onClick={onImproveMatch} disabled={isFixing || openCount === 0}>
            {isFixing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {isFixing ? t('builder.jdMatch.improving') : t('builder.jdMatch.improveMatch')}
          </Button>
          <Button variant="outline" size="sm" onClick={onReanalyze} disabled={isFixing}>
            <RefreshCw className="h-4 w-4" />
            {t('builder.jdMatch.reanalyze')}
          </Button>
        </div>
        {openCount === 0 && (
          <p className="mt-2 font-mono text-[10px] text-success">
            {t('builder.jdMatch.allCovered')}
          </p>
        )}
      </div>

      {/* Coverage list */}
      {STATUS_ORDER.map((statusKey) => {
        const items = grouped[statusKey];
        if (items.length === 0) return null;
        return (
          <div key={statusKey} className="border border-black bg-white">
            <div className="flex items-center gap-2 border-b border-paper-tint px-3 py-2">
              <StatusIcon status={statusKey} />
              <span className="font-mono text-[10px] uppercase tracking-wider">
                {t(`builder.jdMatch.status.${statusKey}`)} ({items.length})
              </span>
            </div>
            <ul className="divide-y divide-paper-tint">
              {items.map((item) => (
                <li key={`${statusKey}-${item.requirement}`} className="px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-medium">{item.requirement}</span>
                    <span className="shrink-0 font-mono text-[9px] uppercase text-ink-soft">
                      {t(`builder.jdMatch.kind.${item.kind}`)}
                    </span>
                  </div>
                  {statusKey !== 'covered' && item.gap_note && (
                    <p className="mt-1 font-mono text-[10px] leading-relaxed text-ink-soft">
                      {item.gap_note}
                    </p>
                  )}
                  {statusKey === 'covered' && item.evidence && (
                    <p className="mt-1 truncate font-mono text-[10px] text-ink-soft">
                      &ldquo;{item.evidence}&rdquo;
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function scoreColor(score: number): string {
  if (score >= 70) return 'text-success';
  if (score >= 45) return 'text-warning';
  return 'text-destructive';
}

function StatusIcon({ status }: { status: RequirementCoverage['status'] }) {
  if (status === 'covered') return <CheckCircle className="h-4 w-4 text-success" />;
  if (status === 'partial') return <AlertTriangle className="h-4 w-4 text-warning" />;
  return <XCircle className="h-4 w-4 text-destructive" />;
}
