"""eco-ai: Estimate and reduce the ecological impact of your AI prompts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from .config import Lang, get_lang, set_lang
from .metrics import MODEL_PRICES_USD, MODEL_TIER, calculate_impact
from .optimizer import analyze as analyze_prompt, detect_task_type, positive_aspects, recommend_model
from .tokenizer import count_tokens, tokenizer_source

_WELCOME_ES = """[bold green]eco-ai[/bold green] — [italic]uso consciente de la inteligencia artificial[/italic]

Este plugin te ayuda a [bold]optimizar tus prompts[/bold] antes de enviarlos a un modelo de IA.
Cada petición consume energía, agua y genera CO₂. Cuantos menos tokens uses, menor es el impacto.

Con eco-ai aprenderás a:
  • Estimar el coste ecológico real de tus prompts
  • Identificar qué partes son innecesarias o redundantes
  • Escribir prompts más precisos y eficientes

[bold green]100% eco-friendly[/bold green] — todo el análisis ocurre en tu dispositivo.
Sin llamadas a APIs externas. Sin transmisión de tus datos. Sin huella adicional.

[dim]Usa [bold]eco-ai --help[/bold] para ver todos los comandos disponibles.[/dim]"""

_WELCOME_EN = """[bold green]eco-ai[/bold green] — [italic]conscious use of artificial intelligence[/italic]

This plugin helps you [bold]optimise your prompts[/bold] before sending them to an AI model.
Every request consumes energy, water and generates CO₂. Fewer tokens means lower impact.

With eco-ai you will learn to:
  • Estimate the real ecological cost of your prompts
  • Identify unnecessary or redundant parts
  • Write more precise and efficient prompts

[bold green]100% eco-friendly[/bold green] — all analysis runs on your device.
No external API calls. No data transmission. No additional footprint.

