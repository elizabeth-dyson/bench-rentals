import streamlit as st

from components.auth import is_authenticated, render_login
from components.navigation import render_navigation
from pages.home import render_home


st.set_page_config(
    page_title="Bench Rental Manager",
    page_icon="🪑",
    layout="wide",
)

if is_authenticated():
    render_navigation()
    render_home()
else:
    render_login()
