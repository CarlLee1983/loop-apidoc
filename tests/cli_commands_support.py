"""The registered CLI command names, derived from the typer app itself.

The app is its own inventory, so a check that documents or gates must cover every
command reads the names from here rather than from a second hand-kept list.
"""

from __future__ import annotations


def registered_cli_commands() -> set[str]:
    """Every invocable command name, sub-app commands included as
    `"<group> <command>"`. Names come from typer's own derivation rather than a
    local copy of it, so an unnamed command cannot drift out of the check."""
    from typer.main import get_command_name

    from loop_apidoc.cli import app

    def names(typer_app, prefix: str = "") -> set[str]:
        found = {
            prefix + (command.name or get_command_name(command.callback.__name__))
            for command in typer_app.registered_commands
        }
        for group in typer_app.registered_groups:
            group_name = group.name or get_command_name(group.typer_instance.info.name or "")
            found |= names(group.typer_instance, f"{prefix}{group_name} ")
        return found

    return names(app)
