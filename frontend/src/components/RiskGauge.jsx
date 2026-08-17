import { useEffect, useState } from 'react';

const RECOMMENDATION_LABEL = {
  buy: 'Buy',
  caution: 'Caution',
  avoid: 'Avoid',
};

export default function RiskGauge({ riskScore, recommendation, level }) {
  const [mounted, setMounted] = useState(false);
  const score = typeof riskScore === 'number' ? Math.max(0, Math.min(100, riskScore)) : null;
  const recommendationLabel = RECOMMENDATION_LABEL[recommendation] || 'Review';
  const resolvedLevel = level || 'low';
  const targetRotation = score === null ? 20 : 20 + (score / 100) * 140;

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="risk-gauge card gauge-card">
      <div className="gauge-frame">
        <svg viewBox="0 0 220 120" className="gauge-svg" aria-hidden="true">
          {/*
            Zone boundaries follow the backend TIER_RANGES (low 0-33 / medium 34-66 / high 67-100),
            split along the same circle implied by the original full-arc endpoints (30,100)-(190,100)
            with r=90, so all three segments still trace one continuous semicircle.
            NOTE: this assumes low/buy sits on the left and high/avoid on the right — flip the three
            paths below if the wireframe intends the opposite direction.
          */}
          <path d="M 30 100 A 90 90 0 0 1 77 57" className="gauge-arc gauge-arc-buy" />
          <path d="M 77 57 A 90 90 0 0 1 143 57" className="gauge-arc gauge-arc-caution" />
          <path d="M 143 57 A 90 90 0 0 1 190 100" className="gauge-arc gauge-arc-avoid" />
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
          <g
            className="gauge-needle-group"
            style={{
              transform: mounted ? `rotate(${targetRotation}deg)` : 'rotate(20deg)',
              transformOrigin: '110px 100px',
            }}
          >
            <line x1="110" y1="100" x2="110" y2="30" className={`gauge-needle gauge-needle-${resolvedLevel}`} />
            <circle cx="110" cy="100" r="8" className="gauge-center" />
          </g>
        </svg>
      </div>

      <div className="gauge-copy">
        <p className="eyebrow">Trust dial</p>
        <p className="gauge-score">
          {score !== null ? score : '—'} <span>/ 100</span>
        </p>
        <p className={`gauge-status ${resolvedLevel}`}>{recommendationLabel}</p>
      </div>
    </div>
  );
}
