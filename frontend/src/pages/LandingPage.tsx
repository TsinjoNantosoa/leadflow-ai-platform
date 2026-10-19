import {
  ArrowRight,
  BrainCircuit,
  ClipboardCheck,
  Database,
  FileCheck2,
  Gauge,
  GitBranch,
  Inbox,
  Layers,
  Lock,
  ScanSearch,
  ShieldCheck,
  Workflow,
} from 'lucide-react'
import type * as React from 'react'
import { Link } from 'react-router-dom'
import { SegmentBadge } from '@/components/domain/badges'
import { ScoreRing } from '@/components/domain/score'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

const FEATURES: { icon: React.ElementType; title: string; text: string }[] = [
  {
    icon: ScanSearch,
    title: 'Compréhension de la demande',
    text: 'Intention, service, budget, échéance et langue extraits par IA sous un schéma strict. Rien n’est inventé : une donnée absente reste vide.',
  },
  {
    icon: Gauge,
    title: 'Score explicable',
    text: 'Cinq règles versionnées calculées par le serveur, pas par le modèle. Chaque point attribué est justifié et auditable.',
  },
  {
    icon: Database,
    title: 'CRM synchronisé sans doublon',
    text: 'Création ou mise à jour HubSpot (ou CRM factice en démo), recherche avant création, reprise sûre après timeout.',
  },
  {
    icon: FileCheck2,
    title: 'Revue humaine obligatoire',
    text: 'Un brouillon de réponse est préparé, relu, modifié puis approuvé ou rejeté par un commercial. Aucun envoi automatique.',
  },
  {
    icon: Workflow,
    title: 'Automatisations observables',
    text: 'Chaque exécution n8n est tracée : durées, tentatives, codes d’erreur, identifiants de corrélation et reprise manuelle.',
  },
  {
    icon: Lock,
    title: 'Fiabilité et sécurité',
    text: 'Outbox transactionnelle, idempotence, sessions serveur, secrets hors du navigateur et protection contre l’injection de prompt.',
  },
]

const STEPS: { icon: React.ElementType; label: string; sub: string }[] = [
  { icon: Inbox, label: 'Formulaire', sub: 'React · validation' },
  { icon: Layers, label: 'API FastAPI', sub: 'lead + outbox atomiques' },
  { icon: Workflow, label: 'n8n', sub: 'orchestration' },
  { icon: BrainCircuit, label: 'OpenAI', sub: 'extraction structurée' },
  { icon: ClipboardCheck, label: 'Score & CRM', sub: 'règles serveur' },
  { icon: FileCheck2, label: 'Revue humaine', sub: 'brouillon DRAFT' },
]

