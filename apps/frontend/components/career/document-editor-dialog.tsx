'use client';

import React, { useEffect, useState } from 'react';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dropdown } from '@/components/ui/dropdown';
import { useTranslations } from '@/lib/i18n';
import {
  CAREER_DOCUMENT_KINDS,
  createCareerDocument,
  fetchCareerDocument,
  updateCareerDocument,
  type CareerDocumentKind,
  type CareerDocumentSummary,
} from '@/lib/api/career';

interface DocumentEditorDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Omit to create; supply a row to edit it (its body is fetched on open). */
  document?: CareerDocumentSummary | null;
  onSaved: () => void;
}

export function DocumentEditorDialog({
  open,
  onOpenChange,
  document,
  onSaved,
}: DocumentEditorDialogProps) {
  const { t } = useTranslations();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [kind, setKind] = useState<CareerDocumentKind>('review');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEdit = Boolean(document);

  // The list endpoint only ships a preview, so editing needs the full body.
  useEffect(() => {
    if (!open) return;
    setError(null);
    if (!document) {
      setTitle('');
      setContent('');
      setKind('review');
      return;
    }
    setTitle(document.title);
    setKind(document.kind);
    setLoading(true);
    fetchCareerDocument(document.document_id)
      .then((full) => setContent(full.content))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : t('career.errors.load')))
      .finally(() => setLoading(false));
  }, [open, document, t]);

  // A dialog that submits on Enter would otherwise swallow newlines.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter') e.stopPropagation();
  };

  const canSave = title.trim().length > 0 && content.trim().length > 0 && !loading && !saving;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      if (document) {
        await updateCareerDocument(document.document_id, { title, content, kind });
      } else {
        await createCareerDocument({ title, content, kind });
      }
      onSaved();
      onOpenChange(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('career.errors.save'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? t('career.documents.edit') : t('career.documents.newTitle')}
          </DialogTitle>
          <DialogDescription>{t('career.subtitle')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="career-doc-title">{t('career.documents.titleLabel')}</Label>
            <Input
              id="career-doc-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={loading}
            />
          </div>

          <Dropdown
            label={t('career.documents.kindLabel')}
            options={CAREER_DOCUMENT_KINDS.map((k) => ({
              id: k,
              label: t(`career.kinds.${k}`),
            }))}
            value={kind}
            onChange={(v) => setKind(v as CareerDocumentKind)}
            disabled={loading}
          />

          <div className="space-y-2">
            <Label htmlFor="career-doc-content">{t('career.documents.contentLabel')}</Label>
            <Textarea
              id="career-doc-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              rows={16}
              className="font-mono text-xs"
            />
            <p className="font-mono text-xs text-steel-grey uppercase tracking-wide">
              {loading
                ? t('career.documents.loading')
                : t('career.documents.charCount', { count: content.length })}
            </p>
          </div>

          {error && (
            <p className="border border-destructive bg-background p-3 font-mono text-xs text-destructive">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('career.documents.cancel')}
          </Button>
          <Button onClick={handleSave} disabled={!canSave}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('career.documents.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
