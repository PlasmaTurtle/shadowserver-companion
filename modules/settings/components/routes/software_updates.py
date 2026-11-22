"""Authenticated local software-update operations; distribution URLs are server-owned."""

from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from ..software_updates import UpdateError


class SeenVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=32)


class InstallReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = Field(min_length=1, max_length=32)
    channel: Literal["stable", "candidate", "unstable"]
    installer_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def register(app, *, updates):
    def call(action):
        try:
            return action()
        except UpdateError as error:
            raise HTTPException(409, detail=str(error)) from None

    @app.get("/api/software/status")
    def status():
        return updates.status()

    @app.post("/api/software/check", status_code=202)
    def check():
        return call(lambda: updates.start("check"))

    @app.post("/api/software/download", status_code=202)
    def download():
        return call(lambda: updates.start("download"))

    @app.post("/api/software/install", status_code=202)
    def install(body: InstallReview, background: BackgroundTasks):
        result = call(lambda: updates.prepare_install(body.model_dump()))
        background.add_task(updates.install)
        return result

    @app.get("/api/software/whats-new")
    def whats_new():
        return updates.whats_new()

    @app.post("/api/software/whats-new/seen")
    def seen(body: SeenVersion):
        return call(lambda: updates.mark_seen(body.version))
