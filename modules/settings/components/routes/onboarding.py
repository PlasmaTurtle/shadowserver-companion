"""Authenticated local setup endpoints; credential values use existing APIs."""

from typing import Literal
from pydantic import BaseModel, ConfigDict

from ..api_models import ProfileValues


class ProgressValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: Literal["connections", "automation"]
    mode: Literal["configured", "manual"]


def register(app, *, setup):
    @app.get("/api/setup")
    def status():
        return setup.status()

    @app.put("/api/setup/profile")
    def profile(body: ProfileValues):
        return setup.save_profile(body.model_dump(exclude_unset=True))

    @app.put("/api/setup/progress")
    def progress(body: ProgressValues):
        return setup.progress(body.step, body.mode)

    @app.post("/api/setup/complete")
    def complete():
        return setup.complete()
