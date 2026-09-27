"""Restore Supabase authentication across full browser refreshes."""

import base64
import json
from typing import Any

import streamlit as st

from services.supabase import clear_supabase_client, get_supabase_client


USER_SESSION_KEY = "authenticated_user"
_AUTH_COOKIE_NAME = "bench_rentals_auth"
_AUTH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
_AUTH_COOKIE_ACTION_KEY = "_auth_cookie_action"
_AUTH_COOKIE_READY_KEY = "_auth_cookie_ready"
_AUTH_RESTORE_BLOCKED_KEY = "_auth_restore_blocked"


def restore_authenticated_session() -> bool:
    """Restore this Streamlit session from the browser's Supabase refresh token."""
    if st.session_state.get(USER_SESSION_KEY) is not None:
        _queue_cookie_for_existing_session()
        return True
    if st.session_state.get(_AUTH_RESTORE_BLOCKED_KEY):
        return False

    refresh_token = _decode_refresh_token(
        st.context.cookies.get(_AUTH_COOKIE_NAME)
    )
    if refresh_token is None:
        if _AUTH_COOKIE_NAME in st.context.cookies:
            queue_auth_cookie_clear()
        return False

    try:
        response = get_supabase_client().auth.refresh_session(refresh_token)
    except Exception:
        clear_supabase_client()
        queue_auth_cookie_clear()
        return False

    if response.user is None or response.session is None:
        clear_supabase_client()
        queue_auth_cookie_clear()
        return False

    st.session_state[USER_SESSION_KEY] = response.user
    queue_auth_cookie_write(response.session)
    return True


def queue_auth_cookie_write(session: Any) -> None:
    """Queue the refreshed browser credential to be written this run."""
    refresh_token = getattr(session, "refresh_token", None)
    if not isinstance(refresh_token, str) or not refresh_token:
        return
    st.session_state[_AUTH_COOKIE_ACTION_KEY] = {
        "value": _encode_refresh_token(refresh_token),
        "max_age": _AUTH_COOKIE_MAX_AGE_SECONDS,
    }
    st.session_state[_AUTH_COOKIE_READY_KEY] = True


def queue_auth_cookie_clear() -> None:
    """Queue removal of the persistent browser credential."""
    st.session_state.pop(_AUTH_COOKIE_READY_KEY, None)
    st.session_state[_AUTH_COOKIE_ACTION_KEY] = {"value": "", "max_age": 0}


def block_auth_restoration() -> None:
    """Prevent a just-logged-out Streamlit session from restoring a stale cookie."""
    st.session_state[_AUTH_RESTORE_BLOCKED_KEY] = True


def allow_auth_restoration() -> None:
    """Clear the same-session logout guard after a successful sign-in."""
    st.session_state.pop(_AUTH_RESTORE_BLOCKED_KEY, None)


def render_pending_auth_cookie() -> None:
    """Apply a queued cookie update with trusted application-owned JavaScript."""
    action = st.session_state.pop(_AUTH_COOKIE_ACTION_KEY, None)
    if not isinstance(action, dict):
        return

    value = action.get("value")
    max_age = action.get("max_age")
    if not isinstance(value, str) or not isinstance(max_age, int):
        return

    cookie_name = json.dumps(_AUTH_COOKIE_NAME)
    cookie_value = json.dumps(value)
    st.html(
        f"""
        <span hidden data-auth-cookie-sync></span>
        <script>
        (() => {{
          const secure = window.location.protocol === "https:" ? "; Secure" : "";
          document.cookie = {cookie_name} + "=" + {cookie_value}
            + "; Path=/; Max-Age={max_age}; SameSite=Lax" + secure;
        }})();
        </script>
        """,
        width="content",
        unsafe_allow_javascript=True,
    )


def _queue_cookie_for_existing_session() -> None:
    """Migrate an already-open authenticated tab to persistent browser auth."""
    if st.session_state.get(_AUTH_COOKIE_READY_KEY):
        return
    try:
        session = get_supabase_client().auth.get_session()
    except Exception:
        return
    if session is not None:
        queue_auth_cookie_write(session)


def _encode_refresh_token(refresh_token: str) -> str:
    encoded = base64.urlsafe_b64encode(refresh_token.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_refresh_token(cookie_value: Any) -> str | None:
    if not isinstance(cookie_value, str) or not cookie_value:
        return None
    try:
        padding = "=" * (-len(cookie_value) % 4)
        refresh_token = base64.urlsafe_b64decode(cookie_value + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return refresh_token or None
