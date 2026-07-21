'use client';

import type { ATSScore } from '@/components/common/resume_previewer_context';

interface ATSBeforeAfterCardProps {
  /** Baseline score for the untailored resume. Omit to show the after score only. */
  before?: ATSScore | null;
  /** Score after tailoring completes. */
  after: ATSScore;
}

const SUB_SCORE_LABELS: Record<string, string> = {
  keyword_match: 'Keyword Match',
  skills_coverage: 'Skills Coverage',
  section_completeness: 'Section Completeness',
};

function fmt(value: number): string {
  return Number.isFinite(value) ? value.toFixed(1) : '—';
}

function clampWidth(value: number): number {
  return Number.isFinite(value) ? Math.min(Math.max(value, 0), 100) : 0;
}

function deltaClass(delta: number): string {
  if (delta > 0) return 'text-success';
  if (delta < 0) return 'text-destructive';
  return 'text-steel-grey';
}

function formatDelta(delta: number): string {
  const rounded = Number(delta.toFixed(1));
  const sign = rounded > 0 ? '+' : '';
  return `${sign}${rounded.toFixed(1)}`;
}

function SubScoreRow({
  label,
  before,
  after,
}: {
  label: string;
  before: number | null;
  after: number;
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between font-mono text-xs uppercase tracking-wide">
        <span className="text-ink-soft">{label}</span>
        <span className="tabular-nums">
          {before !== null && (
            <>
              <span className="text-steel-grey">{fmt(before)}</span>
              <span className="mx-1 text-steel-grey">&rarr;</span>
            </>
          )}
          <span className="font-bold text-ink">{fmt(after)}%</span>
        </span>
      </div>
      <div className="relative h-2 w-full border border-black bg-paper-tint">
        {before !== null && (
          <div
            className="absolute inset-y-0 left-0 bg-steel-grey/40"
            style={{ width: `${clampWidth(before)}%` }}
          />
        )}
        <div
          className="absolute inset-y-0 left-0 bg-primary transition-all duration-500"
          style={{ width: `${clampWidth(after)}%` }}
        />
      </div>
    </div>
  );
}

export function ATSBeforeAfterCard({ before, after }: ATSBeforeAfterCardProps) {
  const beforeOverall = before?.overall_score ?? null;
  const delta = beforeOverall !== null ? after.overall_score - beforeOverall : null;

  return (
    <div className="border border-black bg-white p-6 shadow-sw-default">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between border-b border-black pb-4">
        <div>
          <h3 className="font-serif text-2xl font-bold uppercase tracking-tight">ATS Match</h3>
          <p className="font-mono text-xs uppercase tracking-wider text-primary">
            {beforeOverall !== null ? '// Before → After' : '// Score'}
          </p>
        </div>
        <div className="flex items-end gap-3">
          {beforeOverall !== null && (
            <>
              <div className="text-right">
                <div className="font-mono text-[10px] uppercase tracking-wider text-steel-grey">
                  Before
                </div>
                <div className="font-serif text-2xl font-bold tabular-nums text-steel-grey">
                  {fmt(beforeOverall)}
                </div>
              </div>
              <span className="mb-1 font-serif text-xl text-ink">&rarr;</span>
            </>
          )}
          <div className="text-right">
            <div className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
              After
            </div>
            <div className="font-serif text-4xl font-bold tabular-nums text-ink">
              {fmt(after.overall_score)}
              <span className="font-mono text-sm text-steel-grey">/100</span>
            </div>
          </div>
        </div>
      </div>

      {/* Delta badge */}
      {delta !== null && (
        <div className="mb-6 flex items-center gap-2">
          <span className="font-mono text-xs uppercase tracking-wider text-ink-soft">Change</span>
          <span
            className={`border border-black px-2 py-0.5 font-mono text-sm font-bold tabular-nums ${deltaClass(delta)}`}
          >
            {formatDelta(delta)}
          </span>
        </div>
      )}

      {/* Sub-score bars */}
      <div className="space-y-4">
        {Object.entries(after.sub_scores).map(([key, value]) => (
          <SubScoreRow
            key={key}
            label={SUB_SCORE_LABELS[key] ?? key}
            before={before?.sub_scores?.[key as keyof ATSScore['sub_scores']] ?? null}
            after={value}
          />
        ))}
      </div>

      {/* Missing keyword chips (display-only) */}
      {after.missing_keywords.length > 0 && (
        <div className="mt-6 border-t border-black pt-4">
          <p className="mb-2 font-mono text-xs font-bold uppercase tracking-wider text-ink-soft">
            Missing Keywords
          </p>
          <div className="flex flex-wrap gap-1.5">
            {after.missing_keywords.map((kw, i) => (
              <span
                key={`missing-${i}-${kw}`}
                className="border border-black bg-background px-2 py-0.5 font-mono text-xs text-ink"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
