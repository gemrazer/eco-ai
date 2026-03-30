"""eco-ai: Analiza el impacto ecológico de tus prompts de IA."""

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

WELCOME = """[bold green]eco-ai[/bold green] — [italic]uso consciente de la inteligencia artificial[/italic]

Este plugin te ayuda a [bold]optimizar tus prompts[/bold] antes de enviarlos a un modelo de IA.
Cada petición consume energía, agua y genera CO₂. Cuantos menos tokens uses, menor es el impacto.

Con eco-ai aprenderás a:
  • Estimar el coste ecológico real de tus prompts
  • Identificar qué partes son innecesarias o redundantes
  • Escribir prompts más precisos y eficientes

[bold green]100% eco-friendly[/bold green] — todo el análisis ocurre en tu dispositivo.
Sin llamadas a APIs externas. Sin transmisión de tus datos. Sin huella adicional.

[dim]Usa [bold]eco-ai --help[/bold] para ver todos los comandos disponibles.[/dim]"""


def _print_welcome() -> None:
    console.print()
    console.print(Panel(WELCOME, border_style="green", padding=(1, 2)))
    console.print()


app = typer.Typer(
    name="eco-ai",
    help="Estima el impacto ecológico de tus prompts de IA y sugiere cómo optimizarlos.",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
)

console = Console()


@app.callback()
def main(ctx: typer.Context) -> None:
    """eco-ai — uso consciente de la inteligencia artificial."""
    if ctx.invoked_subcommand is None:
        _print_welcome()

MODELS = list(MODEL_PRICES_USD.keys())


def _print_consent_notice() -> bool:
    console.print()
    console.print(Panel(
        "[bold yellow]Aviso de privacidad y consentimiento[/bold yellow]\n\n"
        "Este análisis se realiza [bold]localmente en tu dispositivo[/bold].\n"
        "Tu texto [bold]no se envía[/bold] a ningún servidor externo.\n\n"
        "Los datos analizados son:\n"
        "  • El texto del prompt que proporciones\n"
        "  • Su longitud y estructura\n\n"
        "Las estimaciones de impacto ecológico son [italic]aproximaciones[/italic] "
        "basadas en investigación publicada — no datos exactos de ningún proveedor.",
        title="[bold]eco-ai[/bold]",
        border_style="yellow",
    ))
    return Confirm.ask("[yellow]¿Autorizas el análisis de tu prompt?[/yellow]")


_DEFAULT_MODEL = "Claude Sonnet 4.6"


def _render_impact_table(impact) -> Table:
    table = Table(box=box.ROUNDED, show_header=False, border_style="green")
    table.add_column("Métrica", style="bold")
    table.add_column("Valor", justify="right")
    table.add_column("Equivalencia", style="dim")

    model_note = "por defecto — usa -m para cambiarlo" if impact.model == _DEFAULT_MODEL else ""
    table.add_row("Modelo", impact.model, model_note)
    table.add_row("Tokens (entrada)", f"{impact.tokens:,}", tokenizer_source())

    energy_str = f"{impact.energy_kwh*1000:.4f} Wh"
    energy_note = impact.energy_time_equiv or "entrada + salida estimada"
    table.add_row("Energía estimada", energy_str, energy_note)

    co2_str = f"{impact.co2_g:.4f} g CO₂e"
    table.add_row("CO₂ equivalente", co2_str, impact.co2_equiv)

    water_note = impact.water_time_equiv or "refrigeración del centro de datos"
    table.add_row("Agua estimada", impact.water_equiv, water_note)

    if impact.cost_usd is not None:
        cost_str = f"${impact.cost_usd:.6f} USD"
        table.add_row("Coste API estimado", cost_str, "entrada + salida estimada (40%)")

    return table


