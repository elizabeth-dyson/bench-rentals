import streamlit as st

from components.auth import is_authenticated, render_login
from components.navigation import render_navigation
from services.auth_session import (
    render_pending_auth_cookie,
    restore_authenticated_session,
)
from utils.scrolling import render_scroll_to_top


st.set_page_config(
    page_title="Bench Rental Manager",
    page_icon=":material/event_seat:",
    layout="wide",
)

restore_authenticated_session()
render_pending_auth_cookie()

if is_authenticated():
    page = render_navigation()
else:
    page = st.navigation(
        [
            st.Page(render_login, title="Sign in", default=True),
            st.Page(render_login, title="Bookings", url_path="bookings"),
        ],
        position="hidden",
    )

page.run()
render_scroll_to_top()
