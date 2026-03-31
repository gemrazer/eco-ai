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

    # 8. Formato de salida no especificado (solo aplica a output de texto)
    # Especificar el formato reduce la longitud de la respuesta al eliminar
    # introducciones, transiciones y conclusiones que el modelo añade por defecto.
    # Referencia: Sclar et al. (2023) cuantifican la sensibilidad de los LLMs
    # al formato del prompt; Anthropic reporta reducción de 10–30% en tokens de salida.
    if output_type == "text" and len(words) > 50 and not any(f in norm for f in fmt_words):
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
