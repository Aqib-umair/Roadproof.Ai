"""Read server-only configuration without putting credentials in the interface."""
import os
from dataclasses import dataclass

import streamlit as st


def setting(name, default=""):
    if name in os.environ:
        return os.environ[name]
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


@dataclass(frozen=True, repr=False)
class BackendSettings:
    backend: str
    url: str
    secret: str
    bucket: str


def backend_settings():
    backend = setting("ROADPROOF_BACKEND", "sqlite").strip().lower()
    if backend not in {"sqlite", "supabase"}:
        raise ValueError("ROADPROOF_BACKEND must be sqlite or supabase.")
    url = setting("SUPABASE_URL").strip().rstrip("/")
    secret = setting("SUPABASE_SECRET_KEY").strip()
    if backend == "supabase":
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.path:
            raise ValueError("Set SUPABASE_URL to your project's HTTPS origin.")
        if not secret or secret.startswith("sb_publishable_"):
            raise ValueError("Supabase needs a server-only secret key, configured outside chat.")
    return BackendSettings(backend, url, secret, "roadproof-evidence")
