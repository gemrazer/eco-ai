# CLAUDE.md — Guía de desarrollo para eco-ai

## Project Overview

**eco-ai** es un CLI plugin de Python que optimiza prompts de IA para reducir su impacto ambiental. Las tres métricas de éxito del proyecto son:

1. **Visual polish** — output rico en terminal (rich library), tablas limpias, colores semánticos
2. **Speed of iteration** — feedback rápido; el análisis es local y offline, sin llamadas a APIs externas
3. **Sustainability metrics** — cada sugerencia debe estar respaldada por investigación publicada y traducirse en una reducción concreta de tokens, energía o iteraciones

El plugin funciona 100% en local: no transmite datos del usuario a ningún servidor. Esta es una **invariante de diseño** que no debe romperse.

## Architecture

```
eco_ai/
├── cli.py       # Capa de presentación (typer + rich). Sin lógica de negocio.
├── optimizer.py # Motor de análisis: patrones, sugerencias, recomendación de modelo,
│                #   clasificación de tipo de tarea
├── metrics.py   # Cálculo de impacto ecológico (energía, CO₂, agua, coste)
├── tokenizer.py # Conteo de tokens (tiktoken con fallback a word × 1.3)
└── config.py    # Configuración persistente en ~/.eco-ai.json (idioma ES/EN)
```

## Coding Conventions

- **Python ≥ 3.8** — no usar syntax posterior (match/case, walrus operator en versiones antiguas)
- **TypeScript no aplica** — pero si se añaden tipos en Python, preferir tipos inferidos y evitar `Any`
- Todos los patrones regex deben operar sobre texto **normalizado** (sin tildes, minúsculas) usando `_normalize_for_match()` — nunca sobre el texto original
- Las sugerencias deben incluir siempre una `source` con la referencia bibliográfica
- Las cadenas de usuario (UI) deben estar en el idioma configurado (`Lang.ES` / `Lang.EN`)
- No añadir dependencias externas sin justificación explícita; el tree de deps es intencionalmente pequeño (typer, rich, tiktoken)

## Safety Rules

- **No modificar el esquema de configuración** (`~/.eco-ai.json`) sin petición explícita — cambiar la estructura rompe instalaciones existentes
- **No añadir llamadas a APIs externas** sin consentimiento explícito del usuario — viola la garantía de privacidad
- **No cambiar las constantes de métricas** (`CO2_KG_PER_KWH`, `WATER_L_PER_KWH`, `ENERGY_KWH_PER_1K_TOKENS`) sin actualizar la fuente bibliográfica correspondiente
- No refactorizar bloques de código que no estén directamente relacionados con la tarea en curso

## Key Reference: Impact Hierarchy

El tipo de tarea es el predictor más fuerte del impacto energético (no la longitud del input):

| Tipo de tarea        | Impacto     | gCO₂e/respuesta (referencia) |
|----------------------|-------------|-------------------------------|
| Q&A                  | Mayor       | ≈ 8.17 gCO₂e                 |
| Generación de código | Moderado    | —                             |
| Verificación hechos  | Menor       | —                             |

La longitud del **output** es el factor dominante; la del input es secundaria.

## Key Reference: Verb Energy Dictionary

| Verbo (ES/EN)         | Nivel     | Wh estimado | Alternativa sugerida |
|-----------------------|-----------|-------------|----------------------|
| Analiza / Analyze     | Muy alto  | 20.39 Wh    | Resume, Lista        |
| Explica / Explain     | Alto      | 17.99 Wh    | Lista, Esquematiza   |
| Crea / Create         | Alto      | 16.93 Wh    | Definir límites      |
| Justifica / Justify   | Alto      | 16.59 Wh    | —                    |
| Mide / Measure        | Medio     | 15.72 Wh    | —                    |
| Escribe / Write       | Medio     | 14.27 Wh    | Formato estructurado |
| Clasifica / Classify  | Bajo      | 11.91 Wh    | —                    |
| Lista / List          | Bajo      | 11.10 Wh    | —                    |
| Resume / Summarize    | Mínimo    |  8.10 Wh    | —                    |

## Key Reference: ROCKS Method

Para validar la estructura de un prompt (reduce iteraciones de prueba y error):

- **R** (Role) — `"Eres un experto en X"` / `"Act as an expert in X"`
- **O** (Objective) — objetivo específico declarado
- **C** (Community) — audiencia definida `"para estudiantes de Y"`
- **K** (Key) — tono y estilo `"en tono formal"`
- **S** (Shape) — formato de salida `"en formato tabla"`

R y S ya están cubiertos por `_ROLE_DEFINED` y `_FORMAT_SPECIFIED`. C y K por `_ES_AUDIENCE`/`_EN_AUDIENCE` y `_ES_KEY_PARAMS`/`_EN_KEY_PARAMS`.

## Key Reference: Green Prompting Rules

1. **Eliminar tokens de cortesía** — "por favor", "gracias", "¿podrías?" → imperativos directos
2. **Restricción de salida** — siempre especificar límite: `"Responde en menos de 100 palabras"`
3. **Evitar vaguedad** — `"cuéntame todo sobre X"` → pregunta enfocada
4. **Chaining logic** — dividir tareas complejas en pasos secuenciales

## Sources

- Luccioni et al. (2023) "Power Hungry Processing" — energía por token de inferencia
- Strubell et al. (2019) — CO₂ de entrenamiento/inferencia NLP
- Microsoft Sustainability Report 2023 — agua en centros de datos
- IEA Global Energy & CO₂ Status 2023 — factor de emisión eléctrica
- Anthropic Prompt Engineering Guide (2024)
- Liu et al. (2023) "Lost in the Middle"
- Min et al. (2022) "Rethinking the Role of Demonstrations"
- Sclar et al. (2023) — sensibilidad al formato del prompt
