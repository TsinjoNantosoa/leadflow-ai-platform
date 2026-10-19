from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.database.session import get_db
from app.schemas.public import LeadCreate, LeadReceipt
from app.services.intake import get_default_org, hash_ip, submit_lead

router = APIRouter(prefix="/public", tags=["public"])
log = logging.getLogger("leadflow.public")


def client_ip(request: Request) -> str | None:
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post(
    "/leads",
    status_code=201,
    response_model=LeadReceipt,
    summary="Soumettre une demande commerciale",
    responses={
        200: {"description": "Rejeu idempotent : même résultat que la création initiale"},
        400: {"description": "Idempotency-Key absente ou invalide"},
        409: {"description": "Idempotency-Key déjà utilisée avec un autre contenu"},
        422: {"description": "Validation"},
        429: {"description": "Limite de débit"},
    },
)
def create_lead(
    payload: LeadCreate,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if not idempotency_key:
        raise ApiError(400, "idempotency_key_required", "En-tête Idempotency-Key (UUID) requis")
    try:
        key = uuid.UUID(idempotency_key)
    except ValueError as exc:
        raise ApiError(400, "idempotency_key_invalid", "Idempotency-Key doit être un UUID") from exc

    if payload.website:  # honeypot rempli : on répond comme un succès sans rien enregistrer
        log.info("honeypot_triggered")
        return LeadReceipt(lead_id=uuid.uuid4(), status="NEW", request_id=uuid.uuid4())

    org = get_default_org(db)
    receipt, replayed = submit_lead(db, org=org, payload=payload, idempotency_key=key,
                                    client_ip_hash=hash_ip(client_ip(request)))
    if replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    return receipt
