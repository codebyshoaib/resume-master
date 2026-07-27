import { API_BASE, apiFetch, apiPost, apiPatch, apiDelete, asJson, extractDetail } from './client';

// What a document is. Mirrors CareerDocumentKind in app/schemas/career.py.
export type CareerDocumentKind =
  | 'resume'
  | 'review'
  | 'brag'
  | 'project'
  | 'jd'
  | 'ladder'
  | 'other';

export const CAREER_DOCUMENT_KINDS: CareerDocumentKind[] = [
  'review',
  'brag',
  'project',
  'resume',
  'jd',
  'ladder',
  'other',
];

// A document as returned by the list endpoint: body truncated to a preview.
export interface CareerDocumentSummary {
  document_id: string;
  title: string;
  kind: CareerDocumentKind;
  filename: string | null;
  include_in_context: boolean;
  preview: string;
  char_count: number;
  created_at: string;
  updated_at: string;
}

// A single document with its full body (only the detail endpoint returns this).
export interface CareerDocument extends CareerDocumentSummary {
  content: string;
}

export interface CareerDocumentListResponse {
  documents: CareerDocumentSummary[];
}

export interface CareerDocumentCreate {
  title: string;
  content: string;
  kind?: CareerDocumentKind;
}

export interface CareerDocumentUpdate {
  title?: string;
  content?: string;
  kind?: CareerDocumentKind;
  include_in_context?: boolean;
}

// List documents, oldest first. Bodies are previews — fetch one to get its text.
export async function listCareerDocuments(
  kind?: CareerDocumentKind
): Promise<CareerDocumentListResponse> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  const res = await apiFetch(`/career/documents${query}`, { credentials: 'include' });
  return asJson<CareerDocumentListResponse>(res, 'Failed to load career documents');
}

// Fetch one document with its full body.
export async function fetchCareerDocument(documentId: string): Promise<CareerDocument> {
  const res = await apiFetch(`/career/documents/${documentId}`, { credentials: 'include' });
  return asJson<CareerDocument>(res, 'Failed to load document');
}

// Create a document from pasted text.
export async function createCareerDocument(payload: CareerDocumentCreate): Promise<CareerDocument> {
  const res = await apiPost('/career/documents', payload);
  return asJson<CareerDocument>(res, 'Failed to save document');
}

// Upload a document file (PDF/DOC/DOCX/TXT/MD); the backend extracts its text.
export async function uploadCareerDocument(
  file: File,
  kind: CareerDocumentKind = 'other'
): Promise<CareerDocument> {
  const body = new FormData();
  body.append('file', file);
  // FormData sets its own multipart boundary — never set Content-Type here.
  const res = await fetch(`${API_BASE}/career/documents/upload?kind=${encodeURIComponent(kind)}`, {
    method: 'POST',
    body,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(extractDetail(data) || `Upload failed (status ${res.status}).`);
  }
  return res.json() as Promise<CareerDocument>;
}

// Patch a document. Omitted fields are left untouched.
export async function updateCareerDocument(
  documentId: string,
  payload: CareerDocumentUpdate
): Promise<CareerDocument> {
  const res = await apiPatch(`/career/documents/${documentId}`, payload);
  return asJson<CareerDocument>(res, 'Failed to update document');
}

// Delete a document. The endpoint returns 204, so there is no body to parse.
export async function deleteCareerDocument(documentId: string): Promise<void> {
  const res = await apiDelete(`/career/documents/${documentId}`);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(extractDetail(data) || `Failed to delete document (status ${res.status}).`);
  }
}
