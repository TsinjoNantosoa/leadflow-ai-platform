from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.config import get_settings
from app.core.constants import REQUESTABLE_SERVICES

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f‪-‮⁦-⁩]")
_LINK = re.compile(r"https?://|www\.", re.I)
_PHONE = re.compile(r"^[+()\d][\d\s().\-]{5,24}$")


def _clean(value: str) -> str:
    return _CTRL.sub("", unicodedata.normalize("NFKC", value)).strip()


class LeadCreate(BaseModel):
    """Corps de POST /api/v1/public/leads. Les champs inconnus sont rejetés (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    company: str | None = Field(None, max_length=120)
    phone: str | None = Field(None, max_length=32)
    requested_service: Literal[REQUESTABLE_SERVICES]  # type: ignore[valid-type]
    message: str = Field(min_length=20)
    consent_privacy: bool = Field(description="Information sur l'usage des données : obligatoire pour traiter la demande")
    consent_marketing: bool = Field(False, description="Facultatif : jamais exigé")
    website: str | None = Field(None, max_length=200, description="Honeypot anti-bots : doit rester vide")

    @field_validator("full_name", "company", "phone", mode="before")
    @classmethod
    def _strip_text(cls, v):
        if isinstance(v, str):
            v = _clean(v)
            return v or None
        return v

    @field_validator("email", mode="before")
    @classmethod
    def _strip_email(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("message", mode="before")
    @classmethod
    def _clean_message(cls, v):
        return _clean(v) if isinstance(v, str) else v

    @field_validator("phone")
    @classmethod
    def _phone_format(cls, v: str | None):
        if v is not None and not _PHONE.match(v):
            raise ValueError("Numéro de téléphone invalide")
        return v

    @field_validator("full_name")
    @classmethod
    def _name_not_blank(cls, v: str | None):
        if not v or len(v) < 2:
            raise ValueError("Nom trop court")
        return v

    @model_validator(mode="after")
    def _business_rules(self) -> LeadCreate:
        limit = get_settings().max_lead_message_length
        if len(self.message) < 20:
            raise ValueError("Le message doit contenir au moins 20 caractères")
        if len(self.message) > limit:
            raise ValueError(f"Le message ne doit pas dépasser {limit} caractères")
        if len(_LINK.findall(self.message)) > 3:
            raise ValueError("Trop de liens dans le message")
        if not self.consent_privacy:
            raise ValueError("Le consentement au traitement de la demande est obligatoire")
        return self

    def canonical(self) -> dict:
        """Représentation stable pour l'empreinte d'idempotence (e-mail normalisé, honeypot exclu)."""
        return {
            "full_name": self.full_name,
            "email": str(self.email).lower(),
            "company": self.company,
            "phone": self.phone,
            "requested_service": self.requested_service,
            "message": self.message,
            "consent_privacy": self.consent_privacy,
            "consent_marketing": self.consent_marketing,
        }


class LeadReceipt(BaseModel):
    lead_id: uuid.UUID
    status: str
    request_id: uuid.UUID
