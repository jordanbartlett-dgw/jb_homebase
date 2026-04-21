from __future__ import annotations

import asyncio

import click
import structlog

from jordan_claw.config import get_settings
from jordan_claw.db.client import close_supabase_client, get_supabase_client
from scripts.obsidian_sync.export import export_notes
from scripts.obsidian_sync.ingest import ingest_vault

log = structlog.get_logger()

DEFAULT_VAULT_PATH = "/home/jb/Documents/Obsidian Vault"


async def _run_ingest(vault_path: str) -> dict:
    settings = get_settings()
    db = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    try:
        return await ingest_vault(
            db,
            org_id=settings.default_org_id,
            vault_path=vault_path,
            openai_api_key=settings.openai_api_key,
        )
    finally:
        await close_supabase_client()


async def _run_export(vault_path: str) -> dict:
    settings = get_settings()
    db = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    try:
        return await export_notes(
            db,
            org_id=settings.default_org_id,
            vault_path=vault_path,
        )
    finally:
        await close_supabase_client()


@click.group()
def cli():
    """Obsidian vault sync tool for Jordan Claw."""
    structlog.configure(
        processors=[
            structlog.dev.ConsoleRenderer(),
        ],
    )


@cli.command()
@click.option("--vault", default=DEFAULT_VAULT_PATH, help="Path to Obsidian vault")
def ingest(vault: str):
    """Ingest vault notes into Supabase."""
    stats = asyncio.run(_run_ingest(vault))
    click.echo(
        f"Ingest complete: {stats['inserted']} inserted, {stats['updated']} updated, "
        f"{stats['skipped']} skipped, {stats['archived']} archived"
    )


@cli.command()
@click.option("--vault", default=DEFAULT_VAULT_PATH, help="Path to Obsidian vault")
def export(vault: str):
    """Export Claw-created notes to vault."""
    stats = asyncio.run(_run_export(vault))
    click.echo(f"Export complete: {stats['exported']} exported")


@cli.command()
@click.option("--vault", default=DEFAULT_VAULT_PATH, help="Path to Obsidian vault")
def run(vault: str):
    """Run ingest then export."""
    ingest_stats = asyncio.run(_run_ingest(vault))
    export_stats = asyncio.run(_run_export(vault))
    click.echo(
        f"Ingest: {ingest_stats['inserted']} inserted, {ingest_stats['updated']} updated, "
        f"{ingest_stats['skipped']} skipped, {ingest_stats['archived']} archived"
    )
    click.echo(f"Export: {export_stats['exported']} exported")


if __name__ == "__main__":
    cli()
