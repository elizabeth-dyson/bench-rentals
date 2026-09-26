from typing import Any

import streamlit as st

from components.presentation import render_wordmark
from services.supabase import clear_supabase_client, get_supabase_client
from utils.scrolling import request_scroll_to_top


_USER_SESSION_KEY = "authenticated_user"


def is_authenticated() -> bool:
    """Return whether this Streamlit session has an authenticated user."""
    return st.session_state.get(_USER_SESSION_KEY) is not None


def get_authenticated_user() -> Any | None:
    """Return the authenticated Supabase user, if present."""
    return st.session_state.get(_USER_SESSION_KEY)


def get_authenticated_user_display_name() -> str:
    """Return the current user's display name, email, or a friendly fallback."""
    user = get_authenticated_user()
    if user is None:
        return "there"

    metadata = user.user_metadata or {}
    return metadata.get("display_name") or user.email or "there"


def render_login() -> None:
    """Render the internal email/password login form."""
    with st.container(horizontal_alignment="center"):
        with st.container(width=440):
            st.space("large")
            render_wordmark()
            st.caption("A little organization for every gathering.")
            with st.form("login_form"):
                st.subheader("Welcome back")
                st.write("Sign in to manage your leads and rentals.")
                email = st.text_input("Email", autocomplete="email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button(
                    "Sign in", type="primary", width="stretch"
                )
            feedback = st.container()

    if not submitted:
        return
    if not email.strip() or not password:
        feedback.error("Enter both your email and password.")
        return

    try:
        response = get_supabase_client().auth.sign_in_with_password(
            {"email": email.strip(), "password": password}
        )
    except Exception:
        feedback.error("We couldn't sign you in. Check your email and password and try again.")
        return

    if response.user is None or response.session is None:
        feedback.error("We couldn't sign you in. Check your email and password and try again.")
        return

    st.session_state[_USER_SESSION_KEY] = response.user
    request_scroll_to_top()
    st.rerun()


def logout() -> None:
    """Sign out of Supabase and clear local authentication state."""
    client = get_supabase_client()
    try:
        client.auth.sign_out()
    except Exception:
        # Local state must still be cleared if the network request fails.
        pass
    finally:
        st.session_state.pop(_USER_SESSION_KEY, None)
        for key in list(st.session_state):
            if key.startswith(("lead_", "edit_", "booking_search_")):
                del st.session_state[key]
        st.query_params.clear()
        clear_supabase_client()
        request_scroll_to_top()


def render_logout_button() -> None:
    """Render a logout button and return to the login screen when clicked."""
    if st.button("Log out", width="stretch"):
        logout()
        st.rerun()
