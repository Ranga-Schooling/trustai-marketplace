import { useEffect, useState } from 'react';

const scoreToRecommendation = (score) => {
  if (score === null) return 'Review';
  if (score < 40) return 'Buy';
  if (score < 70) return 'Caution';
  return 'Avoid';
};

const scoreToLevel = (score) => {
  if (score === null) return 'low';
  if (score < 40) return 'low';
  if (score < 70) return 'medium';
  return 'high';
};

export default function RiskGauge({ riskScore }) {
  const [mounted, setMounted] = useState(false);
  const score = typeof riskScore === 'number' ? Math.max(0, Math.min(100, riskScore)) : null;
  const recommendation = scoreToRecommendation(score);
  const level = scoreToLevel(score);
  const targetRotation = score === null ? 20 : 20 + (score / 100) * 140;

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="risk-gauge card gauge-card">
      <div className="gauge-frame">
        <svg viewBox="0 0 220 120" className="gauge-svg" aria-hidden="true">
          <path d="M 30 100 A 90 90 0 0 1 190 100" className="gauge-arc gauge-arc-buy" />
          <path d="M 30 100 A 90 90 0 0 1 190 100" className="gauge-arc gauge-arc-caution" />
          <path d="M 30 100 A 90 90 0 0 1 190 100" className="gauge-arc gauge-arc-avoid" />
          <g className="gauge-ticks">
            {Array.from({ length: 6 }).map((_, index) => {
              const angle = 20 + index * 28;
              const radians = (angle * Math.PI) / 180;
              const innerX = 110 + Math.cos(radians) * 58;
              const innerY = 100 - Math.sin(radians) * 58;
              const outerX = 110 + Math.cos(radians) * 72;
              const outerY = 100 - Math.sin(radians) * 72;
              return (
                <line
                  key={angle}
                  x1={innerX}
                  y1={innerY}
                  x2={outerX}
                  y2={outerY}
                  className="gauge-tick"
                />
              );
            })}
          </g>
          <g className="gauge-needle-group" style={{ transform: mounted ? `rotate(${targetRotation}deg)` : 'rotate(20deg)' }}>
            <line x1="110" y1="100" x2="110" y2="30" className={`gauge-needle gauge-needle-${level}`} />
            <circle cx="110" cy="100" r="8" className="gauge-center" />
          </g>
        </svg>
      </div>

      <div className="gauge-copy">
        <p className="eyebrow">Trust dial</p>
        <p className="gauge-score">
          {score !== null ? score : '—'} <span>/ 100</span>
        </p>
        <p className={`gauge-status ${level}`}>{recommendation}</p>
      </div>
    </div>
  );
}
