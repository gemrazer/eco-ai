"""Analiza un prompt y sugiere cómo comprimirlo para usar menos tokens."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from .config import Lang


# ---------------------------------------------------------------------------
# Normalización para matching robusto
# ---------------------------------------------------------------------------

def _normalize_for_match(text: str) -> str:
    """
    Versión del texto apta para pattern matching tolerante:
    - Elimina diacríticos: 'podrías' → 'podrias', 'días' → 'dias'
    - Colapsa espacios múltiples
    - Minúsculas
    El texto original NO se modifica — nunca llega al output.
    """
    nfd = unicodedata.normalize("NFD", text)
    ascii_text = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", ascii_text.lower())


# ---------------------------------------------------------------------------
# Patrones ES  (todos en ASCII — la normalización elimina tildes)
# ---------------------------------------------------------------------------

_ES_FILLER = re.compile(
    r"\bpor\s*fa[bv]or\b"       # por favor / porfavor / porfabor (b/v)
    r"|\bplee?a?s+e?\b"         # please / pleese / plese
    r"|\bsi no te importa\b"
    r"|\bsi puedes?\b"
    r"|\bme gustaria que\b"
    r"|\bpodrias?\b"
    r"|\bte agradezco\b"
    r"|\bgracias de antemano\b"
    r"|\bquisiera que\b"
    r"|\bsi es posible\b"
    r"|\bnecesito que\b"
    r"|\bme ayudes?\b",
)
_ES_VAGUE = [
    re.compile(r"\bde alguna manera\b"),
    re.compile(r"\bmas o menos\b"),
    re.compile(r"\balgo asi\b"),
    re.compile(r"\bcomo que\b"),
    re.compile(r"\bno se bien\b"),
    re.compile(r"\btal vez\b.*\btal vez\b"),
]
_ES_INTRO = [
    re.compile(r"^(hola|hey|buenas|buenos dias|buenas tardes|buenas noches)[,.]?\s"),
    re.compile(r"^soy [a-z ]+[,.]\s"),
    re.compile(r"^estoy trabajando en un proyecto"),
    re.compile(r"^como sabes?\b"),
    re.compile(r"^quiero que sepas que\b"),
]
_ES_FORMAT = ["json", "markdown", "lista", "tabla", "bullet", "parrafo", "codigo", "formato", "viñeta", "vineta"]
_ES_EXAMPLES = re.compile(r"\bpor ejemplo\b|\bej\.?\b|\be\.g\.?\b|\bcomo\b")
_ES_SIMPLE = re.compile(
    r"^(traduce|corrige la ortografia|dame un sinonimo"
    r"|que significa\b|define\b|convierte\b|formatea\b|lista de\b|enumera\b)\b",
)

# ---------------------------------------------------------------------------
# Patrones EN
# ---------------------------------------------------------------------------

_EN_FILLER = re.compile(
    r"\bplee?a?s+e?\b"               # please / pleese / plese
    r"|\bcould you\b"
    r"|\bwould you\b"
    r"|\bi would like (you )?(to )?\b"
    r"|\bif you (could|can|don'?t mind)\b"
    r"|\bthank you in advance\b"
    r"|\bthanks in advance\b"
    r"|\bi need you to\b"
    r"|\bcould you help\b"
    r"|\bkindly\b"
    r"|\bif possible\b"
    r"|\bwhenever you (can|get a chance)\b",
)
_EN_VAGUE = [
    re.compile(r"\bkind of\b"),
    re.compile(r"\bsort of\b"),
    re.compile(r"\bmore or less\b"),
    re.compile(r"\bsomething like\b"),
    re.compile(r"\bi('m| am) not sure\b"),
    re.compile(r"\bmaybe\b.*\bmaybe\b"),
]
_EN_INTRO = [
    re.compile(r"^(hello|hi|hey|good morning|good afternoon|good evening)[,!.]?\s"),
    re.compile(r"^i am (a |an )?[a-z ]+(and |who )\b"),
    re.compile(r"^i'?m working on (a |an )?\b"),
    re.compile(r"^as you (know|may know)\b"),
    re.compile(r"^i wanted to (let you know|tell you)\b"),
    re.compile(r"^just (wanted|checking)\b"),
]
_EN_FORMAT = ["json", "markdown", "list", "table", "bullet", "paragraph", "code", "format", "numbered"]
_EN_EXAMPLES = re.compile(r"\bfor example\b|\be\.g\.?\b|\bsuch as\b|\blike\b")
_EN_SIMPLE = re.compile(
    r"^(translate|spell.check|synonym for|what does\b|define\b"
    r"|convert\b|format\b|list of\b|enumerate\b)\b",
)

# ---------------------------------------------------------------------------
# Patrones de recomendación (bilingüe, ASCII tras normalización)
# ---------------------------------------------------------------------------

_COMPLEX_SCIENTIFIC = re.compile(
    r"\b(hipotesis|metodologia|meta.analisis|revision sistematica|peer.review"
    r"|estadistica|regresion|correlacion|varianza|distribucion|significancia"
    r"|articulo cientifico|paper|abstract|bibliografia|citacion|ecuacion diferencial"
    r"|hypothesis|methodology|systematic review|meta.analysis|statistical significance"
    r"|literature review|empirical study|control group|p.value|confidence interval)\b",
)
_COMPLEX_CODE = re.compile(
    r"\b(arquitectura de software|design pattern|refactori[zs]|complejidad algoritmica"
    r"|concurrencia|paralelismo|microservicio|kubernetes|docker|ci.cd|devops"
    r"|machine learning|deep learning|red neuronal|transformer model"
    r"|distributed system|system design|load balancing|race condition)\b",
)
_COMPLEX_DOMAIN = re.compile(
    r"\b(contrato|clausula legal|normativa|regulacion|compliance|juridico"
    r"|diagnostico medico|sintoma|tratamiento|medicamento|dosis"
    r"|analisis financiero|cartera de inversion|fiscalidad|auditoria"
    r"|legal clause|medical diagnosis|financial analysis|tax|audit|liability)\b",
)
_REASONING = re.compile(
    r"\b(analiza|compara|evalua|argumenta|debate|pros y contras"
    r"|ventajas y desventajas|critica|justifica|demuestra|razona paso a paso"
    r"|analyze|evaluate|compare|argue|step by step|pros and cons"
    r"|advantages and disadvantages|critically assess)\b",
)
_CODE_GENERAL = re.compile(
    r"\b(funcion|function|codigo|script|programa|clase|class|metodo|method"
    r"|sql|query|html|css|javascript|python|java|typescript|bash|shell"
    r"|api|endpoint|base de datos|database|algorithm|data structure)\b",
)
_FORMAT_SPECIFIED = re.compile(
    r"\b(json|markdown|lista\b|tabla\b|list\b|table\b|bullet|vineta|parrafo|paragraph"
    r"|codigo|code|formato|format|numera|numbered|en forma de|como tabla|in the form of)\b",
)
_ROLE_DEFINED = re.compile(
    r"\b(actua como|eres un|eres una|como experto|como especialista"
    r"|act as|you are a|you'?re a|as an expert|as a specialist)\b",
)

# ---------------------------------------------------------------------------
# Diccionario de verbos por nivel energético (Sección 3 del doc de referencia)
# Valores Wh estimados por tipo de tarea — Luccioni et al. (2023); jerarquía
# de impacto por verbo basada en mediciones de output energético por tarea.
# ---------------------------------------------------------------------------

# nivel → (wh_estimado, alternativas_ES, alternativas_EN)
_VERB_ENERGY: dict[str, tuple[str, float, list[str], list[str]]] = {
    # ES verbs
    "analiza":   ("very_high", 20.39, ["resume", "lista"],          ["summarize", "list"]),
    "explica":   ("high",      17.99, ["lista", "esquematiza"],     ["list", "outline"]),
    "crea":      ("high",      16.93, ["define los límites"],       ["define the output limits"]),
    "justifica": ("high",      16.59, [],                           []),
    "mide":      ("medium",    15.72, [],                           []),
    "escribe":   ("medium",    14.27, ["usa tabla o lista"],        ["use table or list"]),
    "clasifica": ("low",       11.91, [],                           []),
    "lista":     ("low",       11.10, [],                           []),
    "resume":    ("minimal",    8.10, [],                           []),
    # EN verbs
    "analyze":   ("very_high", 20.39, ["resume", "lista"],          ["summarize", "list"]),
    "explain":   ("high",      17.99, ["lista", "esquematiza"],     ["list", "outline"]),
    "create":    ("high",      16.93, ["define los límites"],       ["define the output limits"]),
    "justify":   ("high",      16.59, [],                           []),
    "measure":   ("medium",    15.72, [],                           []),
    "write":     ("medium",    14.27, ["usa tabla o lista"],        ["use table or list"]),
    "classify":  ("low",       11.91, [],                           []),
    "list":      ("low",       11.10, [],                           []),
    "summarize": ("minimal",    8.10, [],                           []),
}

_VERB_DETECT_RE = re.compile(
    r"^(analiza|explica|crea|justifica|mide|escribe|clasifica|lista|resume"
    r"|analyze|explain|create|justify|measure|write|classify|list|summarize)\b"
)

# ---------------------------------------------------------------------------
# Hints de contexto para prompts muy cortos, indexados por tipo de output.
# Constante de módulo para evitar reconstrucción en cada llamada a analyze().
# ---------------------------------------------------------------------------
_SHORT_PROMPT_HINTS: dict[str, tuple[str, str]] = {
    "text": (
        "¿Para quién es la respuesta? ¿Qué formato esperas (lista, tabla, párrafo)? ¿Qué longitud máxima?",
        "Who is the answer for? What format do you expect (list, table, paragraph)? What maximum length?",
    ),
    "code": (
        "Añade: lenguaje de programación, qué debe hacer la función, inputs y outputs esperados.",
        "Add: programming language, what the function should do, expected inputs and outputs.",
    ),
    "image": (
        "Añade: sujeto principal, estilo visual (fotorrealista, ilustración…) y relación de aspecto.",
        "Add: main subject, visual style (photorealistic, illustration…) and aspect ratio.",
    ),
    "pdf": (
        "Añade: audiencia objetivo, número de páginas aproximado y secciones esperadas.",
        "Add: target audience, approximate page count and expected sections.",
    ),
    "artifact": (
        "Añade: tipo de archivo (CSV, JSON…), columnas/campos esperados y un ejemplo de fila.",
        "Add: file type (CSV, JSON…), expected columns/fields and a sample row.",
    ),
}

# ---------------------------------------------------------------------------
# Restricción de longitud de salida (Green Prompting — Sección 5)
# ---------------------------------------------------------------------------

_ES_OUTPUT_LIMIT = re.compile(
    r"\b(en menos de \d|maximo \d|max\.? \d|no mas de \d|brevemente|concisamente"
    r"|en \d+ palabras|en \d+ punto|en \d+ paso|limita (la|tu) respuesta"
    r"|solo \d+ punto|maximo \d+ punto|responde (en |con )?(menos|max))\b"
)
_EN_OUTPUT_LIMIT = re.compile(
    r"\b(in less than \d|maximum \d|max\.? \d|no more than \d|briefly|concisely"
    r"|in \d+ words|in \d+ (key )?point|in \d+ step|limit (your|the) (response|answer)"
    r"|only \d+ (point|word|bullet)|keep it (short|brief))\b"
)

# ---------------------------------------------------------------------------
# Patrones ROCKS — audiencia (C) y parámetros clave (K) (Sección 4)
# R y S ya están cubiertos por _ROLE_DEFINED y _FORMAT_SPECIFIED.
# ---------------------------------------------------------------------------

_ES_AUDIENCE = re.compile(
    r"\b(para (estudiantes|principiantes|expertos|desarrolladores|profesionales"
    r"|ninos|adultos|mi equipo|el cliente|ejecutivos|ninos|tecnicos)"
    r"|dirigido a|audiencia (de|objetivo)|publico objetivo"
    r"|nivel (basico|intermedio|avanzado|principiante|experto))\b"
)
_EN_AUDIENCE = re.compile(
    r"\b(for (students|beginners|experts|developers|professionals|children"
    r"|adults|my team|the client|executives|technical))"
    r"|\b(targeted (at|to)|target audience|aimed at"
    r"|skill level|(beginner|intermediate|advanced|expert) level)\b"
)
_ES_KEY_PARAMS = re.compile(
    r"\b(tono (formal|informal|tecnico|simple|amigable|profesional|academico|divulgativo)"
    r"|estilo (formal|informal|divulgativo|tecnico|narrativo|conversacional)"
    r"|de manera (formal|informal|simple|clara|tecnica|didactica)"
    r"|en lenguaje (simple|tecnico|coloquial|formal))\b"
)
_EN_KEY_PARAMS = re.compile(
    r"\b((formal|informal|technical|simple|friendly|professional|academic|conversational)"
    r" (tone|style|voice|language)"
    r"|in a (formal|informal|simple|clear|technical|didactic) (way|manner|tone|style)"
    r"|using (plain|technical|formal|casual) (language|english|words))\b"
)

# ---------------------------------------------------------------------------
# Clasificación de tipo de tarea (Sección 2 — jerarquía de impacto)
# ---------------------------------------------------------------------------

_TASK_FACT_RE = re.compile(
    r"^(es (correcto|verdad|cierto|falso|real)|verdadero o falso|es verdad que"
    r"|is (it |this )?(true|correct|accurate|false|real)|true or false|fact.?check"
    r"|verifica si|confirm (if|whether|that))\b"
)
_TASK_CODE_RE = re.compile(
    r"\b(escribe\b.{0,25}\b(codigo|funcion|clase|script|programa|api|algoritmo)"
    r"|genera\b.{0,25}\b(codigo|funcion|clase|script)"
    r"|generate\b.{0,25}\b(code|function|class|script|program)"
    r"|write\b.{0,25}\b(code|function|class|script|program)"
    r"|implement\b.{0,25}\b(function|class|method|algorithm)"
    r"|implementa\b.{0,25}\b(funcion|clase|metodo|algoritmo)"
    r"|crea\b.{0,25}\b(funcion|clase|script|programa|api)"
    r"|create\b.{0,25}\b(function|class|script|program|api))\b"
)
_TASK_QA_RE = re.compile(
    r"^(que es\b|cuales son\b|como funciona\b|por que\b|cuando\b|quien\b|donde\b|cual es\b"
    r"|what is\b|what are\b|how does\b|why\b|when\b|who\b|where\b|which is\b"
    r"|explain\b|explica\b)\b"
)

_DIRECT_START = re.compile(
    r"^(escribe|explica|resume|analiza|traduce|genera|crea|lista|enumera|compara"
    r"|describe|calcula|extrae|clasifica|define|corrige|mejora|revisa"
    r"|write|explain|summarize|analyze|translate|generate|create|list|compare"
    r"|describe|calculate|extract|classify|fix|improve|review)\b",
)

# ---------------------------------------------------------------------------
# Detección de tipo de output (imagen, documento, artefacto, código)
# ---------------------------------------------------------------------------

_IMAGE_OUTPUT_RE = re.compile(
    r"\b(genera(r)? (una? )?imagen|crea(r)? (una? )?imagen|dibuja(r)?|ilustra(r)?"
    r"|diseña(r)? (una? )?(imagen|ilustracion|grafico|icono|logo|banner|portada)"
    r"|generate (an? )?image|create (an? )?image|draw|illustrate"
    r"|design (an? )?(image|illustration|graphic|icon|logo|banner|cover))\b"
)
_DOCUMENT_OUTPUT_RE = re.compile(
    r"\b(genera(r)? (un? )?(pdf|documento|informe|reporte|presentacion|propuesta)"
    r"|crea(r)? (un? )?(pdf|documento|informe|reporte|presentacion|propuesta)"
    r"|redacta(r)? (un? )?(informe|reporte|memoria|propuesta)"
    r"|generate (a )?(pdf|document|report|presentation|proposal|memo)"
    r"|create (a )?(pdf|document|report|presentation|proposal|memo)"
    r"|write (a )?(report|document|proposal|memo|whitepaper))\b"
)
_ARTIFACT_OUTPUT_RE = re.compile(
    r"\b(hoja de calculo|spreadsheet|excel|genera(r)? (un? )?(csv|json|xml|yaml|archivo)"
    r"|crea(r)? (un? )?(csv|json|xml|yaml|fichero)|generate (a )?(csv|json|xml|spreadsheet|file)"
    r"|create (a )?(csv|json|xml|spreadsheet|file))\b"
)
# Atributos de calidad para prompts de imagen
_IMAGE_STYLE_RE = re.compile(
    r"\b(estilo|style|realista|realistic|fotorrealista|photorealistic|anime|cartoon"
    r"|ilustracion|illustration|oil painting|acuarela|watercolor|digital art"
    r"|3d render|isometric|minimalista|minimalist|abstracto|abstract|pixel art"
    r"|cinematografico|cinematic|hiperrealista|hyperrealistic)\b"
)
_IMAGE_ASPECT_RE = re.compile(
    r"\b(relacion de aspecto|aspect ratio|16:9|9:16|4:3|1:1|cuadrado|square"
    r"|horizontal|vertical|portrait|landscape|\d+x\d+|\d+\s*px|4k|8k|hd)\b"
)
_IMAGE_NEGATIVE_RE = re.compile(
    r"\b(negative prompt|prompt negativo|sin incluir|without|evitar|avoid|excluir|exclude"
    r"|no quiero|i don't want|remove|eliminar de la imagen)\b"
)
_DOC_STRUCTURE_RE = re.compile(
    r"\b(secciones?|sections?|capitulos?|chapters?|paginas?|pages?"
    r"|apartados?|indice|table of contents|resumen ejecutivo|executive summary)\b"
)

# ---------------------------------------------------------------------------
# Imagen: estilos contradictorios (fotorrealista + cartoon/anime, etc.)
# Los modelos de imagen tienen dificultad para combinar estilos opuestos;
# el resultado suele requerir múltiples regeneraciones.
# ---------------------------------------------------------------------------
_IMAGE_STYLE_CONFLICT_RE = re.compile(
    r"(?:fotorrealista|photorealistic|realista\b|realistic\b|hiperrealista|hyperrealistic)"
    r".*?(?:cartoon|anime|ilustracion|illustration|abstracto\b|abstract\b|pixel art|vector\b|flat design)"
    r"|(?:cartoon|anime|ilustracion|illustration|abstracto\b|abstract\b|pixel art|vector\b|flat design)"
    r".*?(?:fotorrealista|photorealistic|realista\b|realistic\b|hiperrealista|hyperrealistic)",
    re.DOTALL,  # IGNORECASE omitted — pattern always applied to normalized (lowercase) text
)

# Imagen: iluminación / mood — ausencia aumenta la tasa de regeneración.
# Los modelos de imagen responden fuertemente a señales de iluminación.
_IMAGE_LIGHTING_RE = re.compile(
    r"\b(golden hour|studio lighting|dramatic shadows?|soft light|hard light"
    r"|backlit|silhouette|natural light|neon light|cinematic lighting|rim light"
    r"|volumetric light|sombras dramaticas|iluminacion de estudio|hora dorada"
    r"|contraluz|luz suave|luz natural|ambiente oscuro|atmosfera|mood\b|lighting\b"
    r"|high.?key|low.?key|chiaroscuro|diffused light|spotlight)\b"
)

# ---------------------------------------------------------------------------
# Código: lenguaje de programación especificado en el prompt.
# Fuente: Anthropic Prompt Engineering Guide (2024) — especificidad.
# ---------------------------------------------------------------------------
_CODE_LANGUAGE_RE = re.compile(
    r"\b(python|javascript|typescript|java\b|c\+\+|csharp|c#\b|golang|go\b|rust\b"
    r"|php\b|ruby\b|swift\b|kotlin|scala|bash\b|shell\b|sql\b|html\b|css\b"
    r"|dart\b|lua\b|haskell|elixir|clojure|r\b|matlab|perl)\b"
)

# Código: presencia de tests / docstrings / documentación mencionada.
_CODE_TESTS_RE = re.compile(
    r"\b(test\b|tests\b|testing|docstring|docstrings|documentacion|documentation"
    r"|comentarios|comments\b|type hints|type annotations|assertions|assert\b"
    r"|unit test|prueba unitaria|cobertura|coverage)\b"
)

# Código: múltiples verbos de acción que indican sobrecarga de tarea.
# Fuente: Anthropic Prompt Engineering Guide (2024) — prompt chaining para tareas complejas.
_CODE_MULTI_VERB_RE = re.compile(
    r"\b(ademas\b|tambien\b|y tambien|adicionalmente|also\b|additionally"
    r"|furthermore|moreover|and also|as well as|on top of that|y ademas"
    r"|igualmente|asimismo|de igual (manera|forma)|likewise)\b"
)

# ---------------------------------------------------------------------------
# Few-shot: el prompt describe un patrón/formato esperado pero NO incluye ejemplo.
# Fuente: DAIR.AI Prompt Engineering Guide — few-shot prompting.
# ---------------------------------------------------------------------------
_PATTERN_WITHOUT_EXAMPLE_RE = re.compile(
    r"\b(como este ejemplo|en el mismo formato que|siguiendo este patron"
    r"|similar a esto|como el siguiente|del mismo estilo que"
    r"|like this example|in the same format as|following this pattern"
    r"|same style as|similar to this|in the same style|as in the example"
    r"|matching this format|as shown below|igual que el ejemplo)\b"
)

# Presencia de ejemplo concreto inline (detecta si ya hay un bloque de muestra).
# Aplicar sobre norm (texto normalizado, ya en minúsculas) — IGNORECASE no necesario.
_EXAMPLE_PRESENT_RE = re.compile(
    r"(input\s*:\s*\S|output\s*:\s*\S|entrada\s*:\s*\S|salida\s*:\s*\S"
    r"|ejemplo\s*:\s*\S|example\s*:\s*\S|\binput\b.*\boutput\b|\bpregunta\b.*\brespuesta\b)",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Chain-of-thought: indicación explícita de razonamiento paso a paso ya presente.
# Fuente: Anthropic Prompt Engineering Guide (2024) — extended thinking;
# OpenAI Best Practices (2024) — chain-of-thought prompting.
# ---------------------------------------------------------------------------
_COT_PRESENT_RE = re.compile(
    r"\b(paso a paso|step by step|think step|piensa antes|razona antes"
    r"|razona primero|think before|reason through|let'?s think"
    r"|pensemos|primero analiza|first analyze|think it through"
    r"|before (answering|responding)|antes de responder|piensa en voz alta"
    r"|show (your|the) (reasoning|work|steps)|muestra tu razonamiento)\b"
)

# ---------------------------------------------------------------------------
# Multi-documento: señales de contexto extenso o estructurado en múltiples bloques.
# Fuente: Liu et al. (2023) "Lost in the Middle" — degradación en contextos largos.
# ---------------------------------------------------------------------------
_MULTI_DOC_TAGS_RE = re.compile(
    r"<document\b|<context\b|<doc\b|<texto\b|<article\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Positive aspects: XML tags estructurales y ejemplos concretos inline.
# Fuente: Anthropic Prompt Engineering Guide (2024) — XML structuring;
# DAIR.AI Prompt Engineering Guide — few-shot prompting.
# ---------------------------------------------------------------------------
_XML_STRUCTURAL_TAGS_RE = re.compile(
    r"<[a-zA-Z][a-zA-Z0-9_-]*>[\s\S]*?</[a-zA-Z][a-zA-Z0-9_-]*>"
)
_INLINE_EXAMPLE_RE = re.compile(
    r"\b(por ejemplo\s*:|for example\s*:|e\.g\.\s*:)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Redirección a herramienta más eficiente (tool routing)
# Consultas que una app especializada resuelve con menor energía y mayor precisión.
# Referencia: Luccioni et al. (2023) — coste energético de inferencia vs. búsqueda
# indexada (~0.0003 Wh/búsqueda vs. ~0.001–0.01 Wh/consulta LLM).
# ---------------------------------------------------------------------------

# Tipos de lugar/negocio local (ES + EN normalizados)
_LOCAL_PLACE_TYPE_RE = re.compile(
    r"\b(restaurantes?|bares?|cafeterias?|cafes?|bistros?|tabernas?|bodegas?|tapas?"
    r"|heladerias?|panaderias?|pastelerias?|pizzerias?"
    r"|tiendas?|farmacias?|hospitales?|hoteles?|hostales?|alojamientos?"
    r"|gasolineras?|supermercados?|hipermercados?|bancos?|cajeros? automaticos?"
    r"|gimnasios?|peluquerias?|barberias?|clinicas?|dentistas?"
    r"|discotecas?|clubs?|pubs?"
    r"|museos?|parques?|playas?|monumentos?|iglesias?|catedrales?"
    r"|restaurants?|bars?|cafes?|coffee shops?|taverns?"
    r"|pharmacies?|hospitals?|hotels?|hostels?|accommodations?"
    r"|gas stations?|supermarkets?|banks?|atms?|gyms?|salons?|barbershops?"
    r"|clinics?|dentists?|museums?|parks?|beaches?|monuments?|churches?)\b"
)

# Señal de ubicación geográfica
_LOCATION_SIGNAL_RE = re.compile(
    r"\bcerca (de|del|de la|de los|de las)\b"
    r"|\ben [a-z]{3,}\b"
    r"|\bpor (el centro|el barrio|la zona|mi zona|mi barrio)\b"
    r"|\ben mi (zona|barrio|ciudad|area|pueblo)\b"
    r"|\bnear(by)?\b|\bclose to\b|\baround\b"
    r"|\bin [a-z]{3,}\b"
    r"|\bin my (area|neighborhood|district|city|town)\b"
)

# Intención de búsqueda local explícita
_SEARCH_INTENT_RE = re.compile(
    r"\b(dime|busca|encuentra|recomienda(me)?|dame|hay\b|cuales (son|hay)|donde (hay|estan|puedo encontrar)"
    r"|tell me|find|recommend|give me|are there|which|where (are|is|can i find))\b"
)

# Criterios de calidad vagos aplicados a lugares/productos
# Captura el término exacto para incluirlo en la sugerencia personalizada
_VAGUE_QUALITY_PLACE_RE = re.compile(
    r"\b(buenos?|buenas?|buen\b|buena\b"
    r"|bonitos?|bonitas?\b"
    r"|baratos?|baratas?\b"
    r"|caros?|caras?\b"
    r"|populares?\b"
    r"|famosos?|famosas?\b"
    r"|recomendables?\b"
    r"|tipicos?|tipicas?\b"
    r"|modernos?|modernas?\b"
    r"|autenticos?|autenticas?\b"
    r"|romanticos?|romanticas?\b"
    r"|tranquilos?|tranquilas?\b"
    r"|animados?|animadas?\b"
    r"|de moda\b"
    r"|good\b|great\b|nice\b|cheap\b|affordable\b|popular\b|famous\b"
    r"|recommended\b|typical\b|modern\b|authentic\b|romantic\b"
    r"|quiet\b|lively\b|trendy\b|well.?rated|highly.?rated|top.?rated)\b"
)

# Proximidad vaga sin radio concreto
_VAGUE_PROXIMITY_RE = re.compile(
    r"\bcerca (de|del|de la)\b|\bnearby\b|\bclose to\b|\baround\b|\bproximo (a|al)\b"
)
_CONCRETE_DISTANCE_RE = re.compile(
    r"\b(\d+\s*(km|kms|kilometros|metros?|miles?|minutes? walk|min(uto)?s? (a pie|caminando|en coche|en metro)))\b"
    r"|\b(a pie|walking distance|caminando)\b"
)

# Información en tiempo real (mejor con apps dedicadas)
_REALTIME_RE = re.compile(
    r"\b(tiempo (que hace|atmosferico|va a hacer|hara)"
    r"|que tiempo (va a hacer|hara|hace) (manana|hoy|esta semana|en)"
    r"|clima (de|en|actual)"
    r"|temperatura (actual|de hoy|ahora|en)"
    r"|va a llover|va a nevar|llover(a|ia)\b"
    r"|partidos? de (hoy|esta noche|este fin de semana)"
    r"|resultados? (del?|de) (partido|juego)"
    r"|precio (actual|de hoy|ahora mismo) (de|del)|cotizacion (actual|de)"
    r"|noticias (de hoy|actuales|recientes|de ultima hora)"
    r"|vuelos? disponibles?|precio(s)? de vuelos?"
    r"|hora (actual|en)|que hora (es|son) (en|ahora)"
    r"|cuando (sale|llega|pasa) (el |la )?(proximo|siguiente)? ?(tren|bus|metro|avion|cercanias)"
    r"|weather (today|now|right now|forecast|in|tomorrow)\b|current (weather|temperature)\b"
    r"|will it rain|will it snow|is it (raining|snowing)\b"
    r"|today.?s? (game|score|match|result)|sports (results?|scores?)\b"
    r"|current (price|stock|rate) of\b|stock (price|market)\b"
    r"|(latest|breaking|current|today.?s?) news\b"
    r"|available flights?\b|cheap(est)? flights?\b|flight (schedule|status|prices?)\b"
    r"|current time in\b|(next|upcoming) (train|bus|metro|flight|plane)\b)\b"
)

# Rutas y direcciones
_DIRECTIONS_RE = re.compile(
    r"\bcomo (se llega|llego|llegar) (a|al|desde|hasta)\b"
    r"|\bruta (de|a|hacia|desde|hasta|mas (corta|rapida|directa))\b"
    r"|\bcuanto (tardo|se tarda|tarda) en llegar\b"
    r"|\bque (bus|metro|linea|tren|cercanias|tranvia) (coge|va|lleva|me lleva) (a|hasta|al)\b"
    r"|\bcomo (ir|llegar) (a|al|desde|hasta)\b"
    r"|\bhay (bus|metro|tren) (a|al|hasta|que va)\b"
    r"|\bhow (to get|do i get|can i get) (to|from)\b"
    r"|\bdirections? (to|from)\b"
    r"|\broute (to|from|between)\b"
    r"|\bhow long (to get to|to travel to|does it take to reach)\b"
    r"|\bwhich (bus|train|metro|subway|tram) (goes|takes me|gets me) to\b"
)

# ---------------------------------------------------------------------------
# Consultas personales genéricas — marcadores de primera persona y dominios
# ---------------------------------------------------------------------------

_PERSONAL_ES = re.compile(
    r"\bque (tengo que|debo|deberia|puedo|me conviene|necesito) (tener|saber|tomar|hacer|comer|entrenar|invertir|ahorrar|comprar|estudiar|seguir|llevar)\b"
    r"|\bque tengo que tener\b"
    r"|\bcual es (mi|el mio|la mia)\b"
    r"|\bcuales son (mis|los mios|las mias)\b"
    r"|\bpara mi\b"
    r"|\ben mi caso\b"
    r"|\bmi (nivel|valor|resultado|colesterol|glucosa|tension|peso|talla|imc|dosis|rango)\b"
    r"|\bes (bueno|malo|normal|adecuado|recomendable|ideal) para mi\b"
    r"|\b(deberia|podria|tengo que) (yo )?(tomar|hacer|comer|entrenar|invertir|ahorrar|comprar|estudiar)\b"
    r"|\bcuanto (debo|deberia|puedo|tengo que) (comer|tomar|ahorrar|invertir|ganar|pesar)\b"
)

_PERSONAL_EN = re.compile(
    r"\bshould i\b"
    r"|\bwhat should i\b"
    r"|\bhow much should i\b"
    r"|\bwhat (is|are) (my|the right|the ideal|a good|a normal|the recommended)\b"
    r"|\bfor me\b"
    r"|\bin my case\b"
    r"|\bmy (level|value|result|cholesterol|glucose|blood pressure|weight|height|bmi|dosage|range)\b"
    r"|\bis (it |this )?(good|bad|normal|ok|okay|safe|recommended) for me\b"
    r"|\bi (should|could|might) (take|eat|exercise|invest|save|buy|study)\b"
    r"|\bhow (many|much) (should|do) i\b"
)

# ---------------------------------------------------------------------------
# Revisión vaga sin especificación de qué mejorar
# Fuente: "Designers hit Claude's usage limits faster than anyone" (2026) — lazy prompting.
# ---------------------------------------------------------------------------
_VAGUE_REVISION_ES = re.compile(
    r"\b(hazlo (mejor|mas bonito|mas chulo|mas profesional|diferente|mas limpio|mas claro))"
    r"|\bmejoralo\b|\barreglalo\b|\bcambialo\b"
    r"|\bque (quede|se vea) (mejor|mas bonito|mas limpio|mas profesional)\b"
    r"|\b(queda|se ve|esta) (raro|mal|feo|horrible)\b"
    r"|\ble (falta|hace falta) (algo|vida|dinamismo|energia)\b"
    r"|\bno me (convence|gusta|mola)\b"
    r"|\bpodria (estar|quedar|verse|ser) (mejor|mas claro|mas limpio|mas profesional)\b"
)
_VAGUE_REVISION_EN = re.compile(
    r"\b(make it (better|nicer|cleaner|prettier|more professional|different|look better))"
    r"|\bimprove (it|this)\b"
    r"|\bfix (it|this)\b"
    r"|\bchange (it|this)\b"
    r"|\b(looks?|seems?) (weird|bad|off|wrong|messy|boring|flat)\b"
    r"|\bit('?s| is) (missing something|not quite right|off|lacking|not good enough)\b"
    r"|\bcould (look|be) (better|cleaner|clearer|more polished|nicer)\b"
    r"|\bi don'?t (like|love) (it|this)\b"
)

# ---------------------------------------------------------------------------
# Delegación de estrategia al modelo (outsourcing thinking)
# El modelo no conoce usuarios ni restricciones del proyecto; preguntar sin contexto
# produce opciones genéricas que requieren múltiples rondas de aclaración.
# Fuente: "Designers hit Claude's usage limits faster than anyone" (2026).
# ---------------------------------------------------------------------------
_OUTSOURCE_THINKING_ES = re.compile(
    r"\b(que (deberia|podria|tendria que) (hacer|usar|elegir|poner|escribir|decir|implementar|crear|construir))\b"
    r"|\b(como (deberia|podria) (enfocarlo|abordarlo|plantearlo|hacerlo|estructurarlo))\b"
    r"|\b(cual (es|seria|podria ser) la mejor (forma|manera|opcion|alternativa|estrategia|estructura) (de|para))\b"
    r"|\b(que (crees|piensas|opinas) que (debo|deberia|podria|seria mejor))\b"
    r"|\ba ver que (me propones|se te ocurre|generas|sugieres)\b"
)
_OUTSOURCE_THINKING_EN = re.compile(
    r"\b(what should i (do|use|choose|write|say|implement|pick|go with|build|create))\b"
    r"|\b(how should i (approach|handle|tackle|do|frame|structure|organize) (this|it))\b"
    r"|\b(what('?s| is) (the )?best (way|approach|option|strategy|structure) (to|for))\b"
    r"|\b(what do you (think|suggest|recommend) (i should|about))\b"
    r"|\b(let'?s see what (you|it) (comes? up with|generates?|suggests?))\b"
)

# ---------------------------------------------------------------------------
# Screenshot mencionado sin contexto de recorte / tamaño
# Una captura completa (1000×1000 px) cuesta ~1 334 tokens vs. ~54 de un recorte
# de 200×200 px — diferencia de 25×.
# Fuente: "Designers hit Claude's usage limits faster than anyone" (2026).
# ---------------------------------------------------------------------------
_SCREENSHOT_MENTION_RE = re.compile(
    r"\b(screenshot|captura (de pantalla|de la pantalla|completa)|pantalla completa"
    r"|full.?page (screenshot|capture)|full screen|capture (of|del|de la) (screen|pantalla)"
    r"|imagen (de la|del) (pantalla|interface|interfaz|diseno)"
    r"|foto (de la|del) (pantalla|diseno|interfaz))\b"
)
_SCREENSHOT_CROP_RE = re.compile(
    r"\b(recorta(do)?|crop(ped)?|solo (el|la|este|esta)|only (the|this)|just (the|this)"
    r"|\d+\s*(px|pixels?|pixeles?)|componente (especifico|concreto)|elemento (especifico|concreto)"
    r"|(zona|area|seccion|parte) (especifica|concreta|del|de la))\b"
)

# ---------------------------------------------------------------------------
# Comentario emocional sin valor para el prompt
# Fuente: "Designers hit Claude's usage limits faster than anyone" (2026) — token burn.
# ---------------------------------------------------------------------------
_SENTIMENT_ES = re.compile(
    r"\b(me (lo paso (muy |super )?bien|encanta|gusta (mucho|un monton)|alegra|divierte|fascina)"
    r"|estoy (muy )?(emocionado|contento|feliz|entusiasmado)"
    r"|que (guay|chulo|cool|pasada|gozada)"
    r"|es (genial|increible|alucinante|chulo|super))\b"
)
_SENTIMENT_EN = re.compile(
    r"\b(i (love|really enjoy|really like) (it|this|using|working with)"
    r"|i'?m (so )?(excited|loving it|having (a lot of )?fun)"
    r"|this is (great|awesome|amazing|so cool))\b"
)

# ---------------------------------------------------------------------------
# Petición de ideas vaga sin dominio ni restricciones
# Fuente: "Designers hit Claude's usage limits faster than anyone" (2026) — one-sentence context.
# ---------------------------------------------------------------------------
_VAGUE_IDEAS_ES = re.compile(
    r"\b(dame ideas\b"
    r"|ideas (de|para|sobre)\b"
    r"|que (puedo|podria) (hacer|crear|construir|desarrollar)\b"
    r"|a ver que se (me|te) (ocurre|sale))\b"
)
_VAGUE_IDEAS_EN = re.compile(
    r"\b(give me ideas\b"
    r"|ideas (for|about|on)\b"
    r"|brainstorm( some| ideas)?\b"
    r"|what (can|should|could) i (do|make|build|create)\b)\b"
)


@dataclass
class _PersonalDomain:
    name_es: str
    name_en: str
    triggers: re.Pattern
    missing_context_es: str
    missing_context_en: str
    context_signals: re.Pattern  # si alguna coincide, el contexto ya está presente


_PERSONAL_DOMAINS: list[_PersonalDomain] = [
    _PersonalDomain(
        name_es="salud / analítica",
        name_en="health / lab results",
        triggers=re.compile(
            r"\b(colesterol|trigliceridos|glucosa|tension arterial|hemoglobina"
            r"|ferritina|vitamina d|tiroides|analitica|hdl|ldl|valores normales"
            r"|cholesterol|triglycerides|glucose|blood pressure|hemoglobin|ferritin|thyroid)\b"
        ),
        missing_context_es="edad, sexo/género, enfermedades previas y medicación habitual",
        missing_context_en="age, sex/gender, prior conditions and current medications",
        context_signals=re.compile(
            r"\b(\d{2,3}\s*(anos|years|age)|hombre|mujer|male|female|masculino|femenino"
            r"|diabetes|hipertension|embarazada|pregnant)\b"
        ),
    ),
    _PersonalDomain(
        name_es="nutrición / peso",
        name_en="nutrition / weight",
        triggers=re.compile(
            r"\b(calorias|dieta|macros|proteinas|carbohidratos|adelgazar|engordar|imc"
            r"|peso ideal|bajar de peso|subir de peso|nutricion|plan nutricional"
            r"|calories|diet|macros|protein|carbohydrates|lose weight|gain weight|bmi|ideal weight)\b"
        ),
        missing_context_es="edad, sexo, peso actual, altura, nivel de actividad física y objetivo",
        missing_context_en="age, sex, current weight, height, activity level and goal",
        context_signals=re.compile(
            r"\b(\d{2,3}\s*(kg|lb|kilo|pounds|cm|metros|feet)|sedentari|activ|deport"
            r"|hombre|mujer|male|female|\d{1,3}\s*(anos|years))\b"
        ),
    ),
    _PersonalDomain(
        name_es="ejercicio / fitness",
        name_en="exercise / fitness",
        triggers=re.compile(
            r"\b(entrenar|rutina de ejercicio|gym|gimnasio|ejercicio fisico|cardio"
            r"|hipertrofia|entrenamiento|fuerza muscular"
            r"|workout|exercise routine|strength training|muscle building|training plan)\b"
        ),
        missing_context_es="edad, nivel de forma física actual, objetivo y posibles lesiones",
        missing_context_en="age, current fitness level, goal and any injuries",
        context_signals=re.compile(
            r"\b(\d{1,3}\s*(anos|years)|principiante|intermedio|avanzado|lesion|lesionado"
            r"|beginner|intermediate|advanced|injury|injured)\b"
        ),
    ),
    _PersonalDomain(
        name_es="finanzas personales",
        name_en="personal finance",
        triggers=re.compile(
            r"\b(ahorrar|invertir|hipoteca|prestamo personal|fondo de emergencia"
            r"|plan de ahorro|bolsa de valores|acciones|fondos de inversion|etf|deuda personal"
            r"|save money|invest|mortgage|personal loan|emergency fund|savings plan|stocks|etf|personal debt)\b"
        ),
        missing_context_es="ingresos mensuales, gastos fijos, deudas actuales y horizonte temporal",
        missing_context_en="monthly income, fixed expenses, current debts and time horizon",
        context_signals=re.compile(
            r"\b(\d+\s*(euros?|dolares?|dollars?|\$|€|£)|salario|sueldo|ingresos|income|salary"
            r"|\d+\s*(anos|years)|\d+\s*meses|\d+\s*months)\b"
        ),
    ),
    _PersonalDomain(
        name_es="legal",
        name_en="legal",
        triggers=re.compile(
            r"\b(despido (improcedente|procedente)?|contrato laboral|herencia|divorcio"
            r"|demanda laboral|denuncia penal|baja medica|erte|incapacidad permanente"
            r"|pension de viudedad|wrongful termination|employment contract|inheritance"
            r"|divorce|lawsuit|sick leave|disability benefit|severance pay)\b"
        ),
        missing_context_es="país/comunidad autónoma, tipo de relación laboral o familiar, fechas clave y detalles del caso",
        missing_context_en="country/region, employment or family relationship type, key dates and case details",
        context_signals=re.compile(
            r"\b(espana|madrid|barcelona|cataluna|mexico|colombia|argentina|eeuu|uk"
            r"|spain|france|germany|\d{4}|anos de servicio|years of service"
            r"|tipo de contrato|contract type)\b"
        ),
    ),
    _PersonalDomain(
        name_es="seguros / pensiones",
        name_en="insurance / pensions",
        triggers=re.compile(
            r"\b(seguro de vida|plan de pensiones|pension de jubilacion|seguro medico privado"
            r"|seguro de hogar|seguro del coche|renta vitalicia"
            r"|life insurance|pension plan|retirement plan|private health insurance|home insurance|annuity)\b"
        ),
        missing_context_es="edad, situación familiar (hijos, dependientes), ingresos y horizonte de jubilación",
        missing_context_en="age, family situation (children, dependents), income and retirement horizon",
        context_signals=re.compile(
            r"\b(\d{1,3}\s*(anos|years)|hijos|dependientes|children|dependents"
            r"|\d+\s*(euros?|dolares?|\$|€)|casado|soltero|married|single)\b"
        ),
    ),
    _PersonalDomain(
        name_es="psicología / salud mental",
        name_en="psychology / mental health",
        triggers=re.compile(
            r"\b(ansiedad|depresion|estres cronico|terapia psicologica|psicologo|burnout"
            r"|insomnio cronico|ataque de panico|autoestima baja|agotamiento mental"
            r"|anxiety|depression|chronic stress|psychotherapy|psychologist|burnout"
            r"|chronic insomnia|panic attack|low self.esteem|mental exhaustion)\b"
        ),
        missing_context_es="duración de los síntomas, intensidad percibida, historial previo y contexto vital actual",
        missing_context_en="symptom duration, perceived intensity, prior history and current life context",
        context_signals=re.compile(
            r"\b(\d+\s*(semanas|meses|anos|weeks|months|years)|leve|moderado|grave|severo"
            r"|mild|moderate|severe|diagnosticado|diagnosed|tratamiento previo|prior treatment)\b"
        ),
    ),
    _PersonalDomain(
        name_es="medicación",
        name_en="medication",
        triggers=re.compile(
            r"\b(que dosis|cuanta dosis|tomar (esta |la |el )?(pastilla|medicamento|farmaco)"
            r"|interaccion (de |entre )?(medicamentos?|farmacos?)|efectos? secundario"
            r"|antibiotico|antiinflamatorio|omeprazol|ibuprofeno|paracetamol|metformina|estatina"
            r"|what dosage|how much (to take|medication)|drug interaction|side effects?"
            r"|antibiotic|anti.inflammatory|ibuprofen|paracetamol|metformin|statin)\b"
        ),
        missing_context_es="edad, peso, otras medicaciones actuales, condición médica y posibles alergias",
        missing_context_en="age, weight, other current medications, medical condition and possible allergies",
        context_signals=re.compile(
            r"\b(\d{1,3}\s*(anos|years|kg|lb)|\d+\s*mg|\d+\s*ml"
            r"|alergi|allerg|condicion cronica|chronic condition|diagnostico|diagnosis)\b"
        ),
    ),
    _PersonalDomain(
        name_es="educación / carrera",
        name_en="education / career",
        triggers=re.compile(
            r"\b(que (carrera|master|estudios|ciclo|fp) (estudiar|elegir|hacer|recomiendas?)"
            r"|oposicion (a |de )?[a-z]+"
            r"|cambio de (trabajo|carrera profesional)"
            r"|which (degree|master|course|program) (should i (study|choose)|do you recommend)"
            r"|career change|job change)\b"
        ),
        missing_context_es="nivel académico actual, tiempo disponible, objetivo profesional y experiencia previa",
        missing_context_en="current academic level, available time, professional goal and prior experience",
        context_signals=re.compile(
            r"\b(bachillerato|grado|licenciatura|bachelor|master|phd|doctorado"
            r"|\d+\s*(anos|years) de experiencia|years of experience"
            r"|sin experiencia|no experience|entry.level"
            r"|horas (a la semana|semanales)|hours (per week|a week))\b"
        ),
    ),
    _PersonalDomain(
        name_es="compras / tecnología",
        name_en="shopping / technology",
        triggers=re.compile(
            r"\b(que (movil|portatil|camara|television|ordenador|tablet|auriculares|smartwatch)"
            r"|mejor (movil|portatil|camara|television|ordenador|tablet|auriculares)"
            r"|which (phone|laptop|camera|tv|computer|tablet|headphones|smartwatch)"
            r"|best (phone|laptop|camera|tv|computer|tablet|headphones))\b"
        ),
        missing_context_es="presupuesto, uso principal, preferencias y requisitos de compatibilidad",
        missing_context_en="budget, primary use case, preferences and compatibility requirements",
        context_signals=re.compile(
            r"\b(\d+\s*(euros?|dolares?|dollars?|\$|€|£)|presupuesto|budget"
            r"|gaming|trabajo|work|fotografia|photography|viaje|travel|uso profesional|professional use)\b"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Suggestion:
    category: str
    description: str
    example: Optional[str] = None
    savings_estimate: Optional[str] = None
    source: Optional[str] = None   # referencia bibliográfica (visible con --verbose)


@dataclass
class ModelRecommendation:
    tier: str
    headline: str
    reason: str
    signals: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Análisis de redacción
# ---------------------------------------------------------------------------

def analyze(text: str, lang: Lang = Lang.ES, output_type: str = "text") -> list[Suggestion]:
    """
    Analiza el prompt y devuelve sugerencias de mejora.
    Usa los patrones del idioma indicado para detectar problemas.
    """
    suggestions: list[Suggestion] = []
    words = text.split()
    norm = _normalize_for_match(text)

    # Selección de patrones según idioma
    filler_re  = _ES_FILLER   if lang == Lang.ES else _EN_FILLER
    vague_pats = _ES_VAGUE    if lang == Lang.ES else _EN_VAGUE
    intro_pats = _ES_INTRO    if lang == Lang.ES else _EN_INTRO
    fmt_words  = _ES_FORMAT   if lang == Lang.ES else _EN_FORMAT
    ex_re      = _ES_EXAMPLES if lang == Lang.ES else _EN_EXAMPLES

    # 1. Frases de cortesía / relleno
    # Eliminar cortesías no mejora la comprensión del modelo pero sí reduce tokens.
    # Anthropic Prompt Engineering Guide (2024): instrucciones directas producen
    # resultados equivalentes o mejores con menos tokens.
    if filler_re.search(norm):
        suggestions.append(Suggestion(
            category="Frases de cortesía" if lang == Lang.ES else "Courtesy phrases",
            description=(
                "Los modelos no necesitan cortesías — eliminan tokens sin aportar contexto."
                if lang == Lang.ES else
                "Models don't need courtesy phrases — they burn tokens without adding context."
            ),
            example=(
                '"Por favor, ¿podrías explicarme…?" → "Explica…"' if lang == Lang.ES
                else '"Could you please explain…?" → "Explain…"'
            ),
            savings_estimate=(
                "~5–15% menos tokens" if lang == Lang.ES else "~5–15% fewer tokens"
            ),
            source="Anthropic Prompt Engineering Guide (2024)",
        ))

    # 2. Frases repetidas
    # Coste directo medible: cada token duplicado es un token de más sin valor añadido.
    sentences = re.split(r"[.!?]\s+", text)
    if len(sentences) > 2:
        seen: set[str] = set()
        duplicate_count = 0
        for s in sentences:
            norm_s = re.sub(r"\s+", " ", s.lower().strip())
            if len(norm_s) > 5:
                if norm_s in seen:
                    duplicate_count += 1
                seen.add(norm_s)
        if duplicate_count > 0:
            suggestions.append(Suggestion(
                category="Frases repetidas" if lang == Lang.ES else "Repeated sentences",
                description=(
                    f"Se detectaron {duplicate_count} frases con contenido muy similar. Consolida la idea en una sola vez."
                    if lang == Lang.ES else
                    f"{duplicate_count} sentences with very similar content detected. Consolidate the idea into one."
                ),
                savings_estimate=(
                    "~5–20% menos tokens" if lang == Lang.ES else "~5–20% fewer tokens"
                ),
                source="Principio de economía de tokens (medición directa)",
            ))

    # 3. Introducción innecesaria
    # Los modelos no tienen estado social; saludos y presentaciones no aportan contexto
    # relevante para la tarea. Referencia: Anthropic Prompt Engineering Guide (2024).
    for pat in intro_pats:
        if pat.search(norm):
            suggestions.append(Suggestion(
                category="Introducción innecesaria" if lang == Lang.ES else "Unnecessary introduction",
                description=(
                    "Salta directo a la instrucción — el modelo no necesita saludos ni presentaciones."
                    if lang == Lang.ES else
                    "Go straight to the instruction — the model doesn't need greetings or introductions."
                ),
                example=(
                    '"Hola, soy diseñadora y quiero que me ayudes con…" → "Ayúdame con…"' if lang == Lang.ES
                    else '"Hi, I\'m a developer and I was wondering if you could help me with…" → "Help me with…"'
                ),
                savings_estimate=(
                    "~5–10% menos tokens" if lang == Lang.ES else "~5–10% fewer tokens"
                ),
                source="Anthropic Prompt Engineering Guide (2024)",
            ))
            break

    # 4. Prompt muy largo sin estructura
    # Liu et al. (2023) "Lost in the Middle" demuestra que los modelos retienen peor
    # la información situada en el centro de contextos largos sin estructura.
    if len(words) > 150 and "\n" not in text and "###" not in text and "-" not in text[:200]:
        suggestions.append(Suggestion(
            category="Falta de estructura" if lang == Lang.ES else "Lacks structure",
            description=(
                "Prompts largos sin formato (viñetas, secciones) suelen ser más verbosos. Separa contexto, tarea y formato esperado."
                if lang == Lang.ES else
                "Long unformatted prompts tend to be verbose. Separate context, task and expected format."
            ),
            example=(
                "### Contexto\n...\n### Tarea\n...\n### Formato\n..."
                if lang == Lang.ES else
                "### Context\n...\n### Task\n...\n### Format\n..."
            ),
            savings_estimate=(
                "Puede reducir el prompt un 20–30% y mejorar la respuesta"
                if lang == Lang.ES else
                "Can reduce the prompt by 20–30% and improve the response"
            ),
            source='Liu et al. (2023) "Lost in the Middle: How LMs Use Long Contexts"',
        ))

    # 5. Demasiados ejemplos
    # Min et al. (2022) muestran que el efecto de los ejemplos se satura con 1–2;
    # añadir más no mejora el rendimiento y puede introducir sesgo (Zhao et al., 2021).
    example_count = len(ex_re.findall(norm))
    if example_count > 3:
        suggestions.append(Suggestion(
            category="Demasiados ejemplos" if lang == Lang.ES else "Too many examples",
            description=(
                f"Se encontraron {example_count} referencias a ejemplos. Limita a 1–2 ejemplos concretos; más no mejora la respuesta."
                if lang == Lang.ES else
                f"{example_count} example references found. Limit to 1–2 concrete examples; more doesn't improve the response."
            ),
            savings_estimate=(
                "~10–25% menos tokens" if lang == Lang.ES else "~10–25% fewer tokens"
            ),
            source='Min et al. (2022) "Rethinking the Role of Demonstrations"; Zhao et al. (2021) "Calibrate Before Use"',
        ))

    # 6. Prompt muy corto — sugerencia específica por tipo de output
    # Heurística establecida en guías de prompt engineering: prompts sin contexto
    # suficiente producen respuestas genéricas que requieren turnos de aclaración,
    # aumentando el coste total de la conversación.
    # La sugerencia indica exactamente qué añadir según el tipo de output esperado.
    if len(words) < 10:
        hint_es, hint_en = _SHORT_PROMPT_HINTS.get(output_type, _SHORT_PROMPT_HINTS["text"])
        suggestions.append(Suggestion(
            category="Prompt muy corto" if lang == Lang.ES else "Prompt too short",
            description=(
                f"Un prompt muy breve genera respuestas genéricas que requieren más turnos. {hint_es}"
                if lang == Lang.ES else
                f"A very short prompt generates generic responses that require more turns. {hint_en}"
            ),
            savings_estimate=(
                "Puede evitar 2–3 rondas extra de preguntas"
                if lang == Lang.ES else
                "Can avoid 2–3 extra clarification rounds"
            ),
            source="OpenAI Best Practices (2024); Anthropic Prompt Engineering Guide (2024)",
        ))

    # 7. Lenguaje vago / hedging
    # Webson & Pavlick (2021) demuestran que prompts con instrucciones ambiguas
    # producen outputs impredecibles. La vaguedad fuerza al modelo a asumir
    # o solicitar aclaraciones, incrementando el número de turnos.
    vague_found = sum(1 for p in vague_pats if p.search(norm))
    if vague_found >= 2:
        suggestions.append(Suggestion(
            category="Lenguaje impreciso" if lang == Lang.ES else "Vague language",
            description=(
                "Expresiones vagas ('más o menos', 'algo así') obligan al modelo a pedir aclaraciones o a asumir. Sé específico."
                if lang == Lang.ES else
                "Vague expressions ('kind of', 'something like') force the model to ask for clarification or guess. Be specific."
            ),
            example=(
                '"Quiero algo así como una lista, más o menos" → "Devuelve una lista con viñetas"' if lang == Lang.ES
                else '"Something like a list, kind of" → "Return a numbered list"'
            ),
            savings_estimate=(
                "Reduce turnos de aclaración" if lang == Lang.ES else "Reduces clarification turns"
            ),
            source='Webson & Pavlick (2021) "Do Prompt-Based Models Really Understand the Meaning of Their Prompts?"',
        ))

    # 8. Formato de salida no especificado (solo aplica a output de texto)
    # Especificar el formato reduce la longitud de la respuesta al eliminar
    # introducciones, transiciones y conclusiones que el modelo añade por defecto.
    # Referencia: Sclar et al. (2023) cuantifican la sensibilidad de los LLMs
    # al formato del prompt; Anthropic reporta reducción de 10–30% en tokens de salida.
    if output_type == "text" and len(words) > 50 and not any(f in norm for f in fmt_words):
        suggestions.append(Suggestion(
            category="Formato de salida no indicado" if lang == Lang.ES else "Output format not specified",
            description=(
                "Especificar el formato evita que el modelo genere texto extra (introducciones, conclusiones innecesarias)."
                if lang == Lang.ES else
                "Specifying the format prevents the model from generating extra text (unnecessary introductions, conclusions)."
            ),
            example=(
                'Añade al final: "Responde en forma de lista numerada, sin introducción."' if lang == Lang.ES
                else 'Add at the end: "Respond as a numbered list, no introduction."'
            ),
            savings_estimate=(
                "~10–30% menos tokens de salida" if lang == Lang.ES else "~10–30% fewer output tokens"
            ),
            source='Sclar et al. (2023) "Quantifying Sensitivity to Spurious Features in NLP"; Anthropic Prompt Engineering Guide (2024)',
        ))

    # 10. Verbo de alta energía (no aplica a outputs no textuales donde el verbo es estructural)
    # La jerarquía de impacto por verbo muestra que tareas como "Analizar" consumen
    # hasta 2.5× más energía que "Resumir". Cambiar el verbo es la optimización más
    # barata (coste cero) con mayor impacto en tokens de salida.
    # Fuente: Luccioni et al. (2023); doc de referencia eco-ai Sección 3.
    # Para imagen, pdf, artefacto y código el verbo ("crea", "genera", "escribe") es
    # inherente al tipo de tarea — no tiene alternativa semántica válida.
    verb_match = None if output_type in ("image", "pdf", "artifact", "code") else _VERB_DETECT_RE.match(norm.lstrip())
    if verb_match:
        detected = verb_match.group(1)
        if detected in _VERB_ENERGY:
            level, wh, alt_es, alt_en = _VERB_ENERGY[detected]
            if level in ("very_high", "high") and (alt_es or alt_en):
                alts = alt_es if lang == Lang.ES else alt_en
                alt_str = " o ".join(f'"{a}"' for a in alts) if lang == Lang.ES else " or ".join(f'"{a}"' for a in alts)
                suggestions.append(Suggestion(
                    category="Verbo de alta energía" if lang == Lang.ES else "High-energy verb",
                    description=(
                        f'El verbo "{detected}" genera respuestas largas (~{wh} Wh por respuesta). '
                        f'Considera sustituirlo por {alt_str} para reducir la longitud de salida.'
                        if lang == Lang.ES else
                        f'The verb "{detected}" generates long responses (~{wh} Wh per response). '
                        f'Consider replacing it with {alt_str} to reduce output length.'
                    ),
                    example=(
                        f'"{detected.capitalize()} el proceso de fotosíntesis" → "Lista los pasos de la fotosíntesis"'
                        if lang == Lang.ES else
                        f'"{detected.capitalize()} photosynthesis" → "List the steps of photosynthesis"'
                    ),
                    savings_estimate=(
                        "Cambiar a 'resume/lista' puede ahorrar hasta 60% de tokens de salida"
                        if lang == Lang.ES else
                        "Switching to 'summarize/list' can save up to 60% of output tokens"
                    ),
                    source="Luccioni et al. (2023) — jerarquía de impacto por tipo de tarea; valores Wh por verbo",
                ))

    # 11. Sin restricción de longitud de salida (Green Prompting — solo texto)
    # Forzar al modelo a limitar la extensión de la respuesta es la técnica de mayor
    # ROI energético: elimina tokens de introducción, relleno y conclusiones sin pérdida
    # de información esencial.
    # Para outputs no textuales (imagen, PDF, artefacto, código) no aplica porque
    # la "longitud" viene determinada por el tipo de output, no por palabras.
    # Fuente: Green Prompting methodology; Sclar et al. (2023).
    output_limit_re = _ES_OUTPUT_LIMIT if lang == Lang.ES else _EN_OUTPUT_LIMIT
    if output_type == "text" and len(words) > 30 and not output_limit_re.search(norm):
        suggestions.append(Suggestion(
            category="Sin límite de longitud de salida" if lang == Lang.ES else "No output length limit",
            description=(
                "Añadir un límite explícito de palabras o puntos obliga al modelo a "
                "ser conciso, eliminando introducciones y relleno innecesarios."
                if lang == Lang.ES else
                "Adding an explicit word or point limit forces the model to be concise, "
                "eliminating unnecessary introductions and filler."
            ),
            example=(
                '"Responde en menos de 150 palabras" / "Máximo 3 puntos clave" / "En una sola oración"'
                if lang == Lang.ES else
                '"Answer in less than 150 words" / "Maximum 3 key points" / "In one sentence"'
            ),
            savings_estimate=(
                "~30–50% menos tokens de salida"
                if lang == Lang.ES else
                "~30–50% fewer output tokens"
            ),
            source="Green Prompting methodology; Sclar et al. (2023) — sensibilidad a formato; Luccioni et al. (2023)",
        ))

    # 12. Estructura ROCKS incompleta (para prompts complejos sin meta-información)
    # El método ROCKS (Role, Objective, Community, Key, Shape) reduce el número de
    # intentos para obtener una respuesta útil, ahorrando iteraciones completas.
    # Fuente: metodología ROCKS — Green Prompting (doc de referencia eco-ai, Sección 4).
    if len(words) > 60:
        audience_re = _ES_AUDIENCE if lang == Lang.ES else _EN_AUDIENCE
        key_re = _ES_KEY_PARAMS if lang == Lang.ES else _EN_KEY_PARAMS
        rocks_missing: list[str] = []
        if not _ROLE_DEFINED.search(norm):
            rocks_missing.append("R — rol del modelo" if lang == Lang.ES else "R — model role")
        if not audience_re.search(norm):
            rocks_missing.append("C — audiencia o nivel" if lang == Lang.ES else "C — audience or level")
        if not key_re.search(norm):
            rocks_missing.append("K — tono o estilo" if lang == Lang.ES else "K — tone or style")
        if len(rocks_missing) >= 2:
            missing_str = ", ".join(rocks_missing)
            suggestions.append(Suggestion(
                category="Estructura ROCKS incompleta" if lang == Lang.ES else "Incomplete ROCKS structure",
                description=(
                    f"El método ROCKS minimiza las iteraciones de prueba y error. Faltan: {missing_str}."
                    if lang == Lang.ES else
                    f"The ROCKS method minimizes trial-and-error iterations. Missing: {missing_str}."
                ),
                example=(
                    "R: 'Eres un experto en X' · O: objetivo claro · C: 'para estudiantes de Y' · "
                    "K: 'en tono formal' · S: 'en formato tabla'"
                    if lang == Lang.ES else
                    "R: 'You are an expert in X' · O: clear objective · C: 'for students of Y' · "
                    "K: 'in formal tone' · S: 'in table format'"
                ),
                savings_estimate=(
                    "Evita 2–4 rondas de iteración completas"
                    if lang == Lang.ES else
                    "Avoids 2–4 complete iteration rounds"
                ),
                source="Método ROCKS (Role, Objective, Community, Key, Shape) — Green Prompting, Sección 4",
            ))

    # -----------------------------------------------------------------------
    # Sugerencias específicas por tipo de output
    # -----------------------------------------------------------------------

    # 13. Output = imagen — calidad del prompt visual
    if output_type == "image":
        if not _IMAGE_STYLE_RE.search(norm):
            suggestions.append(Suggestion(
                category="Estilo visual no especificado" if lang == Lang.ES else "Visual style not specified",
                description=(
                    "Los modelos de imagen necesitan una referencia estilística para evitar salidas genéricas. "
                    "Especifica el medio o estilo artístico."
                    if lang == Lang.ES else
                    "Image models need a style reference to avoid generic outputs. "
                    "Specify the medium or artistic style."
                ),
                example=(
                    '"estilo fotorrealista" / "ilustración digital" / "acuarela" / "3D render isométrico"'
                    if lang == Lang.ES else
                    '"photorealistic style" / "digital illustration" / "watercolor" / "isometric 3D render"'
                ),
                savings_estimate=(
                    "Reduce iteraciones de regeneración (cada intento ~2–5× más energía que texto)"
                    if lang == Lang.ES else
                    "Reduces regeneration iterations (each attempt ~2–5× more energy than text)"
                ),
                source="Luccioni et al. (2023) — imagen generativa tiene mayor coste energético que texto",
            ))

        if not _IMAGE_ASPECT_RE.search(norm):
            suggestions.append(Suggestion(
                category="Relación de aspecto no indicada" if lang == Lang.ES else "Aspect ratio not specified",
                description=(
                    "Sin relación de aspecto el modelo usa el cuadrado por defecto, "
                    "que puede no ser lo que necesitas."
                    if lang == Lang.ES else
                    "Without an aspect ratio the model defaults to square, "
                    "which may not fit your use case."
                ),
                example=(
                    '"16:9 (horizontal)" / "9:16 (vertical/móvil)" / "1:1 (cuadrado)"'
                    if lang == Lang.ES else
                    '"16:9 (landscape)" / "9:16 (portrait/mobile)" / "1:1 (square)"'
                ),
                savings_estimate=(
                    "Evita un intento extra solo por recortar la imagen"
                    if lang == Lang.ES else
                    "Avoids a retry just to fix the crop"
                ),
                source="Buenas prácticas de prompt engineering para modelos imagen (DALL·E, Stable Diffusion, Flux)",
            ))

        if not _IMAGE_NEGATIVE_RE.search(norm):
            suggestions.append(Suggestion(
                category="Sin prompt negativo" if lang == Lang.ES else "No negative prompt",
                description=(
                    "Los modelos de imagen atienden a lo que *no* quieres tanto como a lo que sí. "
                    "Añade elementos a excluir para reducir los reintentos."
                    if lang == Lang.ES else
                    "Image models respond to what you *don't* want as much as what you do. "
                    "Add elements to exclude to reduce retries."
                ),
                example=(
                    '"sin texto, sin marcas de agua, sin distorsión de manos"'
                    if lang == Lang.ES else
                    '"no text, no watermarks, no hand distortion"'
                ),
                savings_estimate=(
                    "Puede reducir hasta un 50% los reintentos"
                    if lang == Lang.ES else
                    "Can reduce retries by up to 50%"
                ),
                source="Stable Diffusion / DALL·E best practices; Luccioni et al. (2023)",
            ))

        # 13b. Estilos visuales contradictorios
        # Combinar referencias estilísticas opuestas (fotorrealismo + cartoon) exige
        # varias regeneraciones porque el modelo no puede satisfacer ambas a la vez.
        if _IMAGE_STYLE_CONFLICT_RE.search(norm):
            suggestions.append(Suggestion(
                category="Estilos contradictorios" if lang == Lang.ES else "Contradictory styles",
                description=(
                    "El prompt combina estilos visuales incompatibles (p. ej. fotorrealista + cartoon). "
                    "Los modelos de imagen no pueden satisfacer ambos a la vez; elige un solo estilo."
                    if lang == Lang.ES else
                    "The prompt mixes incompatible visual styles (e.g. photorealistic + cartoon). "
                    "Image models cannot satisfy both at once; choose a single style."
                ),
                example=(
                    '"estilo fotorrealista, iluminación cinematográfica" (un solo estilo coherente)'
                    if lang == Lang.ES else
                    '"photorealistic style, cinematic lighting" (one consistent style)'
                ),
                savings_estimate=(
                    "Evita 2–4 regeneraciones por ambigüedad estilística"
                    if lang == Lang.ES else
                    "Avoids 2–4 regenerations due to style ambiguity"
                ),
                source="Buenas prácticas de prompt engineering para modelos imagen (DALL·E, Stable Diffusion, Flux)",
            ))

        # 13c. Prompt de imagen excesivamente largo (>80 palabras)
        # Los modelos de imagen ponderan más los primeros tokens del prompt;
        # el contenido al final del prompt recibe menos atención.
        # Referencia: arquitectura de atención en modelos de difusión (CLIP encoder).
        if len(words) > 80:
            suggestions.append(Suggestion(
                category="Prompt de imagen demasiado largo" if lang == Lang.ES else "Image prompt too long",
                description=(
                    "Los modelos de imagen leen los primeros tokens con mayor peso. "
                    "Con más de 80 palabras, los elementos del final pueden ignorarse. "
                    "Mueve el sujeto principal y el estilo al principio."
                    if lang == Lang.ES else
                    "Image models weight the first tokens more heavily. "
                    "With more than 80 words, elements at the end may be ignored. "
                    "Move the main subject and style to the beginning."
                ),
                example=(
                    '"[sujeto], [estilo], [iluminación], [detalles secundarios]" — orden de prioridad'
                    if lang == Lang.ES else
                    '"[subject], [style], [lighting], [secondary details]" — priority order'
                ),
                savings_estimate=(
                    "Reduce regeneraciones por elementos ignorados al final"
                    if lang == Lang.ES else
                    "Reduces regenerations caused by elements ignored at the end"
                ),
                source="CLIP token weighting — arquitectura de modelos de difusión (DALL·E, Stable Diffusion)",
            ))

        # 13d. Sin indicación de iluminación / mood
        # La iluminación es uno de los parámetros con mayor impacto visual en modelos
        # de imagen. Su ausencia produce resultados planos que suelen requerir ajuste.
        if not _IMAGE_LIGHTING_RE.search(norm):
            suggestions.append(Suggestion(
                category="Sin indicación de iluminación" if lang == Lang.ES else "No lighting specified",
                description=(
                    "La iluminación determina el mood de la imagen. Sin especificarla, "
                    "el modelo elige una iluminación neutra que puede no encajar con tu visión."
                    if lang == Lang.ES else
                    "Lighting determines the image mood. Without specifying it, "
                    "the model defaults to neutral lighting that may not match your vision."
                ),
                example=(
                    '"golden hour" / "studio lighting" / "dramatic shadows" / "soft natural light"'
                    if lang == Lang.ES else
                    '"golden hour" / "studio lighting" / "dramatic shadows" / "soft natural light"'
                ),
                savings_estimate=(
                    "Evita iteraciones para ajustar el ambiente visual"
                    if lang == Lang.ES else
                    "Avoids iterations to fix the visual atmosphere"
                ),
                source="Buenas prácticas de prompt engineering para modelos imagen (DALL·E, Stable Diffusion, Flux)",
            ))

    # 14. Output = documento/PDF
    elif output_type == "pdf":
        if not _DOC_STRUCTURE_RE.search(norm):
            suggestions.append(Suggestion(
                category="Estructura del documento no definida" if lang == Lang.ES else "Document structure not defined",
                description=(
                    "Sin estructura explícita el modelo genera un único bloque de texto. "
                    "Indica secciones, número de páginas o un índice para obtener un documento usable a la primera."
                    if lang == Lang.ES else
                    "Without explicit structure the model generates a single text block. "
                    "Specify sections, page count or an outline to get a usable document on the first try."
                ),
                example=(
                    '"Incluye: portada, resumen ejecutivo, introducción, 3 secciones temáticas y conclusiones"'
                    if lang == Lang.ES else
                    '"Include: cover page, executive summary, introduction, 3 topic sections and conclusions"'
                ),
                savings_estimate=(
                    "Evita 2–3 rondas de corrección estructural"
                    if lang == Lang.ES else
                    "Avoids 2–3 rounds of structural revision"
                ),
                source="Anthropic Prompt Engineering Guide (2024) — especificidad en tareas de redacción larga",
            ))

    # 15. Output = artefacto (CSV, JSON, spreadsheet…)
    elif output_type == "artifact":
        schema_re = re.compile(r"\b(columnas?|columns?|campos?|fields?|esquema|schema|estructura|structure|formato|format)\b")
        if not schema_re.search(norm):
            suggestions.append(Suggestion(
                category="Esquema del artefacto no especificado" if lang == Lang.ES else "Artifact schema not specified",
                description=(
                    "Para CSV, JSON o spreadsheets, define las columnas/campos esperados. "
                    "Sin esquema el modelo inventa la estructura y suele requerir correcciones."
                    if lang == Lang.ES else
                    "For CSV, JSON or spreadsheets, define the expected columns/fields. "
                    "Without a schema the model invents the structure and corrections are usually needed."
                ),
                example=(
                    '"CSV con columnas: fecha, nombre, importe, categoría"'
                    if lang == Lang.ES else
                    '"CSV with columns: date, name, amount, category"'
                ),
                savings_estimate=(
                    "Evita iterar para corregir la estructura del artefacto"
                    if lang == Lang.ES else
                    "Avoids iterations to fix the artifact structure"
                ),
                source="Principio de especificidad — Anthropic Prompt Engineering Guide (2024)",
            ))

    # 16. Output = código — sugerencias específicas para prompts de programación
    # Fuente: Anthropic Prompt Engineering Guide (2024) — especificidad en tareas de código;
    # prompt chaining para tareas complejas con múltiples funcionalidades.
    elif output_type == "code":
        # 16a. Lenguaje no especificado
        if not _CODE_LANGUAGE_RE.search(norm):
            suggestions.append(Suggestion(
                category="Lenguaje de programación no indicado" if lang == Lang.ES else "Programming language not specified",
                description=(
                    "Sin especificar el lenguaje, el modelo elige por defecto (normalmente Python). "
                    "Indicarlo evita regeneraciones por lenguaje incorrecto."
                    if lang == Lang.ES else
                    "Without a language, the model defaults (usually Python). "
                    "Specifying it avoids regenerations due to the wrong language."
                ),
                example=(
                    '"Escribe en TypeScript una función que…" / "Genera código Python para…"'
                    if lang == Lang.ES else
                    '"Write a TypeScript function that…" / "Generate Python code to…"'
                ),
                savings_estimate=(
                    "Evita 1–2 regeneraciones por lenguaje incorrecto"
                    if lang == Lang.ES else
                    "Avoids 1–2 regenerations for the wrong language"
                ),
                source="Anthropic Prompt Engineering Guide (2024) — especificidad en tareas de código",
            ))

        # 16b. Tests y docstrings no mencionados
        if not _CODE_TESTS_RE.search(norm):
            suggestions.append(Suggestion(
                category="Tests y documentación no especificados" if lang == Lang.ES else "Tests and docs not specified",
                description=(
                    "No se indica si quieres tests unitarios, docstrings o type hints. "
                    "Aclararlo evita una segunda petición para añadir documentación o cobertura."
                    if lang == Lang.ES else
                    "It's not clear whether you want unit tests, docstrings or type hints. "
                    "Specifying this avoids a second request to add documentation or coverage."
                ),
                example=(
                    '"…con docstring, type hints y tests unitarios con pytest"'
                    if lang == Lang.ES else
                    '"…with docstring, type hints and unit tests using pytest"'
                ),
                savings_estimate=(
                    "Evita 1 turno extra para solicitar tests o documentación"
                    if lang == Lang.ES else
                    "Avoids 1 extra turn to request tests or documentation"
                ),
                source="Anthropic Prompt Engineering Guide (2024) — especificidad; OpenAI Best Practices (2024)",
            ))

        # 16c. Múltiples funcionalidades en un solo prompt → prompt chaining
        # Detectar ≥3 señales de verbos de acción/adición sugiere que la tarea
        # podría beneficiarse de ser dividida en pasos secuenciales.
        multi_verb_count = len(_CODE_MULTI_VERB_RE.findall(norm))
        if multi_verb_count >= 2:
            suggestions.append(Suggestion(
                category="Tarea de código demasiado amplia" if lang == Lang.ES else "Code task too broad",
                description=(
                    f"Se detectaron {multi_verb_count + 1} funcionalidades mezcladas en un solo prompt. "
                    "Dividir la tarea en prompts secuenciales (prompt chaining) produce código más limpio "
                    "y es más fácil de depurar."
                    if lang == Lang.ES else
                    f"{multi_verb_count + 1} mixed functionalities detected in a single prompt. "
                    "Splitting into sequential prompts (prompt chaining) produces cleaner code "
                    "and is easier to debug."
                ),
                example=(
                    "1) Crea la función base → 2) Añade validación → 3) Escribe los tests"
                    if lang == Lang.ES else
                    "1) Create the base function → 2) Add validation → 3) Write the tests"
                ),
                savings_estimate=(
                    "Reduce errores de implementación y rondas de corrección"
                    if lang == Lang.ES else
                    "Reduces implementation errors and correction rounds"
                ),
                source="Anthropic Prompt Engineering Guide (2024) — prompt chaining para tareas complejas",
            ))

    # 9. Consulta personal genérica sin contexto suficiente
    # En primera persona sobre salud, finanzas, legal, etc., sin datos personales,
    # los modelos generan respuestas genéricas que requieren turnos extra de aclaración.
    # Referencia: principio de especificidad contextual (Anthropic Prompt Engineering Guide, 2024).
    personal_marker_re = _PERSONAL_ES if lang == Lang.ES else _PERSONAL_EN
    if personal_marker_re.search(norm):
        for domain in _PERSONAL_DOMAINS:
            if domain.triggers.search(norm) and not domain.context_signals.search(norm):
                ctx = domain.missing_context_es if lang == Lang.ES else domain.missing_context_en
                name = domain.name_es if lang == Lang.ES else domain.name_en
                suggestions.append(Suggestion(
                    category=(
                        f"Consulta personal sin contexto ({name})"
                        if lang == Lang.ES
                        else f"Generic personal query ({name})"
                    ),
                    description=(
                        f"Pregunta personal sobre {name} sin datos suficientes para una respuesta precisa. "
                        f"Añade: {ctx}."
                        if lang == Lang.ES
                        else f"Personal query about {name} without enough data for a precise answer. "
                             f"Add: {ctx}."
                    ),
                    savings_estimate=(
                        "Evita respuestas genéricas que requieren 2–3 turnos de aclaración"
                        if lang == Lang.ES
                        else "Avoids generic responses requiring 2–3 clarification turns"
                    ),
                    source="Principio de especificidad contextual — Anthropic Prompt Engineering Guide (2024)",
                ))
                break  # una sugerencia máxima de este tipo por prompt

    # 17. Few-shot: patrón descrito sin ejemplo concreto
    # Si el prompt referencia un patrón o formato esperado pero no incluye un ejemplo
    # de input/output, el modelo tiene que inferir el patrón, lo que eleva la tasa de error.
    # Fuente: DAIR.AI Prompt Engineering Guide — few-shot prompting;
    # Min et al. (2022) — los ejemplos concretos son el signal más fuerte para el formato.
    if _PATTERN_WITHOUT_EXAMPLE_RE.search(norm) and not _EXAMPLE_PRESENT_RE.search(norm):
        suggestions.append(Suggestion(
            category="Patrón sin ejemplo concreto" if lang == Lang.ES else "Pattern without concrete example",
            description=(
                "El prompt describe un patrón o formato pero no incluye un ejemplo de input/output. "
                "Añadir 1–2 ejemplos concretos guía al modelo con precisión."
                if lang == Lang.ES else
                "The prompt describes a pattern or format but includes no input/output example. "
                "Adding 1–2 concrete examples guides the model precisely."
            ),
            example=(
                "Entrada: 'El gato duerme' → Salida: 'The cat sleeps'"
                if lang == Lang.ES else
                "Input: 'The cat sleeps' → Output: 'Der Kater schläft'"
            ),
            savings_estimate=(
                "Reduce errores de formato en un 40–60 % según Min et al. (2022)"
                if lang == Lang.ES else
                "Reduces format errors by 40–60% according to Min et al. (2022)"
            ),
            source="DAIR.AI Prompt Engineering Guide — few-shot prompting; Min et al. (2022)",
        ))

    # 18. Chain-of-thought: tarea de razonamiento sin indicación de paso a paso
    # En tareas analíticas complejas, pedir al modelo que razone explícitamente antes
    # de responder reduce errores sin coste significativo de tokens de input.
    # Fuente: Anthropic Prompt Engineering Guide (2024) — extended thinking;
    # OpenAI Best Practices (2024) — chain-of-thought prompting.
    if _REASONING.search(norm) and not _COT_PRESENT_RE.search(norm):
        suggestions.append(Suggestion(
            category="Sin indicación de razonamiento explícito" if lang == Lang.ES else "No explicit reasoning instruction",
            description=(
                "El prompt requiere razonamiento complejo pero no pide al modelo que piense paso a paso. "
                "Añadir esta instrucción reduce errores analíticos sin coste relevante de tokens."
                if lang == Lang.ES else
                "The prompt requires complex reasoning but doesn't ask the model to think step by step. "
                "Adding this instruction reduces analytical errors without significant token cost."
            ),
            example=(
                '"Piensa paso a paso antes de responder." / "Razona en voz alta y luego da la conclusión."'
                if lang == Lang.ES else
                '"Think step by step before answering." / "Reason through it, then give your conclusion."'
            ),
            savings_estimate=(
                "Reduce errores en tareas de razonamiento; coste: ~5–10 tokens extra de input"
                if lang == Lang.ES else
                "Reduces reasoning errors; cost: ~5–10 extra input tokens"
            ),
            source=(
                "Anthropic Prompt Engineering Guide (2024) — extended thinking; "
                "OpenAI Best Practices (2024) — chain-of-thought prompting"
            ),
        ))

    # -----------------------------------------------------------------------
    # Checks de routing — herramienta especializada vs. LLM
    # -----------------------------------------------------------------------

    # 19. Búsqueda local de lugares — herramienta más eficiente disponible
    # Restaurantes, hoteles, tiendas y servicios cerca de una ubicación se resuelven
    # mejor con Google Maps/TripAdvisor: datos en tiempo real, horarios actualizados,
    # fotos y valoraciones verificadas, con un coste energético ~100–200× menor.
    # Fuente: Luccioni et al. (2023) — inferencia LLM vs. búsqueda indexada.
    place_match = _LOCAL_PLACE_TYPE_RE.search(norm)
    has_location = _LOCATION_SIGNAL_RE.search(norm)
    has_search_intent = _SEARCH_INTENT_RE.search(norm)
    quality_match = _VAGUE_QUALITY_PLACE_RE.search(norm)

    if place_match and (has_location or has_search_intent):
        place_term = place_match.group(0)
        if quality_match:
            vague_term = quality_match.group(0)
            suggestions.append(Suggestion(
                category=(
                    "Herramienta más eficiente disponible"
                    if lang == Lang.ES else
                    "More efficient tool available"
                ),
                description=(
                    f'Tu prompt busca {place_term} con el criterio "{vague_term}", que es subjetivo. '
                    f'Google Maps o TripAdvisor resuelven esto con datos en tiempo real y valoraciones '
                    f'verificadas, con ~100–200× menos energía que un LLM. '
                    f'Si prefieres usar IA, define qué significa "{vague_term}" para ti: '
                    f'tipo de cocina/producto, rango de precio (€/€€/€€€), ocasión (romántico, '
                    f'familiar, negocios), valoración mínima (p. ej. >4★).'
                    if lang == Lang.ES else
                    f'Your prompt searches for {place_term} using the criterion "{vague_term}", which is subjective. '
                    f'Google Maps or TripAdvisor handle this with real-time data and verified reviews, '
                    f'using ~100–200× less energy than an LLM. '
                    f'If you prefer AI, define what "{vague_term}" means to you: '
                    f'cuisine/product type, price range ($/$$/$$$), occasion (romantic, '
                    f'family, business), minimum rating (e.g. >4★).'
                ),
                savings_estimate=(
                    "Búsqueda indexada: ~0.0003 Wh vs. ~0.001–0.01 Wh del LLM"
                    if lang == Lang.ES else
                    "Indexed search: ~0.0003 Wh vs. ~0.001–0.01 Wh for LLM"
                ),
                source="Luccioni et al. (2023) — coste energético de inferencia vs. búsqueda indexada",
            ))
        else:
            suggestions.append(Suggestion(
                category=(
                    "Herramienta más eficiente disponible"
                    if lang == Lang.ES else
                    "More efficient tool available"
                ),
                description=(
                    f'Tu prompt busca {place_term} en una ubicación concreta. '
                    f'Google Maps o TripAdvisor dan horarios en tiempo real, fotos y valoraciones '
                    f'verificadas con ~100–200× menos energía que un LLM. '
                    f'Si usas IA, añade contexto: distancia máxima, rango de precio y ocasión.'
                    if lang == Lang.ES else
                    f'Your prompt is looking for {place_term} in a specific location. '
                    f'Google Maps or TripAdvisor provide live opening hours, photos and verified reviews '
                    f'using ~100–200× less energy than an LLM. '
                    f'If you use AI, add context: maximum distance, price range and occasion.'
                ),
                savings_estimate=(
                    "Búsqueda indexada: ~0.0003 Wh vs. ~0.001–0.01 Wh del LLM"
                    if lang == Lang.ES else
                    "Indexed search: ~0.0003 Wh vs. ~0.001–0.01 Wh for LLM"
                ),
                source="Luccioni et al. (2023) — coste energético de inferencia vs. búsqueda indexada",
            ))
    elif place_match and quality_match:
        # Place type + vague quality but no location — only suggest context enrichment
        place_term = place_match.group(0)
        vague_term = quality_match.group(0)
        suggestions.append(Suggestion(
            category=(
                "Criterio de calidad no definido"
                if lang == Lang.ES else
                "Undefined quality criterion"
            ),
            description=(
                f'El término "{vague_term}" aplicado a {place_term} es subjetivo y produce respuestas '
                f'genéricas. Define qué significa para ti: tipo de cocina/estilo, '
                f'presupuesto, ocasión o ambiente, y valoración mínima.'
                if lang == Lang.ES else
                f'The term "{vague_term}" applied to {place_term} is subjective and leads to generic responses. '
                f'Define what it means to you: cuisine/style type, '
                f'budget, occasion or vibe, and minimum rating.'
            ),
            savings_estimate=(
                "Evita 2–4 rondas de aclaración"
                if lang == Lang.ES else
                "Avoids 2–4 clarification rounds"
            ),
            source="Principio de especificidad contextual — Anthropic Prompt Engineering Guide (2024)",
        ))

    # 20. Proximidad vaga sin radio concreto
    # "Cerca de X" sin distancia concreta hace que el modelo genere listas basadas en
    # criterios arbitrarios. Especificar un radio elimina la ambigüedad y la iteración.
    if (
        has_location
        and not place_match  # ya cubierto por check 19 si hay tipo de lugar
        and _VAGUE_PROXIMITY_RE.search(norm)
        and not _CONCRETE_DISTANCE_RE.search(norm)
    ):
        suggestions.append(Suggestion(
            category=(
                "Proximidad vaga sin radio"
                if lang == Lang.ES else
                "Vague proximity without radius"
            ),
            description=(
                '"Cerca de" es relativo: puede ser 200 m a pie o 5 km en coche. '
                "Especifica la distancia máxima o el medio de transporte para obtener resultados útiles."
                if lang == Lang.ES else
                '"Nearby" is relative: it could mean 200 m on foot or 5 km by car. '
                "Specify a maximum distance or transport mode to get useful results."
            ),
            example=(
                '"a menos de 1 km a pie" / "en un radio de 5 km en coche" / "en el barrio de Gracia"'
                if lang == Lang.ES else
                '"within 1 km walking" / "within a 5 km drive" / "in the Gracia neighbourhood"'
            ),
            savings_estimate=(
                "Evita 1–2 turnos para refinar el criterio de distancia"
                if lang == Lang.ES else
                "Avoids 1–2 turns to refine the distance criterion"
            ),
            source="Principio de especificidad — Anthropic Prompt Engineering Guide (2024)",
        ))

    # 21. Información en tiempo real — datos que el LLM no puede proporcionar con precisión
    # Clima, resultados deportivos, precios actuales, noticias y horarios requieren
    # acceso a datos en vivo. Usar apps especializadas es más preciso y ~30–50× más eficiente.
    # Fuente: Luccioni et al. (2023); Strubell et al. (2019).
    if _REALTIME_RE.search(norm):
        suggestions.append(Suggestion(
            category=(
                "Datos en tiempo real — usa una app dedicada"
                if lang == Lang.ES else
                "Real-time data — use a dedicated app"
            ),
            description=(
                "Tu prompt pide información que cambia constantemente (clima, noticias, precios, "
                "horarios o resultados). Los LLMs tienen fecha de corte de conocimiento y pueden "
                "devolver datos desactualizados. Una app o buscador dedicado es más preciso y "
                "usa ~30–50× menos energía por consulta."
                if lang == Lang.ES else
                "Your prompt asks for information that changes constantly (weather, news, prices, "
                "schedules or results). LLMs have a training cutoff and may return outdated data. "
                "A dedicated app or search engine is more accurate and uses ~30–50× less energy per query."
            ),
            example=(
                "Clima → app del móvil / Weather.com  ·  Noticias → Google News  ·  "
                "Vuelos → Google Flights / Skyscanner  ·  Precios → Google Shopping"
                if lang == Lang.ES else
                "Weather → phone app / Weather.com  ·  News → Google News  ·  "
                "Flights → Google Flights / Skyscanner  ·  Prices → Google Shopping"
            ),
            savings_estimate=(
                "~0.0003 Wh/búsqueda web vs. ~0.001–0.01 Wh/consulta LLM"
                if lang == Lang.ES else
                "~0.0003 Wh/web search vs. ~0.001–0.01 Wh/LLM query"
            ),
            source="Luccioni et al. (2023); Strubell et al. (2019) — coste energético de inferencia vs. búsqueda",
        ))

    # 22. Rutas y direcciones — algoritmos especializados más eficientes
    # Google Maps y equivalentes calculan rutas óptimas con tráfico en tiempo real,
    # opciones de transporte público y tiempos exactos que un LLM no puede ofrecer.
    # Fuente: Luccioni et al. (2023) — routing algorítmico vs. inferencia neuronal.
    if _DIRECTIONS_RE.search(norm):
        suggestions.append(Suggestion(
            category=(
                "Rutas y direcciones — usa Google Maps"
                if lang == Lang.ES else
                "Routes and directions — use Google Maps"
            ),
            description=(
                "Tu prompt pide cómo llegar a un lugar o calcular una ruta. "
                "Google Maps, Waze o Citymapper ofrecen tráfico en tiempo real, "
                "opciones de transporte público actualizadas y tiempos exactos — "
                "con un impacto energético mínimo frente al LLM."
                if lang == Lang.ES else
                "Your prompt asks how to get somewhere or calculate a route. "
                "Google Maps, Waze or Citymapper provide live traffic, "
                "up-to-date public transport options and precise times — "
                "at a fraction of the energy cost of an LLM."
            ),
            example=(
                "Google Maps → tráfico en tiempo real, horarios de autobús y rutas multimodal"
                if lang == Lang.ES else
                "Google Maps → live traffic, bus schedules and multi-modal routes"
            ),
            savings_estimate=(
                "Routing algorítmico vs. LLM: ~1 000× menos energía por consulta"
                if lang == Lang.ES else
                "Algorithmic routing vs. LLM: ~1 000× less energy per query"
            ),
            source="Luccioni et al. (2023) — búsqueda indexada y routing algorítmico vs. inferencia neuronal",
        ))

    # 23. Revisión vaga sin especificación de qué mejorar
    # "Hazlo mejor" no indica qué está mal: el modelo cambia algo arbitrario y la respuesta
    # requiere otra ronda de corrección. Cada iteración reprocesa el historial completo.
    # Fuente: "Designers hit Claude's usage limits faster than anyone" (2026).
    vague_revision_re = _VAGUE_REVISION_ES if lang == Lang.ES else _VAGUE_REVISION_EN
    if vague_revision_re.search(norm):
        suggestions.append(Suggestion(
            category="Revisión vaga" if lang == Lang.ES else "Vague revision",
            description=(
                '"Hazlo mejor" o "arréglalo" no indican qué está mal. El modelo cambia algo '
                "arbitrario y el resultado requiere otra ronda. Especifica el aspecto concreto: "
                "contraste, jerarquía, copy, espaciado, tono, etc."
                if lang == Lang.ES else
                '"Make it better" or "fix it" gives no information about what\'s wrong. '
                "The model changes something arbitrary and you need to correct it again. "
                "Specify the exact aspect: contrast, hierarchy, copy, spacing, tone, etc."
            ),
            example=(
                '"Hazlo mejor" → "El espaciado entre secciones es muy pequeño; aumenta el padding a 32px. El CTA no es claro — cámbialo por una acción directa."'
                if lang == Lang.ES else
                '"Make it better" → "The spacing between sections is too tight; increase padding to 32px. The CTA is unclear — replace it with a direct action."'
            ),
            savings_estimate=(
                "Evita 2–4 rondas de iteración aleatoria"
                if lang == Lang.ES else
                "Avoids 2–4 random iteration rounds"
            ),
            source='"Designers hit Claude\'s usage limits faster than anyone" (2026) — vague revision requests',
        ))

    # 24. Delegación de estrategia al modelo (outsourcing thinking)
    # El modelo no conoce el proyecto, los usuarios ni las restricciones. Preguntar
    # «qué debería usar» sin contexto genera opciones genéricas que requieren 3–5 mensajes
    # de aclaración. Front-loading el contexto antes de enviar es la solución.
    # Fuente: "Designers hit Claude's usage limits faster than anyone" (2026).
    outsource_re = _OUTSOURCE_THINKING_ES if lang == Lang.ES else _OUTSOURCE_THINKING_EN
    if outsource_re.search(norm) and len(words) < 50:
        suggestions.append(Suggestion(
            category="Pensamiento delegado al modelo" if lang == Lang.ES else "Outsourcing thinking to the model",
            description=(
                "El modelo no conoce tus usuarios, restricciones ni objetivos. "
                "Sin contexto genera opciones genéricas que requerirán aclaraciones. "
                "Antes de enviar el prompt respóndete: ¿qué necesitas exactamente?, "
                "¿qué restricciones tienes? y ¿qué significa «hecho» para ti?"
                if lang == Lang.ES else
                "The model doesn't know your users, constraints or goals. "
                "Without context it generates generic options requiring clarifications. "
                "Before sending the prompt, answer yourself: what exactly do you need, "
                "what are your constraints, and what does done look like?"
            ),
            example=(
                '"¿Qué debería usar?" → "Necesito X para Y con restricción Z. ¿Cuál encaja mejor: A o B?"'
                if lang == Lang.ES else
                '"What should I use?" → "I need X for Y with constraint Z. Which fits best: A or B?"'
            ),
            savings_estimate=(
                "Evita 3–5 mensajes de aclaración por falta de contexto"
                if lang == Lang.ES else
                "Avoids 3–5 clarification messages due to missing context"
            ),
            source='"Designers hit Claude\'s usage limits faster than anyone" (2026) — outsourcing thinking entirely',
        ))

    # 25. Screenshot implícito sin instrucción de crop/tamaño
    # Una captura completa (1000×1000 px) consume ~1 334 tokens; un recorte de 200×200 px
    # cuesta ~54 tokens — 25× menos. Recortar al elemento relevante antes de subir
    # es la forma más eficiente de reducir el coste de tokens de imagen.
    # Fuente: "Designers hit Claude's usage limits faster than anyone" (2026).
    if _SCREENSHOT_MENTION_RE.search(norm) and not _SCREENSHOT_CROP_RE.search(norm):
        suggestions.append(Suggestion(
            category="Imagen sin recortar — coste elevado" if lang == Lang.ES else "Uncropped image — high token cost",
            description=(
                "Una captura completa (1000×1000 px) consume ~1 334 tokens. "
                "Un recorte del componente específico (200×200 px) cuesta ~54 tokens: 25× menos. "
                "Recorta la imagen al elemento concreto antes de subirla."
                if lang == Lang.ES else
                "A full-page screenshot (1000×1000 px) costs ~1 334 tokens. "
                "A crop of the specific component (200×200 px) costs ~54 tokens: 25× less. "
                "Crop the image to the specific element before uploading."
            ),
            example=(
                "Captura completa → ~1 334 tokens  ·  Recorte del componente (200×200 px) → ~54 tokens"
                if lang == Lang.ES else
                "Full screenshot → ~1 334 tokens  ·  Component crop (200×200 px) → ~54 tokens"
            ),
            savings_estimate=(
                "~25× menos tokens por imagen recortada al elemento relevante"
                if lang == Lang.ES else
                "~25× fewer tokens by cropping to the relevant element"
            ),
            source='"Designers hit Claude\'s usage limits faster than anyone" (2026) — image token costs scale with size',
        ))

    # 26. Comentario emocional sin valor para el prompt
    # Expresiones de sentimiento consumen tokens sin aportar contexto al modelo.
    # Fuente: "Designers hit Claude's usage limits faster than anyone" (2026) — token burn.
    sentiment_re = _SENTIMENT_ES if lang == Lang.ES else _SENTIMENT_EN
    if sentiment_re.search(norm):
        suggestions.append(Suggestion(
            category="Comentario personal sin valor" if lang == Lang.ES else "Personal commentary without value",
            description=(
                "Expresiones como «me encanta» o «me lo paso muy bien» no aportan contexto "
                "y consumen tokens sin mejorar el output. Sustitúyelas por contexto útil: "
                "qué has construido hasta ahora, tu nivel o el objetivo que persigues."
                if lang == Lang.ES else
                "Expressions like 'I love it' or 'I'm having so much fun' add no context "
                "and burn tokens without improving output. Replace them with useful context: "
                "what you've built so far, your skill level or the goal you're pursuing."
            ),
            savings_estimate=(
                "~5–10% menos tokens + respuestas más precisas"
                if lang == Lang.ES else
                "~5–10% fewer tokens + more precise responses"
            ),
            source='"Designers hit Claude\'s usage limits faster than anyone" (2026) — token burn patterns',
        ))

    # 27. Petición de ideas vaga sin dominio ni restricciones
    # «Dame ideas» sin dominio genera listas genéricas que rara vez encajan y requieren
    # rondas de refinamiento. Especificar área, nivel y formato lo resuelve en un solo turno.
    # Fuente: "Designers hit Claude's usage limits faster than anyone" (2026).
    vague_ideas_re = _VAGUE_IDEAS_ES if lang == Lang.ES else _VAGUE_IDEAS_EN
    if vague_ideas_re.search(norm) and len(words) < 50 and not any(f in norm for f in fmt_words):
        suggestions.append(Suggestion(
            category="Petición de ideas demasiado abierta" if lang == Lang.ES else "Ideas request too open-ended",
            description=(
                "«Dame ideas» sin dominio ni restricciones genera listas genéricas que rara vez encajan. "
                "Especifica: área concreta, tu nivel actual, el usuario final y el formato esperado."
                if lang == Lang.ES else
                '"Give me ideas" without domain or constraints generates generic lists that rarely fit. '
                "Specify: the concrete area, your current level, the end user and the expected format."
            ),
            example=(
                '"Dame ideas" → "Lista 5 ideas de app con la API de Claude para principiantes, enfocadas en productividad, en una frase cada una."'
                if lang == Lang.ES else
                '"Give me ideas" → "List 5 beginner-friendly Claude API app ideas focused on productivity, one sentence each."'
            ),
            savings_estimate=(
                "Evita 2–3 rondas de refinamiento por falta de foco"
                if lang == Lang.ES else
                "Avoids 2–3 refinement rounds due to lack of focus"
            ),
            source='"Designers hit Claude\'s usage limits faster than anyone" (2026) — one-sentence context pattern',
        ))

    return suggestions


# ---------------------------------------------------------------------------
# Recomendación de modelo
# ---------------------------------------------------------------------------

def recommend_model(text: str, tokens: int, lang: Lang = Lang.ES) -> ModelRecommendation:
    """
    Recomienda el tier de modelo más adecuado analizando la complejidad del prompt.

    Scoring basado en:
    - Anthropic Model Selection Guide (2024): heurísticas por tipo de tarea
    - "Lost in the Middle" (Liu et al., 2023): impacto de longitud en rendimiento
    """
    score = 0
    signals: list[str] = []
    norm = _normalize_for_match(text)
    es = lang == Lang.ES

    if tokens > 500:
        score += 3
        signals.append(
            f"prompt extenso ({tokens} tokens)" if es else f"long prompt ({tokens} tokens)"
        )
    elif tokens > 150:
        score += 1

    if _COMPLEX_SCIENTIFIC.search(norm):
        score += 3
        signals.append(
            "contenido científico o académico" if es else "scientific or academic content"
        )

    if _COMPLEX_CODE.search(norm):
        score += 2
        signals.append(
            "ingeniería de software avanzada" if es else "advanced software engineering"
        )

    if _COMPLEX_DOMAIN.search(norm):
        score += 2
        signals.append(
            "dominio especializado (legal / médico / financiero)" if es
            else "specialised domain (legal / medical / financial)"
        )

    if _CODE_GENERAL.search(norm):
        score += 1
        signals.append(
            "tarea de programación o sistemas" if es else "programming or systems task"
        )

    if _REASONING.search(norm):
        score += 1
        signals.append(
            "requiere análisis o razonamiento comparativo" if es
            else "requires analysis or comparative reasoning"
        )

    constraint_count = len(re.findall(
        r"\b(debe|tiene que|es necesario|obligatorio|sin que|nunca|siempre|asegurate|asegurese"
        r"|must|has to|required|mandatory|never|always|make sure|ensure)\b",
        norm,
    ))
    if constraint_count >= 3:
        score += 1
        signals.append(
            f"{constraint_count} restricciones detectadas" if es
            else f"{constraint_count} constraints detected"
        )

    # Señal de contexto multi-documento
    # Liu et al. (2023) "Lost in the Middle" demuestra degradación del rendimiento
    # en contextos largos con múltiples bloques de información sin estructura;
    # estos prompts requieren un modelo con mayor ventana de contexto y capacidad
    # de síntesis, lo que apunta a tiers superiores.
    multi_doc_signals = (
        (1 if _MULTI_DOC_TAGS_RE.search(text) else 0)
        + (1 if text.count("###") >= 2 else 0)
        + (1 if text.count("---") >= 2 else 0)
        + (1 if text.count("```") >= 4 else 0)   # ≥2 code blocks (open + close × 2)
        + (1 if len(re.findall(r"\n\s*\n", text)) >= 3 else 0)
    )
    if multi_doc_signals >= 2:
        score += 2
        signals.append(
            "contexto multi-documento" if es else "multi-document context"
        )

    if (_ES_SIMPLE.search(norm.lstrip()) or _EN_SIMPLE.search(norm.lstrip())) and tokens < 50:
        score -= 2
        signals.append("tarea simple y directa" if es else "simple and direct task")

    if score >= 4:
        return ModelRecommendation(
            tier="large",
            headline="Modelo grande (Opus)" if es else "Large model (Opus)",
            reason=(
                "El prompt requiere razonamiento profundo, conocimiento especializado "
                "o manejo de contexto extenso. Un modelo pequeño podría dar respuestas "
                "superficiales o incorrectas."
                if es else
                "The prompt requires deep reasoning, specialised knowledge or "
                "extensive context handling. A smaller model may give shallow or incorrect answers."
            ),
            signals=signals,
        )
    if score >= 1:
        return ModelRecommendation(
            tier="medium",
            headline="Modelo medio (Sonnet)" if es else "Medium model (Sonnet)",
            reason=(
                "La tarea tiene complejidad moderada. Sonnet ofrece el mejor equilibrio "
                "entre calidad y coste para este tipo de prompt."
                if es else
                "The task has moderate complexity. Sonnet offers the best balance "
                "of quality and cost for this type of prompt."
            ),
            signals=signals,
        )
    return ModelRecommendation(
        tier="small",
        headline="Modelo pequeño (Haiku / mini)" if es else "Small model (Haiku / mini)",
        reason=(
            "La tarea es directa y no requiere razonamiento complejo. "
            "Usando Haiku o GPT-4o mini ahorrarás hasta 10× en coste con resultados equivalentes."
            if es else
            "The task is straightforward and requires no complex reasoning. "
            "Using Haiku or GPT-4o mini saves up to 10× in cost with equivalent results."
        ),
        signals=signals,
    )


# ---------------------------------------------------------------------------
# Aspectos positivos del prompt
# ---------------------------------------------------------------------------

def positive_aspects(text: str, lang: Lang = Lang.ES) -> list[str]:
    """
    Identifica qué hace bien el prompt según principios de ingeniería de prompts.
    Fuentes: Anthropic Prompt Engineering Guide (2024), OpenAI Best Practices (2024).
    """
    aspects: list[str] = []
    words = text.split()
    norm = _normalize_for_match(text)

    if _FORMAT_SPECIFIED.search(norm):
        aspects.append(
            "Especifica el formato de salida → reduce tokens de respuesta un 10–30 %"
            if lang == Lang.ES else
            "Specifies output format → reduces response tokens by 10–30 %"
        )

    if _ROLE_DEFINED.search(norm):
        aspects.append(
            "Define el rol del modelo → mejora precisión en tareas especializadas"
            if lang == Lang.ES else
            "Defines the model role → improves precision on specialised tasks"
        )

    if _DIRECT_START.search(norm.lstrip()):
        aspects.append(
            "Empieza con un verbo de acción → instrucción directa y sin ambigüedad"
            if lang == Lang.ES else
            "Starts with an action verb → direct and unambiguous instruction"
        )

    if "\n" in text and any(c in text for c in ["-", "*", "###", "1."]):
        aspects.append(
            "Usa estructura con secciones o viñetas → más fácil de procesar"
            if lang == Lang.ES else
            "Uses structure with sections or bullets → easier to process"
        )

    filler_re = _ES_FILLER if lang == Lang.ES else _EN_FILLER
    if not filler_re.search(norm):
        aspects.append(
            "Sin frases de cortesía innecesarias → tokens bien aprovechados"
            if lang == Lang.ES else
            "No unnecessary courtesy phrases → tokens well used"
        )

    if 15 <= len(words) <= 200:
        aspects.append(
            "Longitud apropiada — ni demasiado vaga ni innecesariamente larga"
            if lang == Lang.ES else
            "Appropriate length — neither too vague nor unnecessarily long"
        )

    # XML tags estructurales → Claude los procesa con mayor precisión que texto plano.
    # Fuente: Anthropic Prompt Engineering Guide (2024) — XML structuring.
    if _XML_STRUCTURAL_TAGS_RE.search(text):
        aspects.append(
            "Usa XML tags para estructurar el prompt → Claude los procesa con mayor precisión"
            if lang == Lang.ES else
            "Uses XML tags to structure the prompt → Claude processes them with higher precision"
        )

    # Ejemplos concretos inline (por ejemplo: / for example: seguido de contenido).
    # Fuente: DAIR.AI Prompt Engineering Guide — few-shot prompting.
    if _INLINE_EXAMPLE_RE.search(text):
        aspects.append(
            "Incluye ejemplos concretos → guía al modelo hacia el formato esperado"
            if lang == Lang.ES else
            "Includes concrete examples → guides the model toward the expected format"
        )

    return aspects


# ---------------------------------------------------------------------------
# Clasificación de tipo de tarea (Sección 2 — jerarquía de impacto energético)
# ---------------------------------------------------------------------------

def detect_task_type(text: str, lang: Lang = Lang.ES) -> tuple[str, str, str]:
    """
    Clasifica el tipo de tarea del prompt según la jerarquía de impacto energético.

    Devuelve (tipo, etiqueta, nota_impacto) donde tipo es:
      'fact'    — Verificación de hechos (menor impacto energético)
      'code'    — Generación de código (impacto moderado)
      'qa'      — Pregunta y Respuesta (mayor impacto energético)
      'general' — Tarea general

    Fuente: Luccioni et al. (2023); media Q&A ≈ 8.17 gCO₂e/respuesta,
    31.8 mWh/token de salida.
    """
    norm = _normalize_for_match(text)
    stripped = norm.lstrip()

    if _IMAGE_OUTPUT_RE.search(norm):
        if lang == Lang.ES:
            return ("image", "Generación de imagen", "Impacto muy alto — inferencia visual intensiva")
        return ("image", "Image Generation", "Very high impact — intensive visual inference")

    if _DOCUMENT_OUTPUT_RE.search(norm):
        if lang == Lang.ES:
            return ("document", "Generación de documento", "Impacto alto — salida extensa y estructurada")
        return ("document", "Document Generation", "High impact — long and structured output")

    if _ARTIFACT_OUTPUT_RE.search(norm):
        if lang == Lang.ES:
            return ("artifact", "Generación de artefacto", "Impacto moderado — salida estructurada y acotada")
        return ("artifact", "Artifact Generation", "Moderate impact — structured and bounded output")

    if _TASK_FACT_RE.search(stripped):
        if lang == Lang.ES:
            return ("fact", "Verificación de hechos", "Menor impacto — respuestas cortas y directas")
        return ("fact", "Fact Verification", "Lowest impact — short and direct answers")

    if _TASK_CODE_RE.search(norm):
        if lang == Lang.ES:
            return ("code", "Generación de código", "Impacto moderado — salida estructurada y acotada")
        return ("code", "Code Generation", "Moderate impact — structured and bounded output")

    if _TASK_QA_RE.search(stripped):
        if lang == Lang.ES:
            return ("qa", "Pregunta y Respuesta", "Mayor impacto — media ≈ 8.17 gCO₂e/respuesta")
        return ("qa", "Q&A", "Highest impact — avg ≈ 8.17 gCO₂e/response")

    if lang == Lang.ES:
        return ("general", "Tarea general", "")
    return ("general", "General task", "")
