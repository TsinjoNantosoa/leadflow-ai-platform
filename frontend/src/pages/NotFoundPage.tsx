import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Compass className="h-6 w-6" aria-hidden />
      </div>
      <h1 className="text-2xl font-semibold">Page introuvable</h1>
      <p className="max-w-sm text-sm text-muted-foreground">Cette adresse n’existe pas ou a été déplacée.</p>
      <Button asChild className="mt-2">
        <Link to="/">Retour à l’accueil</Link>
      </Button>
    </div>
  )
}
