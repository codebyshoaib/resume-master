'use client';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useTranslations } from '@/lib/i18n';
import type { CloseGapsResult, GapChange } from '@/lib/api/resume';
import { AlertTriangle, Loader2, Plus } from 'lucide-react';

interface GapFixDialogProps {
  isOpen: boolean;
  result: CloseGapsResult | null;
  isApplying: boolean;
  onClose: () => void;
  onApply: () => void;
}

/**
 * Review gate for gap-closing changes.
 *
 * The backend proposes but never saves, so this dialog is the only path from a
 * suggestion to the resume. Every change is shown with the reason it was made,
 * because these are additions the candidate has to be able to defend.
 */
export function GapFixDialog({ isOpen, result, isApplying, onClose, onApply }: GapFixDialogProps) {
  const { t } = useTranslations();
  const changes = result?.changes ?? [];

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <div className="border-b border-black px-6 py-4">
          <DialogHeader>
            <DialogTitle className="font-serif text-lg font-bold">
              {t('builder.jdMatch.gapFix.title')}
            </DialogTitle>
          </DialogHeader>
          <p className="mt-1 font-mono text-[10px] text-ink-soft">
            {t('builder.jdMatch.gapFix.subtitle', { count: changes.length })}
          </p>
        </div>

        <div className="max-h-[55vh] overflow-y-auto px-6 py-4">
          {result?.warnings?.map((warning) => (
            <div
              key={warning}
              className="mb-3 flex items-start gap-2 border border-warning bg-white p-3 font-mono text-[10px]"
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
              <span>{warning}</span>
            </div>
          ))}

          {changes.length === 0 ? (
            <p className="font-mono text-xs text-ink-soft">
              {t('builder.jdMatch.gapFix.noChanges')}
            </p>
          ) : (
            <ul className="space-y-3">
              {changes.map((change, index) => (
                <li key={`${change.path}-${index}`} className="border border-black bg-white p-3">
                  <div className="flex items-center gap-2">
                    <Plus className="h-3.5 w-3.5 text-success" />
                    <span className="font-mono text-[10px] uppercase tracking-wider text-ink-soft">
                      {t(`builder.jdMatch.gapFix.action.${actionKey(change)}`)}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed">{renderValue(change)}</p>
                  <p className="mt-2 font-mono text-[10px] leading-relaxed text-ink-soft">
                    {change.reason}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <DialogFooter className="gap-2 border-t border-black px-6 py-4">
          <Button variant="outline" size="sm" onClick={onClose} disabled={isApplying}>
            {t('common.cancel')}
          </Button>
          <Button size="sm" onClick={onApply} disabled={isApplying || changes.length === 0}>
            {isApplying && <Loader2 className="h-4 w-4 animate-spin" />}
            {isApplying ? t('common.saving') : t('builder.jdMatch.gapFix.apply')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function actionKey(change: GapChange): 'skill' | 'bullet' {
  return change.action === 'add_skill' ? 'skill' : 'bullet';
}

function renderValue(change: GapChange): string {
  return Array.isArray(change.value) ? change.value.join(', ') : change.value;
}
