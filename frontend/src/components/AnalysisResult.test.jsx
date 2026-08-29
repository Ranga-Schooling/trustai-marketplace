import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api';
import AnalysisResult from './AnalysisResult';

const ANALYSIS = {
  id: 42,
  risk_level: 'low',
  risk_score: 10,
  recommendation: 'buy',
  price_assessment: 'The price requires independent verification.',
  price_plausibility: 'plausible',
  summary: 'No obvious risk indicators were found.',
  risk_indicators: [],
  seller_questions: ['Can I inspect the item before paying?'],
  model_used: 'test-model',
};

describe('AnalysisResult', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('discloses text-only analysis and model-knowledge limitations', () => {
    render(
      <AnalysisResult
        analysis={ANALYSIS}
        onBack={vi.fn()}
        onViewHistory={vi.fn()}
      />,
    );

    expect(
      screen.getByText('Text-only analysis — photos from the listing URL were not inspected.'),
    ).toBeVisible();
    expect(
      screen.getByText(
        'Knowledge limitation — model knowledge may not include recently released products or current market conditions; verify time-sensitive claims with a current authoritative source.',
      ),
    ).toBeVisible();
  });

  it('exposes Visual Inspection only from a completed analysis result', () => {
    render(
      <AnalysisResult
        analysis={ANALYSIS}
        onBack={vi.fn()}
        onViewHistory={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('heading', { name: 'Add photos for visual inspection' }),
    ).toBeVisible();
  });

  it('keeps the Trust result intact after visual findings and after resetting them', async () => {
    const events = userEvent.setup();
    vi.spyOn(api, 'visualInspect').mockResolvedValue({
      findings: [
        {
          category: 'visible_damage',
          observation: 'Photo 1 visibly shows a scratch on the upper-right corner.',
          photo_numbers: [1],
        },
      ],
    });

    render(
      <AnalysisResult
        analysis={ANALYSIS}
        onBack={vi.fn()}
        onViewHistory={vi.fn()}
      />,
    );
    const photo = new File(['jpeg'], 'private-photo-name.jpg', { type: 'image/jpeg' });
    await events.upload(screen.getByLabelText('Choose photos'), photo);
    await events.click(
      screen.getByRole('checkbox', {
        name: /I consent to sending these photos to OpenAI for visual inspection/i,
      }),
    );
    await events.click(screen.getByRole('button', { name: 'Inspect photos' }));

    expect(
      await screen.findByText('Photo 1 visibly shows a scratch on the upper-right corner.'),
    ).toBeVisible();
    expect(screen.getByText('No obvious risk indicators were found.')).toBeVisible();
    expect(screen.getByText('The price requires independent verification.')).toBeVisible();
    expect(screen.getAllByText('Buy').length).toBeGreaterThan(0);
    expect(screen.getByText('10')).toBeVisible();

    await events.click(screen.getByRole('button', { name: 'Inspect another set' }));

    await waitFor(() => {
      expect(
        screen.queryByText('Photo 1 visibly shows a scratch on the upper-right corner.'),
      ).not.toBeInTheDocument();
    });
    expect(screen.getByText('No obvious risk indicators were found.')).toBeVisible();
    expect(screen.getByText('The price requires independent verification.')).toBeVisible();
    expect(screen.getAllByText('Buy').length).toBeGreaterThan(0);
    expect(screen.getByText('10')).toBeVisible();
  });
});
