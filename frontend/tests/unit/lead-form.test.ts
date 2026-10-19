import { describe, expect, it } from 'vitest'
import { leadFormSchema, SAMPLE_LEAD } from '@/features/lead-form'

const valid = { ...SAMPLE_LEAD }
const issues = (v: object) => {
  const r = leadFormSchema.safeParse(v)
  return r.success ? [] : r.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`)
}

describe('schéma du formulaire public', () => {
  it('accepte le scénario fictif', () => {
    expect(leadFormSchema.safeParse(valid).success).toBe(true)
  })

  it.each([
    [{ full_name: ' ' }, 'full_name'],
    [{ email: 'pas-un-email' }, 'email'],
    [{ email: '' }, 'email'],
    [{ requested_service: '' }, 'requested_service'],
    [{ message: 'trop court' }, 'message'],
    [{ message: 'x'.repeat(4001) }, 'message'],
    [{ consent_privacy: false }, 'consent_privacy'],
    [{ phone: 'abc' }, 'phone'],
  ])('rejette %j', (override, field) => {
    expect(issues({ ...valid, ...override }).some((m) => m.startsWith(field))).toBe(true)
  })

  it('normalise : espaces retirés, champs facultatifs vides => undefined', () => {
    const r = leadFormSchema.parse({ ...valid, full_name: '  Alice  ', company: '   ', phone: '' })
    expect(r.full_name).toBe('Alice')
    expect(r.company).toBeUndefined()
    expect(r.phone).toBeUndefined()
  })

  it('le consentement marketing n’est jamais obligatoire', () => {
    expect(leadFormSchema.safeParse({ ...valid, consent_marketing: false }).success).toBe(true)
  })

  it('messages d’erreur en français, sans jargon technique', () => {
    expect(issues({ ...valid, consent_privacy: false })[0]).toContain('consentement')
    expect(issues({ ...valid, message: 'court' })[0]).toContain('au moins 20 caractères')
  })
})