[dim]Use [bold]eco-ai --help[/bold] to see all available commands.[/dim]"""


def _print_welcome(lang: Lang) -> None:
    console.print()
    console.print(Panel(
        _WELCOME_ES if lang == Lang.ES else _WELCOME_EN,
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


app = typer.Typer(
    name="eco-ai",
    help="Estimate the ecological impact of your AI prompts and get optimisation suggestions.",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
)

console = Console()


@app.callback()
def main(ctx: typer.Context) -> None:
    """eco-ai — conscious use of artificial intelligence."""
    if ctx.invoked_subcommand is None:
        _print_welcome(get_lang())

MODELS = list(MODEL_PRICES_USD.keys())


def _print_consent_notice(lang: Lang) -> bool:
    console.print()
    if lang == Lang.ES:
        body = (
            "[bold yellow]Aviso de privacidad y consentimiento[/bold yellow]\n\n"
            "Este análisis se realiza [bold]localmente en tu dispositivo[/bold].\n"
            "Tu texto [bold]no se envía[/bold] a ningún servidor externo.\n\n"
            "Los datos analizados son:\n"
            "  • El texto del prompt que proporciones\n"
            "  • Su longitud y estructura\n\n"
            "Las estimaciones de impacto ecológico son [italic]aproximaciones[/italic] "
            "basadas en investigación publicada — no datos exactos de ningún proveedor."
        )
        question = "[yellow]¿Autorizas el análisis de tu prompt?[/yellow]"
    else:
        body = (
            "[bold yellow]Privacy notice and consent[/bold yellow]\n\n"
            "This analysis runs [bold]locally on your device[/bold].\n"
            "Your text is [bold]never sent[/bold] to any external server.\n\n"
            "The data analysed is:\n"
            "  • The prompt text you provide\n"
            "  • Its length and structure\n\n"
            "Ecological impact estimates are [italic]approximations[/italic] "
            "based on published research — not exact figures from any provider."
        )
        question = "[yellow]Do you authorise the analysis of your prompt?[/yellow]"
    console.print(Panel(body, title="[bold]eco-ai[/bold]", border_style="yellow"))
    return Confirm.ask(question)


_DEFAULT_MODEL = "Claude Sonnet 4.6"


def _render_impact_table(impact, lang: Lang) -> Table:
    if lang == Lang.ES:
        col_metric, col_value, col_equiv = "Métrica", "Valor", "Equivalencia"
        row_model       = "Modelo"
        row_tokens      = "Tokens (entrada)"
        row_energy      = "Energía estimada"
        row_co2         = "CO₂ equivalente"
        row_water       = "Agua estimada"
        row_cost        = "Coste API estimado"
        note_default    = "por defecto — usa -m para cambiarlo"
        note_io         = "entrada + salida estimada"
        note_cooling    = "refrigeración del centro de datos"
        note_cost       = "entrada + salida estimada (40%)"
    else:
        col_metric, col_value, col_equiv = "Metric", "Value", "Equivalent"
        row_model       = "Model"
        row_tokens      = "Tokens (input)"
        row_energy      = "Estimated energy"
        row_co2         = "CO₂ equivalent"
        row_water       = "Estimated water"
        row_cost        = "Estimated API cost"
        note_default    = "default — use -m to change it"
        note_io         = "input + estimated output"
        note_cooling    = "data centre cooling"
        note_cost       = "input + estimated output (40%)"

    table = Table(box=box.ROUNDED, show_header=False, border_style="green")
    table.add_column(col_metric, style="bold")
    table.add_column(col_value, justify="right")
    table.add_column(col_equiv, style="dim")

    model_note = note_default if impact.model == _DEFAULT_MODEL else ""
    table.add_row(row_model, impact.model, model_note)
    table.add_row(row_tokens, f"{impact.tokens:,}", tokenizer_source())

    energy_str  = f"{impact.energy_kwh*1000:.4f} Wh"
    energy_note = impact.energy_time_equiv or note_io
    table.add_row(row_energy, energy_str, energy_note)

    co2_str = f"{impact.co2_g:.4f} g CO₂e"
    table.add_row(row_co2, co2_str, impact.co2_equiv)

    water_note = impact.water_time_equiv or note_cooling
    table.add_row(row_water, impact.water_equiv, water_note)

    if impact.cost_usd is not None:
        cost_str = f"${impact.cost_usd:.6f} USD"
        table.add_row(row_cost, cost_str, note_cost)

    return table


def _render_model_recommendation(rec, lang: Lang) -> None:
    tier_color = {"large": "red", "medium": "yellow", "small": "green"}.get(rec.tier, "white")
    lines = [
        f"[bold {tier_color}]{rec.headline}[/bold {tier_color}]",
        rec.reason,
    ]
    if rec.signals:
        label = "Señales detectadas" if lang == Lang.ES else "Detected signals"
        lines.append(f"\n[dim]{label}: {', '.join(rec.signals)}[/dim]")
    title = "Modelo recomendado para esta tarea" if lang == Lang.ES else "Recommended model for this task"
    console.print(Panel(
        "\n".join(lines),
        title=f"[bold]{title}[/bold]",
        border_style=tier_color,
        padding=(0, 1),
    ))


def _render_suggestions(suggestions, rec, positives, lang: Lang, verbose: bool = False) -> None:
    # --- Recomendación de modelo (siempre visible) ---
    console.print()
    _render_model_recommendation(rec, lang)

    # --- Feedback de redacción ---
    if not suggestions:
        ok_msg = (
            "[bold green]✓ El prompt no tiene problemas obvios de redacción.[/bold green]"
            if lang == Lang.ES else
            "[bold green]✓ The prompt has no obvious writing issues.[/bold green]"
        )
        lines = [ok_msg]
        if positives:
            lines.append("")
            for asp in positives:
                lines.append(f"  [green]✓[/green] {asp}")
        guide_hint = (
            "\n[dim]Si quieres seguir mejorando, consulta los principios en [bold]eco-ai guide[/bold].[/dim]"
            if lang == Lang.ES else
            "\n[dim]To keep improving, check the principles in [bold]eco-ai guide[/bold].[/dim]"
        )
        lines.append(guide_hint)
        panel_title = "Calidad del prompt" if lang == Lang.ES else "Prompt quality"
        console.print(Panel("\n".join(lines), title=panel_title, border_style="green", padding=(0, 1)))
        return

    found_label = "encontradas" if lang == Lang.ES else "found"
    header = (
        "Sugerencias para reducir tokens" if lang == Lang.ES else "Suggestions to reduce tokens"
    )
    console.print(f"\n[bold cyan]{header}[/bold cyan] "
                  f"[dim]({len(suggestions)} {found_label})[/dim]\n")

    example_label = "Ejemplo" if lang == Lang.ES else "Example"
    source_label  = "Fuente"  if lang == Lang.ES else "Source"

    for i, sug in enumerate(suggestions, 1):
        lines = [f"[bold]{sug.category}[/bold]", sug.description]
        if sug.example:
            lines.append(f"\n[dim]{example_label}:[/dim] {sug.example}")
        if sug.savings_estimate:
            lines.append(f"[green]{sug.savings_estimate}[/green]")
        if verbose and sug.source:
            lines.append(f"\n[dim]{source_label}: {sug.source}[/dim]")

        console.print(Panel(
            "\n".join(lines),
            title=f"[cyan]{i}[/cyan]",
            border_style="cyan",
            padding=(0, 1),
        ))


@app.command()
def analyze(
    prompt: Optional[str] = typer.Argument(None, help="Prompt text to analyse"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read the prompt from a text file"),
    model: str = typer.Option(_DEFAULT_MODEL, "--model", "-m",
                               help="Reference model (run 'eco-ai models' for the full list)."),
    no_consent: bool = typer.Option(False, "--yes", "-y", help="Skip the privacy consent screen"),
    no_tips: bool = typer.Option(False, "--no-tips", help="Show metrics only, no suggestions"),
    output_ratio: float = typer.Option(0.4, "--output-ratio",
                                        help="Estimated output-to-input token ratio (0–2)"),
    lang: Optional[Lang] = typer.Option(None, "--lang", "-l",
                                         help="Prompt language: es (Spanish) or en (English). Defaults to saved config."),
    verbose: bool = typer.Option(False, "--verbose", "-v",
                                  help="Show bibliographic reference for each suggestion."),
    output_type: str = typer.Option(
        "auto", "--output-type", "-t",
        help="Expected output type: auto (detect), text, image, code, pdf, artifact.",
    ),
) -> None:
    """Analyse the ecological impact of a prompt and suggest optimisations."""

    # Determinar idioma antes de cualquier output para que toda la UI sea consistente
    effective_lang = lang or get_lang()
    es = effective_lang == Lang.ES

    # --- Leer texto ---
    text: str | None = None

    if file and prompt:
        console.print(
            "[yellow]Aviso: se ignorará el argumento posicional porque se proporcionó --file.[/yellow]"
            if es else
            "[yellow]Warning: positional argument ignored because --file was provided.[/yellow]"
        )
    if file:
        if not file.exists():
            console.print(
                f"[red]{'Error: el fichero' if es else 'Error: file'} '{file}' "
                f"{'no existe' if es else 'does not exist'}.[/red]"
            )
            raise typer.Exit(1)
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            console.print(
                f"[red]{'Error: el fichero' if es else 'Error: file'} '{file}' "
                f"{'no es UTF-8. Conviértelo con:' if es else 'is not UTF-8. Convert it with:'}[/red]"
            )
            console.print(f"[dim]  iconv -f latin1 -t utf-8 {file} > {file}.utf8[/dim]")
            raise typer.Exit(1)
    elif prompt:
        text = prompt
    elif not sys.stdin.isatty():
        text = sys.stdin.read()

    if not text or not text.strip():
        if es:
            console.print("[red]Error: proporciona un prompt (argumento, --file, o stdin).[/red]")
            console.print("\n[dim]Uso: eco-ai analyze \"tu prompt aquí\"[/dim]")
            console.print("[dim]     eco-ai analyze --file prompt.txt[/dim]")
            console.print("[dim]     echo \"tu prompt\" | eco-ai analyze[/dim]")
        else:
            console.print("[red]Error: provide a prompt (argument, --file, or stdin).[/red]")
            console.print("\n[dim]Usage: eco-ai analyze \"your prompt here\"[/dim]")
            console.print("[dim]       eco-ai analyze --file prompt.txt[/dim]")
            console.print("[dim]       echo \"your prompt\" | eco-ai analyze[/dim]")
        raise typer.Exit(1)

    # --- Validar output_ratio ---
    if output_ratio < 0:
        console.print(
            f"[red]{'Error: --output-ratio debe ser ≥ 0' if es else 'Error: --output-ratio must be ≥ 0'} "
            f"({'recibido' if es else 'got'}: {output_ratio}).[/red]"
        )
        raise typer.Exit(1)

    # --- Validar modelo ---
    if model not in MODEL_PRICES_USD:
        model_lower = model.lower()
        matches = [m for m in MODELS if model_lower in m.lower()]
        if len(matches) == 1:
            model = matches[0]
        elif len(matches) > 1:
            model = matches[0]
            ambig_msg = (
                f"[yellow]Modelo ambiguo '{model_lower}' — usando '{model}'. "
                f"Otros: {', '.join(matches[1:])}[/yellow]"
                if es else
                f"[yellow]Ambiguous model '{model_lower}' — using '{model}'. "
                f"Others: {', '.join(matches[1:])}[/yellow]"
            )
            console.print(ambig_msg)
        else:
            console.print(
                f"[red]{'Modelo desconocido' if es else 'Unknown model'}:[/red] '{model}'"
            )
            console.print(f"[dim]{'Disponibles' if es else 'Available'}: {', '.join(MODELS)}[/dim]")
            raise typer.Exit(1)

    # --- Consentimiento ---
    if not no_consent:
        authorized = _print_consent_notice(effective_lang)
        if not authorized:
            console.print(
                "\n[yellow]Análisis cancelado. No se ha procesado ningún dato.[/yellow]\n"
                if es else
                "\n[yellow]Analysis cancelled. No data was processed.[/yellow]\n"
            )
            raise typer.Exit(0)

    # --- Análisis ---
    console.print()
    tokens = count_tokens(text)
    impact = calculate_impact(tokens, model, output_ratio, effective_lang)

    impact_title = "Impacto ecológico estimado" if es else "Estimated ecological impact"
    console.print(Panel(
        _render_impact_table(impact, effective_lang),
        title=f"[bold green]{impact_title}[/bold green]",
        border_style="green",
    ))

    # Tipo de tarea (siempre visible — afecta al impacto energético)
    task_type, task_label, task_note = detect_task_type(text, effective_lang)
    _type_color = {
        "qa": "red", "code": "yellow", "fact": "green",
        "image": "magenta", "document": "blue", "artifact": "cyan",
        "general": "dim",
    }.get(task_type, "dim")
    task_line = f"[{_type_color}]{task_label}[/{_type_color}]"
    if task_note:
        task_line += f"  [dim]{task_note}[/dim]"
    task_detected = "Tipo de tarea detectado" if es else "Detected task type"
    console.print(f"[bold]{task_detected}:[/bold] {task_line}\n")

    # Resolver tipo de output efectivo
    _valid_output_types = {"text", "image", "code", "pdf", "artifact"}
    if output_type in _valid_output_types:
        effective_output_type = output_type
    else:
        _task_to_output = {"image": "image", "document": "pdf", "artifact": "artifact", "code": "code"}
        effective_output_type = _task_to_output.get(task_type, "text")

    if not no_tips:
        suggestions = analyze_prompt(text, effective_lang, effective_output_type)
        rec = recommend_model(text, tokens, effective_lang)
        positives = positive_aspects(text, effective_lang)
        _render_suggestions(suggestions, rec, positives, effective_lang, verbose=verbose)

    # Nota de cierre
    if es:
        note = (
            "[dim]Nota: estas estimaciones son aproximaciones basadas en literatura científica. "
            "Los valores reales varían según el proveedor, el centro de datos y la carga del sistema.[/dim]\n"
        )
    else:
        note = (
            "[dim]Note: these estimates are approximations based on scientific literature. "
            "Actual values vary by provider, data centre and system load.[/dim]\n"
        )
    console.print(note)


@app.command()
def models() -> None:
    """List available models and their prices per 1 000 tokens."""
    lang = get_lang()
    es = lang == Lang.ES

    title   = "Modelos disponibles"           if es else "Available models"
    col_mod = "Modelo"                         if es else "Model"
    col_in  = "Input ($/1K tok)"
    col_out = "Output ($/1K tok)"
    footer  = "Usa --model \"Nombre del modelo\" en el comando analyze." if es else \
              "Use --model \"Model name\" in the analyze command."

    table = Table(title=title, box=box.ROUNDED, border_style="blue")
    table.add_column(col_mod, style="bold")
    table.add_column("Tier", justify="center")
    table.add_column(col_in, justify="right")
    table.add_column(col_out, justify="right")

    for name, prices in MODEL_PRICES_USD.items():
        tier = MODEL_TIER.get(name, "medium")
        tier_color = {"large": "red", "medium": "yellow", "small": "green"}.get(tier, "white")
        table.add_row(
            name,
            f"[{tier_color}]{tier}[/{tier_color}]",
            f"${prices['input']:.5f}",
            f"${prices['output']:.5f}",
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]{footer}[/dim]\n")


@app.command()
def compare(
    prompt: Optional[str] = typer.Argument(None, help="Prompt text to compare"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read the prompt from a text file"),
    no_consent: bool = typer.Option(False, "--yes", "-y", help="Skip the privacy consent screen"),
    output_ratio: float = typer.Option(0.4, "--output-ratio",
                                        help="Estimated output-to-input token ratio (0–2)"),
) -> None:
    """Compare the ecological impact of the same prompt across all available models."""

    lang = get_lang()
    es = lang == Lang.ES

    text: str | None = None
    if file and prompt:
        console.print(
            "[yellow]Aviso: se ignorará el argumento posicional porque se proporcionó --file.[/yellow]"
            if es else
            "[yellow]Warning: positional argument ignored because --file was provided.[/yellow]"
        )
    if file:
        if not file.exists():
            console.print(
                f"[red]{'Error: el fichero' if es else 'Error: file'} '{file}' "
                f"{'no existe' if es else 'does not exist'}.[/red]"
            )
            raise typer.Exit(1)
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            console.print(
                f"[red]{'Error: el fichero' if es else 'Error: file'} '{file}' "
                f"{'no es UTF-8. Conviértelo con:' if es else 'is not UTF-8. Convert it with:'}[/red]"
            )
            console.print(f"[dim]  iconv -f latin1 -t utf-8 {file} > {file}.utf8[/dim]")
            raise typer.Exit(1)
    elif prompt:
        text = prompt
    elif not sys.stdin.isatty():
        text = sys.stdin.read()

    if not text or not text.strip():
        console.print(
            "[red]Error: proporciona un prompt.[/red]" if es else
            "[red]Error: provide a prompt.[/red]"
        )
        raise typer.Exit(1)

    if output_ratio < 0:
        console.print(
            f"[red]{'Error: --output-ratio debe ser ≥ 0' if es else 'Error: --output-ratio must be ≥ 0'} "
            f"({'recibido' if es else 'got'}: {output_ratio}).[/red]"
        )
        raise typer.Exit(1)

    if not no_consent:
        authorized = _print_consent_notice(lang)
        if not authorized:
            console.print(
                "\n[yellow]Análisis cancelado.[/yellow]\n" if es else
                "\n[yellow]Analysis cancelled.[/yellow]\n"
            )
            raise typer.Exit(0)

    tokens = count_tokens(text)

    col_model  = "Modelo"       if es else "Model"
    col_energy = "Energía (Wh)" if es else "Energy (Wh)"
    col_water  = "Agua (mL)"    if es else "Water (mL)"
    col_cost   = "Coste USD"    if es else "Cost USD"
    tbl_title  = f"{'Comparativa de impacto' if es else 'Impact comparison'} — {tokens} tokens"

    table = Table(title=tbl_title, box=box.ROUNDED, border_style="magenta")
    table.add_column(col_model, style="bold")
    table.add_column(col_energy, justify="right")
    table.add_column("CO₂ (g)", justify="right")
    table.add_column(col_water, justify="right")
    table.add_column(col_cost, justify="right")

    for model in MODELS:
        impact = calculate_impact(tokens, model, output_ratio, lang)
        cost_str = f"${impact.cost_usd:.6f}" if impact.cost_usd is not None else "—"
        table.add_row(
            model,
            f"{impact.energy_kwh*1000:.4f}",
            f"{impact.co2_g:.4f}",
            f"{impact.water_ml:.2f}",
            cost_str,
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]{'Tokenizador' if es else 'Tokenizer'}: {tokenizer_source()}[/dim]\n")


@app.command()
def config(
    set_language: Optional[Lang] = typer.Option(None, "--lang", "-l",
                                                  help="Set the default language: es or en."),
    show: bool = typer.Option(False, "--show", help="Show the current configuration."),
) -> None:
    """Manage persistent eco-ai configuration (~/.eco-ai.json)."""
    from .config import load, get_lang as _get_lang

    if set_language:
        set_lang(set_language)
        # Confirmation always in the newly set language
        if set_language == Lang.ES:
            console.print(f"[green]✓[/green] Idioma por defecto establecido a [bold]{set_language.value}[/bold].")
        else:
            console.print(f"[green]✓[/green] Default language set to [bold]{set_language.value}[/bold].")
        return

    cfg = load()
    current_lang = _get_lang()
    es = current_lang == Lang.ES

    table = Table(box=box.ROUNDED, show_header=False, border_style="blue")
    table.add_column("Clave" if es else "Key", style="bold")
    table.add_column("Valor" if es else "Value")
    table.add_column("Descripción" if es else "Description", style="dim")
    table.add_row(
        "lang",
        current_lang.value,
        "Idioma del prompt analizado (es = español, en = inglés)"
        if es else
        "Language of the analysed prompt (es = Spanish, en = English)",
    )
    table.add_row(
        "config_file",
        str(__import__('pathlib').Path.home() / '.eco-ai.json'),
        "Ruta del fichero de configuración" if es else "Path to the configuration file",
    )
    console.print()
    panel_title = "Configuración actual" if es else "Current configuration"
    console.print(Panel(table, title=f"[bold blue]{panel_title}[/bold blue]", border_style="blue"))
    hint = (
        "\n[dim]Para cambiar: [bold]eco-ai config --lang en[/bold] "
        "o usa [bold]--lang[/bold] en cada comando.[/dim]\n"
        if es else
        "\n[dim]To change: [bold]eco-ai config --lang es[/bold] "
        "or use [bold]--lang[/bold] on each command.[/dim]\n"
    )
    console.print(hint)


@app.command()
def guide() -> None:
    """Show the eco-ai usage guide."""

    lang = get_lang()
    es = lang == Lang.ES

    console.print()

    # --- Qué es eco-ai ---
    if es:
        about = (
            "[bold green]eco-ai[/bold green] estima el impacto ecológico de tus prompts "
            "(energía, CO₂, agua y coste) y analiza su calidad [bold]sin enviar nada a servidores externos[/bold].\n\n"
            "Todo el procesamiento ocurre en tu dispositivo."
        )
        about_title = "[bold green]¿Qué es eco-ai?[/bold green]"
    else:
        about = (
            "[bold green]eco-ai[/bold green] estimates the ecological impact of your prompts "
            "(energy, CO₂, water and cost) and analyses their quality [bold]without sending anything to external servers[/bold].\n\n"
            "All processing runs on your device."
        )
        about_title = "[bold green]What is eco-ai?[/bold green]"
    console.print(Panel(about, title=about_title, border_style="green", padding=(0, 2)))

    # --- Comandos ---
    cmd_table = Table(box=box.SIMPLE, show_header=True, header_style="bold green", border_style="green")
    cmd_table.add_column("Command" if not es else "Comando", style="bold cyan", no_wrap=True)
    cmd_table.add_column("What it does" if not es else "Qué hace")
    cmd_table.add_column("Basic usage" if not es else "Uso básico", style="dim", no_wrap=True)
    if es:
        cmd_table.add_row("analyze", "Analiza el impacto ecológico de un prompt y sugiere mejoras",
                          'eco-ai analyze "tu prompt"')
        cmd_table.add_row("compare", "Muestra el impacto del mismo prompt en todos los modelos",
                          'eco-ai compare "tu prompt"')
        cmd_table.add_row("models",  "Lista los modelos disponibles con sus precios por token", "eco-ai models")
        cmd_table.add_row("guide",   "Esta guía de uso", "eco-ai guide")
    else:
        cmd_table.add_row("analyze", "Analyses the ecological impact of a prompt and suggests improvements",
                          'eco-ai analyze "your prompt"')
        cmd_table.add_row("compare", "Shows the impact of the same prompt across all models",
                          'eco-ai compare "your prompt"')
        cmd_table.add_row("models",  "Lists available models with their per-token prices", "eco-ai models")
        cmd_table.add_row("guide",   "This usage guide", "eco-ai guide")
    console.print(Panel(cmd_table, title=f"[bold]{'Comandos' if es else 'Commands'}[/bold]", border_style="green"))

    # --- Opciones de analyze ---
    opt_table = Table(box=box.SIMPLE, show_header=True, header_style="bold", border_style="blue")
    opt_table.add_column("Option" if not es else "Opción", style="bold cyan", no_wrap=True)
    opt_table.add_column("Description" if not es else "Descripción")
    opt_table.add_column("Example" if not es else "Ejemplo", style="dim", no_wrap=True)
    if es:
        opt_table.add_row("-m / --model", f"Modelo de referencia (por defecto: {_DEFAULT_MODEL})",
                          '-m "Claude Haiku 4.5"  o  -m haiku')
        opt_table.add_row("-f / --file", "Lee el prompt desde un fichero de texto", "--file mi_prompt.txt")
        opt_table.add_row("--output-ratio", "Fracción estimada de tokens de salida vs entrada (por defecto: 0.4)",
                          "--output-ratio 1.2")
        opt_table.add_row("-t / --output-type",
                          "Tipo de output: auto (por defecto), text, image, code, pdf, artifact",
                          "-t image  o  --output-type pdf")
        opt_table.add_row("--no-tips", "Muestra solo métricas, sin sugerencias", "--no-tips")
        opt_table.add_row("-y / --yes", "Omite la pantalla de consentimiento", "-y")
    else:
        opt_table.add_row("-m / --model", f"Reference model (default: {_DEFAULT_MODEL})",
                          '-m "Claude Haiku 4.5"  or  -m haiku')
        opt_table.add_row("-f / --file", "Read the prompt from a text file", "--file my_prompt.txt")
        opt_table.add_row("--output-ratio", "Estimated output-to-input token ratio (default: 0.4)",
                          "--output-ratio 1.2")
        opt_table.add_row("-t / --output-type",
                          "Output type: auto (default), text, image, code, pdf, artifact",
                          "-t image  or  --output-type pdf")
        opt_table.add_row("--no-tips", "Show metrics only, no suggestions", "--no-tips")
        opt_table.add_row("-y / --yes", "Skip the privacy consent screen", "-y")
    opt_title = "Opciones de [cyan]analyze[/cyan]" if es else "Options for [cyan]analyze[/cyan]"
    console.print(Panel(opt_table, title=f"[bold]{opt_title}[/bold]", border_style="blue"))

    # --- Cómo pasar el prompt ---
    if es:
        input_text = (
            "[bold]1. Argumento directo[/bold]\n"
            '[dim]eco-ai analyze "Explica qué es la fotosíntesis"[/dim]\n\n'
            "[bold]2. Fichero de texto[/bold]\n"
            "[dim]eco-ai analyze --file mi_prompt.txt[/dim]\n\n"
            "[bold]3. Stdin (pipe)[/bold]\n"
            "[dim]cat mi_prompt.txt | eco-ai analyze[/dim]\n"
            "[dim]echo \"Explica X\" | eco-ai analyze -y --no-tips[/dim]"
        )
        input_title = "Cómo pasar el prompt"
    else:
        input_text = (
            "[bold]1. Direct argument[/bold]\n"
            '[dim]eco-ai analyze "Explain what photosynthesis is"[/dim]\n\n'
            "[bold]2. Text file[/bold]\n"
            "[dim]eco-ai analyze --file my_prompt.txt[/dim]\n\n"
            "[bold]3. Stdin (pipe)[/bold]\n"
            "[dim]cat my_prompt.txt | eco-ai analyze[/dim]\n"
            "[dim]echo \"Explain X\" | eco-ai analyze -y --no-tips[/dim]"
        )
        input_title = "How to pass the prompt"
    console.print(Panel(input_text, title=f"[bold]{input_title}[/bold]", border_style="blue"))

    # --- Selección de modelo ---
    if es:
        model_text = (
            "eco-ai acepta el nombre completo o una parte del mismo (sin distinción de mayúsculas):\n\n"
            "[dim]eco-ai analyze \"...\" -m \"Claude Haiku 4.5\"[/dim]   [green]✓ nombre exacto[/green]\n"
            "[dim]eco-ai analyze \"...\" -m haiku[/dim]               [green]✓ coincidencia parcial[/green]\n"
            "[dim]eco-ai analyze \"...\" -m sonnet[/dim]              [yellow]⚠ ambiguo → usa el más reciente[/yellow]\n\n"
            "Consulta todos los modelos disponibles con [bold cyan]eco-ai models[/bold cyan]."
        )
        model_title = "Especificar modelo"
    else:
        model_text = (
            "eco-ai accepts the full name or a partial match (case-insensitive):\n\n"
            "[dim]eco-ai analyze \"...\" -m \"Claude Haiku 4.5\"[/dim]   [green]✓ exact name[/green]\n"
            "[dim]eco-ai analyze \"...\" -m haiku[/dim]               [green]✓ partial match[/green]\n"
            "[dim]eco-ai analyze \"...\" -m sonnet[/dim]              [yellow]⚠ ambiguous → uses the most recent[/yellow]\n\n"
            "See all available models with [bold cyan]eco-ai models[/bold cyan]."
        )
        model_title = "Specifying a model"
    console.print(Panel(model_text, title=f"[bold]{model_title}[/bold]", border_style="blue"))

    # --- Interpretar los resultados ---
    if es:
        results_text = (
            "[bold]Energía estimada[/bold]  — consumo del centro de datos para procesar el prompt "
            "(entrada + salida estimada). Se muestra en Wh y, si es ≥ 1 s de bombilla LED, también "
            "como equivalente cotidiano.\n\n"
            "[bold]CO₂ equivalente[/bold]  — emisiones de gases de efecto invernadero. "
            "Se compara con km en coche o búsquedas en Google.\n\n"
            "[bold]Agua estimada[/bold]    — consumo de refrigeración del centro de datos.\n\n"
            "[bold]Coste API estimado[/bold] — precio aproximado si usaras la API pública "
            "del modelo seleccionado (entrada + 40 % de salida estimada).\n\n"
            "[bold]Modelo recomendado[/bold] — tier sugerido según la complejidad detectada "
            "en el contenido del prompt.\n\n"
            "[dim]Todas las cifras son estimaciones basadas en literatura científica publicada, "
            "no datos exactos de ningún proveedor.[/dim]"
        )
        results_title = "Cómo interpretar los resultados"
    else:
        results_text = (
            "[bold]Estimated energy[/bold]  — data centre consumption to process the prompt "
            "(input + estimated output). Shown in Wh and, if ≥ 1 s of an LED bulb, also as "
            "a everyday equivalent.\n\n"
            "[bold]CO₂ equivalent[/bold]   — greenhouse gas emissions. "
            "Compared to km by car or Google searches.\n\n"
            "[bold]Estimated water[/bold]  — data centre cooling consumption.\n\n"
            "[bold]Estimated API cost[/bold] — approximate price if you used the public API "
            "of the selected model (input + 40 % estimated output).\n\n"
            "[bold]Recommended model[/bold] — suggested tier based on the complexity detected "
            "in the prompt content.\n\n"
            "[dim]All figures are estimates based on published scientific literature, "
            "not exact data from any provider.[/dim]"
        )
        results_title = "How to interpret the results"
    console.print(Panel(results_text, title=f"[bold]{results_title}[/bold]", border_style="magenta"))

    footer = (
        "[dim]Para más detalle sobre cada opción: "
        "[bold]eco-ai analyze --help[/bold] · [bold]eco-ai compare --help[/bold][/dim]\n"
        if es else
        "[dim]For more details on each option: "
        "[bold]eco-ai analyze --help[/bold] · [bold]eco-ai compare --help[/bold][/dim]\n"
    )
    console.print(footer)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
