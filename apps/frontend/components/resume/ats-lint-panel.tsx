'use client';

import React, { useEffect, useState } from 'react';
import { fetchAtsLint, type AtsLintFinding, type AtsLintResult } from '@/lib/api/resume';
import { useTranslations } from '@/lib/i18n';

type Severity = AtsLintFinding['severity'];

// Swiss alert palette per severity (pale-100 background, 600/700 border+label).
const SEVERITY_STYLES: Record<Severity, { box: string; label: string; square: string }> = {
  error: {
    box: 'bg-red-100 border-2 border-red-600',
    label: 'text-red-600',
    square: 'bg-red-600',
  },
  warn: {
    box: 'bg-orange-100 border-2 border-orange-600',
    label: 'text-orange-600',
    square: 'bg-orange-500',
  },
  info: {
    box: 'bg-blue-100 border-2 border-blue-700',
    label: 'text-blue-700',
    square: 'bg-blue-700',
  },
};

// Render order: most severe first.
const SEVERITY_ORDER: Severity[] = ['error', 'warn', 'info'];

interface AtsLintPanelProps {
  resumeId: string;
  className?: string;
}

export function AtsLintPanel({ resumeId, className }: AtsLintPanelProps) {
  const { t } = useTranslations();
  const [result, setResult] = useState<AtsLintResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!resumeId) return;
    let active = true;
    setLoading(true);
    setError(false);
    fetchAtsLint(resumeId)
      .then((data) => {
        if (active) setResult(data);
      })
      .catch((err) => {
        console.error('Failed to load ATS lint:', err);
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [resumeId]);

  const groupLabels: Record<Severity, string> = {
    error: t('atsLint.groups.errors'),
    warn: t('atsLint.groups.warnings'),
    info: t('atsLint.groups.infos'),
  };

  return (
    <section
      className={`bg-white border-2 border-black rounded-none shadow-sw-default p-6 ${className ?? ''}`}
      aria-label={t('atsLint.title')}
    >
      <div className="mb-1 flex items-baseline justify-between gap-4">
        <h3 className="font-serif text-2xl font-bold">{t('atsLint.title')}</h3>
        {result && (
          <span className="font-mono text-xs uppercase tracking-wider text-steel-grey">
            {t('atsLint.counts', {
              errors: String(result.summary.errors),
              warnings: String(result.summary.warnings),
              infos: String(result.summary.infos),
            })}
          </span>
        )}
      </div>
      <p className="font-mono text-xs uppercase tracking-wider text-steel-grey mb-4">
        {t('atsLint.subtitle')}
      </p>

      {loading && (
        <p className="font-mono text-sm uppercase tracking-wider text-steel-grey">
          {t('atsLint.loading')}
        </p>
      )}

      {!loading && error && (
        <p className="font-mono text-sm uppercase tracking-wider text-red-600">
          {t('atsLint.error')}
        </p>
      )}

      {!loading && !error && result && result.findings.length === 0 && (
        <div className="bg-green-100 border-2 border-green-700 p-4">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-green-700" aria-hidden="true" />
            <p className="font-mono uppercase text-sm font-bold text-green-700">
              {t('atsLint.allClear')}
            </p>
          </div>
        </div>
      )}

      {!loading && !error && result && result.findings.length > 0 && (
        <div className="flex flex-col gap-4">
          {SEVERITY_ORDER.map((severity) => {
            const items = result.findings.filter((f) => f.severity === severity);
            if (items.length === 0) return null;
            const styles = SEVERITY_STYLES[severity];
            return (
              <div key={severity}>
                <div className="flex items-center gap-2 mb-2">
                  <div className={`w-3 h-3 ${styles.square}`} aria-hidden="true" />
                  <span
                    className={`font-mono uppercase text-sm font-bold tracking-wider ${styles.label}`}
                  >
                    {groupLabels[severity]} ({items.length})
                  </span>
                </div>
                <ul className="flex flex-col gap-2">
                  {items.map((finding, idx) => (
                    <li
                      key={`${finding.code}-${finding.path ?? idx}`}
                      className={`${styles.box} p-4`}
                    >
                      <p className="font-sans text-sm font-bold text-ink">{finding.message}</p>
                      <p className="font-sans text-sm text-ink-soft mt-1">
                        <span className="font-mono uppercase text-xs tracking-wider mr-2">
                          {t('atsLint.fixLabel')}
                        </span>
                        {finding.fix}
                      </p>
                      {finding.path && (
                        <p className="font-mono text-xs text-steel-grey mt-1 break-all">
                          {finding.path}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
