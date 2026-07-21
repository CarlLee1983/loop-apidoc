"""Output models for Markdown API draft facts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DraftField(BaseModel):
    """A literal row from an explicitly labelled parameter table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    name: str
    type: str | None = None
    required: str | None = None
    description: str | None = None
    start_line: int
    end_line: int


class DraftExample(BaseModel):
    """An exact fenced example block inside an endpoint section."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    language: str
    label: str | None = None
    start_line: int
    end_line: int
    content: str


class EndpointDraft(BaseModel):
    """A mechanically recognized endpoint heading and its local facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: str
    path: str
    heading: str
    start_line: int
    end_line: int
    fields: tuple[DraftField, ...] = ()
    examples: tuple[DraftExample, ...] = ()


class MarkdownDraft(BaseModel):
    """Facts from one Markdown source; never an assemble input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str
    endpoints: tuple[EndpointDraft, ...] = ()
    omitted_tables: int = 0


class MarkdownDraftIndex(BaseModel):
    """Deterministic facts across manifest-named Markdown sources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = "markdown_api_drafts"
    authoritative: bool = False
    sources: tuple[MarkdownDraft, ...] = ()
