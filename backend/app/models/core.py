"""Organisations, utilisateurs, sessions, contacts, leads, événements d'intake."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import LeadStatus, Role
from app.database.base import Base, created_at_col, sql_in, updated_at_col, uuid_pk


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = created_at_col()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email_normalized"),
        CheckConstraint(sql_in("role", Role), name="role"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Seul le hash du jeton est stocké : une fuite de la base ne donne pas de sessions utilisables.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (Index("ix_sessions_expires_at", "expires_at"),)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("organization_id", "email_normalized"),
        # Cible de la clé étrangère composite de `leads` (cohérence d'organisation).
        UniqueConstraint("organization_id", "id", name="uq_contacts_org_id"),
        CheckConstraint("consent_status IN ('unknown','granted','denied')", name="consent_status"),
        CheckConstraint("email_normalized = lower(btrim(email_normalized))", name="email_normalized_canonical"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    consent_status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown", server_default="unknown")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    leads: Mapped[list[Lead]] = relationship(back_populates="contact")


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_leads_org_contact",
        ),
        CheckConstraint(sql_in("status", LeadStatus), name="status"),
        Index("ix_leads_org_created", "organization_id", "created_at"),
        Index("ix_leads_org_status", "organization_id", "status"),
        Index("ix_leads_contact", "contact_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="website", server_default="website")
    requested_service: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW", server_default="NEW")
    status_reason: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    privacy_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_notice_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    contact: Mapped[Contact] = relationship(
        back_populates="leads", foreign_keys=[organization_id, contact_id], overlaps="leads"
    )


class IntakeEvent(Base):
    __tablename__ = "intake_events"
    __table_args__ = (
        UniqueConstraint("organization_id", "client_request_id"),
        Index("ix_intake_ip_created", "client_ip_hash", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), nullable=False)
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request_body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="website", server_default="website")
    client_ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_col()


__all__ = ["Contact", "IntakeEvent", "Lead", "Organization", "User", "UserSession"]
