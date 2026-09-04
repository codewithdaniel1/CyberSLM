from __future__ import annotations

import json
import os
from contextlib import suppress
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
    authorization_contexts = api_request("GET", "/api/authorization-contexts")
except RuntimeError as error:
    st.error(str(error), icon="⚠️")
    st.code("./start.sh", language="bash")
    st.stop()

mode_by_name = {item["name"]: item for item in modes}
mode_names = list(mode_by_name)
authorization_by_name = {item["name"]: item for item in authorization_contexts}
authorization_names = list(authorization_by_name)

if "selected_mode" not in st.session_state:
    st.session_state.selected_mode = "General"
if "conversation_id" not in st.session_state:
    default_key = mode_by_name[st.session_state.selected_mode]["key"]
    st.session_state.conversation_id = load_or_create_conversation(default_key)
if "selected_authorization" not in st.session_state:
    initial_conversation = api_request(
        "GET", f"/api/conversations/{st.session_state.conversation_id}"
    )
    st.session_state.selected_authorization = next(
        (
            item["name"]
            for item in authorization_contexts
            if item["key"] == initial_conversation.get("authorization_context", "unspecified")
        ),
        "Not specified",
    )
if "delete_confirmation" not in st.session_state:
    st.session_state.delete_confirmation = None
if "active_generation_id" not in st.session_state:
    st.session_state.active_generation_id = None
if "rag_policy" not in st.session_state:
    st.session_state.rag_policy = "Auto"


