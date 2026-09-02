import { useEffect, useState } from 'react';

const RECOMMENDATION_LABEL = {
  buy: 'Buy',
  caution: 'Caution',
  avoid: 'Avoid',
};

const GAUGE_CENTER = { x: 110, y: 100 };
const GAUGE_RADIUS = 80;
// Keep these visual half-step boundaries synchronized with TIER_RANGES in
// backend/app/services/scoring.py: 33.5/66.5 separate the integer 0–33,
// 34–66, and 67–100 tiers; backend threshold changes require updates here.
const GAUGE_ZONES = [
  { start: 0, end: 33.5, className: 'gauge-arc-buy' },
  { start: 33.5, end: 66.5, className: 'gauge-arc-caution' },
  { start: 66.5, end: 100, className: 'gauge-arc-avoid' },
];
const TICK_SCORES = [0, 20, 40, 60, 80, 100];

function scoreToRotation(score) {
  return -90 + score * 1.8;
}

function pointAtScore(score, radius) {
  const radians = (scoreToRotation(score) * Math.PI) / 180;
  return {
    x: GAUGE_CENTER.x + Math.sin(radians) * radius,
    y: GAUGE_CENTER.y - Math.cos(radians) * radius,
  };
}

function arcPath(startScore, endScore) {
  const start = pointAtScore(startScore, GAUGE_RADIUS);
  const end = pointAtScore(endScore, GAUGE_RADIUS);
  return `M ${start.x} ${start.y} A ${GAUGE_RADIUS} ${GAUGE_RADIUS} 0 0 1 ${end.x} ${end.y}`;
}

export default function RiskGauge({ riskScore, recommendation, level }) {
  const [mounted, setMounted] = useState(false);
  const score = typeof riskScore === 'number' ? Math.max(0, Math.min(100, riskScore)) : null;
  const recommendationLabel = RECOMMENDATION_LABEL[recommendation] || 'Review';
  const resolvedLevel = level || 'low';
  const startRotation = scoreToRotation(0);
  const targetRotation = score === null ? startRotation : scoreToRotation(score);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <div className="risk-gauge card gauge-card">
      <div className="gauge-frame">
        <svg viewBox="0 0 220 120" className="gauge-svg" aria-hidden="true">
          {GAUGE_ZONES.map((zone) => (
            <path
              key={zone.className}
              d={arcPath(zone.start, zone.end)}
              className={`gauge-arc ${zone.className}`}
            />
          ))}
          <g className="gauge-ticks">
            {TICK_SCORES.map((tickScore) => {
              const inner = pointAtScore(tickScore, 58);
              const outer = pointAtScore(tickScore, 72);
              return (
                <line
                  key={tickScore}
                  x1={inner.x}
                  y1={inner.y}
                  x2={outer.x}
                  y2={outer.y}
                  className="gauge-tick"
                />
              );
            })}
          </g>
          <g
            className="gauge-needle-group"
            style={{
              transform: `rotate(${mounted ? targetRotation : startRotation}deg)`,
              transformOrigin: `${GAUGE_CENTER.x}px ${GAUGE_CENTER.y}px`,
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
