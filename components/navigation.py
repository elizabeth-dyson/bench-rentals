import streamlit as st

from components.auth import (
    get_authenticated_user,
    get_authenticated_user_display_name,
    render_logout_button,
)


def render_navigation() -> None:
    """Render the authenticated app navigation and account controls."""
    user = get_authenticated_user()
    display_name = get_authenticated_user_display_name()

    with st.sidebar:
        st.title("Bench Rental Manager")
        st.caption("Navigation")

        st.button(
            "Home",
            key="nav_home",
            type="primary",
            disabled=True,
            use_container_width=True,
        )
        st.button(
            "Bookings · Coming soon",
            key="nav_bookings",
            disabled=True,
            use_container_width=True,
        )
        st.button(
            "Availability · Coming soon",
            key="nav_availability",
            disabled=True,
            use_container_width=True,
        )
        st.button(
            "Settings · Coming soon",
            key="nav_settings",
            disabled=True,
            use_container_width=True,
        )

        st.divider()
        st.caption("Signed in as")
        st.write(display_name)
        if user is not None and user.email:
            if user.email != display_name:
                st.caption(user.email)
        render_logout_button()
