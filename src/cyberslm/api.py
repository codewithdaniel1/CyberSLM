from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from cyberslm.code_validation import CCodeValidator, validation_footer
from cyberslm.config import settings
from cyberslm.database import Database
from cyberslm.knowledge import KnowledgeStore
from cyberslm.knowledge.embeddings import LocalEmbedder, rebuild_embeddings
from cyberslm.knowledge.ingest import sync_source
from cyberslm.knowledge.retrieve import RetrievalDecision, decide_retrieval, retrieve
from cyberslm.knowledge.sources import SOURCES
from cyberslm.knowledge.sync_job import KnowledgeSyncManager
from cyberslm.model import GenerationCancelled, GenerationRequest, create_backend
from cyberslm.modes import AUTHORIZATION_CONTEXTS, MODES, get_mode
from cyberslm.response_guard import apply_response_guard, response_guard_status

settings.ensure_directories()
db = Database(settings.database_path)
knowledge_store = KnowledgeStore(settings.knowledge_database_path)
knowledge_embedder = (
    LocalEmbedder(settings.rag_embedding_model, settings.embedding_cache_dir)
    if settings.rag_semantic_enabled
    else None
)
model_backend = create_backend(settings)
knowledge_sync = KnowledgeSyncManager()
code_validator = CCodeValidator(
    enabled=settings.code_validation_enabled,
    configured_compiler=settings.c_compiler,
    timeout_seconds=max(0.5, settings.code_validation_timeout),
)
_generation_lock = threading.Lock()
_generations: dict[str, threading.Event] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    db.initialize()
    yield


app = FastAPI(
    title="CyberSLM API",
    description="Local-first multimodal cybersecurity assistant",
    version="0.5.0",
    lifespan=lifespan,
)


class ConversationCreate(BaseModel):
    mode: str = "general"
    title: str = Field(default="New conversation", min_length=1, max_length=120)
    authorization_context: str = "unspecified"


class ConversationUpdate(BaseModel):
    mode: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    authorization_context: str | None = None


@dataclass(slots=True)
class PreparedMessage:
    conversation_id: str
    content: str
    selected_mode: str
    selected_authorization: str
    attachments: list[dict[str, str]]
    existing: list[dict]
    request: GenerationRequest
    knowledge_documents: list[dict]
    retrieval_decision: RetrievalDecision
    code_validation_requested: bool


def require_conversation(conversation_id: str) -> dict:
    conversation = db.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def clean_title(content: str) -> str:
    compact = " ".join(content.split())
    if len(compact) <= 52:
        return compact
    return f"{compact[:49].rstrip()}…"


async def save_image(upload: UploadFile) -> dict[str, str]:
    allowed = {"image/png", "image/jpeg", "image/webp"}
    if upload.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Only PNG, JPEG, and WebP images are supported")

    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[upload.content_type]
    path = settings.upload_dir / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with path.open("wb") as destination:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Image exceeds the {settings.max_upload_mb} MB limit",
                    )
                destination.write(chunk)
        with Image.open(path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400, detail="The uploaded file is not a valid image"
        ) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return {
        "name": upload.filename or path.name,
        "content_type": upload.content_type,
        "path": str(path),
    }


def public_knowledge(documents: list[dict]) -> list[dict]:
    return [
        {
            "id": document["id"],
            "title": document["title"],
            "url": document["url"],
            "source_key": document["source_key"],
            "source_version": document["source_version"],
            "retrieval_method": document["retrieval_method"],
        }
        for document in documents
    ]


def delete_attachments(attachments: list[dict[str, str]]) -> None:
    for attachment in attachments:
        Path(attachment["path"]).unlink(missing_ok=True)


