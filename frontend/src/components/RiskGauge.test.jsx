import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import RiskGauge from './RiskGauge';

function needleRotation(container) {
  const needle = container.querySelector('.gauge-needle-group');
  expect(needle).not.toBeNull();

  const match = needle.style.transform.match(/^rotate\((-?\d+(?:\.\d+)?)deg\)$/);
  expect(match).not.toBeNull();
  return Number(match[1]);
}

describe('RiskGauge', () => {
  it.each([
    { score: 0, expectedRotation: -90, level: 'low', recommendation: 'buy', label: 'Buy' },
    { score: 33, expectedRotation: -30.6, level: 'low', recommendation: 'buy', label: 'Buy' },
    { score: 34, expectedRotation: -28.8, level: 'medium', recommendation: 'caution', label: 'Caution' },
    { score: 66, expectedRotation: 28.8, level: 'medium', recommendation: 'caution', label: 'Caution' },
    { score: 67, expectedRotation: 30.6, level: 'high', recommendation: 'avoid', label: 'Avoid' },
    { score: 100, expectedRotation: 90, level: 'high', recommendation: 'avoid', label: 'Avoid' },
  ])(
    'maps score $score to $expectedRotation degrees in the $level tier',
    ({ score, expectedRotation, level, recommendation, label }) => {
      const { container } = render(
        <RiskGauge riskScore={score} recommendation={recommendation} level={level} />,
      );

      expect(needleRotation(container)).toBeCloseTo(expectedRotation, 5);
      expect(container.querySelector('.gauge-needle')).toHaveClass(`gauge-needle-${level}`);
      expect(screen.getByText(label)).toHaveClass('gauge-status', level);
    },
  );

  it('clamps a score below zero to the start of the gauge', () => {
    const { container } = render(<RiskGauge riskScore={-10} recommendation="buy" level="low" />);

    expect(needleRotation(container)).toBeCloseTo(-90, 5);
    expect(container.querySelector('.gauge-score')).toHaveTextContent('0 / 100');
  });

  it('clamps a score above 100 to the end of the gauge', () => {
    const { container } = render(<RiskGauge riskScore={110} recommendation="avoid" level="high" />);

    expect(needleRotation(container)).toBeCloseTo(90, 5);
    expect(container.querySelector('.gauge-score')).toHaveTextContent('100 / 100');
  });

  it('keeps an absent score at the gauge start and renders the existing fallback copy', () => {
    const { container } = render(<RiskGauge />);

    expect(needleRotation(container)).toBeCloseTo(-90, 5);
    expect(container.querySelector('.gauge-score')).toHaveTextContent('— / 100');
    expect(screen.getByText('Review')).toHaveClass('gauge-status', 'low');
  });

  it('displays the clamped numeric score independently of the needle animation', () => {
    const { container } = render(
      <RiskGauge riskScore={54} recommendation="caution" level="medium" />,
    );

    expect(container.querySelector('.gauge-score')).toHaveTextContent('54 / 100');
  });
});
