from urllib.parse import urlsplit

import streamlit as st

from components.auth import is_authenticated, render_login
from components.navigation import render_navigation
from services.auth_session import (
    render_pending_auth_cookie,
    restore_authenticated_session,
)
from utils.scrolling import render_scroll_to_top
from views.inquiry import render_inquiry


st.set_page_config(
    page_title="Bench Rental Manager",
    page_icon=":material/event_seat:",
    layout="wide",
)

# Direct public requests bypass staff cookies, restoration, and navigation.
public_route = urlsplit(st.context.url or "").path.rstrip("/") == "/inquiry"
inquiry_page = st.Page(render_inquiry, title="Request a quote", url_path="inquiry", visibility="hidden")

if not public_route:
    restore_authenticated_session()
    render_pending_auth_cookie()

if public_route:
    page = st.navigation([st.Page(render_login, title="Sign in", default=True), inquiry_page], position="hidden")
elif is_authenticated():
    page = render_navigation()
else:
    page = st.navigation(
        [
            st.Page(render_login, title="Sign in", default=True),
            st.Page(render_login, title="Bookings", url_path="bookings"),
            inquiry_page,
        ],
        position="hidden",
    )

page.run()
render_scroll_to_top()