async def prepare_message(
    conversation_id: str,
    content: str,
    mode: str | None,
    authorization_context: str | None,
    rag_policy: str,
    validate_code: bool,
    images: list[UploadFile] | None,
) -> PreparedMessage:
    conversation = require_conversation(conversation_id)
    selected_mode = mode or conversation["mode"]
    if selected_mode not in MODES:
        raise HTTPException(status_code=422, detail="Unknown cyber mode")
    selected_authorization = authorization_context or conversation["authorization_context"]
    if selected_authorization not in AUTHORIZATION_CONTEXTS:
        raise HTTPException(status_code=422, detail="Unknown authorization context")
    try:
        retrieval_decision = decide_retrieval(
            content,
            selected_mode,
            rag_policy,
            enabled=settings.rag_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if images and len(images) > 4:
        raise HTTPException(status_code=413, detail="A maximum of four images is supported")

    attachments: list[dict[str, str]] = []
    try:
        for image in images or []:
            attachments.append(await save_image(image))
    except Exception:
        delete_attachments(attachments)
        raise

    existing = db.list_messages(conversation_id)
    history = [
        *existing,
        {"role": "user", "content": content.strip(), "attachments": attachments},
    ]
    active_attachments = attachments
    if not active_attachments:
        active_attachments = next(
            (
                message["attachments"]
                for message in reversed(existing)
                if message["role"] == "user" and message["attachments"]
            ),
            [],
        )
    knowledge_documents = []
    if retrieval_decision.should_retrieve:
        knowledge_documents = retrieve(
            knowledge_store,
            content,
            selected_mode,
            limit=settings.rag_results,
            max_chars=settings.rag_max_chars,
            embedder=knowledge_embedder,
            source_keys=retrieval_decision.source_keys,
        )
    return PreparedMessage(
        conversation_id=conversation_id,
        content=content.strip(),
        selected_mode=selected_mode,
        selected_authorization=selected_authorization,
        attachments=attachments,
        existing=existing,
        request=GenerationRequest(
            get_mode(selected_mode),
            history,
            [Path(item["path"]) for item in active_attachments],
            selected_authorization,
            knowledge_documents,
        ),
        knowledge_documents=knowledge_documents,
        retrieval_decision=retrieval_decision,
        code_validation_requested=validate_code,
    )


def apply_output_checks(
    prepared: PreparedMessage,
    response_text: str,
) -> tuple[str, dict, dict]:
    guarded = apply_response_guard(prepared.request, response_text)
    report = code_validator.validate(
        guarded.text,
        requested=prepared.code_validation_requested,
    )
    return guarded.text + validation_footer(report), report, guarded.metadata()


def persist_message(
    prepared: PreparedMessage,
    response_text: str,
    code_validation: dict,
    response_guard: dict,
) -> dict:
    user_message = db.add_message(
        prepared.conversation_id,
        "user",
        prepared.content,
        prepared.attachments,
    )
    assistant_message = db.add_message(
        prepared.conversation_id,
        "assistant",
        response_text,
    )
    updates = {
        "mode": prepared.selected_mode,
        "authorization_context": prepared.selected_authorization,
    }
    if not prepared.existing:
        updates["title"] = clean_title(prepared.content)
    db.update_conversation(prepared.conversation_id, **updates)
    return {
        "user": user_message,
        "assistant": assistant_message,
        "model": model_backend.status,
        "knowledge": public_knowledge(prepared.knowledge_documents),
        "rag": prepared.retrieval_decision.metadata(len(prepared.knowledge_documents)),
        "code_validation": code_validation,
        "response_guard": response_guard,
    }


def ndjson_event(event_type: str, **payload: object) -> str:
    return json.dumps({"type": event_type, **payload}, separators=(",", ":")) + "\n"


def rebuild_knowledge(update) -> None:
    source_dir = settings.knowledge_dir / "sources"
    source_total = len(SOURCES)
    for position, source in enumerate(SOURCES.values(), start=1):
        update(
            phase="sources",
            message=f"Verifying and indexing {source.name} {source.version}…",
            completed=position - 1,
            total=source_total,
        )
        sync_source(knowledge_store, source, source_dir)
        update(completed=position)

    embedder = LocalEmbedder(
        settings.rag_embedding_model,
        settings.embedding_cache_dir,
        allow_download=True,
    )

    def embedding_progress(completed: int, total: int) -> None:
        update(
            phase="embeddings",
            message=f"Building local semantic index: {completed:,}/{total:,}",
            completed=completed,
            total=total,
        )

    update(
        phase="embeddings",
        message="Checking local semantic index…",
        completed=0,
        total=knowledge_store.status()["chunk_count"],
    )
    rebuild_embeddings(knowledge_store, embedder, progress=embedding_progress)
    status = knowledge_store.status()
    indexed = {item["source_key"]: item for item in status["sources"]}
    if any(
        source.key not in indexed
        or indexed[source.key]["version"] != source.version
        or indexed[source.key]["sha256"] != source.sha256
        or indexed[source.key]["document_count"] != source.document_count
        for source in SOURCES.values()
    ):
        raise RuntimeError("Indexed source metadata did not pass verification")
    embedded = next(
        (
            item["count"]
            for item in status["embedding_models"]
            if item["model"] == settings.rag_embedding_model
        ),
        0,
    )
    if settings.rag_semantic_enabled and embedded != status["chunk_count"]:
        raise RuntimeError(
            f"Semantic index is incomplete: {embedded}/{status['chunk_count']} passages"
        )


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": model_backend.status,
        "knowledge": knowledge_store.status(),
        "rag_enabled": settings.rag_enabled,
        "rag_semantic_enabled": settings.rag_semantic_enabled,
        "code_validation": code_validator.status,
        "response_guard": response_guard_status(),
    }