def _render_model_recommendation(rec) -> None:
    tier_color = {"large": "red", "medium": "yellow", "small": "green"}.get(rec.tier, "white")
    lines = [
        f"[bold {tier_color}]{rec.headline}[/bold {tier_color}]",
        rec.reason,
    ]
    if rec.signals:
        lines.append(f"\n[dim]Señales detectadas: {', '.join(rec.signals)}[/dim]")
    console.print(Panel(
        "\n".join(lines),
        title="[bold]Modelo recomendado para esta tarea[/bold]",
        border_style=tier_color,
        padding=(0, 1),
    ))


def _render_suggestions(suggestions, rec, positives, verbose: bool = False) -> None:
    # --- Recomendación de modelo (siempre visible) ---
    console.print()
    _render_model_recommendation(rec)

    # --- Feedback de redacción ---
    if not suggestions:
        lines = ["[bold green]✓ El prompt no tiene problemas obvios de redacción.[/bold green]"]
        if positives:
            lines.append("")
            for asp in positives:
                lines.append(f"  [green]✓[/green] {asp}")
        lines.append(
            "\n[dim]Si quieres seguir mejorando, consulta los principios en [bold]eco-ai guide[/bold].[/dim]"
        )
        console.print(Panel("\n".join(lines), title="Calidad del prompt", border_style="green", padding=(0, 1)))
        return

    console.print(f"\n[bold cyan]Sugerencias para reducir tokens[/bold cyan] "
                  f"[dim]({len(suggestions)} encontradas)[/dim]\n")

    for i, sug in enumerate(suggestions, 1):
        lines = [f"[bold]{sug.category}[/bold]", sug.description]
        if sug.example:
            lines.append(f"\n[dim]Ejemplo:[/dim] {sug.example}")
        if sug.savings_estimate:
            lines.append(f"[green]{sug.savings_estimate}[/green]")
        if verbose and sug.source:
            lines.append(f"\n[dim]Fuente: {sug.source}[/dim]")

        console.print(Panel(
            "\n".join(lines),
            title=f"[cyan]{i}[/cyan]",
            border_style="cyan",
            padding=(0, 1),
        ))


