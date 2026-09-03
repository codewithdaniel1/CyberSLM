from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
import streamlit as st

API_URL = os.getenv("CYBERSLM_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = httpx.Timeout(600.0, connect=5.0)


st.set_page_config(
    page_title="CyberSLM",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        color-scheme: light;
        --cyber-green: #08785b;
        --cyber-blue: #126782;
        --cyber-ink: #17212b;
        --cyber-muted: #536574;
        --cyber-border: #d5e0e6;
        --cyber-panel: #ffffff;
    }
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(circle at 82% 3%, rgba(18, 103, 130, .08), transparent 32rem),
            radial-gradient(circle at 12% 95%, rgba(8, 120, 91, .06), transparent 28rem),
            #f7fafc;
        color: var(--cyber-ink);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f2f6f8 0%, #eaf1f4 100%);
        border-right: 1px solid var(--cyber-border);
    }
    .block-container {
        max-width: 1040px;
        padding-top: 2.2rem;
        padding-bottom: 7rem;
    }
    .cyber-brand {
        letter-spacing: .1em;
        font-size: 1.7rem;
        line-height: 1.25;
        font-weight: 750;
        color: var(--cyber-ink);
        margin-bottom: .2rem;
    }
    .cyber-brand span { color: var(--cyber-green); }
    .cyber-subtitle {
        color: var(--cyber-muted);
        font-size: .9rem;
        line-height: 1.5;
        margin-bottom: 1.5rem;
    }
    .mode-card {
        padding: .9rem 1.05rem;
        background: #eef8f5;
        border: 1px solid #c8e3da;
        border-left: 4px solid var(--cyber-green);
        border-radius: 12px;
        color: #344753;
        font-size: 1rem;
        line-height: 1.5;
        margin: .35rem 0 1.25rem;
    }
    .mode-card strong { color: #075f49; }
    .status-dot {
        display: inline-block; width: 8px; height: 8px; border-radius: 50%;
        background: var(--cyber-green);
        margin-right: .45rem;
    }
    [data-testid="stChatMessage"] {
        background: var(--cyber-panel);
        border: 1px solid var(--cyber-border);
        border-radius: 14px;
        box-shadow: 0 2px 8px rgba(29, 52, 65, .04);
        padding: .45rem .85rem;
        margin-bottom: .7rem;
    }
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessage"] li {
        color: var(--cyber-ink);
        font-size: 1rem;
        line-height: 1.68;
    }
    [data-testid="stChatInput"] {
        background: #ffffff;
        border: 1px solid #aec1cb;
        box-shadow: 0 4px 18px rgba(29, 52, 65, .09);
    }
    [data-testid="stChatInput"]:focus-within {
        border-color: var(--cyber-green);
        box-shadow: 0 0 0 3px rgba(8, 120, 91, .12);
    }
    [data-testid="stFileUploader"] {
        background: rgba(255, 255, 255, .72);
        border-radius: 12px;
        padding: .2rem .65rem;
    }
    section[data-testid="stSidebar"] .stButton button {
        justify-content: flex-start;
        text-align: left;
        min-height: 2.65rem;
    }
    .stMarkdown p, .stMarkdown li { line-height: 1.62; }
    .stCaptionContainer { color: var(--cyber-muted); }
    code { color: #075f49 !important; }
    a { color: #075f74 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_request(method: str, path: str, **kwargs: Any) -> Any:
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.request(method, f"{API_URL}{path}", **kwargs)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()
    except httpx.ConnectError as exc:
        raise RuntimeError("CyberSLM backend is offline. Start the app with ./start.sh.") from exc
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text
        raise RuntimeError(str(detail)) from exc


def short_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%b %d · %H:%M")
    except ValueError:
        return ""


def load_or_create_conversation(mode: str) -> str:
    conversations = api_request("GET", "/api/conversations")
    if conversations:
        return conversations[0]["id"]
    conversation = api_request("POST", "/api/conversations", json={"mode": mode})
    return conversation["id"]


try:
    health = api_request("GET", "/api/health")
    modes = api_request("GET", "/api/modes")
except RuntimeError as error:
    st.error(str(error), icon="⚠️")
    st.code("./start.sh", language="bash")
    st.stop()

mode_by_name = {item["name"]: item for item in modes}
mode_names = list(mode_by_name)

if "selected_mode" not in st.session_state:
    st.session_state.selected_mode = "General"
if "conversation_id" not in st.session_state:
    default_key = mode_by_name[st.session_state.selected_mode]["key"]
    st.session_state.conversation_id = load_or_create_conversation(default_key)
if "delete_confirmation" not in st.session_state:
    st.session_state.delete_confirmation = None


with st.sidebar:
    st.markdown('<div class="cyber-brand">CYBER<span>SLM</span></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cyber-subtitle">LOCAL SECURITY INTELLIGENCE</div>',
        unsafe_allow_html=True,
    )

    if st.button("＋ New conversation", use_container_width=True, type="primary"):
        mode_key = mode_by_name[st.session_state.selected_mode]["key"]
        conversation = api_request("POST", "/api/conversations", json={"mode": mode_key})
        st.session_state.conversation_id = conversation["id"]
        st.session_state.delete_confirmation = None
        st.rerun()

    st.caption("CONVERSATIONS")
    conversations = api_request("GET", "/api/conversations")
    for item in conversations:
        active = item["id"] == st.session_state.conversation_id
        label = f"{'◆' if active else '◇'}  {item['title']}"
        if st.button(label, key=f"chat-{item['id']}", use_container_width=True):
            st.session_state.conversation_id = item["id"]
            stored_mode = next((m["name"] for m in modes if m["key"] == item["mode"]), "General")
            st.session_state.selected_mode = stored_mode
            st.session_state.delete_confirmation = None
            st.rerun()
        if active:
            st.caption(short_date(item["updated_at"]))

    active_conversation = next(
        (item for item in conversations if item["id"] == st.session_state.conversation_id),
        None,
    )
    if active_conversation:
        if st.session_state.delete_confirmation == active_conversation["id"]:
            st.warning(f"Delete “{active_conversation['title']}”? This cannot be undone.")
            confirm_column, cancel_column = st.columns(2)
            if confirm_column.button(
                "Delete",
                key="confirm-delete-conversation",
                type="primary",
                use_container_width=True,
            ):
                api_request("DELETE", f"/api/conversations/{active_conversation['id']}")
                remaining = api_request("GET", "/api/conversations")
                if remaining:
                    replacement = remaining[0]
                else:
                    current_mode = mode_by_name[st.session_state.selected_mode]["key"]
                    replacement = api_request(
                        "POST", "/api/conversations", json={"mode": current_mode}
                    )
                st.session_state.conversation_id = replacement["id"]
                st.session_state.selected_mode = next(
                    (m["name"] for m in modes if m["key"] == replacement["mode"]),
                    "General",
                )
                st.session_state.delete_confirmation = None
                st.rerun()
            if cancel_column.button(
                "Cancel", key="cancel-delete-conversation", use_container_width=True
            ):
                st.session_state.delete_confirmation = None
                st.rerun()
        elif st.button(
            "Delete current conversation",
            key="delete-current-conversation",
            icon=":material/delete:",
            use_container_width=True,
        ):
            st.session_state.delete_confirmation = active_conversation["id"]
            st.rerun()

    st.divider()
    model_status = health["model"]
    backend_label = model_status.get("model_id", model_status["backend"])
    load_label = "ready" if model_status["loaded"] else "loads on first prompt"
    st.markdown(
        f'<div class="cyber-subtitle"><span class="status-dot"></span>{backend_label}<br>'
        f'<span style="padding-left: 1.05rem">{load_label} · private/local</span></div>',
        unsafe_allow_html=True,
    )


conversation = api_request("GET", f"/api/conversations/{st.session_state.conversation_id}")
stored_mode_name = next((m["name"] for m in modes if m["key"] == conversation["mode"]), "General")
if st.session_state.selected_mode not in mode_names:
    st.session_state.selected_mode = stored_mode_name

header_left, header_right = st.columns([3, 1.2], vertical_alignment="center")
with header_left:
    st.markdown('<div class="cyber-brand">Cyber<span>SLM</span></div>', unsafe_allow_html=True)
    st.caption("Your private multimodal cybersecurity analyst")
with header_right:
    selected_mode = st.selectbox(
        "Analysis mode",
        mode_names,
        key="selected_mode",
        label_visibility="collapsed",
    )

selected = mode_by_name[selected_mode]
if selected["key"] != conversation["mode"]:
    conversation = api_request(
        "PATCH",
        f"/api/conversations/{conversation['id']}",
        json={"mode": selected["key"]},
    )
    conversation["messages"] = api_request("GET", f"/api/conversations/{conversation['id']}")[
        "messages"
    ]

st.markdown(
    f'<div class="mode-card"><strong>{selected["icon"]} {selected["name"]}</strong>'
    f" &nbsp;·&nbsp; {selected['description']}</div>",
    unsafe_allow_html=True,
)

messages = conversation.get("messages", [])
if not messages:
    st.markdown("### What are we investigating?")
    st.write(
        "Ask about an alert, paste a log or code sample, or attach up to four screenshots. "
        "Everything stays on this Mac."
    )

for message in messages:
    avatar = "assistant" if message["role"] == "assistant" else "user"
    with st.chat_message(message["role"], avatar=avatar):
        for attachment in message.get("attachments", []):
            st.image(attachment["path"], caption=attachment["name"], width=480)
        st.markdown(message["content"])

uploads = st.file_uploader(
    "Attach screenshots (optional)",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
    help="PNG, JPEG, or WebP; up to four images and 10 MB each.",
)
prompt = st.chat_input(f"Ask CyberSLM in {selected['name']} mode…")

if prompt:
    if len(uploads) > 4:
        st.error("Please attach no more than four images.")
        st.stop()

    files = [
        ("images", (upload.name, upload.getvalue(), upload.type or "application/octet-stream"))
        for upload in uploads
    ]
    with st.chat_message("user", avatar="user"):
        for upload in uploads:
            st.image(upload.getvalue(), caption=upload.name, width=480)
        st.markdown(prompt)

    with (
        st.chat_message("assistant", avatar="assistant"),
        st.spinner("Analyzing locally… First model load can take a few minutes."),
    ):
        completed = False
        try:
            result = api_request(
                "POST",
                f"/api/conversations/{conversation['id']}/messages",
                data={"content": prompt, "mode": selected["key"]},
                files=files,
            )
            st.markdown(result["assistant"]["content"])
            completed = True
        except RuntimeError as error:
            st.error(str(error), icon="⚠️")
    if completed:
        st.rerun()

if messages:
    with st.expander("Conversation settings"):
        title = st.text_input("Title", value=conversation["title"], max_chars=120)
        if st.button("Save title", use_container_width=True):
            api_request("PATCH", f"/api/conversations/{conversation['id']}", json={"title": title})
            st.rerun()