@app.get("/api/modes")
def list_modes() -> list[dict]:
    return [
        {
            "key": mode.key,
            "name": mode.name,
            "icon": mode.icon,
            "description": mode.description,
        }
        for mode in MODES.values()
    ]


@app.get("/api/authorization-contexts")
def list_authorization_contexts() -> list[dict]:
    return [
        {
            "key": context.key,
            "name": context.name,
            "description": context.description,
        }
        for context in AUTHORIZATION_CONTEXTS.values()
    ]


@app.get("/api/knowledge/status")
def knowledge_status() -> dict:
    return {
        **knowledge_store.status(),
        "enabled": settings.rag_enabled,
        "sync": knowledge_sync.status(),
    }


@app.get("/api/knowledge/sync")
def knowledge_sync_status() -> dict:
    return knowledge_sync.status()


@app.post("/api/knowledge/sync", status_code=202)
def start_knowledge_sync() -> dict:
    job = knowledge_sync.start(rebuild_knowledge)
    if job is None:
        raise HTTPException(status_code=409, detail="Knowledge synchronization is already running")
    return job


@app.get("/api/knowledge/search")
def search_knowledge(q: str, limit: int = 4, mode: str = "general") -> list[dict]:
    if mode not in MODES:
        raise HTTPException(status_code=422, detail="Unknown cyber mode")
    return retrieve(
        knowledge_store,
        q,
        mode,
        limit=min(max(limit, 1), 10),
        max_chars=settings.rag_max_chars,
        embedder=knowledge_embedder,
    )


@app.get("/api/conversations")
def list_conversations() -> list[dict]:
    return db.list_conversations()


@app.post("/api/conversations", status_code=201)
def create_conversation(payload: ConversationCreate) -> dict:
    if payload.mode not in MODES:
        raise HTTPException(status_code=422, detail="Unknown cyber mode")
    if payload.authorization_context not in AUTHORIZATION_CONTEXTS:
        raise HTTPException(status_code=422, detail="Unknown authorization context")
    return db.create_conversation(
        mode=payload.mode,
        title=payload.title,
        authorization_context=payload.authorization_context,
    )


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    conversation = require_conversation(conversation_id)
    conversation["messages"] = db.list_messages(conversation_id)
    return conversation


