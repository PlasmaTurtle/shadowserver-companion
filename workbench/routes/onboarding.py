"""Authenticated local setup endpoints; credential values use existing APIs."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ProfileValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analyst_name: str = Field(min_length=1, max_length=300)
    analyst_title: str = Field(default="", max_length=300)
    agency: str = Field(min_length=1, max_length=500)
    department: str = Field(default="", max_length=500)
    office: str = Field(min_length=1, max_length=500)
    email: str = Field(default="", max_length=500)
    regions: list[str] = Field(min_length=1, max_length=100)
    display_timezone: str = Field(default="America/New_York", max_length=100)


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
        return setup.save_profile(body.model_dump())

    @app.put("/api/setup/progress")
    def progress(body: ProgressValues):
        return setup.progress(body.step, body.mode)

    @app.post("/api/setup/complete")
    def complete():
        return setup.complete()
