import { zodResolver } from '@hookform/resolvers/zod'
import { CheckCircle2, FlaskConical, Info, Send } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { CopyId } from '@/components/domain/misc'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, errorMessage } from '@/components/ui/feedback'
import { Checkbox, FieldError, Input, Label, Select, Textarea } from '@/components/ui/form-controls'
import { MAX_MESSAGE, leadFormSchema, SAMPLE_LEAD, type LeadFormOutput, type LeadFormValues } from '@/features/lead-form'
import { ApiError, warmUpBackend } from '@/lib/api'
import { SERVICES } from '@/lib/labels'
import { newIdempotencyKey } from '@/lib/utils'
import { publicService } from '@/services/api-services'
import type { LeadReceipt } from '@/types/api'

const EMPTY: LeadFormValues = {
  full_name: '',
  email: '',
  company: '',
  phone: '',
  requested_service: '',
  message: '',
  consent_privacy: false,
  consent_marketing: false,
  website: '',
}

export default function DemoPage() {
  const form = useForm<LeadFormValues, unknown, LeadFormOutput>({
    resolver: zodResolver(leadFormSchema),
    defaultValues: EMPTY,
    mode: 'onTouched',
  })
  const { register, handleSubmit, reset, watch, formState } = form
  const { errors, isSubmitting } = formState
  const [receipt, setReceipt] = React.useState<LeadReceipt | null>(null)
  const [submitError, setSubmitError] = React.useState<unknown>(null)
  // Une même saisie réutilise la même clé : double clic ou nouvel essai après une coupure ne créent jamais deux demandes.
  const keyRef = React.useRef<string>(newIdempotencyKey())
  const submittingRef = React.useRef(false)

  React.useEffect(() => warmUpBackend(), [])

  // Toute modification du contenu = nouvelle demande => nouvelle clé d'idempotence.
  React.useEffect(() => {
    const sub = watch(() => {
      if (!submittingRef.current) keyRef.current = newIdempotencyKey()
    })
    return () => sub.unsubscribe()
  }, [watch])

  const messageLength = (watch('message') ?? '').length

  async function onSubmit(values: LeadFormOutput) {
    if (submittingRef.current) return // garde synchrone contre les doubles clics
    submittingRef.current = true
    setSubmitError(null)
    try {
      const res = await publicService.submitLead(
        {
          full_name: values.full_name,
          email: values.email,
          company: values.company ?? null,
          phone: values.phone ?? null,
          requested_service: values.requested_service,
          message: values.message,
          consent_privacy: values.consent_privacy,
          consent_marketing: values.consent_marketing,
          website: values.website || undefined,
        },
        keyRef.current,
      )
      setReceipt(res)
    } catch (e) {
      setSubmitError(e)
    } finally {
      submittingRef.current = false
    }
  }

  if (receipt) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 sm:px-6">
        <Card className="animate-fade-in text-center">
          <CardContent className="space-y-4 p-8">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-success-soft text-success">
              <CheckCircle2 className="h-7 w-7" aria-hidden />
            </div>
            <h1 className="text-xl font-semibold">Demande bien reçue</h1>
            <p className="text-sm text-muted-foreground">
              Votre demande est enregistrée. Son traitement (analyse, scoring, préparation d’une réponse) se fait en arrière-plan ; un
              commercial relira tout avant toute réponse. <strong>Aucun e-mail automatique n’est envoyé.</strong>
            </p>
            <dl className="mx-auto inline-grid grid-cols-[auto_auto] items-center gap-x-4 gap-y-2 rounded-lg bg-muted px-4 py-3 text-left text-sm">
              <dt className="text-muted-foreground">Identifiant de demande</dt>
              <dd data-testid="request-id">
                <CopyId value={receipt.request_id} />
              </dd>
              <dt className="text-muted-foreground">Référence du lead</dt>
              <dd>
                <CopyId value={receipt.lead_id} />
              </dd>
            </dl>
            <div className="flex flex-col justify-center gap-2 pt-2 sm:flex-row">
              <Button
                variant="outline"
                onClick={() => {
                  setReceipt(null)
                  reset(EMPTY)
                  keyRef.current = newIdempotencyKey()
                }}
              >
                Envoyer une autre demande
              </Button>
              <Button asChild>
                <Link to="/login">Voir le tableau de bord</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const submitMsg = submitError ? errorMessage(submitError) : null
  const fieldErrors = submitError instanceof ApiError && submitError.status === 422

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6 sm:py-14">
      <div className="mb-8 space-y-2">
        <p className="text-sm font-medium text-primary">Démonstration NovaDigital</p>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Décrivez votre projet</h1>
        <p className="text-muted-foreground">
          Ce formulaire alimente le véritable pipeline : validation, enregistrement, qualification par IA, scoring, CRM et brouillon de réponse.
        </p>
      </div>

      <Alert tone="info" title="Environnement de démonstration" className="mb-6">
        NovaDigital est une agence fictive. N’utilisez que des données fictives (adresse en <code>@example.org</code> recommandée).
      </Alert>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-base">Votre demande</CardTitle>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => reset(SAMPLE_LEAD)}
            disabled={isSubmitting}
            data-testid="fill-sample"
          >
            <FlaskConical className="h-3.5 w-3.5" aria-hidden /> Préremplir un scénario fictif
          </Button>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-5" aria-label="Formulaire de demande commerciale">
            {/* Honeypot : hors écran, ignoré par les lecteurs d'écran et la navigation clavier */}
            <div aria-hidden className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
              <label>
                Ne pas remplir
                <input type="text" tabIndex={-1} autoComplete="off" {...register('website')} />
              </label>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <Label htmlFor="full_name">Nom complet *</Label>
                <Input id="full_name" autoComplete="name" className="mt-1.5" aria-invalid={!!errors.full_name}
                  aria-describedby={errors.full_name ? 'full_name-err' : undefined} {...register('full_name')} />
                <FieldError id="full_name-err">{errors.full_name?.message}</FieldError>
              </div>
              <div>
                <Label htmlFor="email">E-mail *</Label>
                <Input id="email" type="email" autoComplete="email" inputMode="email" className="mt-1.5" aria-invalid={!!errors.email}
                  aria-describedby={errors.email ? 'email-err' : undefined} {...register('email')} />
                <FieldError id="email-err">{errors.email?.message}</FieldError>
              </div>
              <div>
                <Label htmlFor="company">Entreprise</Label>
                <Input id="company" autoComplete="organization" className="mt-1.5" aria-invalid={!!errors.company} {...register('company')} />
                <FieldError>{errors.company?.message}</FieldError>
              </div>
              <div>
                <Label htmlFor="phone">Téléphone</Label>
                <Input id="phone" type="tel" autoComplete="tel" inputMode="tel" className="mt-1.5" aria-invalid={!!errors.phone}
                  aria-describedby={errors.phone ? 'phone-err' : undefined} {...register('phone')} />
                <FieldError id="phone-err">{errors.phone?.message}</FieldError>
              </div>
            </div>

            <div>
              <Label htmlFor="requested_service">Service recherché *</Label>
              <Select id="requested_service" className="mt-1.5" aria-invalid={!!errors.requested_service}
                aria-describedby={errors.requested_service ? 'service-err' : undefined} {...register('requested_service')}>
                <option value="">Sélectionnez…</option>
                {SERVICES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </Select>
              <FieldError id="service-err">{errors.requested_service?.message}</FieldError>
            </div>

            <div>
              <div className="flex items-baseline justify-between">
                <Label htmlFor="message">Votre message *</Label>
                <span className={`text-xs tabular-nums ${messageLength > MAX_MESSAGE ? 'text-danger' : 'text-muted-foreground'}`} aria-live="polite">
                  {messageLength} / {MAX_MESSAGE}
                </span>
              </div>
              <Textarea id="message" rows={6} className="mt-1.5" aria-invalid={!!errors.message}
                aria-describedby={errors.message ? 'message-err' : 'message-help'} {...register('message')} />
              <p id="message-help" className="mt-1.5 flex gap-1.5 text-xs text-muted-foreground">
                <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden /> Précisez votre besoin, votre budget indicatif et vos délais si vous le souhaitez.
              </p>
              <FieldError id="message-err">{errors.message?.message}</FieldError>
            </div>

            <fieldset className="space-y-3 rounded-lg border bg-muted/40 p-4">
              <legend className="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Consentements</legend>
              <div className="flex gap-3">
                <Checkbox id="consent_privacy" aria-invalid={!!errors.consent_privacy}
                  aria-describedby={errors.consent_privacy ? 'privacy-err' : undefined} {...register('consent_privacy')} />
                <div>
                  <Label htmlFor="consent_privacy" className="font-normal leading-snug">
                    J’accepte que mes informations soient utilisées pour traiter ma demande (analyse automatisée par IA incluse) et
                    conservées dans le CRM de démonstration. *
                  </Label>
                  <FieldError id="privacy-err">{errors.consent_privacy?.message}</FieldError>
                </div>
              </div>
              <div className="flex gap-3">
                <Checkbox id="consent_marketing" {...register('consent_marketing')} />
                <Label htmlFor="consent_marketing" className="font-normal leading-snug">
                  (Facultatif) J’accepte de recevoir des informations commerciales de NovaDigital.
                </Label>
              </div>
            </fieldset>

            {submitMsg && (
              <Alert tone="danger" title={submitMsg.title}>
                {fieldErrors ? 'Certaines informations sont invalides, vérifiez le formulaire.' : submitMsg.detail}
                {submitMsg.correlationId && <span className="mt-1 block font-mono text-[11px]">Référence : {submitMsg.correlationId}</span>}
                {!fieldErrors && <span className="mt-1 block text-xs">Vous pouvez réessayer : aucune demande en double ne sera créée.</span>}
              </Alert>
            )}

            <Button type="submit" size="lg" className="w-full" loading={isSubmitting}>
              {!isSubmitting && <Send className="h-4 w-4" aria-hidden />}
              {isSubmitting ? 'Envoi en cours…' : 'Envoyer ma demande'}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              Vos données de démonstration peuvent être supprimées sur demande. Aucune réponse automatique n’est envoyée par e-mail.
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