@app.patch("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: str, payload: ConversationUpdate) -> dict:
    require_conversation(conversation_id)
    if payload.mode is not None and payload.mode not in MODES:
        raise HTTPException(status_code=422, detail="Unknown cyber mode")
    if (
        payload.authorization_context is not None
        and payload.authorization_context not in AUTHORIZATION_CONTEXTS
    ):
        raise HTTPException(status_code=422, detail="Unknown authorization context")
    return db.update_conversation(
        conversation_id,
        title=payload.title,
        mode=payload.mode,
        authorization_context=payload.authorization_context,
    )  # type: ignore[return-value]


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str) -> None:
    conversation = require_conversation(conversation_id)
    messages = db.list_messages(conversation_id)
    db.delete_conversation(conversation_id)
    for message in messages:
        for attachment in message["attachments"]:
            path = Path(attachment.get("path", ""))
            if path.parent == settings.upload_dir:
                path.unlink(missing_ok=True)
    del conversation


@app.post("/api/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    content: Annotated[str, Form(min_length=1, max_length=50_000)],
    mode: Annotated[str | None, Form()] = None,
    authorization_context: Annotated[str | None, Form()] = None,
    rag_policy: Annotated[str, Form()] = "auto",
    validate_code: Annotated[bool, Form()] = False,
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> dict:
    prepared = await prepare_message(
        conversation_id,
        content,
        mode,
        authorization_context,
        rag_policy,
        validate_code,
        images,
    )
    try:
        response_text = await run_in_threadpool(
            model_backend.generate,
            prepared.request,
        )
    except RuntimeError as exc:
        delete_attachments(prepared.attachments)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    response_text, validation, guard = await run_in_threadpool(
        apply_output_checks,
        prepared,
        response_text,
    )
    return persist_message(prepared, response_text, validation, guard)


@app.post("/api/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str,
    content: Annotated[str, Form(min_length=1, max_length=50_000)],
    mode: Annotated[str | None, Form()] = None,
    authorization_context: Annotated[str | None, Form()] = None,
    rag_policy: Annotated[str, Form()] = "auto",
    validate_code: Annotated[bool, Form()] = False,
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> StreamingResponse:
    prepared = await prepare_message(
        conversation_id,
        content,
        mode,
        authorization_context,
        rag_policy,
        validate_code,
        images,
    )
    generation_id = uuid.uuid4().hex
    cancellation = threading.Event()
    with _generation_lock:
        _generations[generation_id] = cancellation

    def events() -> Iterator[str]:
        chunks: list[str] = []
        completed = False
        try:
            yield ndjson_event(
                "start",
                generation_id=generation_id,
                knowledge=public_knowledge(prepared.knowledge_documents),
                rag=prepared.retrieval_decision.metadata(len(prepared.knowledge_documents)),
                code_validation={
                    "requested": prepared.code_validation_requested,
                    **code_validator.status,
                },
                response_guard=response_guard_status(),
            )
            for chunk in model_backend.stream(prepared.request, cancellation.is_set):
                chunks.append(chunk)
            response_text = "".join(chunks).strip()
            if not response_text:
                response_text = "The model returned an empty response."
            response_text, validation, guard = apply_output_checks(prepared, response_text)
            for start in range(0, len(response_text), 64):
                if cancellation.is_set():
                    raise GenerationCancelled
                yield ndjson_event("token", text=response_text[start : start + 64])
            result = persist_message(prepared, response_text, validation, guard)
            completed = True
            yield ndjson_event("done", result=result)
        except GenerationCancelled:
            yield ndjson_event("cancelled")
        except RuntimeError as exc:
            yield ndjson_event("error", detail=str(exc))
        finally:
            if not completed:
                delete_attachments(prepared.attachments)
            with _generation_lock:
                _generations.pop(generation_id, None)

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.delete("/api/generations/{generation_id}", status_code=202)
def cancel_generation(generation_id: str) -> dict[str, bool]:
    with _generation_lock:
        cancellation = _generations.get(generation_id)
    if cancellation is None:
        raise HTTPException(status_code=404, detail="Generation is no longer active")
    cancellation.set()
    return {"cancelled": True}