with st.sidebar:
    st.markdown('<div class="cyber-brand">CYBER<span>SLM</span></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="cyber-subtitle">LOCAL SECURITY INTELLIGENCE</div>',
        unsafe_allow_html=True,
    )

    if st.button("＋ New conversation", use_container_width=True, type="primary"):
        mode_key = mode_by_name[st.session_state.selected_mode]["key"]
        authorization_key = authorization_by_name[st.session_state.selected_authorization]["key"]
        conversation = api_request(
            "POST",
            "/api/conversations",
            json={"mode": mode_key, "authorization_context": authorization_key},
        )
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
            st.session_state.selected_authorization = next(
                (
                    context["name"]
                    for context in authorization_contexts
                    if context["key"] == item.get("authorization_context", "unspecified")
                ),
                "Not specified",
            )
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
                    current_authorization = authorization_by_name[
                        st.session_state.selected_authorization
                    ]["key"]
                    replacement = api_request(
                        "POST",
                        "/api/conversations",
                        json={
                            "mode": current_mode,
                            "authorization_context": current_authorization,
                        },
                    )
                st.session_state.conversation_id = replacement["id"]
                st.session_state.selected_mode = next(
                    (m["name"] for m in modes if m["key"] == replacement["mode"]),
                    "General",
                )
                st.session_state.selected_authorization = next(
                    (
                        context["name"]
                        for context in authorization_contexts
                        if context["key"] == replacement.get("authorization_context", "unspecified")
                    ),
                    "Not specified",
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
    knowledge_status = health.get("knowledge", {})
    knowledge_count = knowledge_status.get("document_count", 0)
    passage_count = knowledge_status.get("chunk_count", 0)
    embedding_count = max(
        (item.get("count", 0) for item in knowledge_status.get("embedding_models", [])),
        default=0,
    )
    if health.get("rag_enabled") and knowledge_count:
        if health.get("rag_semantic_enabled") and embedding_count >= passage_count > 0:
            knowledge_label = f"Hybrid RAG ready · {embedding_count:,} passages"
        elif health.get("rag_semantic_enabled") and embedding_count:
            knowledge_label = f"Semantic indexing · {embedding_count:,}/{passage_count:,}"
        else:
            knowledge_label = f"Lexical RAG ready · {knowledge_count:,} references"
    elif health.get("rag_enabled"):
        knowledge_label = "RAG empty · run knowledge sync"
    else:
        knowledge_label = "RAG disabled"
    st.markdown(
        f'<div class="cyber-subtitle"><span class="status-dot"></span>{backend_label}<br>'
        f'<span style="padding-left: 1.05rem">{load_label} · private/local</span><br>'
        f'<span style="padding-left: 1.05rem">{knowledge_label}</span></div>',
        unsafe_allow_html=True,
    )
    if health.get("rag_enabled"):
        with st.expander("Knowledge and updates"):
            for source in knowledge_status.get("sources", []):
                st.markdown(
                    f"**{source['name']} {source['version']}**  \n"
                    f"{source['document_count']:,} indexed documents"
                )
            sync_status = api_request("GET", "/api/knowledge/sync")
            if sync_status["status"] == "running":
                st.info(sync_status["message"])
                if sync_status["total"]:
                    st.progress(
                        min(sync_status["completed"] / sync_status["total"], 1.0)
                    )
                if st.button("Refresh update status", use_container_width=True):
                    st.rerun()
            elif sync_status["status"] == "failed":
                st.error(sync_status.get("error") or sync_status["message"])
            elif sync_status["status"] == "complete":
                st.success(sync_status["message"])
            if st.button(
                "Sync verified knowledge",
                disabled=sync_status["status"] == "running",
                help="Downloads pinned sources, verifies hashes, and resumes local embeddings.",
                use_container_width=True,
            ):
                api_request("POST", "/api/knowledge/sync")
                st.rerun()
            st.code(
                "uv run cyberslm-knowledge sync\nuv run cyberslm-knowledge verify",
                language="bash",
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
authorization_name = st.selectbox(
    "Environment / authorization context",
    authorization_names,
    key="selected_authorization",
    help=(
        "Saved with this conversation as user-provided context. "
        "It does not verify permission or override safety boundaries."
    ),
)
authorization = authorization_by_name[authorization_name]
st.caption(authorization["description"])

conversation_updates = {}
if selected["key"] != conversation["mode"]:
    conversation_updates["mode"] = selected["key"]
if authorization["key"] != conversation.get("authorization_context", "unspecified"):
    conversation_updates["authorization_context"] = authorization["key"]
if conversation_updates:
    conversation = api_request(
        "PATCH",
        f"/api/conversations/{conversation['id']}",
        json=conversation_updates,
    )
    conversation["messages"] = api_request("GET", f"/api/conversations/{conversation['id']}")[
        "messages"
    ]

st.markdown(
    f'<div class="mode-card"><strong>{selected["icon"]} {selected["name"]}</strong>'
    f" &nbsp;·&nbsp; {selected['description']}</div>",
    unsafe_allow_html=True,
)
if selected["key"] in {"offensive", "ctf"} and authorization["key"] == "unspecified":
    st.warning(
        "Set the environment context before requesting operational offensive or CTF guidance."
    )

if st.session_state.active_generation_id and st.button(
    "Stop generating",
    key="cancel-active-generation",
    icon=":material/stop_circle:",
    type="primary",
):
    with suppress(RuntimeError):
        api_request("DELETE", f"/api/generations/{st.session_state.active_generation_id}")
    st.session_state.active_generation_id = None
    st.rerun()

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
rag_policy = st.segmented_control(
    "Local knowledge",
    options=["Auto", "On", "Off"],
    key="rag_policy",
    disabled=not health.get("rag_enabled"),
    help=(
        "Auto searches local ATT&CK, CWE, or CAPEC references only when this message appears "
        "to benefit. On always searches; Off answers without local references."
    ),
)
if health.get("rag_enabled"):
    st.caption(
        "Auto is recommended: exact IDs always search, while ordinary conversation skips RAG."
    )
else:
    st.caption("Local knowledge is disabled by CYBERSLM_RAG_ENABLED.")
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

    stream_state = {"completed": False}
    try:
        with httpx.Client(timeout=TIMEOUT) as client, client.stream(
            "POST",
            f"{API_URL}/api/conversations/{conversation['id']}/messages/stream",
            data={
                "content": prompt,
                "mode": selected["key"],
                "authorization_context": authorization["key"],
                "rag_policy": (rag_policy or "Auto").lower(),
            },
            files=files,
        ) as response:
            response.raise_for_status()
            lines = response.iter_lines()
            first = json.loads(next(lines))
            if first.get("type") != "start":
                raise RuntimeError("The local generation stream did not start correctly.")
            st.session_state.active_generation_id = first["generation_id"]
            selected_sources = first.get("knowledge", [])
            rag_result = first.get("rag", {})
            if selected_sources:
                with st.expander(
                    f"{len(selected_sources)} local source(s) selected",
                    expanded=True,
                ):
                    for source in selected_sources:
                        st.markdown(
                            f"[{source['title']}]({source['url']})  \n"
                            f"{source['source_key']} {source['source_version']} · "
                            f"{source['retrieval_method']}"
                        )
            elif rag_result.get("attempted"):
                st.caption("Local knowledge was searched, but no matching reference was found.")
            elif rag_result.get("reason") == "not_source_relevant":
                st.caption("Auto skipped local knowledge for this message.")
            elif rag_result.get("reason") == "disabled_for_message":
                st.caption("Local knowledge was off for this message.")

            with st.chat_message("assistant", avatar="assistant"):
                st.button(
                    "Stop generating",
                    key="cancel-active-generation",
                    icon=":material/stop_circle:",
                )

                def tokens():
                    for line in lines:
                        event = json.loads(line)
                        if event["type"] == "token":
                            yield event["text"]
                        elif event["type"] == "done":
                            stream_state["completed"] = True
                        elif event["type"] == "cancelled":
                            return
                        elif event["type"] == "error":
                            raise RuntimeError(event.get("detail", "Local generation failed"))

                st.write_stream(tokens())
    except (httpx.HTTPError, RuntimeError, StopIteration, ValueError) as error:
        st.error(str(error), icon="⚠️")
    finally:
        st.session_state.active_generation_id = None
    if stream_state["completed"]:
        st.rerun()

if messages:
    with st.expander("Conversation settings"):
        title = st.text_input("Title", value=conversation["title"], max_chars=120)
        if st.button("Save title", use_container_width=True):
            api_request("PATCH", f"/api/conversations/{conversation['id']}", json={"title": title})
            st.rerun()
