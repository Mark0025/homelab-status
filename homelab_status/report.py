"""Rich terminal report renderer."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .checker import CheckResult
from .services import CATEGORY_LABELS

console = Console()


def _status_badge(r: CheckResult) -> Text:
    if r.error == "timeout":
        return Text("TIMEOUT", style="bold yellow")
    if r.error:
        return Text("ERROR", style="bold red")
    if not r.reachable:
        return Text(f"DOWN ({r.status_code})", style="bold red")
    if r.redirect_is_auth:
        return Text(f"AUTH WALL ({r.status_code})", style="bold cyan")
    if r.status_code and r.status_code < 300:
        return Text(f"UP ({r.status_code})", style="bold green")
    if r.status_code and r.status_code < 400:
        return Text(f"REDIRECT ({r.status_code})", style="yellow")
    return Text(f"HTTP {r.status_code}", style="red")


def _ms(ms: float) -> str:
    if ms == 0:
        return "-"
    if ms < 500:
        return f"[green]{ms:.0f}ms[/green]"
    if ms < 2000:
        return f"[yellow]{ms:.0f}ms[/yellow]"
    return f"[red]{ms:.0f}ms[/red]"


def render_summary(results: list[CheckResult]) -> None:
    up = sum(1 for r in results if r.reachable and not r.error)
    down = sum(1 for r in results if not r.reachable or r.error)
    auth_walled = sum(1 for r in results if r.redirect_is_auth)
    with_docs = sum(1 for r in results if r.has_docs)
    with_health = sum(1 for r in results if r.has_health)

    console.print(Panel(
        f"[bold green]{up} UP[/bold green]  |  "
        f"[bold red]{down} DOWN/ERROR[/bold red]  |  "
        f"[bold cyan]{auth_walled} AUTH WALL[/bold cyan]  |  "
        f"[bold blue]{with_docs} have /docs[/bold blue]  |  "
        f"[bold magenta]{with_health} have /health[/bold magenta]  |  "
        f"Total: {len(results)}",
        title="[bold]Homelab Status Summary[/bold]",
        border_style="bright_blue",
    ))


def render_by_category(results: list[CheckResult]) -> None:
    by_cat: dict[str, list[CheckResult]] = {}
    for r in results:
        by_cat.setdefault(r.service.category, []).append(r)

    for cat, cat_results in by_cat.items():
        label = CATEGORY_LABELS.get(cat, cat.upper())
        up = sum(1 for r in cat_results if r.reachable and not r.error)
        total = len(cat_results)
        color = "green" if up == total else ("red" if up == 0 else "yellow")

        console.rule(f"[bold {color}]{label}[/bold {color}]  [{color}]{up}/{total} up[/{color}]")

        table = Table(
            box=box.SIMPLE,
            show_header=True,
            header_style="bold dim",
            show_edge=False,
            padding=(0, 2),
        )
        table.add_column("Service", style="bright_white", min_width=26, no_wrap=True)
        table.add_column("Status", min_width=20, no_wrap=True)
        table.add_column("Time", justify="right", min_width=8, no_wrap=True)
        table.add_column("Docs", justify="center", min_width=5, no_wrap=True)
        table.add_column("Health", justify="center", min_width=10, no_wrap=True)
        table.add_column("URL", style="dim", no_wrap=True)

        for r in sorted(cat_results, key=lambda x: x.service.name):
            docs_mark = "[green]✓[/green]" if r.has_docs else "[dim]·[/dim]"
            health_mark = f"[green]{r.health_status or 'ok'}[/green]" if r.has_health else "[dim]·[/dim]"
            table.add_row(
                r.service.name,
                _status_badge(r),
                _ms(r.response_time_ms),
                docs_mark,
                health_mark,
                r.service.url,
            )

        console.print(table)
        console.print()


def render_verbose(results: list[CheckResult]) -> None:
    """Full verbose dump — one panel per service with description, what it does, status."""
    by_cat: dict[str, list[CheckResult]] = {}
    for r in results:
        by_cat.setdefault(r.service.category, []).append(r)

    for cat, cat_results in by_cat.items():
        label = CATEGORY_LABELS.get(cat, cat.upper())
        console.rule(f"[bold bright_yellow]{label}[/bold bright_yellow]", style="bright_yellow")

        for r in sorted(cat_results, key=lambda x: x.service.name):
            svc = r.service
            lines: list[str] = []

            status = _status_badge(r)
            lines.append(f"[dim]URL:[/dim]       {svc.url}")
            if r.redirected_to and r.redirected_to != svc.url:
                lines.append(f"[dim]Redirected:[/dim] {r.redirected_to}")
            if r.redirect_is_auth:
                lines.append("[cyan]→ Protected by auth wall (Clerk / login redirect)[/cyan]")
            lines.append(f"[dim]Time:[/dim]      {r.response_time_ms:.0f}ms" if r.response_time_ms else "[dim]Time: -[/dim]")
            if r.server_header:
                lines.append(f"[dim]Server:[/dim]    {r.server_header}")
            if r.title:
                lines.append(f"[dim]Title:[/dim]     {r.title}")

            lines.append("")
            lines.append(f"[bold]What it is:[/bold] {svc.description}")
            lines.append(f"[bold]What it does:[/bold] {svc.what_it_does}")

            if svc.repo:
                lines.append(f"[dim]Repo:[/dim]      github.com/{svc.repo}")
            if r.has_docs:
                lines.append(f"[green]Docs:[/green]      {r.docs_url}")
            if r.has_health:
                lines.append(f"[green]Health:[/green]    {svc.url}{svc.health_path} → {r.health_status}")
            if r.error:
                lines.append(f"[red]Error:[/red]     {r.error}")

            border = "green" if r.reachable and not r.error else ("cyan" if r.redirect_is_auth else "red")
            console.print(Panel(
                "\n".join(lines),
                title=f"[bold]{svc.name}[/bold]  {status}",
                border_style=border,
                padding=(0, 1),
            ))
        console.print()


def render_problems(results: list[CheckResult]) -> None:
    """Only show services that are down or erroring."""
    problems = [r for r in results if not r.reachable or r.error]
    if not problems:
        console.print("[bold green]All services reachable — no problems detected.[/bold green]")
        return

    console.print(Panel(f"[bold red]{len(problems)} problem(s) found[/bold red]", border_style="red"))
    for r in problems:
        console.print(
            f"  [red]✗[/red] [bold]{r.service.name}[/bold]  {_status_badge(r)}  "
            f"[dim]{r.service.url}[/dim]"
            + (f"  → {r.error}" if r.error else "")
        )
