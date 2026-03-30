# eco-ai

CLI para estimar el impacto ecológico de tus prompts de IA y optimizar su redacción.

Analiza energía consumida, CO₂ generado, agua utilizada y coste de API — todo **localmente**, sin enviar datos a ningún servidor externo.

## Instalación

```bash
pip install -e .
```

## Uso

```bash
# Analizar un prompt
eco-ai analyze "tu prompt aquí"

# Analizar desde fichero
eco-ai analyze --file prompt.txt

# Analizar desde stdin
echo "tu prompt" | eco-ai analyze

# Comparar todos los modelos
eco-ai compare "tu prompt"

# Ver modelos disponibles
eco-ai models

# Guía de uso
eco-ai guide

# Configuración
eco-ai config --lang en   # cambiar idioma (es / en)
eco-ai config --show      # ver configuración actual
```

## Opciones de `analyze`

| Opción | Descripción | Por defecto |
|--------|-------------|-------------|
| `-m / --model` | Modelo de referencia | Claude Sonnet 4.6 |
| `-f / --file` | Leer prompt desde fichero | — |
| `--output-ratio` | Fracción estimada de tokens de salida | 0.4 |
| `--lang` | Idioma del prompt (`es` o `en`) | Config guardada |
| `--verbose` | Muestra referencias bibliográficas de cada sugerencia | — |
| `--no-tips` | Solo métricas, sin sugerencias | — |
| `-y / --yes` | Omitir pantalla de consentimiento | — |

## Modelos soportados

| Tier | Modelos |
|------|---------|
| small | Claude Haiku 4.5, GPT-4o mini |
| medium | Claude Sonnet 4.6, Claude Sonnet 4, Gemini 1.5 Pro |
| large | Claude Opus 4.6, Claude Opus 4, GPT-4o, Llama 3 70B |

## Cómo funciona

1. **Tokenización** — cuenta tokens con `tiktoken` (cl100k_base) o aproxima con palabras × 1.3
2. **Métricas energéticas** — estima kWh basándose en el tier del modelo (Luccioni et al., 2023)
3. **CO₂** — convierte energía a emisiones usando factor de emisión de grandes nubes (IEA, 2023)
4. **Agua** — estima consumo de refrigeración de centros de datos (Microsoft Sustainability Report, 2023)
5. **Análisis de redacción** — detecta frases de cortesía, lenguaje vago, falta de estructura, etc.
6. **Recomendación de modelo** — sugiere el tier más adecuado según la complejidad del prompt

## Fuentes

- Luccioni et al. (2023) *Power Hungry Processing: Scrutinizing Energy Use in NLP*
- Liu et al. (2023) *Lost in the Middle: How Language Models Use Long Contexts*
- Min et al. (2022) *Rethinking the Role of Demonstrations in Few-Shot Prompting*
- Webson & Pavlick (2021) *Do Prompt-Based Models Really Understand the Meaning of Their Prompts?*
- Anthropic Prompt Engineering Guide (2024)

## Privacidad

Todo el análisis ocurre en tu dispositivo. El texto del prompt nunca se envía a servidores externos.
