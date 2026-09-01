"""Offline-first command-line interface with explicit private-input boundaries."""

from __future__ import annotations

import asyncio
import os
from contextlib import nullcontext
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError
from rich.console import Console
from typer._click.core import Context
from typer._click.exceptions import UsageError
from typer.core import TyperCommand, TyperGroup

from .context import load_explicit_context
from .errors import CouncilError, InputError, OutputError, ProviderError, QuorumError
from .models import CouncilConfig, CouncilDecision, CouncilRequest
from .orchestrator import CouncilEngine
from .providers.fake import DeterministicProvider
from .providers.google import DEFAULT_MODEL, GoogleGenAIProvider
from .renderers import render_html, render_json, render_markdown, write_output
from .security import resolve_safe_path


class _SafeCommand(TyperCommand):
    """Keep command parser errors from reproducing arbitrary option values."""

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except UsageError:
            raise UsageError(
                "Invalid run options. Run llm-council run --help for usage.", ctx
            ) from None


class _SafeGroup(TyperGroup):
    """Keep parser errors from reproducing arbitrary option values or arguments."""

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except UsageError:
            raise UsageError(
                "Invalid command options. Run llm-council --help for usage.", ctx
            ) from None

    def invoke(self, ctx: Context) -> Any:
        try:
            return super().invoke(ctx)
        except UsageError:
            raise UsageError(
                "Invalid run options. Run llm-council run --help for usage.", ctx
            ) from None


app = typer.Typer(
    cls=_SafeGroup,
    help=(
        "LLM Council for Digital Marketing: five specialist perspectives and one structured "
        "decision. SEO covers conventional search foundations; AEO (Answer Engine Optimization) "
        "supports answer eligibility and clarity; GEO (Generative Engine Optimization) supports "
        "generative understanding, retrieval, and citation. These methods do not guarantee "
        "outcomes. Offline demo by default."
    ),
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)


@app.callback()
def main() -> None:
    """Use the run command to generate a digital marketing council decision."""


@app.command(cls=_SafeCommand)
def run(
    question: Annotated[
        str,
        typer.Option(help="Digital marketing decision question. Required; never read implicitly."),
    ],
    context_file: Annotated[
        Path | None,
        typer.Option(help="Explicit UTF-8 .md/.txt/.json/.csv file inside the working directory."),
    ] = None,
    provider: Annotated[
        str,
        typer.Option(
            metavar="[demo|google]",
            help="demo is offline; google sends the question/context and may incur API charges.",
        ),
    ] = "demo",
    model: Annotated[str, typer.Option(help="Google model ID; ignored by the fixed demo.")] = DEFAULT_MODEL,
    format: Annotated[
        str, typer.Option(metavar="[markdown|json|html]", help="Decision output format.")
    ] = "markdown",
    output: Annotated[
        Path | None,
        typer.Option(help="Save inside the working directory; parent must exist. Default: stdout."),
    ] = None,
    overwrite: Annotated[bool, typer.Option(help="Allow replacing an existing output file.")] = False,
    timeout: Annotated[
        str, typer.Option(metavar="SECONDS", help="Per-completion timeout, greater than 0 and at most 300.")
    ] = "30",
    seed: Annotated[
        str | None, typer.Option(metavar="INTEGER", help="Seed anonymous label shuffling, not model output.")
    ] = None,
) -> None:
    r"""Run a digital marketing council offline or opt into Google with GOOGLE_API_KEY.

    Demo returns a fixed simulated B2B SaaS digital marketing decision, not an
    analysis of your question. AEO (Answer Engine Optimization) supports answer
    eligibility and clarity; GEO (Generative Engine Optimization) supports generative
    understanding, retrieval, and citation. SEO, AEO, and GEO do not guarantee
    rankings, citations, traffic, or revenue. Google additionally requires installing
    llm-council\[google]. No context is read unless --context-file is supplied.
    Progress and notices go to stderr.
    """
    try:
        request = _validate_request(question, timeout, seed, model, provider, format)
        root = Path.cwd()
        if context_file is not None:
            request = _with_context(request, context_file, root)
        if output is not None:
            _preflight_output(output, root, overwrite)

        if provider == "demo":
            typer.echo(
                "Demo: fixed simulated B2B SaaS digital marketing output with SEO, AEO, and GEO; "
                "not an analysis of your question or context and not a promise of rankings, "
                "citations, traffic, or revenue. No network requests or API key required.",
                err=True,
            )
        console = Console(stderr=True)
        progress = console.status("Running council...") if console.is_terminal else nullcontext()
        with progress:
            decision = asyncio.run(_run_council(request, provider, model))
        render = {"markdown": render_markdown, "json": render_json, "html": render_html}[format]
        content = render(decision)
        if output is None:
            typer.echo(content, nl=not content.endswith("\n"))
        else:
            write_output(content, output, root, overwrite=overwrite)
            typer.echo("Decision saved to the requested output file.", err=True)
    except CouncilError as error:
        typer.echo(f"Error: {_safe_error_message(error)}", err=True)
        raise typer.Exit(code=1) from None


