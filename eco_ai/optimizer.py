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
_DIRECT_START = re.compile(
    r"^(escribe|explica|resume|analiza|traduce|genera|crea|lista|enumera|compara"
    r"|describe|calcula|extrae|clasifica|define|corrige|mejora|revisa"
    r"|write|explain|summarize|analyze|translate|generate|create|list|compare"
    r"|describe|calculate|extract|classify|fix|improve|review)\b",
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

def analyze(text: str, lang: Lang = Lang.ES) -> list[Suggestion]:
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
            category="Frases de cortesía",
            description="Los modelos no necesitan cortesías — eliminan tokens sin aportar contexto.",
            example=(
                '"Por favor, ¿podrías explicarme…?" → "Explica…"' if lang == Lang.ES
                else '"Could you please explain…?" → "Explain…"'
            ),
            savings_estimate="~5–15% menos tokens",
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
                category="Frases repetidas",
                description=f"Se detectaron {duplicate_count} frases con contenido muy similar. Consolida la idea en una sola vez.",
                savings_estimate="~5–20% menos tokens",
                source="Principio de economía de tokens (medición directa)",
            ))

    # 3. Introducción innecesaria
    # Los modelos no tienen estado social; saludos y presentaciones no aportan contexto
    # relevante para la tarea. Referencia: Anthropic Prompt Engineering Guide (2024).
    for pat in intro_pats:
        if pat.search(norm):
            suggestions.append(Suggestion(
                category="Introducción innecesaria",
                description="Salta directo a la instrucción — el modelo no necesita saludos ni presentaciones.",
                example=(
                    '"Hola, soy diseñadora y quiero que me ayudes con…" → "Ayúdame con…"' if lang == Lang.ES
                    else '"Hi, I\'m a developer and I was wondering if you could help me with…" → "Help me with…"'
                ),
                savings_estimate="~5–10% menos tokens",
                source="Anthropic Prompt Engineering Guide (2024)",
            ))
            break

    # 4. Prompt muy largo sin estructura
    # Liu et al. (2023) "Lost in the Middle" demuestra que los modelos retienen peor
    # la información situada en el centro de contextos largos sin estructura.
    if len(words) > 150 and "\n" not in text and "###" not in text and "-" not in text[:200]:
        suggestions.append(Suggestion(
            category="Falta de estructura",
            description="Prompts largos sin formato (viñetas, secciones) suelen ser más verbosos. Separa contexto, tarea y formato esperado.",
            example="### Contexto\n...\n### Tarea\n...\n### Formato\n...",
            savings_estimate="Puede reducir el prompt un 20–30% y mejorar la respuesta",
            source='Liu et al. (2023) "Lost in the Middle: How LMs Use Long Contexts"',
        ))

    # 5. Demasiados ejemplos
    # Min et al. (2022) muestran que el efecto de los ejemplos se satura con 1–2;
    # añadir más no mejora el rendimiento y puede introducir sesgo (Zhao et al., 2021).
    example_count = len(ex_re.findall(norm))
    if example_count > 3:
        suggestions.append(Suggestion(
            category="Demasiados ejemplos",
            description=f"Se encontraron {example_count} referencias a ejemplos. Limita a 1–2 ejemplos concretos; más no mejora la respuesta.",
            savings_estimate="~10–25% menos tokens",
            source='Min et al. (2022) "Rethinking the Role of Demonstrations"; Zhao et al. (2021) "Calibrate Before Use"',
        ))

    # 6. Prompt muy corto
    # Heurística establecida en guías de prompt engineering: prompts sin contexto
    # suficiente producen respuestas genéricas que requieren turnos de aclaración,
    # aumentando el coste total de la conversación.
    if len(words) < 10:
        suggestions.append(Suggestion(
            category="Prompt muy corto",
            description="Un prompt muy breve puede generar respuestas genéricas que requieren más turnos de conversación. Añade contexto mínimo: rol, tarea, formato.",
            savings_estimate="Puede evitar 2–3 rondas extra de preguntas",
            source="OpenAI Best Practices (2024); Anthropic Prompt Engineering Guide (2024)",
        ))

    # 7. Lenguaje vago / hedging
    # Webson & Pavlick (2021) demuestran que prompts con instrucciones ambiguas
    # producen outputs impredecibles. La vaguedad fuerza al modelo a asumir
    # o solicitar aclaraciones, incrementando el número de turnos.
    vague_found = sum(1 for p in vague_pats if p.search(norm))
    if vague_found >= 2:
        suggestions.append(Suggestion(
            category="Lenguaje impreciso",
            description="Expresiones vagas ('más o menos', 'algo así') obligan al modelo a pedir aclaraciones o a asumir. Sé específico.",
            example=(
                '"Quiero algo así como una lista, más o menos" → "Devuelve una lista con viñetas"' if lang == Lang.ES
                else '"Something like a list, kind of" → "Return a numbered list"'
            ),
            savings_estimate="Reduce turnos de aclaración",
            source='Webson & Pavlick (2021) "Do Prompt-Based Models Really Understand the Meaning of Their Prompts?"',
        ))

    # 8. Formato de salida no especificado
    # Especificar el formato reduce la longitud de la respuesta al eliminar
    # introducciones, transiciones y conclusiones que el modelo añade por defecto.
    # Referencia: Sclar et al. (2023) cuantifican la sensibilidad de los LLMs
    # al formato del prompt; Anthropic reporta reducción de 10–30% en tokens de salida.
    if len(words) > 50 and not any(f in norm for f in fmt_words):
        suggestions.append(Suggestion(
            category="Formato de salida no indicado",
            description="Especificar el formato evita que el modelo genere texto extra (introducciones, conclusiones innecesarias).",
            example=(
                'Añade al final: "Responde en forma de lista numerada, sin introducción."' if lang == Lang.ES
                else 'Add at the end: "Respond as a numbered list, no introduction."'
            ),
            savings_estimate="~10–30% menos tokens de salida",
            source='Sclar et al. (2023) "Quantifying Sensitivity to Spurious Features in NLP"; Anthropic Prompt Engineering Guide (2024)',
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

    return suggestions


# ---------------------------------------------------------------------------
# Recomendación de modelo
# ---------------------------------------------------------------------------

def recommend_model(text: str, tokens: int) -> ModelRecommendation:
    """
    Recomienda el tier de modelo más adecuado analizando la complejidad del prompt.

    Scoring basado en:
    - Anthropic Model Selection Guide (2024): heurísticas por tipo de tarea
    - "Lost in the Middle" (Liu et al., 2023): impacto de longitud en rendimiento
    """
    score = 0
    signals: list[str] = []
    norm = _normalize_for_match(text)

    if tokens > 500:
        score += 3
        signals.append(f"prompt extenso ({tokens} tokens)")
    elif tokens > 150:
        score += 1

    if _COMPLEX_SCIENTIFIC.search(norm):
        score += 3
        signals.append("contenido científico o académico")

    if _COMPLEX_CODE.search(norm):
        score += 2
        signals.append("ingeniería de software avanzada")

    if _COMPLEX_DOMAIN.search(norm):
        score += 2
        signals.append("dominio especializado (legal / médico / financiero)")

    if _CODE_GENERAL.search(norm):
        score += 1
        signals.append("tarea de programación o sistemas")

    if _REASONING.search(norm):
        score += 1
        signals.append("requiere análisis o razonamiento comparativo")

    constraint_count = len(re.findall(
        r"\b(debe|tiene que|es necesario|obligatorio|sin que|nunca|siempre|asegurate|asegurese"
        r"|must|has to|required|mandatory|never|always|make sure|ensure)\b",
        norm,
    ))
    if constraint_count >= 3:
        score += 1
        signals.append(f"{constraint_count} restricciones detectadas")

    if (_ES_SIMPLE.search(norm.lstrip()) or _EN_SIMPLE.search(norm.lstrip())) and tokens < 50:
        score -= 2
        signals.append("tarea simple y directa")

    if score >= 4:
        return ModelRecommendation(
            tier="large",
            headline="Modelo grande (Opus)",
            reason=(
                "El prompt requiere razonamiento profundo, conocimiento especializado "
                "o manejo de contexto extenso. Un modelo pequeño podría dar respuestas "
                "superficiales o incorrectas."
            ),
            signals=signals,
        )
    if score >= 1:
        return ModelRecommendation(
            tier="medium",
            headline="Modelo medio (Sonnet)",
            reason=(
                "La tarea tiene complejidad moderada. Sonnet ofrece el mejor equilibrio "
                "entre calidad y coste para este tipo de prompt."
            ),
            signals=signals,
        )
    return ModelRecommendation(
        tier="small",
        headline="Modelo pequeño (Haiku / mini)",
        reason=(
            "La tarea es directa y no requiere razonamiento complejo. "
            "Usando Haiku o GPT-4o mini ahorrarás hasta 10× en coste con resultados equivalentes."
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
        aspects.append("Especifica el formato de salida → reduce tokens de respuesta un 10–30 %")

    if _ROLE_DEFINED.search(norm):
        aspects.append("Define el rol del modelo → mejora precisión en tareas especializadas")

    if _DIRECT_START.search(norm.lstrip()):
        aspects.append("Empieza con un verbo de acción → instrucción directa y sin ambigüedad")

    if "\n" in text and any(c in text for c in ["-", "*", "###", "1."]):
        aspects.append("Usa estructura con secciones o viñetas → más fácil de procesar")

    filler_re = _ES_FILLER if lang == Lang.ES else _EN_FILLER
    if not filler_re.search(norm):
        aspects.append("Sin frases de cortesía innecesarias → tokens bien aprovechados")

    if 15 <= len(words) <= 200:
        aspects.append("Longitud apropiada — ni demasiado vaga ni innecesariamente larga")

    return aspects
