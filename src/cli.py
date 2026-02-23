"""
CLI entry point for the ClearPass flow diagram generator.

Usage:
    python -m src.cli service.xml --output diagram.svg
    python -m src.cli service.xml --output diagram.png --format png
    python -m src.cli service.xml --output diagram.svg --service "My Service Name"
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

from . import parser as xml_parser
from . import policy_ir as ir_builder
from .flow_ir import compile_service
from .renderer import render


@click.command()
@click.argument("xml_file", type=click.Path(exists=True, readable=True, path_type=Path))
@click.option(
    "--output", "-o",
    default="diagram.svg",
    show_default=True,
    help="Output file path (extension determines format if --format is omitted).",
)
@click.option(
    "--format", "-f", "fmt",
    default=None,
    type=click.Choice(["svg", "png", "pdf"], case_sensitive=False),
    help="Output format. Inferred from --output extension if omitted.",
)
@click.option(
    "--service", "-s",
    default=None,
    help="Name of the service to render. Defaults to the first service found.",
)
@click.option(
    "--list-services", is_flag=True, default=False,
    help="List all services in the XML file and exit.",
)
def main(
    xml_file: Path,
    output: str,
    fmt: str | None,
    service: str | None,
    list_services: bool,
) -> None:
    """Generate a flow diagram SVG from a ClearPass XML service export."""

    # Phase 1: Parse
    click.echo(f"Parsing {xml_file} ...")
    raw = xml_parser.parse(xml_file)

    # Phase 2+3: Build Policy IR
    ir = ir_builder.build(raw, source_file=str(xml_file))

    if list_services:
        click.echo("Services found:")
        for svc in ir.services.values():
            click.echo(f"  - {svc.name}")
        return

    if not ir.services:
        click.echo("No services found in XML.", err=True)
        sys.exit(1)

    # Select service
    target_svc = None
    if service:
        target_svc = next(
            (s for s in ir.services.values() if s.name == service), None
        )
        if target_svc is None:
            click.echo(f"Service {service!r} not found.", err=True)
            click.echo("Available services:", err=True)
            for svc in ir.services.values():
                click.echo(f"  - {svc.name}", err=True)
            sys.exit(1)
    else:
        target_svc = next(iter(ir.services.values()))
        click.echo(f"Using service: {target_svc.name!r}")

    # Phase 4: Compile flow
    click.echo("Compiling flow graph ...")
    flow = compile_service(target_svc, ir)
    click.echo(f"  {len(flow.nodes)} nodes, {len(flow.edges)} edges")

    # Determine output format
    output_path = Path(output)
    if fmt is None:
        ext = output_path.suffix.lstrip(".")
        fmt = ext if ext in ("svg", "png", "pdf") else "svg"

    # Phase 5: Render
    click.echo(f"Rendering {fmt.upper()} to {output_path} ...")
    result = render(flow, output_path.with_suffix(""), fmt=fmt)
    click.echo(f"Done: {result}")


if __name__ == "__main__":
    main()
