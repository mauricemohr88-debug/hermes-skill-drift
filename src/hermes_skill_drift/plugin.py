"""Native Hermes CLI adapter; deliberately no model-callable filesystem tool."""

from .cli import configure, execute


def register(ctx):
    ctx.register_cli_command(
        name="skill-drift",
        help="Read-only source-version review for selected skills",
        description="Compare committed Hermes interfaces with selected local skill references.",
        setup_fn=configure,
        handler_fn=execute,
    )
