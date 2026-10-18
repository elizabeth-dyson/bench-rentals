"""Streamlit configuration/client boundary for the public form only."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import streamlit as st
from supabase import create_client


@dataclass(frozen=True)
class PublicInquiryConfig:
    url: str
    anon_key: str
    gateway_secret: str
    site_key: str
    turnstile_secret: str
    hostname: str


def load_public_config() -> PublicInquiryConfig | None:
    try:
        if st.secrets.get("PUBLIC_INQUIRY_ENABLED", False) is not True:
            return None
        names = ("SUPABASE_URL", "PUBLIC_SUPABASE_ANON_KEY", "PUBLIC_INQUIRY_GATEWAY_SECRET",
                 "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY", "PUBLIC_INQUIRY_HOSTNAME")
        values = [st.secrets.get(name) for name in names]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            return None
        config = PublicInquiryConfig(*(value.strip() for value in values))
        url = urlsplit(config.url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", config.gateway_secret):
            return None
        if not re.fullmatch(r"[A-Za-z0-9.-]+", config.hostname):
            return None
        # Supabase publishable keys are safe; legacy JWT keys must explicitly be anon.
        if not config.anon_key.startswith("sb_publishable_"):
            import base64
            import json
            part = config.anon_key.split(".")[1]
            payload = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
            if payload.get("role") != "anon":
                return None
        return config
    except Exception:
        return None


def create_public_client(config: PublicInquiryConfig):
    """Fresh anonymous client; no cookies, auth restoration, or shared cache."""
    return create_client(config.url, config.anon_key)
