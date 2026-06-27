"""Agent-CLI extraction backend (claude -p / codex exec).

An alternative to the NotebookLM browser backend: drive a headless coding-agent
CLI that reads the local source documents directly. Stateless per invocation, so
none of NotebookLM's chat-state pitfalls apply. Mirrors the notebooklm adapter's
ask()/auth contract so the extraction orchestrator can use it unchanged.
"""
