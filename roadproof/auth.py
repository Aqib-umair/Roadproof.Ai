"""Session-scoped demo access with no committed password."""
import hashlib
import hmac
import os
import time

import streamlit as st
from .settings import setting


def open_demo_access():
    return setting("ROADPROOF_ADMIN_MODE", "password").strip().lower() == "demo"


def configured_password():
    value = os.environ.get("ROADPROOF_ADMIN_PASSWORD", "")
    if not value:
        try:
            value = st.secrets.get("admin_password", "")
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            pass
    return str(value)


def is_admin():
    if open_demo_access():
        return True
    password = configured_password()
    fingerprint = hashlib.sha256(password.encode()).hexdigest() if password else ""
    valid = (bool(password) and st.session_state.get("admin_fingerprint") == fingerprint
             and time.time() < st.session_state.get("admin_until", 0))
    return valid


def admin_gate():
    if open_demo_access():
        return True
    if is_admin():
        return True
    st.info("Administrator access is required to change records or review repair evidence.")
    if not configured_password():
        st.caption("Local setup: set ROADPROOF_ADMIN_PASSWORD or admin_password in .streamlit/secrets.toml, then restart. No password is supplied with the prototype.")
        return False
    cooldown = st.session_state.get("login_cooldown", 0)
    if time.time() < cooldown:
        st.warning("Too many attempts. Please wait one minute before trying again.")
        return False
    with st.form("admin_login"):
        value = st.text_input("Demo administrator password", type="password")
        submitted = st.form_submit_button("Unlock demo controls", type="primary")
    if submitted:
        if hmac.compare_digest(value.encode(), configured_password().encode()):
            st.session_state.admin_fingerprint = hashlib.sha256(configured_password().encode()).hexdigest()
            st.session_state.admin_until = time.time() + 3600
            st.session_state.login_attempts = 0
            st.rerun()
        st.session_state.login_attempts = st.session_state.get("login_attempts", 0) + 1
        if st.session_state.login_attempts >= 5:
            st.session_state.login_cooldown = time.time() + 60
            st.session_state.login_attempts = 0
        st.error("The password did not match.")
    return False
