import { z } from 'zod'

export const MAX_MESSAGE = 4000
export const MIN_MESSAGE = 20

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max, `${max} caractères maximum`)
    .optional()
    .transform((v) => (v ? v : undefined))

export const leadFormSchema = z.object({
  full_name: z.string().trim().min(2, 'Indiquez votre nom complet').max(120, '120 caractères maximum'),
  email: z.string().trim().min(1, 'Indiquez votre e-mail').email('Adresse e-mail invalide').max(254),
  company: optionalText(120),
  phone: z
    .string()
    .trim()
    .max(32)
    .optional()
    .refine((v) => !v || /^[+()\d][\d\s().-]{5,24}$/.test(v), 'Numéro de téléphone invalide')
    .transform((v) => (v ? v : undefined)),
  requested_service: z.string().min(1, 'Choisissez un service'),
  message: z
    .string()
    .trim()
    .min(MIN_MESSAGE, `Décrivez votre besoin en au moins ${MIN_MESSAGE} caractères`)
    .max(MAX_MESSAGE, `${MAX_MESSAGE} caractères maximum`),
  consent_privacy: z.boolean().refine((v) => v === true, 'Ce consentement est nécessaire pour traiter votre demande'),
  consent_marketing: z.boolean(),
  // Honeypot : invisible pour les humains. Les robots le remplissent.
  website: z.string().max(200).optional(),
})

export type LeadFormValues = z.input<typeof leadFormSchema>
export type LeadFormOutput = z.output<typeof leadFormSchema>

/** Scénario fictif préremplissable (adresse réservée @example.org). */
export const SAMPLE_LEAD: LeadFormValues = {
  full_name: 'Alice Martin',
  email: 'alice.martin@example.org',
  company: 'NovaDigital Demo',
  phone: '',
  requested_service: 'customer_support_automation',
  message:
    'Bonjour, notre équipe veut automatiser le traitement des demandes clients. Budget indicatif 3000 EUR. Démarrage dans un mois.',
  consent_privacy: true,
  consent_marketing: false,
  website: '',
}
