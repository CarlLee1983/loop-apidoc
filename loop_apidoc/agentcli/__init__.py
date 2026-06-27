"""Agent-CLI extraction backend (claude -p / codex exec).

Drives a headless coding-agent CLI that reads the local source documents
directly. Each invocation is stateless, so there is no accumulated chat state to
corrupt extraction. Exposes a simple ask() contract consumed by the collapsed
extraction pipeline.
"""
