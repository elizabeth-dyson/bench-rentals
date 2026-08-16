import streamlit as st
from supabase import Client, create_client


_CLIENT_SESSION_KEY = "supabase_client"


def get_supabase_client() -> Client:
    """Return a Supabase client scoped to the current Streamlit session."""
    if _CLIENT_SESSION_KEY not in st.session_state:
        st.session_state[_CLIENT_SESSION_KEY] = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"],
        )
    return st.session_state[_CLIENT_SESSION_KEY]


def clear_supabase_client() -> None:
    """Remove the current session's client after logout."""
    st.session_state.pop(_CLIENT_SESSION_KEY, None)