export default function LandingPage() {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="bg-grid absolute inset-0 -z-10" aria-hidden />
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 sm:py-24 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-6">
            <span className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground shadow-xs">
              <span className="h-1.5 w-1.5 rounded-full bg-success" aria-hidden /> Prototype fonctionnel · données fictives
            </span>
            <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl">
              Qualifiez vos demandes commerciales, <span className="text-primary">sans perdre le contrôle.</span>
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground">
              LeadFlow AI reçoit une demande, comprend le besoin, calcule un score explicable, synchronise votre CRM et prépare une réponse que
              votre équipe valide avant toute action.
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button asChild size="lg">
                <Link to="/demo">
                  Tester la démo <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link to="/login">Accéder au tableau de bord</Link>
              </Button>
            </div>
            <ul className="flex flex-wrap gap-x-6 gap-y-2 pt-2 text-sm text-muted-foreground">
              <li className="flex items-center gap-1.5"><ShieldCheck className="h-4 w-4 text-success" aria-hidden /> Aucun envoi d’e-mail automatique</li>
              <li className="flex items-center gap-1.5"><GitBranch className="h-4 w-4 text-success" aria-hidden /> Score déterministe</li>
              <li className="flex items-center gap-1.5"><Lock className="h-4 w-4 text-success" aria-hidden /> Sessions serveur</li>
            </ul>
          </div>

          {/* Aperçu illustratif — exemple de sortie, pas une donnée en direct */}
          <Card className="relative overflow-hidden p-5" aria-label="Exemple illustratif de qualification">
            <p className="mb-4 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Exemple illustratif (scénario fictif)</p>
            <div className="flex items-center gap-4">
              <ScoreRing score={100} segment="HOT" />
              <div className="min-w-0 space-y-1">
                <p className="font-medium">Alice Martin</p>
                <p className="text-xs text-muted-foreground">NovaDigital Demo · Automatisation du support client</p>
                <SegmentBadge segment="HOT" />
              </div>
            </div>
            <ul className="mt-5 space-y-2 text-sm">
              {[
                ['Service du catalogue', '30/30'],
                ['Budget conforme (3 000 € ≥ 2 000 €)', '25/25'],
                ['Échéance courte (30 jours)', '20/20'],
                ['Besoin explicite', '15/15'],
                ['Coordonnées complètes', '10/10'],
              ].map(([l, p]) => (
                <li key={l} className="flex items-center justify-between rounded-md bg-muted/60 px-3 py-1.5">
                  <span>{l}</span>
                  <span className="font-mono text-xs text-success">{p}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 rounded-md border border-dashed p-3 text-xs text-muted-foreground">
              Brouillon préparé · <strong>en attente de validation humaine</strong> · aucun envoi.
            </p>
          </Card>
        </div>
      </section>

      {/* Fonctionnalités */}
      <section id="fonctionnalites" className="border-t bg-muted/30">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <h2 className="text-3xl font-semibold tracking-tight">Une chaîne complète, de la demande au brouillon</h2>
            <p className="mt-3 text-muted-foreground">Chaque étape est persistée, observable et reprenable.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <Card key={title} className="p-5 transition-shadow hover:shadow-md">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-primary-soft text-primary">
                  <Icon className="h-5 w-5" aria-hidden />
                </div>
                <h3 className="font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{text}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Architecture */}
      <section id="architecture" className="border-t">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
          <div className="mx-auto mb-10 max-w-2xl text-center">
            <h2 className="text-3xl font-semibold tracking-tight">Architecture fonctionnelle</h2>
            <p className="mt-3 text-muted-foreground">
              PostgreSQL est la source de vérité. FastAPI contrôle chaque écriture métier ; n8n orchestre ; l’IA extrait et rédige mais ne décide jamais.
            </p>
          </div>
          <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6" aria-label="Étapes du pipeline">
            {STEPS.map(({ icon: Icon, label, sub }, i) => (
              <li key={label} className="relative">
                <Card className="flex h-full flex-col items-center gap-2 p-4 text-center">
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground">
                    <Icon className="h-5 w-5" aria-hidden />
                  </span>
                  <span className="text-sm font-semibold">
                    <span className="mr-1 text-muted-foreground">{i + 1}.</span>
                    {label}
                  </span>
                  <span className="text-xs text-muted-foreground">{sub}</span>
                </Card>
              </li>
            ))}
          </ol>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {[
              ['Outbox transactionnelle', 'La demande et son événement sont écrits dans la même transaction. La confirmation ne dépend ni de l’IA ni du CRM.'],
              ['Une seule autorité de reprise', 'Le backend décide des tentatives (backoff, dead-letter). n8n exécute, il ne réessaie pas de son côté.'],
              ['Indépendance des briques', 'Frontend, API, base et n8n se déploient séparément et communiquent en HTTPS.'],
            ].map(([t, d]) => (
              <div key={t} className="rounded-lg border bg-card p-4">
                <p className="text-sm font-semibold">{t}</p>
                <p className="mt-1 text-sm text-muted-foreground">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* NovaDigital */}
      <section id="novadigital" className="border-t bg-muted/30">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:items-center">
          <div className="space-y-4">
            <h2 className="text-3xl font-semibold tracking-tight">Cas d’usage : l’agence NovaDigital</h2>
            <p className="text-muted-foreground">
              NovaDigital est une agence <strong>fictive</strong> spécialisée en sites web, automatisation et solutions IA. Ses prospects arrivent par un
              formulaire ; ses commerciaux veulent trier vite, comprendre pourquoi un lead est chaud, et répondre avec un texte relu.
            </p>
            <ul className="space-y-2 text-sm">
              {[
                'Un commercial ouvre un lead et voit la demande d’origine, les informations extraites et le détail du score.',
                'Un manager repère les automatisations en échec et relance en un clic.',
                'Un administrateur garde la maîtrise : aucune réponse ne part sans décision humaine.',
              ].map((t) => (
                <li key={t} className="flex gap-2">
                  <ClipboardCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />
                  {t}
                </li>
              ))}
            </ul>
            <Button asChild size="lg" className="mt-2">
              <Link to="/demo">
                Soumettre une demande fictive <ArrowRight className="h-4 w-4" aria-hidden />
              </Link>
            </Button>
          </div>
          <Card className="p-6">
            <p className="mb-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Ce que vous pouvez essayer</p>
            <ol className="space-y-4 text-sm">
              {[
                ['Soumettez', 'le formulaire de démo (un scénario fictif est préremplissable).'],
                ['Suivez', 'le parcours dans le tableau de bord : qualification, score, CRM, brouillon.'],
                ['Relisez', 'le brouillon, modifiez-le, approuvez-le ou rejetez-le.'],
                ['Supervisez', 'les automatisations et leurs éventuelles erreurs.'],
              ].map(([a, b], i) => (
                <li key={a} className="flex gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary">{i + 1}</span>
                  <span>
                    <strong>{a}</strong> {b}
                  </span>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </section>

      {/* CTA final */}
      <section className="border-t">
        <div className="mx-auto max-w-3xl px-4 py-16 text-center sm:px-6">
          <h2 className="text-3xl font-semibold tracking-tight">Voyez le pipeline fonctionner</h2>
          <p className="mx-auto mt-3 max-w-xl text-muted-foreground">
            Envoyez une demande fictive, puis ouvrez le tableau de bord pour suivre chaque étape réellement enregistrée.
          </p>
          <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
            <Button asChild size="lg">
              <Link to="/demo">Tester la démo</Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link to="/login">Se connecter</Link>
            </Button>
          </div>
        </div>
      </section>
    </>
  )
}
