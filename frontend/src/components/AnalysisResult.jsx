// E5 Frontend (owner: Adrian) — US-3.1 result view.
// Render: verdict banner (recommendation + risk_level, colored by
// .verdict.low/.medium/.high), summary, price assessment, indicators
// (.indicator + .badge classes), seller questions, model_used.
// Empty indicators must still say "does not guarantee the listing is safe".
export default function AnalysisResult({ analysis, onBack }) {
  return (
    <div>
      <div className={`verdict ${analysis.risk_level}`}>
        <span className="word">TODO</span>
      </div>
      <button className="ghost" onClick={onBack}>Back</button>
    </div>
  );
}
