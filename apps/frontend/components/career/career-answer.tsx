'use client';

import React, { useState } from 'react';
import AlertTriangle from 'lucide-react/dist/esm/icons/triangle-alert';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useTranslations } from '@/lib/i18n';
import { answerCareerQuestion, type CareerAnswer } from '@/lib/api/career';

interface CareerAnswerPanelProps {
  /** Number of sources currently in the corpus; 0 disables asking. */
  sourceCount: number;
}

export function CareerAnswerPanel({ sourceCount }: CareerAnswerPanelProps) {
  const { t } = useTranslations();
  const [question, setQuestion] = useState('');
  const [tone, setTone] = useState('');
  const [maxWords, setMaxWords] = useState(250);
  const [result, setResult] = useState<CareerAnswer | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const empty = sourceCount === 0;
  const canAsk = question.trim().length > 0 && !asking && !empty;

  // The panel sits inside a page, not a form, but keep the repo's textarea
  // convention so a future wrapper cannot swallow newlines.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter') e.stopPropagation();
  };

  const handleAsk = async () => {
    if (!canAsk) return;
    setAsking(true);
    setError(null);
    setResult(null);
    setCopied(false);
    try {
      setResult(
        await answerCareerQuestion({
          question,
          tone: tone.trim() || undefined,
          max_words: maxWords,
        })
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('career.errors.load'));
    } finally {
      setAsking(false);
    }
  };

  const handleCopy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.answer);
      setCopied(true);
    } catch {
      // Clipboard access can be denied; the text is on screen either way.
      setCopied(false);
    }
  };

  return (
    <section className="border border-black bg-background">
      <header className="border-b border-black p-6">
        <h2 className="font-serif text-2xl uppercase tracking-tight text-black">
          {t('career.answer.heading')}
        </h2>
        <p className="mt-1 max-w-2xl text-sm text-ink-soft">{t('career.answer.subtitle')}</p>
      </header>

      <div className="space-y-4 p-6">
        {empty && (
          <p className="border border-black bg-paper-tint p-4 font-mono text-xs uppercase tracking-wide text-black">
            {t('career.answer.emptyCorpus')}
          </p>
        )}

        <div className="space-y-2">
          <Label htmlFor="career-question">{t('career.answer.questionLabel')}</Label>
          <Textarea
            id="career-question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('career.answer.placeholder')}
            rows={4}
            disabled={empty}
          />
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-[220px] flex-1 space-y-2">
            <Label htmlFor="career-tone">{t('career.answer.toneLabel')}</Label>
            <Input
              id="career-tone"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              disabled={empty}
            />
          </div>
          <div className="w-[140px] space-y-2">
            <Label htmlFor="career-max-words">{t('career.answer.maxWordsLabel')}</Label>
            <Input
              id="career-max-words"
              type="number"
              min={30}
              max={1000}
              value={maxWords}
              onChange={(e) => setMaxWords(Number(e.target.value))}
              disabled={empty}
            />
          </div>
          <Button onClick={handleAsk} disabled={!canAsk}>
            {asking && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {asking ? t('career.answer.asking') : t('career.answer.ask')}
          </Button>
        </div>

        {error && (
          <p
            role="alert"
            className="border border-destructive bg-background p-4 font-mono text-xs text-destructive"
          >
            {error}
          </p>
        )}

        {result && (
          <div className="space-y-4 border-t border-black pt-4">
            <div>
              <div className="flex items-center justify-between gap-4">
                <h3 className="font-mono text-xs font-bold uppercase tracking-wide text-blue-700">
                  {t('career.answer.answerLabel')}
                </h3>
                <Button variant="outline" size="sm" onClick={handleCopy}>
                  {copied ? t('career.answer.copied') : t('career.answer.copy')}
                </Button>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm text-black">{result.answer}</p>
            </div>

            {/* Citations are the point: they are how the user verifies the answer
                quoted a real job rather than a plausible one. */}
            <div>
              <h3 className="font-mono text-xs font-bold uppercase tracking-wide text-blue-700">
                {t('career.answer.sourcesLabel')}
              </h3>
              {result.used_sources.length === 0 ? (
                <p className="mt-2 flex items-start gap-2 text-xs text-warning">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  {t('career.answer.noSources')}
                </p>
              ) : (
                <ul className="mt-2 flex flex-wrap gap-2">
                  {result.used_sources.map((source) => (
                    <li
                      key={source.source_id}
                      className="border border-black bg-paper-tint px-3 py-1 font-mono text-xs uppercase tracking-wide"
                    >
                      {source.title}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {result.gaps.length > 0 && (
              <div>
                <h3 className="font-mono text-xs font-bold uppercase tracking-wide text-warning">
                  {t('career.answer.gapsLabel')}
                </h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-ink-soft">
                  {result.gaps.map((gap) => (
                    <li key={gap}>{gap}</li>
                  ))}
                </ul>
              </div>
            )}

            {result.truncated && (
              <p className="border border-warning bg-background p-3 font-mono text-xs text-warning">
                {t('career.answer.truncated')}
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
