'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  closeJdMatchGaps,
  fetchJdMatch,
  type CloseGapsResult,
  type JdMatchResult,
} from '@/lib/api/resume';

export type JdMatchStatus = 'idle' | 'loading' | 'ready' | 'error';

interface UseJdMatchResult {
  match: JdMatchResult | null;
  status: JdMatchStatus;
  error: string | null;
  /** Re-grade against the server, bypassing its cache. */
  reanalyze: () => Promise<void>;
  /** Ask for gap-closing changes. Returns null on failure (error is set). */
  requestGapFix: () => Promise<CloseGapsResult | null>;
  isFixing: boolean;
}

/**
 * Owns the semantic JD match analysis for one resume.
 *
 * Fetches once when `enabled` turns true (i.e. the JD Match tab is opened) and
 * whenever the resume changes. The result is cached server-side by a hash of the
 * resume data + JD, so remounting the tab is free and saving an edit
 * automatically produces a fresh grade on the next load.
 */
export function useJdMatch(resumeId: string | null, enabled: boolean): UseJdMatchResult {
  const [match, setMatch] = useState<JdMatchResult | null>(null);
  const [status, setStatus] = useState<JdMatchStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [isFixing, setIsFixing] = useState(false);

  // Guards against a slow response from a previous resume landing in state after
  // the user has switched resumes.
  const requestRef = useRef(0);

  const load = useCallback(
    async (refresh: boolean) => {
      if (!resumeId) return;
      const requestId = ++requestRef.current;
      setStatus('loading');
      setError(null);
      try {
        const result = await fetchJdMatch(resumeId, refresh);
        if (requestRef.current !== requestId) return;
        setMatch(result);
        setStatus('ready');
      } catch (err) {
        if (requestRef.current !== requestId) return;
        console.error('JD match analysis failed:', err);
        setMatch(null);
        setError(err instanceof Error ? err.message : String(err));
        setStatus('error');
      }
    },
    [resumeId]
  );

  useEffect(() => {
    if (!enabled || !resumeId) return;
    void load(false);
  }, [enabled, resumeId, load]);

  const reanalyze = useCallback(() => load(true), [load]);

  const requestGapFix = useCallback(async (): Promise<CloseGapsResult | null> => {
    if (!resumeId) return null;
    setIsFixing(true);
    setError(null);
    try {
      return await closeJdMatchGaps(resumeId);
    } catch (err) {
      console.error('Gap closing failed:', err);
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      setIsFixing(false);
    }
  }, [resumeId]);

  return { match, status, error, reanalyze, requestGapFix, isFixing };
}