@app.command()
def analyze(
    prompt: Optional[str] = typer.Argument(None, help="Texto del prompt a analizar"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Fichero de texto con el prompt"),
    model: str = typer.Option(_DEFAULT_MODEL, "--model", "-m",
                               help="Modelo de referencia (usa 'eco-ai models' para ver la lista completa)."),
    no_consent: bool = typer.Option(False, "--yes", "-y", help="Omitir la pantalla de consentimiento"),
    no_tips: bool = typer.Option(False, "--no-tips", help="Mostrar solo métricas, sin sugerencias"),
    output_ratio: float = typer.Option(0.4, "--output-ratio",
                                        help="Fracción estimada de tokens de salida respecto a entrada (0–2)"),
    lang: Optional[Lang] = typer.Option(None, "--lang", "-l",
                                         help="Idioma del prompt: es (español) o en (inglés). Por defecto usa la config guardada."),
    verbose: bool = typer.Option(False, "--verbose", "-v",
                                  help="Muestra la referencia bibliográfica de cada sugerencia."),
) -> None:
    """Analiza el impacto ecológico de un prompt y sugiere optimizaciones."""

    # --- Leer texto ---
    text: str | None = None

    if file and prompt:
        console.print("[yellow]Aviso: se ignorará el argumento posicional porque se proporcionó --file.[/yellow]")
    if file:
        if not file.exists():
            console.print(f"[red]Error: el fichero '{file}' no existe.[/red]")
            raise typer.Exit(1)
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            console.print(f"[red]Error: el fichero '{file}' no es UTF-8. Conviértelo con:[/red]")
            console.print(f"[dim]  iconv -f latin1 -t utf-8 {file} > {file}.utf8[/dim]")
            raise typer.Exit(1)
    elif prompt:
        text = prompt
    elif not sys.stdin.isatty():
        text = sys.stdin.read()

    if not text or not text.strip():
        console.print("[red]Error: proporciona un prompt (argumento, --file, o stdin).[/red]")
        console.print("\n[dim]Uso: eco-ai analyze \"tu prompt aquí\"[/dim]")
        console.print("[dim]     eco-ai analyze --file prompt.txt[/dim]")
        console.print("[dim]     echo \"tu prompt\" | eco-ai analyze[/dim]")
        raise typer.Exit(1)

    # --- Validar output_ratio ---
    if output_ratio < 0:
        console.print(f"[red]Error: --output-ratio debe ser ≥ 0 (recibido: {output_ratio}).[/red]")
        raise typer.Exit(1)

    # --- Validar modelo ---
    if model not in MODEL_PRICES_USD:
        model_lower = model.lower()
        matches = [m for m in MODELS if model_lower in m.lower()]
        if len(matches) == 1:
            model = matches[0]
        elif len(matches) > 1:
            # Elegir el más reciente (primero en la lista, que está ordenada de más nuevo a más viejo)
            model = matches[0]
            console.print(f"[yellow]Modelo ambiguo '{model_lower}' — usando '{model}'. "
                          f"Otros: {', '.join(matches[1:])}[/yellow]")
        else:
            console.print(f"[red]Modelo desconocido:[/red] '{model}'")
            console.print(f"[dim]Disponibles: {', '.join(MODELS)}[/dim]")
            raise typer.Exit(1)

    # --- Consentimiento ---
    if not no_consent:
        authorized = _print_consent_notice()
        if not authorized:
            console.print("\n[yellow]Análisis cancelado. No se ha procesado ningún dato.[/yellow]\n")
            raise typer.Exit(0)

    # --- Análisis ---
    console.print()
    tokens = count_tokens(text)
    impact = calculate_impact(tokens, model, output_ratio)

    console.print(Panel(
        _render_impact_table(impact),
        title="[bold green]Impacto ecológico estimado[/bold green]",
        border_style="green",
    ))

    effective_lang = lang or get_lang()

    # Tipo de tarea (siempre visible — afecta al impacto energético)
    task_type, task_label, task_note = detect_task_type(text, effective_lang)
    _type_color = {"qa": "red", "code": "yellow", "fact": "green", "general": "dim"}.get(task_type, "dim")
    task_line = f"[{_type_color}]{task_label}[/{_type_color}]"
    if task_note:
        task_line += f"  [dim]{task_note}[/dim]"
    console.print(f"[bold]Tipo de tarea detectado:[/bold] {task_line}\n")

    if not no_tips:
        suggestions = analyze_prompt(text, effective_lang)
        rec = recommend_model(text, tokens)
        positives = positive_aspects(text, effective_lang)
        _render_suggestions(suggestions, rec, positives, verbose=verbose)

    # Nota de cierre
    console.print(
        "[dim]Nota: estas estimaciones son aproximaciones basadas en literatura científica. "
        "Los valores reales varían según el proveedor, el centro de datos y la carga del sistema.[/dim]\n"
    )


@app.command()
def models() -> None:
    """Lista los modelos disponibles y sus precios por 1 000 tokens."""
    table = Table(title="Modelos disponibles", box=box.ROUNDED, border_style="blue")
    table.add_column("Modelo", style="bold")
    table.add_column("Tier", justify="center")
    table.add_column("Input ($/1K tok)", justify="right")
    table.add_column("Output ($/1K tok)", justify="right")

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
    console.print(
        "\n[dim]Usa --model \"Nombre del modelo\" en el comando analyze.[/dim]\n"
    )


@app.command()
def compare(
    prompt: Optional[str] = typer.Argument(None, help="Texto del prompt a comparar"),
    file: Optional[Path] = typer.Option(None, "--file", "-f"),
    no_consent: bool = typer.Option(False, "--yes", "-y"),
    output_ratio: float = typer.Option(0.4, "--output-ratio",
                                        help="Fracción estimada de tokens de salida respecto a entrada (0–2)"),
) -> None:
    """Compara el impacto ecológico del mismo prompt en todos los modelos disponibles."""

    text: str | None = None
    if file and prompt:
        console.print("[yellow]Aviso: se ignorará el argumento posicional porque se proporcionó --file.[/yellow]")
    if file:
        if not file.exists():
            console.print(f"[red]Error: el fichero '{file}' no existe.[/red]")
            raise typer.Exit(1)
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            console.print(f"[red]Error: el fichero '{file}' no es UTF-8. Conviértelo con:[/red]")
            console.print(f"[dim]  iconv -f latin1 -t utf-8 {file} > {file}.utf8[/dim]")
            raise typer.Exit(1)
    elif prompt:
        text = prompt
    elif not sys.stdin.isatty():
        text = sys.stdin.read()

    if not text or not text.strip():
        console.print("[red]Error: proporciona un prompt.[/red]")
        raise typer.Exit(1)

    if output_ratio < 0:
        console.print(f"[red]Error: --output-ratio debe ser ≥ 0 (recibido: {output_ratio}).[/red]")
        raise typer.Exit(1)

    if not no_consent:
        authorized = _print_consent_notice()
        if not authorized:
            console.print("\n[yellow]Análisis cancelado.[/yellow]\n")
            raise typer.Exit(0)

    tokens = count_tokens(text)

    table = Table(
        title=f"Comparativa de impacto — {tokens} tokens",
        box=box.ROUNDED,
        border_style="magenta",
    )
    table.add_column("Modelo", style="bold")
    table.add_column("Energía (Wh)", justify="right")
    table.add_column("CO₂ (g)", justify="right")
    table.add_column("Agua (mL)", justify="right")
    table.add_column("Coste USD", justify="right")

    for model in MODELS:
        impact = calculate_impact(tokens, model, output_ratio)
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
    console.print(f"\n[dim]Tokenizador: {tokenizer_source()}[/dim]\n")


@app.command()
def config(
    set_language: Optional[Lang] = typer.Option(None, "--lang", "-l",
                                                  help="Establece el idioma por defecto: es o en."),
    show: bool = typer.Option(False, "--show", help="Muestra la configuración actual."),
) -> None:
    """Gestiona la configuración persistente de eco-ai (~/.eco-ai.json)."""
    from .config import load, get_lang as _get_lang

    if set_language:
        set_lang(set_language)
        console.print(f"[green]✓[/green] Idioma por defecto establecido a [bold]{set_language.value}[/bold].")
        return

    # Sin argumentos o con --show → mostrar config actual
    cfg = load()
    current_lang = _get_lang()
    table = Table(box=box.ROUNDED, show_header=False, border_style="blue")
    table.add_column("Clave", style="bold")
    table.add_column("Valor")
    table.add_column("Descripción", style="dim")
    table.add_row("lang", current_lang.value,
                  "Idioma del prompt analizado (es = español, en = inglés)")
    table.add_row("config_file", str(__import__('pathlib').Path.home() / '.eco-ai.json'),
                  "Ruta del fichero de configuración")
    console.print()
    console.print(Panel(table, title="[bold blue]Configuración actual[/bold blue]", border_style="blue"))
    console.print(
        "\n[dim]Para cambiar: [bold]eco-ai config --lang en[/bold] "
        "o usa [bold]--lang[/bold] en cada comando.[/dim]\n"
    )


@app.command()
def guide() -> None:
    """Muestra la guía de uso del plugin eco-ai."""

    console.print()

    # --- Qué es eco-ai ---
    console.print(Panel(
        "[bold green]eco-ai[/bold green] estima el impacto ecológico de tus prompts "
        "(energía, CO₂, agua y coste) y analiza su calidad [bold]sin enviar nada a servidores externos[/bold].\n\n"
        "Todo el procesamiento ocurre en tu dispositivo.",
        title="[bold green]¿Qué es eco-ai?[/bold green]",
        border_style="green",
        padding=(0, 2),
    ))

    # --- Comandos ---
    cmd_table = Table(box=box.SIMPLE, show_header=True, header_style="bold green", border_style="green")
    cmd_table.add_column("Comando", style="bold cyan", no_wrap=True)
    cmd_table.add_column("Qué hace")
    cmd_table.add_column("Uso básico", style="dim", no_wrap=True)
    cmd_table.add_row(
        "analyze",
        "Analiza el impacto ecológico de un prompt y sugiere mejoras",
        'eco-ai analyze "tu prompt"',
    )
    cmd_table.add_row(
        "compare",
        "Muestra el impacto del mismo prompt en todos los modelos",
        'eco-ai compare "tu prompt"',
    )
    cmd_table.add_row(
        "models",
        "Lista los modelos disponibles con sus precios por token",
        "eco-ai models",
    )
    cmd_table.add_row(
        "guide",
        "Esta guía de uso",
        "eco-ai guide",
    )
    console.print(Panel(cmd_table, title="[bold]Comandos[/bold]", border_style="green"))

    # --- Opciones de analyze ---
    opt_table = Table(box=box.SIMPLE, show_header=True, header_style="bold", border_style="blue")
    opt_table.add_column("Opción", style="bold cyan", no_wrap=True)
    opt_table.add_column("Descripción")
    opt_table.add_column("Ejemplo", style="dim", no_wrap=True)
    opt_table.add_row(
        "-m / --model",
        f"Modelo de referencia para el cálculo (por defecto: {_DEFAULT_MODEL})",
        '-m "Claude Haiku 4.5"  o  -m haiku',
    )
    opt_table.add_row(
        "-f / --file",
        "Lee el prompt desde un fichero de texto en lugar de la línea de comandos",
        "--file mi_prompt.txt",
    )
    opt_table.add_row(
        "--output-ratio",
        "Fracción estimada de tokens de salida vs entrada (por defecto: 0.4 = 40 %)",
        "--output-ratio 1.2",
    )
    opt_table.add_row(
        "--no-tips",
        "Muestra solo las métricas, sin sugerencias ni recomendación de modelo",
        "--no-tips",
    )
    opt_table.add_row(
        "-y / --yes",
        "Omite la pantalla de consentimiento de privacidad",
        "-y",
    )
    console.print(Panel(opt_table, title="[bold]Opciones de [cyan]analyze[/cyan][/bold]", border_style="blue"))

    # --- Formas de pasar el prompt ---
    input_text = (
        "[bold]1. Argumento directo[/bold]\n"
        '[dim]eco-ai analyze "Explica qué es la fotosíntesis"[/dim]\n\n'
        "[bold]2. Fichero de texto[/bold]\n"
        "[dim]eco-ai analyze --file mi_prompt.txt[/dim]\n\n"
        "[bold]3. Stdin (pipe)[/bold]\n"
        "[dim]cat mi_prompt.txt | eco-ai analyze[/dim]\n"
        "[dim]echo \"Explica X\" | eco-ai analyze -y --no-tips[/dim]"
    )
    console.print(Panel(input_text, title="[bold]Cómo pasar el prompt[/bold]", border_style="blue"))

    # --- Selección de modelo ---
    model_text = (
        "eco-ai acepta el nombre completo o una parte del mismo (sin distinción de mayúsculas):\n\n"
        "[dim]eco-ai analyze \"...\" -m \"Claude Haiku 4.5\"[/dim]   [green]✓ nombre exacto[/green]\n"
        "[dim]eco-ai analyze \"...\" -m haiku[/dim]               [green]✓ coincidencia parcial[/green]\n"
        "[dim]eco-ai analyze \"...\" -m sonnet[/dim]              [yellow]⚠ ambiguo → usa el más reciente[/yellow]\n\n"
        "Consulta todos los modelos disponibles con [bold cyan]eco-ai models[/bold cyan]."
    )
    console.print(Panel(model_text, title="[bold]Especificar modelo[/bold]", border_style="blue"))

    # --- Interpretar los resultados ---
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
    console.print(Panel(results_text, title="[bold]Cómo interpretar los resultados[/bold]", border_style="magenta"))

    console.print(
        "[dim]Para más detalle sobre cada opción: "
        "[bold]eco-ai analyze --help[/bold] · [bold]eco-ai compare --help[/bold][/dim]\n"
    )


def run() -> None:
    app()


if __name__ == "__main__":
    run()
