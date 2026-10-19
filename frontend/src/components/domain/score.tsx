import { Check, Minus } from 'lucide-react'
import { SegmentBadge } from '@/components/domain/badges'
import { cn } from '@/lib/utils'
import type { Qualification, Segment } from '@/types/api'

const ringColor: Record<Segment, string> = { HOT: 'var(--hot)', WARM: 'var(--warm)', COLD: 'var(--cold)' }

export function ScoreRing({ score, segment, size = 88 }: { score: number; segment: Segment; size?: number }) {
  const stroke = 8
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} role="img" aria-label={`Score ${score} sur 100, segment ${segment}`} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--muted)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={ringColor[segment]}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - score / 100)}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
        <span className="text-2xl font-semibold tabular-nums">{score}</span>
        <span className="mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">/ 100</span>
      </div>
    </div>
  )
}

/** Score explicable : chaque facteur indique ses points, son plafond et la donnée utilisée. */
export function ScoreBreakdown({ qualification }: { qualification: Qualification }) {
  const exp = qualification.score_explanation
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <ScoreRing score={qualification.score} segment={qualification.segment} />
        <div className="space-y-1.5">
          <SegmentBadge segment={qualification.segment} />
          <p className="text-xs text-muted-foreground">
            Règles <span className="font-mono">{qualification.scoring_rule_version}</span> · calculé par le serveur, jamais par le modèle IA.
          </p>
          <p className="text-xs text-muted-foreground">
            HOT ≥ {exp.thresholds.HOT} · WARM ≥ {exp.thresholds.WARM} · le score aide au tri et ne rejette jamais un prospect.
          </p>
        </div>
      </div>
      <ul className="divide-y rounded-lg border">
        {exp.factors.map((f) => (
          <li key={f.id} className="flex items-start gap-3 p-3">
            <span
              className={cn(
                'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full',
                f.awarded ? 'bg-success-soft text-success' : 'bg-muted text-muted-foreground',
              )}
              aria-hidden
            >
              {f.awarded ? <Check className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{f.label}</span>
                <span className="shrink-0 text-sm tabular-nums">
                  <span className={f.awarded ? 'font-semibold' : 'text-muted-foreground'}>{f.points}</span>
                  <span className="text-xs text-muted-foreground"> / {f.max_points}</span>
                </span>
              </div>
              <p className="text-xs text-muted-foreground">{f.detail}</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
