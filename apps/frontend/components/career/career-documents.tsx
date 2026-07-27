'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import FileText from 'lucide-react/dist/esm/icons/file-text';
import Loader2 from 'lucide-react/dist/esm/icons/loader-2';
import Lock from 'lucide-react/dist/esm/icons/lock';
import Trash2 from 'lucide-react/dist/esm/icons/trash-2';
import Upload from 'lucide-react/dist/esm/icons/upload';
import { Button } from '@/components/ui/button';
import { ConfirmDialog } from '@/components/ui/confirm-dialog';
import { Dropdown } from '@/components/ui/dropdown';
import { ToggleSwitch } from '@/components/ui/toggle-switch';
import { useTranslations } from '@/lib/i18n';
import {
  CAREER_DOCUMENT_KINDS,
  deleteCareerDocument,
  listCareerDocuments,
  updateCareerDocument,
  uploadCareerDocument,
  type CareerDocumentKind,
  type CareerDocumentSummary,
} from '@/lib/api/career';
import { fetchResumeList, type ResumeListItem } from '@/lib/api/resume';
import { DocumentEditorDialog } from './document-editor-dialog';

// Mirrors CAREER_TYPES in app/routers/_uploads.py — the backend is the authority;
// this only spares the user a round-trip to learn the file is unsupported.
const ACCEPT = '.pdf,.doc,.docx,.txt,.md';

