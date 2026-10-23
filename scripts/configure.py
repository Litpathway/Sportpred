"""Generate local configuration without committing or printing credentials."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env already exists; edit it locally rather than overwrite secrets.")
text = (root / ".env.example").read_text()
for key in ("JWT_SECRET", "ADMIN_PASSWORD", "POSTGRES_PASSWORD"):
    text = text.replace(f"{key}=\n", f"{key}={secrets.token_urlsafe(36)}\n")
target.write_text(text)
print("Created .env with unique secrets. Read ADMIN_EMAIL and ADMIN_PASSWORD locally to sign in.")
