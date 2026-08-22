import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import AnalysisResult from './AnalysisResult';

describe('AnalysisResult', () => {
  it('discloses text-only analysis and model-knowledge limitations', () => {
    render(
      <AnalysisResult
        analysis={{
          risk_level: 'low',
          risk_score: 10,
          recommendation: 'buy',
          price_assessment: 'The price requires independent verification.',
          price_plausibility: 'plausible',
          summary: 'No obvious risk indicators were found.',
          risk_indicators: [],
          seller_questions: ['Can I inspect the item before paying?'],
          model_used: 'test-model',
        }}
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
});
