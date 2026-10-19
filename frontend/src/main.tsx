import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { AppProviders, makeQueryClient } from '@/app/providers'
import { createRouter } from '@/app/router'
import '@/styles/index.css'

const queryClient = makeQueryClient()
const router = createRouter()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
)
