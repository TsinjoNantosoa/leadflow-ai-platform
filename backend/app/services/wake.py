"""Réveil best-effort de n8n après une soumission.

L'événement outbox est déjà committé : ce signal n'est qu'un accélérateur de latence. Il ne transporte aucune
donnée métier, n'est jamais attendu par la requête du visiteur (BackgroundTasks) et toute erreur est ignorée —
le poll de récupération de LF-WF-04 réserve de toute façon les événements en attente.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger("leadflow.wake")


def notify_n8n_wake() -> bool:
    settings = get_settings()
    url = settings.n8n_wake_webhook_url.strip()
    if not url:
        return False
    secret = settings.n8n_webhook_secret.get_secret_value()
    try:
        r = httpx.post(url, json={"source": "leadflow-api"}, timeout=settings.n8n_wake_timeout_seconds,
                       headers={"X-LeadFlow-Webhook-Secret": secret} if secret else {})
        ok = r.status_code < 300
        if not ok:
            log.warning("n8n_wake_rejected", extra={"status": r.status_code})
        return ok
    except httpx.HTTPError as exc:
        log.warning("n8n_wake_failed", extra={"error": type(exc).__name__})
        return False
