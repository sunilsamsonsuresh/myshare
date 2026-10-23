"""Print a JWT for a demo user (default: demo@myshare.app). Used by `make token`.

uv run python scripts/get_token.py [email] [password]
"""

import os
import sys

import httpx

email = sys.argv[1] if len(sys.argv) > 1 else "demo@myshare.app"
password = sys.argv[2] if len(sys.argv) > 2 else "password123"
api = os.environ.get("MYSHARE_API_URL", "http://localhost:8000")
try:
    r = httpx.post(f"{api}/auth/login", json={"email": email, "password": password}, timeout=5)
except httpx.HTTPError:
    sys.exit(f"Could not reach the API at {api}. Is it running? (make api)")
if r.status_code != 200:
    sys.exit(f"Login failed: {r.text}")
print(r.json()["access_token"])
