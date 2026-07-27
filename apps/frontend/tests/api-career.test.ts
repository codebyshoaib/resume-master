import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createCareerDocument,
  deleteCareerDocument,
  fetchCareerDocument,
  listCareerDocuments,
  updateCareerDocument,
  uploadCareerDocument,
} from '@/lib/api/career';

/**
 * Career corpus API client contracts: each wrapper must hit the right
 * method/URL, send the right payload, and surface the backend's own error
 * message rather than a generic one.
 */

describe('career API client', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const lastCall = () => {
    const [url, options] = fetchMock.mock.calls.at(-1)!;
    return { url: String(url), options: (options ?? {}) as RequestInit };
  };

  const ok = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });

  it('lists documents without a kind filter', async () => {
    fetchMock.mockResolvedValue(ok({ documents: [] }));
    const result = await listCareerDocuments();
    expect(result.documents).toEqual([]);
    expect(lastCall().url).toContain('/career/documents');
    expect(lastCall().url).not.toContain('kind=');
  });

  it('passes the kind filter as a query param', async () => {
    fetchMock.mockResolvedValue(ok({ documents: [] }));
    await listCareerDocuments('review');
    expect(lastCall().url).toContain('kind=review');
  });

  it('fetches a single document by id', async () => {
    fetchMock.mockResolvedValue(ok({ document_id: 'd1', content: 'body' }));
    const doc = await fetchCareerDocument('d1');
    expect(doc.content).toBe('body');
    expect(lastCall().url).toContain('/career/documents/d1');
  });

  it('creates a document with a JSON POST', async () => {
    fetchMock.mockResolvedValue(ok({ document_id: 'd1' }, 201));
    await createCareerDocument({ title: 'Review', content: 'text', kind: 'review' });
    const { url, options } = lastCall();
    expect(url).toContain('/career/documents');
    expect(options.method).toBe('POST');
    expect(JSON.parse(String(options.body))).toEqual({
      title: 'Review',
      content: 'text',
      kind: 'review',
    });
  });

  it('uploads a file as multipart with the kind in the query string', async () => {
    fetchMock.mockResolvedValue(ok({ document_id: 'd1' }, 201));
    const file = new File(['hello'], 'review.pdf', { type: 'application/pdf' });
    await uploadCareerDocument(file, 'review');
    const { url, options } = lastCall();
    expect(url).toContain('/career/documents/upload');
    expect(url).toContain('kind=review');
    expect(options.method).toBe('POST');
    expect(options.body).toBeInstanceOf(FormData);
    // Setting Content-Type by hand would clobber the multipart boundary.
    expect(options.headers).toBeUndefined();
  });

  it('patches only the supplied fields', async () => {
    fetchMock.mockResolvedValue(ok({ document_id: 'd1', title: 'New' }));
    await updateCareerDocument('d1', { title: 'New' });
    const { url, options } = lastCall();
    expect(url).toContain('/career/documents/d1');
    expect(options.method).toBe('PATCH');
    expect(JSON.parse(String(options.body))).toEqual({ title: 'New' });
  });

  it('deletes without parsing a body (204 has none)', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(deleteCareerDocument('d1')).resolves.toBeUndefined();
    expect(lastCall().options.method).toBe('DELETE');
  });

  it('surfaces the backend detail message on failure', async () => {
    fetchMock.mockResolvedValue(ok({ detail: 'Document not found' }, 404));
    await expect(fetchCareerDocument('nope')).rejects.toThrow('Document not found');
  });

  it('flattens FastAPI validation errors into one message', async () => {
    fetchMock.mockResolvedValue(
      ok(
        { detail: [{ msg: 'String should have at least 1 character', loc: ['body', 'title'] }] },
        422
      )
    );
    await expect(createCareerDocument({ title: '', content: 'x' })).rejects.toThrow(
      'String should have at least 1 character'
    );
  });

  it('surfaces the upload error detail rather than a bare status', async () => {
    fetchMock.mockResolvedValue(ok({ detail: 'Invalid file type: image/png' }, 400));
    const file = new File(['x'], 'a.png', { type: 'image/png' });
    await expect(uploadCareerDocument(file)).rejects.toThrow('Invalid file type: image/png');
  });
});
