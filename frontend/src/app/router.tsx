import * as React from 'react'
import { createBrowserRouter, Navigate, type RouteObject } from 'react-router-dom'
import { AppShell, PublicLayout, RequireAuth } from '@/components/layout/layouts'
import { Skeleton } from '@/components/ui/feedback'

// Pages chargées à la demande : la landing reste légère, les graphiques ne pèsent que sur le dashboard.
const LandingPage = React.lazy(() => import('@/pages/LandingPage'))
const DemoPage = React.lazy(() => import('@/pages/DemoPage'))
const LoginPage = React.lazy(() => import('@/pages/LoginPage'))
const OverviewPage = React.lazy(() => import('@/pages/OverviewPage'))
const LeadsPage = React.lazy(() => import('@/pages/LeadsPage'))
const LeadDetailPage = React.lazy(() => import('@/pages/LeadDetailPage'))
const ReviewsPage = React.lazy(() => import('@/pages/ReviewsPage'))
const RunsPage = React.lazy(() => import('@/pages/RunsPage'))
const NotFoundPage = React.lazy(() => import('@/pages/NotFoundPage'))

const fallback = (
  <div className="p-6" role="status" aria-label="Chargement">
    <Skeleton className="h-8 w-56" />
  </div>
)
const lazy = (el: React.ReactNode) => <React.Suspense fallback={fallback}>{el}</React.Suspense>

export const routes: RouteObject[] = [
  {
    element: <PublicLayout />,
    children: [
      { index: true, element: lazy(<LandingPage />) },
      { path: 'demo', element: lazy(<DemoPage />) },
    ],
  },
  { path: 'login', element: lazy(<LoginPage />) },
  {
    // Garde d'UX uniquement : la sécurité réelle est appliquée par l'API (session + rôle sur chaque endpoint).
    element: <RequireAuth />,
    children: [
      {
        path: 'app',
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="overview" replace /> },
          { path: 'overview', element: lazy(<OverviewPage />) },
          { path: 'leads', element: lazy(<LeadsPage />) },
          { path: 'leads/:id', element: lazy(<LeadDetailPage />) },
          { path: 'reviews', element: lazy(<ReviewsPage />) },
          { path: 'runs', element: lazy(<RunsPage />) },
        ],
      },
    ],
  },
  { path: '*', element: lazy(<NotFoundPage />) },
]

export const createRouter = () => createBrowserRouter(routes)
