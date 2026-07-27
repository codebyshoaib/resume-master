import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CareerDocuments } from '@/components/career/career-documents';

/**
 * Career documents panel.
 *
 * `t` is mocked to echo its key (the convention in this suite — see
 * dashboard-master-choice.test.tsx) so assertions survive copy edits. Params are
 * appended as JSON because the corpus-summary maths is real logic worth pinning.
 *
 * The pinned master-résumé row is the behaviour most worth locking down: it must
 * link to the Builder and expose no editable body or delete control, because the
 * corpus reads the master résumé live rather than copying it.
 */

vi.mock('@/lib/i18n', () => ({
  useTranslations: () => ({
    t: (key: string, params?: Record<string, string | number>) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
  }),
}));

const { listCareerDocuments, updateCareerDocument, deleteCareerDocument, fetchResumeList } =
  vi.hoisted(() => ({
    listCareerDocuments: vi.fn(),
    updateCareerDocument: vi.fn(),
    deleteCareerDocument: vi.fn(),
    fetchResumeList: vi.fn(),
  }));

vi.mock('@/lib/api/career', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/career')>();
  return {
    ...actual,
    listCareerDocuments,
    updateCareerDocument,
    deleteCareerDocument,
    uploadCareerDocument: vi.fn(),
    fetchCareerDocument: vi.fn().mockResolvedValue({ content: 'body' }),
    createCareerDocument: vi.fn(),
  };
});

vi.mock('@/lib/api/resume', () => ({ fetchResumeList }));

const doc = (over: Record<string, unknown> = {}) => ({
  document_id: 'd1',
  title: '2024 Review',
  kind: 'review',
  filename: 'review.pdf',
  include_in_context: true,
  preview: 'Led the SQLite migration.',
  char_count: 25,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...over,
});

const MASTER = {
  resume_id: 'm1',
  filename: 'master.pdf',
  is_master: true,
  parent_id: null,
  processing_status: 'ready' as const,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('CareerDocuments', () => {
  beforeEach(() => {
    listCareerDocuments.mockResolvedValue({ documents: [doc()] });
    updateCareerDocument.mockResolvedValue(doc({ include_in_context: false }));
    deleteCareerDocument.mockResolvedValue(undefined);
    fetchResumeList.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders a document row with its title and preview', async () => {
    render(<CareerDocuments />);
    expect(await screen.findByText('2024 Review')).toBeTruthy();
    expect(screen.getByText('Led the SQLite migration.')).toBeTruthy();
  });

  it('shows the empty state when there are no documents', async () => {
    listCareerDocuments.mockResolvedValue({ documents: [] });
    render(<CareerDocuments />);
    expect(await screen.findByText('career.documents.empty')).toBeTruthy();
  });

  it('surfaces a load failure rather than rendering an empty corpus as success', async () => {
    listCareerDocuments.mockRejectedValue(new Error('backend down'));
    render(<CareerDocuments />);
    expect(await screen.findByRole('alert')).toHaveTextContent('backend down');
  });

  it('counts only included documents in the corpus summary', async () => {
    listCareerDocuments.mockResolvedValue({
      documents: [
        doc({ document_id: 'a', char_count: 100 }),
        doc({ document_id: 'b', char_count: 900, include_in_context: false }),
      ],
    });
    render(<CareerDocuments />);
    // The muted document contributes neither to the count nor the char total.
    expect(
      await screen.findByText('career.documents.summary:{"count":1,"chars":"100"}')
    ).toBeTruthy();
  });

  it('filters the list by kind', async () => {
    listCareerDocuments.mockResolvedValue({
      documents: [
        doc({ document_id: 'a', title: 'A review', kind: 'review' }),
        doc({ document_id: 'b', title: 'B brag', kind: 'brag' }),
      ],
    });
    render(<CareerDocuments />);
    await screen.findByText('A review');
    fireEvent.click(screen.getByRole('button', { name: /career.documents.filterAll/ }));
    fireEvent.click(screen.getByText('career.kinds.brag'));
    await waitFor(() => expect(screen.queryByText('A review')).toBeNull());
    expect(screen.getByText('B brag')).toBeTruthy();
  });

  it('mutes a document from the corpus via the toggle', async () => {
    render(<CareerDocuments />);
    await screen.findByText('2024 Review');
    fireEvent.click(screen.getByRole('switch'));
    await waitFor(() =>
      expect(updateCareerDocument).toHaveBeenCalledWith('d1', { include_in_context: false })
    );
  });

  it('does not delete until the confirmation is accepted', async () => {
    render(<CareerDocuments />);
    await screen.findByText('2024 Review');
    fireEvent.click(screen.getByRole('button', { name: 'career.documents.delete' }));
    // The dialog is open, but nothing is deleted yet.
    expect(deleteCareerDocument).not.toHaveBeenCalled();
    const confirms = screen.getAllByRole('button', { name: 'career.documents.delete' });
    fireEvent.click(confirms[confirms.length - 1]);
    await waitFor(() => expect(deleteCareerDocument).toHaveBeenCalledWith('d1'));
  });

  describe('pinned master résumé', () => {
    beforeEach(() => {
      fetchResumeList.mockResolvedValue([MASTER]);
    });

    it('renders it as a Builder link, not an editable document', async () => {
      render(<CareerDocuments />);
      expect(await screen.findByText('career.masterResume.label')).toBeTruthy();
      const link = screen.getByRole('link');
      expect(link.getAttribute('href')).toBe('/builder');
    });

    it('explains that it is linked rather than copied', async () => {
      render(<CareerDocuments />);
      expect(await screen.findByText('career.masterResume.hint')).toBeTruthy();
    });

    it('is not offered a delete control', async () => {
      render(<CareerDocuments />);
      await screen.findByText('career.masterResume.label');
      // Only the single real document row has a delete button.
      expect(screen.getAllByRole('button', { name: 'career.documents.delete' })).toHaveLength(1);
    });

    it('is omitted when no master résumé exists yet', async () => {
      fetchResumeList.mockResolvedValue([]);
      render(<CareerDocuments />);
      await screen.findByText('2024 Review');
      expect(screen.queryByText('career.masterResume.label')).toBeNull();
    });
  });
});
