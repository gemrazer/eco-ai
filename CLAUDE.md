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

## Key Reference: Additional Analysis Rules

### Few-shot prompting
Si el prompt describe un patrón o formato esperado (detectar: "como este ejemplo", "en el mismo formato que", "following this pattern"…) pero **no incluye un ejemplo concreto** de input/output → sugerir añadir 1–2 ejemplos.
Patrón: `_PATTERN_WITHOUT_EXAMPLE_RE`. Fuente: DAIR.AI Prompt Engineering Guide.

### Chain-of-thought
Si `_REASONING` detecta una tarea de razonamiento complejo **y** el prompt no contiene "paso a paso" / "step by step" / "think step" → sugerir `"Piensa paso a paso antes de responder."`.
Fuente: Anthropic Prompt Engineering Guide (2024) — extended thinking; OpenAI Best Practices (2024).

### Contexto multi-documento (scoring de modelo)
≥2 de estas señales → `score += 2` con señal "contexto multi-documento": XML tags (`<document`, `<context`…), `###` repetidos, `---` repetidos, ≥2 bloques de código, ≥3 saltos de línea dobles.
Fuente: Liu et al. (2023) "Lost in the Middle".

### Imagen: checks adicionales
- **Estilos contradictorios** — fotorrealista + cartoon/anime → elegir un solo estilo.
- **Prompt >80 palabras** — mover sujeto y estilo al principio (CLIP pondera primeros tokens).
- **Sin iluminación/mood** — sugerir golden hour, studio lighting, dramatic shadows, etc.

### Código: checks específicos (`output_type == "code"`)
- Lenguaje no especificado → indicar lenguaje.
- Tests/docstrings no mencionados → aclarar si se quieren.
- ≥2 conectores aditivos ("además", "también", "also"…) → prompt chaining.
Fuente: Anthropic Prompt Engineering Guide (2024) — prompt chaining para tareas complejas.

### Tool routing — herramienta especializada más eficiente (checks 19–22)

Detectar cuando un LLM no es la herramienta óptima y sugerir alternativas de menor impacto energético.
La sugerencia siempre **menciona el término exacto del usuario** (p. ej. `"buenos"`, `"baratos"`) para máxima personalización.

| Check | Trigger | Herramienta sugerida |
|-------|---------|----------------------|
| **19. Búsqueda local** | `_LOCAL_PLACE_TYPE_RE` + (`_LOCATION_SIGNAL_RE` o `_SEARCH_INTENT_RE`) | Google Maps, TripAdvisor |
| **19b. Criterio vago** | place type + `_VAGUE_QUALITY_PLACE_RE` (sin ubicación) | Añadir contexto específico |
| **20. Proximidad vaga** | `_VAGUE_PROXIMITY_RE` + ubicación + sin `_CONCRETE_DISTANCE_RE` | Especificar radio/medio |
| **21. Tiempo real** | `_REALTIME_RE` (clima, noticias, precios, vuelos, horarios) | App dedicada, buscador |
| **22. Rutas** | `_DIRECTIONS_RE` (cómo llegar, rutas, transporte) | Google Maps, Waze |

**Regla de personalización:** si `_VAGUE_QUALITY_PLACE_RE` coincide, el término detectado se incrusta literalmente en `description` con `match.group(0)`.
**Referencia energética:** búsqueda indexada ~0.0003 Wh vs. inferencia LLM ~0.001–0.01 Wh/consulta.
Fuente: Luccioni et al. (2023) — coste energético de inferencia vs. búsqueda indexada.

## Sources

- Luccioni et al. (2023) "Power Hungry Processing" — energía por token de inferencia
- Strubell et al. (2019) — CO₂ de entrenamiento/inferencia NLP
- Microsoft Sustainability Report 2023 — agua en centros de datos
- IEA Global Energy & CO₂ Status 2023 — factor de emisión eléctrica
- Anthropic Prompt Engineering Guide (2024) — especificidad, XML structuring, extended thinking, prompt chaining
- OpenAI Best Practices (2024) — chain-of-thought, especificidad
- DAIR.AI Prompt Engineering Guide — few-shot prompting
- Liu et al. (2023) "Lost in the Middle" — degradación en contextos largos
- Min et al. (2022) "Rethinking the Role of Demonstrations" — saturación de few-shot
- Sclar et al. (2023) — sensibilidad al formato del prompt
- Zhao et al. (2021) "Calibrate Before Use" — sesgo con demasiados ejemplos few-shot
