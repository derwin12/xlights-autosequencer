import sys

import click
import webbrowser


@click.command()
@click.option("--dev", is_flag=True, help="Start in dev mode (skip auto-open browser).")
@click.option("--port", default=5000, show_default=True, help="Port to listen on.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind.")
def main(dev: bool, port: int, host: str) -> None:
    """Launch the xOnset review UI."""
    # Windows defaults stdout/stderr to cp1252 unless the console is UTF-8,
    # which crashes on unicode glyphs (✓/✗) used throughout analyzer output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    from src.review.server import create_app

    app = create_app()
    url = f"http://{host}:{port}"
    if not dev:
        webbrowser.open(url)
    click.echo(f"xOnset running at {url}")
    app.run(host=host, port=port, debug=False)
