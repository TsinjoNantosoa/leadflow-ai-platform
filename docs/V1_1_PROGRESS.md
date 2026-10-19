# Avancement V1.1

| Phase | Contenu | État |
| --- | --- | --- |
| 1 Audit | `V1_1_AUDIT.md` | terminé |
| 2 Backend / Render / outbox | `TRUSTED_PROXY_HOPS`, réveil n8n best-effort, `create_admin`, guide Render sans Shell | terminé |
| 3 OpenAI | `openai_smoke.py`, `OPENAI_VALIDATION.md` ; tests mock / SDK simulé de la V1 conservés | terminé (réel non exécuté) |
| 4 n8n | WF-04 : poll 20 min configurable + webhook de réveil ; `validate_workflows.py` ; import du WF-04 modifié vérifié sur n8n 2.43.8 local | terminé (limites : `N8N_VALIDATION.md`) |
| 5 Frontend | `configure:vercel` + garde de build, indicateurs d'automatisation | terminé |
| 6 Sécurité | `SECURITY_REVIEW.md` | terminé |
| 7 Base | Migration 0001 reproductible sur base vierge (`alembic upgrade head`, `alembic check`, `verify_schema`) | terminé |
| 8 Tests | Voir `TEST_REPORT.md` | terminé |
| 9 Déploiement | Guides Render, Vercel, n8n mis à jour ; CI GitHub | terminé (rien déployé) |
| 10 Rapport | `V1_1_FINAL_REPORT.md` | terminé |
