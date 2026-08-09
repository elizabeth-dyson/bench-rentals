import streamlit as st
from supabase import Client, create_client


@st.cache_resource
def get_supabase() -> Client:
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


supabase = get_supabase()


st.set_page_config(
    page_title="Bench Rental Manager",
    page_icon="🪑",
    layout="wide",
)

st.title("🪑 Bench Rental Manager")
st.success("The bench empire is online.")

response = supabase.table("connection-test").select("*").execute()

st.write(response.data)