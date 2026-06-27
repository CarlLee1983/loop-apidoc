from __future__ import annotations

from loop_apidoc.agentcli.config import AgentConfig

# Grounding contract: the agent must answer ONLY from the local source files and
# never from prior knowledge or the web. Read-only tools enforce the boundary;
# this system prompt enforces the intent and the "say so when absent" rule.
GROUNDING_SYSTEM_PROMPT = (
    "You are a source-grounded API-documentation extractor. Answer ONLY from the "
    "source documents in the directory provided to you (read them with your file "
    "tools). Never use prior knowledge, REST/OAuth conventions, or the web. If the "
    "sources do not state something, say so explicitly rather than guessing. When "
    "you state a fact, it must be supported by the sources. Output exactly what the "
    "question asks for and nothing else."
)


def build_ask_argv(config: AgentConfig, question: str) -> list[str]:
    prompt = (
        f"Read the source document(s) under {config.sources_dir} and answer the "
        f"following STRICTLY from them.\n\n{question}"
    )
    argv = [
        config.executable,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--append-system-prompt",
        GROUNDING_SYSTEM_PROMPT,
        "--add-dir",
        str(config.sources_dir),
    ]
    if config.allowed_tools:
        argv += ["--allowedTools", *config.allowed_tools]
    if config.model:
        argv += ["--model", config.model]
    return argv
