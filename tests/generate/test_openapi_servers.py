from __future__ import annotations

from loop_apidoc.generate.openapi import build_openapi
from loop_apidoc.plan.models import (
    EndpointEntry,
    EnvironmentEntry,
    NormalizationPlan,
    PlanItemStatus,
)


def _plan(server: str | None) -> NormalizationPlan:
    # notebook_url 是 NormalizationPlan 唯一的必填欄位(無預設值)。
    plan = NormalizationPlan(notebook_url="")
    plan.environments = [
        EnvironmentEntry(name="production", base_url="https://api.example.com",
                         status=PlanItemStatus.SUPPORTED),
        EnvironmentEntry(name="reporting", base_url="https://report.example.com",
                         status=PlanItemStatus.SUPPORTED),
    ]
    plan.endpoints = [
        EndpointEntry(method="GET", path="/bets", summary="查詢投注",
                      server=server, status=PlanItemStatus.SUPPORTED),
    ]
    return plan


def test_endpoint_server_becomes_operation_level_servers():
    doc = build_openapi(_plan("reporting"))

    op = doc["paths"]["/bets"]["get"]
    assert op["servers"] == [
        {"url": "https://report.example.com", "description": "reporting"}
    ]


def test_absent_server_leaves_operation_without_servers():
    """欄位缺席時,產物與現況逐字相同 —— 沿用 root-level servers。"""
    doc = build_openapi(_plan(None))

    assert "servers" not in doc["paths"]["/bets"]["get"]
    assert doc["servers"][0]["url"] == "https://api.example.com"


def test_unknown_server_name_produces_no_operation_servers():
    """cross_file 已在輸入邊界擋下;generator 不臆測,靜默略過而非產出壞 URL。"""
    doc = build_openapi(_plan("nonexistent"))

    assert "servers" not in doc["paths"]["/bets"]["get"]
