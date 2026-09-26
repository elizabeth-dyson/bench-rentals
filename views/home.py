import streamlit as st

from components.auth import get_authenticated_user_display_name


def render_home() -> None:
    """Render the authenticated home screen."""
    st.title("Bench Rental Manager")
    st.subheader(f"Welcome, {get_authenticated_user_display_name()}!")
    st.write(
        "This will be the home base for managing the bench rental business. "
        "Bookings and availability tools are coming next."
    )
