from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from loop_apidoc.validate.models import ValidationReport


class ContractFormat(str, Enum):
    GRAPHQL = "graphql"
    ASYNCAPI = "asyncapi"


class ProtocolRunInputError(ValueError):
    """The requested protocol run cannot be formed from its input."""


class ProtocolRunResult(BaseModel):
    format: ContractFormat
    status: str
    run_dir: str
    report: ValidationReport

    @property
    def ok(self) -> bool:
        return self.report.ok