def _validate_request(
    question: str, timeout: str, seed: str | None, model: str, provider: str, format: str
) -> CouncilRequest:
    """Validate scalar options without touching credentials or optional SDKs."""
    if provider not in {"demo", "google"} or format not in {"markdown", "json", "html"}:
        raise InputError("Invalid provider or format.")
    if not model.strip():
        raise InputError("Model must not be blank.")
    try:
        config = CouncilConfig(
            advisor_timeout_seconds=float(timeout),
            random_seed=int(seed) if seed is not None else None,
        )
        return CouncilRequest(question=question, config=config)
    except (ValidationError, ValueError, OverflowError):
        raise InputError("Invalid question, timeout, or seed.") from None


def _with_context(request: CouncilRequest, path: Path, root: Path) -> CouncilRequest:
    try:
        context = load_explicit_context(path, root)
        return CouncilRequest(question=request.question, context=context, config=request.config)
    except (OSError, ValueError):
        raise InputError("Unable to read a nonblank UTF-8 context file.") from None


def _preflight_output(path: Path, root: Path, overwrite: bool) -> None:
    """Reject predictable destination failures before any potentially paid work.

    This is not a reservation. The atomic writer repeats the security and overwrite
    checks at publication time, including when another process changes the path.
    """
    try:
        target = resolve_safe_path(path, root, must_exist=False)
        if target.exists() and (not target.is_file() or not overwrite):
            raise OutputError("Output file already exists or is not a regular file.")
        if not target.parent.is_dir() or not os.access(target.parent, os.W_OK):
            raise OutputError("Output parent must exist and be writable.")
    except (OSError, ValueError):
        raise OutputError("Unable to access output destination.") from None


async def _run_council(request: CouncilRequest, provider: str, model: str) -> CouncilDecision:
    if provider == "demo":
        return await CouncilEngine(DeterministicProvider()).run(request)
    google = GoogleGenAIProvider(model=model)
    try:
        return await CouncilEngine(google).run(request)
    finally:
        await google.aclose()


def _safe_error_message(error: CouncilError) -> str:
    """Never display exception payloads, including otherwise-safe domain errors."""
    if isinstance(error, ProviderError):
        return (
            "Google/provider operation failed. Set GOOGLE_API_KEY, install llm-council[google], "
            "and check model access, quota, network, and --timeout. No decision was produced."
        )
    if isinstance(error, QuorumError):
        return "Council quorum was not met. Check provider availability and --timeout; no decision produced."
    if isinstance(error, OutputError):
        return (
            "Cannot save output. Use a file inside the working directory with an existing writable "
            "parent, no symlinks, and --overwrite only when replacement is intended."
        )
    return (
        "Invalid input. Check the question, provider, format, model, timeout (0 < seconds <= 300), "
        "integer seed, and explicit context file. Run llm-council run --help for usage."
    )
