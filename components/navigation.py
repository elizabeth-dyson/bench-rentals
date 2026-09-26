import streamlit as st

from components.auth import (
    get_authenticated_user,
    get_authenticated_user_display_name,
    render_logout_button,
)
from views.bookings import render_bookings
from views.home import render_home


def render_navigation():
    """Render authenticated navigation and return the selected Streamlit page."""
    user = get_authenticated_user()
    display_name = get_authenticated_user_display_name()

    page = st.navigation(
        {
            "Bench Rental Manager": [
                st.Page(
                    render_home,
                    title="Home",
                    icon=":material/home:",
                    default=True,
                ),
                st.Page(
                    render_bookings,
                    title="Bookings",
                    icon=":material/event_note:",
                    url_path="bookings",
                ),
            ]
        },
        position="sidebar",
    )

    with st.sidebar:
        st.caption("Coming soon")
        st.button(
            "Availability",
            key="nav_availability",
            disabled=True,
            width="stretch",
        )
        st.button(
            "Settings",
            key="nav_settings",
            disabled=True,
            width="stretch",
        )

        st.divider()
        st.caption("Signed in as")
        st.write(display_name)
        if user is not None and user.email:
            if user.email != display_name:
                st.caption(user.email)
        render_logout_button()

    return page
