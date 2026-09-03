from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from cyberslm.config import settings
from cyberslm.database import Database
from cyberslm.model import GenerationRequest, create_backend
from cyberslm.modes import AUTHORIZATION_CONTEXTS, MODES, get_mode

settings.ensure_directories()
db = Database(settings.database_path)
model_backend = create_backend(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    db.initialize()
    yield


app = FastAPI(
    title="CyberSLM API",
    description="Local-first multimodal cybersecurity assistant",
    version="0.2.0",
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


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "model": model_backend.status}


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
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> dict:
    conversation = require_conversation(conversation_id)
    selected_mode = mode or conversation["mode"]
    if selected_mode not in MODES:
        raise HTTPException(status_code=422, detail="Unknown cyber mode")
    selected_authorization = authorization_context or conversation["authorization_context"]
    if selected_authorization not in AUTHORIZATION_CONTEXTS:
        raise HTTPException(status_code=422, detail="Unknown authorization context")
    if images and len(images) > 4:
        raise HTTPException(status_code=413, detail="A maximum of four images is supported")

    attachments: list[dict[str, str]] = []
    try:
        for image in images or []:
            attachments.append(await save_image(image))
    except Exception:
        for attachment in attachments:
            Path(attachment["path"]).unlink(missing_ok=True)
        raise

    existing = db.list_messages(conversation_id)
    pending_user_message = {
        "role": "user",
        "content": content.strip(),
        "attachments": attachments,
    }
    history = [*existing, pending_user_message]

    # Reuse the latest image-bearing turn for questions such as "what about the IP here?"
    # without sending every screenshot in a long conversation back through the vision encoder.
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
    image_paths = [Path(item["path"]) for item in active_attachments]
    try:
        response_text = await run_in_threadpool(
            model_backend.generate,
            GenerationRequest(
                get_mode(selected_mode), history, image_paths, selected_authorization
            ),
        )
    except RuntimeError as exc:
        for attachment in attachments:
            Path(attachment["path"]).unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    user_message = db.add_message(conversation_id, "user", content.strip(), attachments)
    assistant_message = db.add_message(conversation_id, "assistant", response_text)
    updates = {
        "mode": selected_mode,
        "authorization_context": selected_authorization,
    }
    if not existing:
        updates["title"] = clean_title(content)
    db.update_conversation(conversation_id, **updates)
    return {"user": user_message, "assistant": assistant_message, "model": model_backend.status}
