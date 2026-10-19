"""Seed idempotent : organisation, comptes démo, données synthétiques NovaDigital.

    python -m scripts.seed_demo                 # organisation + comptes + données de démo
    python -m scripts.seed_demo --users-only    # organisation + comptes uniquement (ex. production)

Les mots de passe viennent de DEMO_ADMIN_PASSWORD / DEMO_SALES_PASSWORD ; en développement, s'ils sont absents,
un mot de passe aléatoire est généré et affiché UNE fois. Rien d'existant n'est écrasé.
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_settings
from app.database.session import get_sessionmaker
from app.services.seed import ensure_organization, ensure_users, seed_demo_data


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--users-only", action="store_true", help="ne pas insérer les leads de démonstration")
    args = parser.parse_args()

    settings = get_settings()
    with get_sessionmaker()() as db:
        org = ensure_organization(db)
        generated = ensure_users(db, org)
        created = {} if args.users_only else seed_demo_data(db, org)
        db.commit()

    print(f"[seed] organisation : {org.slug} (env={settings.app_env})")
    for role, pw in generated.items():
        if pw:
            print(f"[seed] mot de passe généré pour {role}@novadigital.example : {pw}  (affiché une seule fois)")
    if created:
        print(f"[seed] leads de démonstration créés : {created['leads']} (0 = déjà présents)")
    print("[seed] terminé — les données de démonstration sont marquées is_demo=true")


if __name__ == "__main__":
    main()
