import { zodResolver } from '@hookform/resolvers/zod'
import { LogIn } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { useAuth } from '@/app/providers'
import { Logo } from '@/components/layout/layouts'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Alert } from '@/components/ui/feedback'
import { FieldError, Input, Label } from '@/components/ui/form-controls'
import { ApiError } from '@/lib/api'

const schema = z.object({
  email: z.string().trim().min(1, 'Indiquez votre e-mail').email('Adresse e-mail invalide'),
  password: z.string().min(1, 'Indiquez votre mot de passe'),
})
type Values = z.infer<typeof schema>

export default function LoginPage() {
  const { login, status } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from
  const [error, setError] = React.useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } })
  const { errors, isSubmitting } = formState

  if (status === 'authenticated') return <Navigate to={from && from.startsWith('/app') ? from : '/app/overview'} replace />

  async function onSubmit(v: Values) {
    setError(null)
    try {
      await login(v.email, v.password)
      navigate(from && from.startsWith('/app') ? from : '/app/overview', { replace: true })
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setError('E-mail ou mot de passe incorrect, ou compte temporairement verrouillé.')
      else if (e instanceof ApiError && e.isNetwork) setError('Serveur injoignable. Il peut être en veille : patientez environ une minute puis réessayez.')
      else if (e instanceof ApiError && e.status === 429) setError('Trop de tentatives. Réessayez dans quelques instants.')
      else setError('Connexion impossible pour le moment.')
    }
  }

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4 py-10">
      <div className="bg-grid absolute inset-0 -z-10" aria-hidden />
      <div className="w-full max-w-sm space-y-6">
        <div className="flex justify-center">
          <Link to="/" aria-label="Retour à l’accueil">
            <Logo className="text-lg" />
          </Link>
        </div>
        <Card>
          <CardContent className="space-y-5 p-6">
            <div className="space-y-1">
              <h1 className="text-lg font-semibold">Connexion</h1>
              <p className="text-sm text-muted-foreground">Espace opérationnel réservé à l’équipe commerciale.</p>
            </div>
            <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-4" aria-label="Connexion">
              <div>
                <Label htmlFor="email">E-mail</Label>
                <Input id="email" type="email" autoComplete="username" className="mt-1.5" aria-invalid={!!errors.email}
                  aria-describedby={errors.email ? 'email-err' : undefined} {...register('email')} />
                <FieldError id="email-err">{errors.email?.message}</FieldError>
              </div>
              <div>
                <Label htmlFor="password">Mot de passe</Label>
                <Input id="password" type="password" autoComplete="current-password" className="mt-1.5" aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? 'password-err' : undefined} {...register('password')} />
                <FieldError id="password-err">{errors.password?.message}</FieldError>
              </div>
              {error && <Alert tone="danger">{error}</Alert>}
              <Button type="submit" className="w-full" loading={isSubmitting}>
                {!isSubmitting && <LogIn className="h-4 w-4" aria-hidden />} Se connecter
              </Button>
            </form>
            <p className="text-center text-xs text-muted-foreground">
              L’authentification est vérifiée côté serveur (session sécurisée). Les comptes de démonstration ne donnent accès qu’à des données synthétiques.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