export function CareerDocuments() {
  const { t } = useTranslations();
  const [documents, setDocuments] = useState<CareerDocumentSummary[]>([]);
  const [master, setMaster] = useState<ResumeListItem | null>(null);
  const [kindFilter, setKindFilter] = useState<'all' | CareerDocumentKind>('all');
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<CareerDocumentSummary | null>(null);
  const [pendingDelete, setPendingDelete] = useState<CareerDocumentSummary | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { documents: rows } = await listCareerDocuments();
      setDocuments(rows);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('career.errors.load'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  // The master résumé is shown as a linked, read-only row. It is never copied
  // into the corpus — the backend reads it live — so there is nothing to sync.
  useEffect(() => {
    fetchResumeList(true)
      .then((rows) => setMaster(rows.find((r) => r.is_master) ?? null))
      .catch(() => setMaster(null));
  }, []);

  const visible = useMemo(
    () => (kindFilter === 'all' ? documents : documents.filter((d) => d.kind === kindFilter)),
    [documents, kindFilter]
  );

  const corpusStats = useMemo(() => {
    const included = documents.filter((d) => d.include_in_context);
    return {
      count: included.length,
      chars: included.reduce((sum, d) => sum + d.char_count, 0),
    };
  }, [documents]);

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset immediately so re-picking the same file still fires onChange.
    event.target.value = '';
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadCareerDocument(file);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('career.errors.upload'));
    } finally {
      setUploading(false);
    }
  };

  const handleToggleInclude = async (doc: CareerDocumentSummary, next: boolean) => {
    // Optimistic: the toggle is the fastest-feeling control on the page, and a
    // failure re-syncs from the server below.
    setDocuments((rows) =>
      rows.map((r) => (r.document_id === doc.document_id ? { ...r, include_in_context: next } : r))
    );
    try {
      await updateCareerDocument(doc.document_id, { include_in_context: next });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('career.errors.save'));
      await load();
    }
  };

  const handleDelete = async () => {
    if (!pendingDelete) return;
    try {
      await deleteCareerDocument(pendingDelete.document_id);
      setPendingDelete(null);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t('career.errors.delete'));
    }
  };

  return (
    <section className="border border-black bg-background">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-black p-6">
        <div>
          <h2 className="font-serif text-2xl uppercase tracking-tight text-black">
            {t('career.documents.heading')}
          </h2>
          <p className="mt-1 font-mono text-xs uppercase tracking-wide text-blue-700">
            {t('career.documents.summary', {
              count: corpusStats.count,
              chars: corpusStats.chars.toLocaleString(),
            })}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Dropdown
            options={[
              { id: 'all', label: t('career.documents.filterAll') },
              ...CAREER_DOCUMENT_KINDS.map((k) => ({ id: k, label: t(`career.kinds.${k}`) })),
            ]}
            value={kindFilter}
            onChange={(v) => setKindFilter(v as 'all' | CareerDocumentKind)}
            className="min-w-[180px]"
          />
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            onChange={handleUpload}
            className="hidden"
          />
          <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={uploading}>
            {uploading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            {uploading ? t('career.documents.uploading') : t('career.documents.upload')}
          </Button>
          <Button
            onClick={() => {
              setEditing(null);
              setEditorOpen(true);
            }}
          >
            {t('career.documents.paste')}
          </Button>
        </div>
      </header>

      {error && (
        <p
          role="alert"
          className="border-b border-black bg-background p-4 font-mono text-xs text-destructive"
        >
          {error}
        </p>
      )}

      {/* Master résumé — pinned, read-only, edited in the Builder. */}
      {master && (
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-black bg-paper-tint p-5">
          <div className="flex items-start gap-3">
            <Lock className="mt-1 h-4 w-4 shrink-0 text-steel-grey" aria-hidden="true" />
            <div>
              <p className="font-bold uppercase tracking-wide text-black">
                {t('career.masterResume.label')}
              </p>
              <p className="mt-1 font-mono text-xs uppercase tracking-wide text-steel-grey">
                {t('career.masterResume.linked')}
              </p>
              <p className="mt-2 max-w-xl text-xs text-ink-soft">{t('career.masterResume.hint')}</p>
            </div>
          </div>
          <Link
            href="/builder"
            className="border border-black bg-background px-6 py-2 text-center font-bold uppercase tracking-wide shadow-sw-sm transition-all hover:translate-x-[1px] hover:translate-y-[1px] hover:shadow-none"
          >
            {t('career.documents.edit')}
          </Link>
        </div>
      )}

      {loading ? (
        <p className="p-6 font-mono text-xs uppercase tracking-wide text-steel-grey">
          {t('career.documents.loading')}
        </p>
      ) : visible.length === 0 ? (
        <p className="p-6 text-sm text-ink-soft">{t('career.documents.empty')}</p>
      ) : (
        <ul>
          {visible.map((doc) => (
            <li
              key={doc.document_id}
              className="border-b border-black last:border-b-0 p-5 hover:bg-paper-tint"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 shrink-0 text-blue-700" aria-hidden="true" />
                    <h3 className="truncate font-bold uppercase tracking-wide text-black">
                      {doc.title}
                    </h3>
                  </div>
                  <p className="mt-1 font-mono text-xs uppercase tracking-wide text-steel-grey">
                    {t(`career.kinds.${doc.kind}`)} ·{' '}
                    {t('career.documents.charCount', { count: doc.char_count })}
                    {!doc.include_in_context && ` · ${t('career.documents.muted')}`}
                  </p>
                  {doc.preview && (
                    <p className="mt-2 line-clamp-2 text-xs text-ink-soft">{doc.preview}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <ToggleSwitch
                    checked={doc.include_in_context}
                    onCheckedChange={(next) => void handleToggleInclude(doc, next)}
                    label={t('career.documents.inCorpus')}
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditing(doc);
                      setEditorOpen(true);
                    }}
                  >
                    {t('career.documents.edit')}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t('career.documents.delete')}
                    onClick={() => setPendingDelete(doc)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <DocumentEditorDialog
        open={editorOpen}
        onOpenChange={setEditorOpen}
        document={editing}
        onSaved={() => void load()}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title={t('career.documents.delete')}
        description={t('career.documents.deleteConfirm')}
        confirmLabel={t('career.documents.delete')}
        cancelLabel={t('career.documents.cancel')}
        variant="danger"
        onConfirm={() => void handleDelete()}
      />
    </section>
  );
}
