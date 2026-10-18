"""Small v2 browser bridge. Only the public site key and token cross this boundary."""

import streamlit as st

from services.public_inquiry import TURNSTILE_ACTION


_TURNSTILE = st.components.v2.component(
    "inquiry_turnstile",
    html='<div class="inquiry-verification" aria-label="Spam verification"></div>',
    # Turnstile manages its own iframe and document-level styles.
    isolate_styles=False,
    js="""
export default function ({parentElement, data, setStateValue}) {
  let disposed = false;
  let widget;
  const host = parentElement.querySelector('.inquiry-verification');
  if (!window.__benchTurnstileLoader) {
    window.__benchTurnstileLoader = new Promise((resolve, reject) => {
      if (window.turnstile) { resolve(); return; }
      const script = document.createElement('script');
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => { script.remove(); reject(new Error('load')); };
      document.head.appendChild(script);
    }).catch(error => { window.__benchTurnstileLoader = null; throw error; });
  }
  window.__benchTurnstileLoader.then(() => {
    if (disposed) return;
    widget = window.turnstile.render(host, {
      sitekey: data.siteKey, action: data.action, size: 'flexible',
      callback: token => { if (!disposed) { setStateValue('token', token); setStateValue('error', false); } },
      'expired-callback': () => { if (!disposed) setStateValue('token', ''); },
      'error-callback': () => {
        if (!disposed) { setStateValue('token', ''); setStateValue('error', true); }
      }
    });
  }).catch(() => { if (!disposed) setStateValue('error', true); });
  return () => { disposed = true; if (widget !== undefined && window.turnstile) window.turnstile.remove(widget); };
}
""",
)


def render_turnstile(site_key: str, *, key: str) -> str:
    result = _TURNSTILE(
        key=key, data={"siteKey": site_key, "action": TURNSTILE_ACTION},
        default={"token": "", "error": False},
        on_token_change=lambda: None, on_error_change=lambda: None,
    )
    if result.error:
        st.warning("Verification could not load. Use Restart verification to try again.")
    return result.token or ""
