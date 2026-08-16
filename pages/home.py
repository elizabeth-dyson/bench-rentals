from typing import Any

import streamlit as st

from components.auth import get_authenticated_user, render_logout_button
from services.supabase import get_supabase_client


def _user_display_name(user: Any) -> str:
    metadata = user.user_metadata or {}
    return metadata.get("display_name") or user.email or "there"


def render_home() -> None:
    """Render the authenticated home screen and verify protected DB access."""
    user = get_authenticated_user()
    if user is None:
        return

    st.title("Bench Rental Manager")
    st.write(f"Welcome, {_user_display_name(user)}!")

    with st.sidebar:
        st.caption(user.email or "Signed in")
        render_logout_button()

    st.subheader("Connection check")
    try:
        response = get_supabase_client().table("bookings").select("*").limit(1).execute()
    except Exception as error:
        st.error("The authenticated bookings query failed.")
        st.exception(error)
    else:
        st.success("Authenticated access to bookings succeeded.")
        st.write(response.data)
