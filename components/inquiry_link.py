"""Streamlit configuration boundary and shared inquiry-link presentation."""

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from services.inquiry_links import validate_public_inquiry_url


def render_configured_inquiry_link(*, key: str) -> None:
    """Resolve the optional setting at the UI boundary, without database access."""
    try:
        url = validate_public_inquiry_url(st.secrets.get("PUBLIC_INQUIRY_URL"))
    except StreamlitSecretNotFoundError as error:
        # Missing secrets are an unconfigured feature; a malformed secrets file
        # has an underlying parsing error. Never render the error or raw value.
        render_inquiry_link(None, key=key, unavailable=error.__cause__ is not None)
    except ValueError:
        render_inquiry_link(None, key=key, unavailable=True)
    else:
        render_inquiry_link(url, key=key)


def render_inquiry_link(url: str | None, *, key: str, unavailable: bool = False) -> None:
    """Render a validated URL using native controls; copying stays in the browser."""
    with st.container(width="content"):
        with st.popover(
            "Copy inquiry link",
            icon=":material/content_copy:",
            disabled=url is None or unavailable,
            width="content",
            key=key,
            on_change="ignore",
        ):
            if url is not None and not unavailable:
                st.caption("Use the copy icon, then paste the link into your conversation.")
                st.code(url, language=None, wrap_lines=True)
        if unavailable:
            st.caption("The inquiry link is unavailable.")
        elif url is None:
            st.caption("Inquiry form sharing isn’t available yet.")
