"""Création contrôlée du premier administrateur (production). Idempotent, jamais destructif.

    LF_ADMIN_EMAIL=you@example.com LF_ADMIN_PASSWORD='...' python -m scripts.create_admin
    python -m scripts.create_admin --email you@example.com        # mot de passe demandé sans écho

Si l'utilisateur existe déjà, rien n'est modifié (utiliser --reset-password pour le changer explicitement).
Ne crée AUCUNE donnée de démonstration. Mot de passe : 12 caractères minimum.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.database.session import get_sessionmaker
from app.models import User
from app.security.passwords import hash_password
from app.services.seed import ensure_organization


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", default=os.environ.get("LF_ADMIN_EMAIL"))
    ap.add_argument("--name", default=os.environ.get("LF_ADMIN_NAME", "Administrateur"))
    ap.add_argument("--reset-password", action="store_true")
    args = ap.parse_args()
    if not args.email or "@" not in args.email:
        print("[admin] e-mail requis (--email ou LF_ADMIN_EMAIL)", file=sys.stderr)
        return 2
    password = os.environ.get("LF_ADMIN_PASSWORD") or getpass.getpass("Mot de passe administrateur : ")
    if len(password) < 12:
        print("[admin] mot de passe trop court (12 caractères minimum)", file=sys.stderr)
        return 2
    email = args.email.strip().lower()
    with get_sessionmaker()() as db:
        org = ensure_organization(db)
        user = db.scalar(select(User).where(User.organization_id == org.id, User.email_normalized == email))
        if user and not args.reset_password:
            print("[admin] utilisateur déjà présent : aucune modification")
            return 0
        if user:
            user.password_hash = hash_password(password)
            user.failed_login_count = 0
            user.locked_until = None
            user.is_active = True
            print("[admin] mot de passe réinitialisé")
        else:
            db.add(User(organization_id=org.id, email=args.email.strip(), email_normalized=email, full_name=args.name, role="ADMIN",
                        password_hash=hash_password(password)))
            print("[admin] administrateur créé")
        db.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
