import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { CareerAnswerPanel } from '@/components/career/career-answer';

/**
 * Career answer panel. `t` echoes its key (suite convention).
 *
 * The behaviours worth pinning are all about *trust*: an answer with no
 * citations must be visibly flagged rather than presented as verified, gaps must
 * render, and an empty corpus must disable asking instead of firing a request
 * that can only 422.
 */

vi.mock('@/lib/i18n', () => ({
  useTranslations: () => ({
    t: (key: string, params?: Record<string, string | number>) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
  }),
}));

const { answerCareerQuestion } = vi.hoisted(() => ({ answerCareerQuestion: vi.fn() }));

vi.mock('@/lib/api/career', () => ({ answerCareerQuestion }));

const ask = (question = 'Describe a time you led a project.') => {
  fireEvent.change(screen.getByLabelText('career.answer.questionLabel'), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole('button', { name: 'career.answer.ask' }));
};

describe('CareerAnswerPanel', () => {
  beforeEach(() => {
    answerCareerQuestion.mockResolvedValue({
      answer: 'I led the SQLite migration.',
      used_sources: [{ source_id: 'd1', kind: 'document', title: '2024 Review' }],
      gaps: [],
      truncated: false,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders the answer and its citations', async () => {
    render(<CareerAnswerPanel sourceCount={2} />);
    ask();
    expect(await screen.findByText('I led the SQLite migration.')).toBeTruthy();
    expect(screen.getByText('2024 Review')).toBeTruthy();
  });

  it('sends the question, tone and word limit', async () => {
    render(<CareerAnswerPanel sourceCount={2} />);
    fireEvent.change(screen.getByLabelText('career.answer.toneLabel'), {
      target: { value: 'blunt' },
    });
    fireEvent.change(screen.getByLabelText('career.answer.maxWordsLabel'), {
      target: { value: '120' },
    });
    ask('Why this company?');
    await waitFor(() =>
      expect(answerCareerQuestion).toHaveBeenCalledWith({
        question: 'Why this company?',
        tone: 'blunt',
        max_words: 120,
      })
    );
  });

  it('omits an empty tone rather than sending a blank string', async () => {
    render(<CareerAnswerPanel sourceCount={2} />);
    ask();
    await waitFor(() =>
      expect(answerCareerQuestion).toHaveBeenCalledWith(
        expect.objectContaining({ tone: undefined })
      )
    );
  });

  it('flags an uncited answer instead of presenting it as verified', async () => {
    answerCareerQuestion.mockResolvedValue({
      answer: 'I am a strong communicator.',
      used_sources: [],
      gaps: [],
      truncated: false,
    });
    render(<CareerAnswerPanel sourceCount={2} />);
    ask();
    // Without this warning an ungrounded answer looks the same as a sourced one.
    expect(await screen.findByText('career.answer.noSources')).toBeTruthy();
  });

  it('renders gaps so an honest partial answer is legible', async () => {
    answerCareerQuestion.mockResolvedValue({
      answer: 'I have not managed a team that size.',
      used_sources: [],
      gaps: ['No evidence of managing 50+ people'],
      truncated: false,
    });
    render(<CareerAnswerPanel sourceCount={2} />);
    ask();
    expect(await screen.findByText('No evidence of managing 50+ people')).toBeTruthy();
  });

  it('warns when the corpus was truncated', async () => {
    answerCareerQuestion.mockResolvedValue({
      answer: 'a',
      used_sources: [{ source_id: 'd1', kind: 'document', title: 'D' }],
      gaps: [],
      truncated: true,
    });
    render(<CareerAnswerPanel sourceCount={2} />);
    ask();
    expect(await screen.findByText('career.answer.truncated')).toBeTruthy();
  });

  it('surfaces a backend error', async () => {
    answerCareerQuestion.mockRejectedValue(new Error('No career material yet.'));
    render(<CareerAnswerPanel sourceCount={2} />);
    ask();
    expect(await screen.findByRole('alert')).toHaveTextContent('No career material yet.');
  });

  it('does not ask on an empty question', () => {
    render(<CareerAnswerPanel sourceCount={2} />);
    fireEvent.click(screen.getByRole('button', { name: 'career.answer.ask' }));
    expect(answerCareerQuestion).not.toHaveBeenCalled();
  });

  describe('empty corpus', () => {
    it('explains why and blocks the request', () => {
      render(<CareerAnswerPanel sourceCount={0} />);
      expect(screen.getByText('career.answer.emptyCorpus')).toBeTruthy();
      fireEvent.change(screen.getByLabelText('career.answer.questionLabel'), {
        target: { value: 'anything' },
      });
      fireEvent.click(screen.getByRole('button', { name: 'career.answer.ask' }));
      // Firing a request that can only 422 would be a worse experience than
      // disabling the control.
      expect(answerCareerQuestion).not.toHaveBeenCalled();
    });
  });
});
