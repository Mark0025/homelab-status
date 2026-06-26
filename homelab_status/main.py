"""Homelab status CLI."""

import asyncio
from typing import Optional

import typer

from .logging_config import configure_logging
from .checker import check_all
from .db import get_routes, get_topology, init_db, save_network_topology, save_routes, save_run
from .git_history import get_commit_stats, get_recent_commits, get_repo_summaries, refresh_all
from .report import console, render_by_category, render_problems, render_summary, render_verbose
from .services import CATEGORY_LABELS, SERVICES

app = typer.Typer(help="Check the status of all homelab public endpoints.")


def _configure_logging(verbose: bool) -> None:
    # Shared config (issue #22) — verbose flag maps to DEBUG, else env/INFO.
    configure_logging(level="DEBUG" if verbose else None, force=True)


@app.command()
def check(
    category: Optional[str] = typer.Option(None, "--category", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    problems_only: bool = typer.Option(False, "--problems", "-p"),
    concurrency: int = typer.Option(20, "--concurrency", "-n"),
    log_debug: bool = typer.Option(False, "--debug"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to SQLite"),
) -> None:
    """Check all homelab public endpoints."""
    _configure_logging(log_debug)

    services = SERVICES
    if category:
        if category not in CATEGORY_LABELS:
            console.print(f"[red]Unknown category '{category}'. Choose: {', '.join(CATEGORY_LABELS.keys())}[/red]")
            raise typer.Exit(1)
        services = [s for s in SERVICES if s.category == category]

    console.print(f"[dim]Checking {len(services)} endpoints...[/dim]\n")
    results = asyncio.run(check_all(services, concurrency=concurrency))

    if save:
        from datetime import datetime
        run_id = save_run(results, datetime.now())
        route_total = 0
        for r in results:
            if r.api_routes:
                route_total += save_routes(
                    r.service.name, r.service.url, r.api_routes,
                    container_name=r.service.container_name,
                )
        save_network_topology(services)
        logger.info(f"Saved run #{run_id}, {route_total} API routes, network topology to SQLite")

    render_summary(results)
    console.print()

    if problems_only:
        render_problems(results)
    elif verbose:
        render_verbose(results)
    else:
        render_by_category(results)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    log_debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Start the web dashboard at http://localhost:8765"""
    import uvicorn
    _configure_logging(log_debug)
    init_db()
    console.print(f"[bold green]Starting homelab-status dashboard at http://{host}:{port}[/bold green]")
    uvicorn.run("homelab_status.web:api", host=host, port=port, log_level="warning")


@app.command()
def routes(
    service: Optional[str] = typer.Option(None, "--service", "-s", help="Filter by service name"),
) -> None:
    """Show all API routes discovered and stored in SQLite."""
    import json
    rows = get_routes(service)
    if not rows:
        console.print("[yellow]No routes in DB yet. Run 'check' first.[/yellow]")
        return

    from rich.table import Table
    from rich import box
    table = Table(box=box.SIMPLE, show_edge=False, padding=(0, 2))
    table.add_column("Service", style="bright_white", min_width=22, no_wrap=True)
    table.add_column("Method", min_width=8, no_wrap=True)
    table.add_column("Path", style="dim", min_width=30, no_wrap=True)
    table.add_column("Summary", min_width=30)
    table.add_column("Tags", style="cyan")

    METHOD_COLORS = {"GET": "green", "POST": "blue", "PUT": "yellow", "PATCH": "magenta", "DELETE": "red"}
    for r in rows:
        color = METHOD_COLORS.get(r["method"], "white")
        tags = json.loads(r["tags"]) if r["tags"] else []
        table.add_row(
            r["service_name"],
            f"[{color}]{r['method']}[/{color}]",
            r["path"],
            r["summary"] or "",
            ", ".join(tags),
        )

    console.print(table)
    console.print(f"\n[dim]{len(rows)} routes total[/dim]")


@app.command()
def list_services(
    category: Optional[str] = typer.Option(None, "--category", "-c"),
) -> None:
    """List all known services without making HTTP requests."""
    services = SERVICES if not category else [s for s in SERVICES if s.category == category]
    by_cat: dict[str, list] = {}
    for s in services:
        by_cat.setdefault(s.category, []).append(s)

    for cat, svcs in by_cat.items():
        console.print(f"\n[bold bright_yellow]{CATEGORY_LABELS.get(cat, cat)}[/bold bright_yellow]  ({len(svcs)})")
        for s in svcs:
            tags = (" [blue][API][/blue]" if s.has_api else "") + (" [green][docs][/green]" if s.has_docs_path else "")
            console.print(f"  [bright_white]{s.name}[/bright_white]{tags}")
            console.print(f"    [dim]{s.url}[/dim]")
            console.print(f"    {s.description}")


@app.command()
def git(
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Pull fresh data from GitHub"),
    repo: Optional[str] = typer.Option(None, "--repo", help="Filter by repo name"),
    limit: int = typer.Option(50, "--limit", "-n"),
) -> None:
    """Show git commit history across all repos (reads from SQLite cache)."""
    import asyncio as _asyncio
    _configure_logging(False)

    if refresh:
        console.print("[dim]Fetching from GitHub API...[/dim]")
        stats = _asyncio.run(refresh_all(force=True))
        console.print(f"[green]Done:[/green] {stats['repos_refreshed']} repos, {stats['commits_saved']} commits saved")

    summary = get_commit_stats()
    if summary["total_commits"] == 0:
        console.print("[yellow]No commits cached yet. Run with --refresh first.[/yellow]")
        return

    console.print(
        f"\n[bold]Git History[/bold]  "
        f"[green]{summary['total_commits']} commits[/green]  "
        f"[blue]{summary['total_repos']} repos[/blue]  "
        f"[purple]{summary['commits_last_7d']} last 7d[/purple]  "
        f"[yellow]{summary['commits_last_30d']} last 30d[/yellow]\n"
    )

    from rich.table import Table
    from rich import box
    table = Table(box=box.SIMPLE, show_edge=False, padding=(0, 2))
    table.add_column("SHA", style="dim", min_width=8, no_wrap=True)
    table.add_column("Repo", style="cyan", min_width=20, no_wrap=True)
    table.add_column("Message", min_width=50)
    table.add_column("Author", style="dim", min_width=15, no_wrap=True)
    table.add_column("Date", style="dim", min_width=10, no_wrap=True)
    table.add_column("+/-", justify="right", min_width=10, no_wrap=True)

    commits = get_recent_commits(limit=limit, repo=repo)
    for c in commits:
        subject = (c["message"] or "").split("\n")[0][:70]
        adds = c.get("additions", 0)
        dels = c.get("deletions", 0)
        diff = f"[green]+{adds}[/green] [red]-{dels}[/red]" if adds or dels else ""
        date = (c.get("author_date") or "")[:10]
        table.add_row(
            (c["sha"] or "")[:7],
            c["repo"],
            subject,
            c.get("author_name", "")[:20],
            date,
            diff,
        )

    console.print(table)
    if not refresh:
        fresh = "[green]fresh[/green]" if summary["cache_fresh"] else "[yellow]stale — run --refresh[/yellow]"
        console.print(f"\n[dim]Cache: {fresh}  Last synced: {summary['last_fetched'] or 'never'}[/dim]")


if __name__ == "__main__":
    app()
