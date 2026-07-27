'use client';

import { useMemo } from 'react';
import { type ResumeData } from '@/components/dashboard/resume-component';
import { extractKeywords, calculateMatchStats } from '@/lib/utils/keyword-matcher';
import { JDDisplay } from './jd-display';
import { HighlightedResumeView } from './highlighted-resume-view';
import { CheckCircle, Target } from 'lucide-react';
import { useTranslations } from '@/lib/i18n';

interface JDComparisonViewProps {
  jobDescription: string;
  resumeData: ResumeData;
  /** Semantic match score (0-100) when the analysis is available. */
  semanticScore?: number | null;
  /**
   * Curated JD terms from the backend extractor. When present these replace the
   * browser-side extraction, which treated every non-stopword in the posting
   * ("onsite", "benefits") as a keyword and made the counts meaningless.
   */
  highlightTerms?: string[];
}

/**
 * Split view comparing job description with resume.
 * Left: JD (read-only)
 * Right: Resume with matching keywords highlighted
 */
export function JDComparisonView({
  jobDescription,
  resumeData,
  semanticScore = null,
  highlightTerms,
}: JDComparisonViewProps) {
  const { t } = useTranslations();

  // Highlight set: curated extractor terms when we have them, else fall back to
  // browser-side extraction. Multi-word terms ("REST APIs") are split into
  // tokens because the highlighter matches word by word.
  const keywords = useMemo(() => {
    if (highlightTerms && highlightTerms.length > 0) {
      const tokens = new Set<string>();
      for (const term of highlightTerms) {
        for (const token of extractKeywords(term)) {
          tokens.add(token);
        }
      }
      if (tokens.size > 0) return tokens;
    }
    return extractKeywords(jobDescription);
  }, [highlightTerms, jobDescription]);

  // Build full resume text for stats calculation
  const resumeText = useMemo(() => {
    const parts: string[] = [];

    if (resumeData.summary) parts.push(resumeData.summary);

    resumeData.workExperience?.forEach((exp) => {
      if (exp.title) parts.push(exp.title);
      if (exp.company) parts.push(exp.company);
      exp.description?.forEach((d) => parts.push(d));
    });

    resumeData.education?.forEach((edu) => {
      if (edu.degree) parts.push(edu.degree);
      if (edu.institution) parts.push(edu.institution);
    });

    resumeData.personalProjects?.forEach((proj) => {
      if (proj.name) parts.push(proj.name);
      if (proj.role) parts.push(proj.role);
      proj.description?.forEach((d) => parts.push(d));
    });

    if (resumeData.additional) {
      resumeData.additional.technicalSkills?.forEach((s) => parts.push(s));
      resumeData.additional.languages?.forEach((l) => parts.push(l));
      resumeData.additional.certificationsTraining?.forEach((c) => parts.push(c));
    }

    return parts.join(' ');
  }, [resumeData]);

  // Calculate match statistics
  const stats = useMemo(() => calculateMatchStats(resumeText, keywords), [resumeText, keywords]);

  return (
    <div className="h-full flex flex-col">
      {/* Stats Bar */}
      <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-paper-tint">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-blue-600" />
            <span className="text-sm font-mono">
              {t('builder.jdMatch.stats.keywordsExtracted', { count: keywords.size })}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-600" />
            <span className="text-sm font-mono">
              {t('builder.jdMatch.stats.matchesFound', { count: stats.matchCount })}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {/* Keyword hit rate is a reading aid now, not the headline: it counts
              literal term presence, which is why it disagrees with the score. */}
          <div className="flex items-center gap-2">
            <span className="text-sm font-mono text-ink-soft">
              {t('builder.jdMatch.stats.keywordRateLabel')}
            </span>
            <span className="text-sm font-mono">{stats.matchPercentage}%</span>
          </div>
          {semanticScore !== null && (
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono text-ink-soft">
                {t('builder.jdMatch.stats.matchRateLabel')}
              </span>
              <span
                className={`text-lg font-bold ${
                  semanticScore >= 70
                    ? 'text-success'
                    : semanticScore >= 45
                      ? 'text-warning'
                      : 'text-destructive'
                }`}
              >
                {Math.round(semanticScore)}%
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Split View */}
      <div className="flex-1 grid grid-cols-2 min-h-0">
        {/* Left: JD */}
        <div className="border-r border-paper-tint overflow-hidden">
          <JDDisplay content={jobDescription} />
        </div>

        {/* Right: Resume with highlights */}
        <div className="overflow-hidden">
          <HighlightedResumeView resumeData={resumeData} keywords={keywords} />
        </div>
      </div>
    </div>
  );
}
