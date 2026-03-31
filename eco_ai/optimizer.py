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
