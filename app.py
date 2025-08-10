from __future__ import annotations
import os
import time
from typing import Optional, List

import streamlit as st

from backend.storage import Storage


st.set_page_config(page_title="Umer Chat", layout="wide")


def get_storage() -> Storage:
    # Fresh instance each run (stateless), file-backed persistence
    return Storage()


def login_view(storage: Storage) -> None:
    tab_login, tab_signup = st.tabs(["Login", "Sign up"])

    with tab_login:
        st.subheader("Login")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username").strip()
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
        if submitted:
            if username and password and storage.verify_user(username, password):
                st.session_state["username"] = username.lower()
                st.success("Logged in")
                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab_signup:
        st.subheader("Create account")
        with st.form("signup_form", clear_on_submit=True):
            new_username = st.text_input("Username").strip()
            new_password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            submitted_s = st.form_submit_button("Sign up")
        if submitted_s:
            if not new_username or not new_password:
                st.error("Username and password required")
            elif new_password != confirm:
                st.error("Passwords do not match")
            elif storage.user_exists(new_username):
                st.error("Username already exists")
            else:
                ok, msg = storage.create_user(new_username, new_password)
                if ok:
                    st.success("Account created. You can log in now.")
                else:
                    st.error(msg)


def sidebar_view(storage: Storage, username: str) -> Optional[str]:
    st.sidebar.markdown(f"**Logged in as:** `{username}`")
    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()
    # Live updates toggle
    if "auto_refresh" not in st.session_state:
        st.session_state["auto_refresh"] = True
    st.sidebar.checkbox("Auto-refresh (every 3s)", key="auto_refresh")


    st.sidebar.markdown("---")
    st.sidebar.subheader("Your Chats")
    chats = storage.list_user_chats(username)
    chat_labels = []
    for c in chats:
        if c["type"] == "dm":
            others = [p for p in c["participants"] if p != username]
            label = f"DM: {others[0]}" if others else f"DM: {username}"
        else:
            label = f"Group: {c.get('name') or c['chat_id']}"
        chat_labels.append(label)
    selected_idx = None
    if chats:
        selected_idx = st.sidebar.selectbox(
            "Select chat",
            options=list(range(len(chats))),
            format_func=lambda i: chat_labels[i],
            index=0 if "active_chat_id" not in st.session_state else next((i for i, c in enumerate(chats) if c["chat_id"] == st.session_state["active_chat_id"]), 0),
        )
        st.session_state["active_chat_id"] = chats[selected_idx]["chat_id"]

    st.sidebar.markdown("---")
    st.sidebar.subheader("New conversation")
    with st.sidebar.expander("New DM"):
        all_users = [u for u in storage.list_users() if u != username]
        target = st.selectbox("User", options=["-"] + all_users, key="dm_target")
        if st.button("Create DM", key="create_dm"):
            if target and target != "-":
                chat_id = storage.create_private_chat(username, target)
                st.session_state["active_chat_id"] = chat_id
                st.rerun()
            else:
                st.warning("Please select a user")

    with st.sidebar.expander("New Group"):
        group_name = st.text_input("Group name", key="grp_name")
        members = st.multiselect("Participants", options=[u for u in storage.list_users() if u != username], key="grp_members")
        if st.button("Create Group", key="create_group"):
            if group_name and members:
                chat_id = storage.create_group_chat(group_name, [username] + members)
                st.session_state["active_chat_id"] = chat_id
                st.rerun()
            else:
                st.warning("Provide a group name and at least one member")

    return st.session_state.get("active_chat_id")


def render_message(storage: Storage, msg: dict) -> None:
    sender = msg.get("sender", "?")
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(msg.get("ts", time.time())))
    st.markdown(f"**{sender}** · {ts}")
    if msg.get("text"):
        st.write(msg["text"]) 
    if msg.get("image") and os.path.exists(msg["image"]):
        st.image(msg["image"], width=320)
    st.divider()


def chat_view(storage: Storage, username: str, chat_id: str) -> None:
    chat = storage.get_chat(chat_id)
    if not chat:
        st.warning("Chat not found")
        return

    # Header
    if chat["type"] == "dm":
        others = [p for p in chat["participants"] if p != username]
        title = f"DM with {others[0]}" if others else "Direct Message"
    else:
        title = chat.get("name") or chat_id
    st.subheader(title)
    st.caption(
        "Participants: " + ", ".join(chat.get("participants", []))
    )

    # Auto refresh marker in URL (avoid deprecated experimental_set_query_params)
    st.query_params["ts"] = str(int(time.time()))
    st.sidebar.empty()  # keep sidebar reactive
    st_autorefresh = st.empty()
    st_autorefresh.info("Messages refresh every ~3s")
    st.runtime.legacy_caching.clear_cache() if hasattr(st.runtime, "legacy_caching") else None

    # Messages
    with st.container(border=True):
        for msg in chat.get("messages", []):
            render_message(storage, msg)

    # Composer
    st.markdown("---")
    # If we flagged a reset on the previous submit, clear the text before widget creation
    if st.session_state.get("reset_compose", False):
        st.session_state["compose_text"] = ""
        st.session_state["reset_compose"] = False
    with st.form("send_message_form"):
        text = st.text_area("Message", key="compose_text", height=80)
        uploaded = st.file_uploader("Attach image (optional)", type=["png", "jpg", "jpeg", "gif", "webp"], accept_multiple_files=False)
        sent = st.form_submit_button("Send")
    if sent:
        image_path: Optional[str] = None
        if uploaded is not None:
            raw = uploaded.read()
            ext = os.path.splitext(uploaded.name)[1].lstrip(".") or "png"
            image_path = storage.save_image_bytes(raw, ext)
        if (text and text.strip()) or image_path:
            storage.append_message(chat_id, username, text.strip() if text else None, image_path)
            # Flag to clear the text input on next run, then rerun
            st.session_state["reset_compose"] = True
            st.rerun()

    # Auto-refresh loop (polling)
    if st.session_state.get("auto_refresh", True):
        time.sleep(3)
        st.rerun()


def main() -> None:
    storage = get_storage()
    username = st.session_state.get("username")
    if not username:
        login_view(storage)
        return

    active_chat_id = sidebar_view(storage, username)
    if active_chat_id:
        chat_view(storage, username, active_chat_id)
    else:
        st.info("No chat selected. Create a new DM or Group from the sidebar.")


if __name__ == "__main__":
    main()


