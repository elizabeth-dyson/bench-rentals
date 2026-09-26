"""Site-wide scroll restoration for Streamlit navigation."""

from typing import Any

import streamlit as st


_SCROLL_REQUEST_KEY = "_app_scroll_to_top_requested"
_ROUTE_SIGNATURE_KEY = "_app_scroll_route_signature"
_SCROLL_RENDER_KEY = "_app_scroll_render_count"


def request_scroll_to_top() -> None:
    """Request a scroll reset after the next completed Streamlit rerun."""
    st.session_state[_SCROLL_REQUEST_KEY] = True


def render_scroll_to_top() -> None:
    """Reset scroll after a route change or an explicitly requested transition."""
    route_signature = _current_route_signature()
    previous_signature = st.session_state.get(_ROUTE_SIGNATURE_KEY)
    explicitly_requested = bool(st.session_state.pop(_SCROLL_REQUEST_KEY, False))
    st.session_state[_ROUTE_SIGNATURE_KEY] = route_signature

    route_changed = (
        previous_signature is not None and previous_signature != route_signature
    )
    if not explicitly_requested and not route_changed:
        return

    render_count = int(st.session_state.get(_SCROLL_RENDER_KEY, 0)) + 1
    st.session_state[_SCROLL_RENDER_KEY] = render_count

    # This is a constant application-owned script. No user or database content is
    # interpolated into it; the counter only ensures consecutive resets remount.
    st.html(
        f"""
        <span hidden data-scroll-reset="{render_count}"></span>
        <script>
        (() => {{
          const scrollToTop = () => {{
            const scrollers = [
              document.querySelector('[data-testid="stMain"]'),
              document.querySelector('section.main'),
              document.scrollingElement,
            ];
            for (const scroller of scrollers) {{
              if (scroller) {{
                scroller.scrollTop = 0;
                scroller.scrollLeft = 0;
              }}
            }}
            window.scrollTo({{ top: 0, left: 0, behavior: 'auto' }});
          }};

          scrollToTop();
          requestAnimationFrame(() => requestAnimationFrame(scrollToTop));
          setTimeout(scrollToTop, 100);
        }})();
        </script>
        """,
        width="content",
        unsafe_allow_javascript=True,
    )


def _current_route_signature() -> tuple[str, tuple[tuple[str, tuple[Any, ...]], ...]]:
    """Return the current path and query parameters in a stable form."""
    query_values = tuple(
        (key, tuple(st.query_params.get_all(key)))
        for key in sorted(st.query_params.keys())
    )
    return str(st.context.url), query_values
