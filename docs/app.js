// ─── Constants ────────────────────────────────────────────
// Energy: medium-tier model (Claude Sonnet, GPT-4o) — Luccioni et al. 2023
const KWH_PER_1K_TOKENS    = 0.0008;
// CO₂: global cloud average 2023 — IEA
const CO2_KG_PER_KWH       = 0.30;
// Water: data centre cooling average — Microsoft Sustainability Report 2023
const WATER_L_PER_KWH      = 0.90;
// Output token estimate: 40% of input (conservative default)
const OUTPUT_RATIO         = 0.4;
// Pricing: Claude Sonnet 4.6 (March 2026)
const INPUT_PRICE_PER_1K   = 0.003;
const OUTPUT_PRICE_PER_1K  = 0.015;
const TOKENS_PER_WORD      = 1.3;
// Everyday equivalents
const LED_KW               = 0.010;   // 10 W LED bulb
const TAP_L_PER_S          = 5 / 60;  // tap at 5 L/min
const CAR_G_CO2_PER_KM     = 170;     // avg car g CO₂/km
const SEARCH_G_CO2         = 0.14;    // g CO₂ per Google search

// ─── DOM refs ─────────────────────────────────────────────
const promptInput   = document.getElementById('prompt-input');
const tokenCounter  = document.getElementById('token-counter');
const analyzeBtn    = document.getElementById('analyze-btn');
const resultsArea   = document.getElementById('results-area');
const placeholder   = document.getElementById('placeholder-hint');
const themeToggle   = document.getElementById('theme-toggle');

// ─── Theme toggle ─────────────────────────────────────────
function getInitialTheme() {
  const saved = localStorage.getItem('eco-ai-theme');
  if (saved) return saved;
  try {
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  } catch (e) {
    return 'dark';
  }
}
document.documentElement.setAttribute('data-theme', getInitialTheme());

themeToggle.addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('eco-ai-theme', next);
});

// Cached token count — kept in sync by the input handler,
// consumed by renderResults so countTokens isn't called twice.
let cachedTokens = 0;

// ─── Token estimation ─────────────────────────────────────
function countTokens(text) {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return Math.round(words * TOKENS_PER_WORD);
}

// ─── Model recommendation (ported from eco_ai/optimizer.py) ──
// Scoring mirrors recommend_model() — Anthropic Model Selection Guide (2024)
const _RX_SCIENTIFIC = /\b(hypothesis|methodology|systematic review|meta.?analysis|statistical significance|literature review|empirical study|control group|p.?value|confidence interval|hipotesis|metodolog[ií]a|meta.?an[aá]lisis|revisi[oó]n sistem[aá]tica|estad[ií]stica|regresi[oó]n|correlaci[oó]n|varianza|significancia|art[ií]culo cient[ií]fico|abstract|bibliograf[ií]a|ecuaci[oó]n diferencial)\b/i;
const _RX_COMPLEX_CODE = /\b(design pattern|refactor|algorithmic complexity|concurren(cy|cia)|paraleli(sm|smo)|microservice|kubernetes|docker|ci.?cd|devops|machine learning|deep learning|neural network|transformer model|distributed system|system design|load balancing|race condition|arquitectura de software|complejidad algor[ií]tmica)\b/i;
const _RX_DOMAIN = /\b(legal clause|medical diagnosis|financial analysis|tax compliance|audit|liability|contrato|cl[aá]usula legal|normativa|regulaci[oó]n|compliance|jur[ií]dico|diagn[oó]stico m[eé]dico|s[ií]ntoma|tratamiento|medicamento|dosis|an[aá]lisis financiero|cartera de inversi[oó]n|fiscalidad|auditor[ií]a)\b/i;
const _RX_REASONING = /\b(analyze|evaluate|compare|argue|step by step|pros and cons|advantages and disadvantages|critically assess|analiza|compara|eval[uú]a|argumenta|debate|pros y contras|ventajas y desventajas|cr[ií]tica|justifica|demuestra|razona paso a paso)\b/i;
const _RX_CODE = /\b(function|funcion|c[oó]digo|code|script|program(a)?|class|clase|m[eé]todo|method|sql|query|html|css|javascript|python|java|typescript|bash|shell|api|endpoint|database|base de datos|algorithm|data structure)\b/i;
const _RX_SIMPLE = /^(translate|traduce|spell.?check|corrige la ortograf[ií]a|synonym|sin[oó]nimo|what does|que significa|define|conv(iert)?e|format(ea)?|list of|lista de|enumerate|enumera)\b/i;
const _RX_CONSTRAINTS = /\b(must|has to|required|mandatory|never|always|make sure|ensure|debe|tiene que|es necesario|obligatorio|nunca|siempre|aseg[uú]rate)\b/gi;

function recommendModel(text, tokens) {
  let score = 0;
  const norm = text.toLowerCase();

  if (tokens > 500)       score += 3;
  else if (tokens > 150)  score += 1;

  if (_RX_SCIENTIFIC.test(norm))   score += 3;
  if (_RX_COMPLEX_CODE.test(norm)) score += 2;
  if (_RX_DOMAIN.test(norm))       score += 2;
  if (_RX_CODE.test(norm))         score += 1;
  if (_RX_REASONING.test(norm))    score += 1;

  const constraints = (text.match(_RX_CONSTRAINTS) || []).length;
  if (constraints >= 3) score += 1;

  if (_RX_SIMPLE.test(text.trimStart()) && tokens < 50) score -= 2;

  if (score >= 4) return {
    tier: 'large',
    label: 'Opus · GPT-4o',
    reason: 'Deep reasoning or specialized knowledge required'
  };
  if (score >= 1) return {
    tier: 'medium',
    label: 'Sonnet · GPT-4o',
    reason: 'Moderate complexity — best quality/cost balance'
  };
  return {
    tier: 'small',
    label: 'Haiku · GPT-4o mini',
    reason: 'Simple task — small model gives equivalent results at ~10× lower cost'
  };
}

// ─── Suggestions logic (mirrors eco_ai/optimizer.py) ────────────────────
function detectOutputType(text) {
  if (/\b(generate|create|draw|illustrate|design)\b.{0,30}\b(image|photo|picture|illustration|icon|logo|banner)\b|\b(imagen|foto|ilustraci[oó]n|icono|logo)\b/i.test(text)) return 'image';
  if (/\b(write|create|generate|implement)\b.{0,25}\b(function|class|script|code|program|algorithm|api|query)\b|\b(funci[oó]n|clase|script|c[oó]digo|programa)\b/i.test(text)) return 'code';
  if (/\b(write|generate|create)\b.{0,25}\b(pdf|report|document|presentation|proposal|memo)\b|\b(informe|reporte|presentaci[oó]n|propuesta)\b/i.test(text)) return 'document';
  return 'text';
}

const _RX_FILLER     = /\bpleas+e?\b|\bcould you\b|\bwould you\b|\bi would like( you)? to\b|\bif you (could|can|don'?t mind)\b|\bthanks? in advance\b|\bi need you to\b|\bkindly\b|\bif possible\b|\bpor\s*fa[bv]or\b|\bpodri[aá]s?\b|\bme gustar[ií]a que\b|\bsi puedes?\b|\bsi no te importa\b/i;
const _RX_SENTIMENT  = /\b(me (lo paso (muy |s[uú]per )?bien|encanta|gusta (mucho|un mont[oó]n)|alegra|divierte|fascina|flipa)|estoy (muy )?(emocionad[ao]|content[ao]|feliz|entusiasmad[ao])|qu[eé] (guay|chulo|cool|pasada|gozada)|es (genial|incre[ií]ble|alucinante|chul[oa]|super[- ]?(chulo|guay))|i (love|really enjoy|really like) (it|this|using|working with)|i'?m (so )?(excited|loving it|having (a lot of )?fun)|this is (great|awesome|amazing|so cool))\b/i;
const _RX_VAGUE_REQ  = /\b(dame ideas|give me ideas|ideas (de |para |sobre |for |about |on )\w|brainstorm( some| ideas)?|qu[eé] (puedo|podr[ií]a) (hacer|crear|construir|desarrollar|hacer)\b|what (can|should|could) i (do|make|build|create)\b)/i;
const _RX_VAGUE_REVISION = /\b(hazlo (mejor|mas? bonito|mas? chulo|mas? profesional|diferente|mas? limpio)|mej[oó]ralo|arr[eé]glalo|c[aá]mbialo|make it (better|nicer|cleaner|prettier|more professional|different)|improve (it|this)\b|fix (it|this)\b|change (it|this)\b|(looks?|seems?) (weird|bad|off|wrong|messy|boring|flat)\b|could (look|be) (better|cleaner|clearer|nicer)\b|i don'?t (like|love) (it|this)\b)\b/i;
const _RX_OUTSOURCE  = /\b(qu[eé] (deber[ií]a|podr[ií]a|tendr[ií]a que) (hacer|usar|elegir|escribir|implementar|crear|construir)\b|c[oó]mo (deber[ií]a|podr[ií]a) (enfocarlo|abordarlo|hacerlo|estructurarlo)\b|cu[aá]l (es|ser[ií]a) la mejor (forma|manera|opci[oó]n|estrategia) (de|para)\b|what should i (do|use|choose|write|implement|pick|go with|build|create)\b|how should i (approach|handle|tackle|frame|structure) (this|it)\b|what('?s| is) (the )?best (way|approach|option|strategy) (to|for)\b|what do you (think|suggest|recommend) (i should|about)\b)\b/i;
const _RX_SCREENSHOT = /\b(screenshot|captura (de pantalla|completa)|pantalla completa|full.?page (screenshot|capture)|full screen)\b/i;
const _RX_CROP       = /\b(recortad[ao]|crop(ped)?|solo (el|la|este|esta)|only (the|this)|just (the|this)|\d+\s*(px|pixels?)|componente (espec[ií]fico|concreto)|elemento (espec[ií]fico|concreto))\b/i;
const _RX_INTRO      = /^(hello|hi|hey|good morning|good afternoon|hola|buenas?|buenos d[ií]as)[,!.]?\s/i;
const _RX_VAGUE      = /\bkind of\b|\bsort of\b|\bmore or less\b|\bsomething like\b|\bm[aá]s o menos\b|\balgo as[ií]\b|\bde alguna manera\b/gi;
const _RX_HIGH_VERB  = /^(analiz[ae]|analyze|explain|explica|create|crea|justify|justifica|write|escribe)\b/i;
const _RX_OUT_LIMIT  = /\bin less than \d|\bmax(imum)?.?\d|\bno more than \d|\bbriefly\b|\bconcisely\b|\bin \d+ words|\bin \d+ (key )?points?|\blimit (your|the) (response|answer)|\bonly \d+ (point|word|bullet)|\bkeep it (short|brief)\b|\ben menos de \d|\bm[aá]ximo \d|\bno m[aá]s de \d|\bbrevemente\b|\bconcisamente\b|\ben \d+ palabras/i;
const _RX_FORMAT     = /\b(table|list|json|bullet|numbered|paragraph|markdown|csv|code|format|structure|tabla|lista|vi[ñn]eta|p[aá]rrafo|formato|numerado)\b/i;
const _RX_ROLE       = /\b(act as|you are a|you'?re a|as an? (expert|specialist)|actua como|eres un[ao]?|como experto|como especialista)\b/i;
const _RX_AUDIENCE   = /\b(for (students|beginners|experts|developers|professionals|children|adults|my team)|para (estudiantes|principiantes|expertos|desarrolladores|profesionales|ni[ñn]os|adultos|mi equipo)|(beginner|intermediate|advanced|expert) level|nivel (b[aá]sico|intermedio|avanzado|principiante|experto))\b/i;
const _RX_TONE       = /\b(formal|informal|technical|simple|friendly|professional|academic|conversational) (tone|style|voice|language)|in a (formal|informal|simple|clear|technical) (way|tone|style)|tono (formal|informal|t[eé]cnico|simple)|estilo (formal|informal|narrativo)\b/i;
const _RX_IMG_STYLE  = /\b(photorealistic|realistic|illustration|cartoon|anime|watercolor|3d render|digital art|minimalist|abstract|oil painting|style|estilo|fotorrealista|ilustraci[oó]n|acuarela)\b/i;

// ─── Discovery / local search detection ─────────────────────────────────
// Triggers when someone asks for places, venues or local recommendations
const _RX_DISC_PLACE = /\b(restaurantes?|hotels?|hoteles?|bares?|caf[eé]s?|tiendas?|farmacias?|gimnasio|gym|peluquer[ií]as?|dentista|m[eé]dico|hospital|parques?|museo|cine|teatro|playa|mercado|librer[ií]a|restaurant|bar|caf[eé]|shop|store|pharmacy|park|museum|cinema|beach|market|bookstore|spa|barbería|barbershop)\b/i;
const _RX_DISC_VERB  = /\b(recomi[eé]nd[ae]me|d[ií]me (algunos?|cu[aá]les|los mejores?)|qu[eé] (restaurantes?|lugares?|sitios?|hoteles?|bares?)|cu[aá]les son (los|las) mejores?|mejores? \w+ (en|cerca|de|por)|best (restaurants?|hotels?|bars?|places?|things? to do)|recommend (me |some |a )?(good |nice )?\w+|where (can i|to) (eat|find|go|stay)|suggest (some|a few|good)\b)/i;
const _RX_DISC_LOC   = /\b(cerca de|en [a-záéíóúñ]+|por [a-záéíóúñ]+|near|in [a-z]+|around [a-z]+|por la zona)\b/i;
// Missing context signals for discovery queries
const _RX_HAS_CUISINE    = /\b(italiana?|japonesa?|mexicana?|española?|francesa?|china|thai|griega?|india?|mediterr[aá]nea?|italiana|japanese|italian|mexican|french|chinese|greek|thai|mediterranean|vegetarian|vegan|sushi|pizza|tapas|seafood|marisco|vegano|vegetariano|burger|kebab|ramen|poke|fusion)\b/i;
const _RX_HAS_ATMOSPHERE = /\b(rom[aá]ntic[ao]?|familiar|moderno|tradicional|informal|casual|terraza|rooftop|[ií]ntim[ao]|animado|tranquilo|lively|cozy|trendy|fine.?dining|family.?friendly|outdoor|al aire libre|con vistas?|vista al mar|garden)\b/i;
const _RX_HAS_BUDGET     = /\b(barato|econ[oó]mico|asequible|precio|presupuesto|lujo|gama alta|cheap|affordable|budget|luxury|mid.?range|\$\$?|€€?|price range|less than|menos de)\b/i;
const _RX_HAS_AREA       = /\b(barrio|distrito|neighborhood|district|eixample|gracia|gr[àa]cia|born|raval|g[oò]tic|poblenou|poble.?sec|sarri[aà]|centro|downtown|old town|casco antiguo|chueca|malasa[ñn]a|sol|retiro|lavapi[eé]s)\b/i;

function isDiscoveryQuery(t) {
  return (_RX_DISC_PLACE.test(t) && (_RX_DISC_VERB.test(t) || _RX_DISC_LOC.test(t)));
}

const _SHORT_PROMPT_HINTS = {
  text:     'Add who the answer is for, what format you expect, and a max length.',
  code:     'Add the programming language, what the function should do, and expected inputs/outputs.',
  image:    'Add a main subject, a visual style (photorealistic, illustration…) and an aspect ratio.',
  document: 'Add a target audience, approximate page count and expected sections.',
};

const _DISC_CTX_CHECKS = [
  [_RX_HAS_CUISINE,    'type of cuisine or category'],
  [_RX_HAS_ATMOSPHERE, 'atmosphere or occasion (romantic, casual, terrace…)'],
  [_RX_HAS_BUDGET,     'budget or price range'],
  [_RX_HAS_AREA,       'specific neighbourhood or area'],
];

function getSuggestions(text) {
  const suggestions = [];
  const t = text.toLowerCase();
  const trimmed = text.trimStart();
  const wc = text.trim().split(/\s+/).length;
  const type = detectOutputType(t);

  if (isDiscoveryQuery(t)) {
    const missingCtx = _DISC_CTX_CHECKS.filter(([rx]) => !rx.test(t)).map(([, label]) => label);
    if (missingCtx.length > 0) {
      suggestions.push({ strong: 'Add context before asking', rest: ` — the more specific you are, the less the model has to guess. Missing: ${missingCtx.join('; ')}.` });
    }
    suggestions.push({ strong: 'Consider Google Maps or Search instead', rest: ' — for finding real places nearby, a search engine is more accurate, uses live data, and consumes ~50× less energy per query than an AI model.' });
  }

  if (_RX_SENTIMENT.test(t))  suggestions.push({ strong: 'Remove personal commentary', rest: ' — phrases like "me lo paso muy bien" add no context and burn tokens without improving output. Replace sentiment with what you\'ve built so far, your skill level, or your goal.' });
  if (_RX_VAGUE_REQ.test(t) && wc < 50 && !_RX_FORMAT.test(t)) suggestions.push({ strong: '"Dame ideas" is too open-ended', rest: ' — specify domain, constraints and format: e.g. "List 5 beginner-friendly Claude API app ideas in one sentence each, focused on productivity."' });
  if (_RX_VAGUE_REVISION.test(t)) suggestions.push({ strong: 'Vague revision — specify what\'s wrong', rest: ' — "make it better" gives the model nothing to work with. Name the exact issue: contrast, spacing, copy, hierarchy, tone. Without it the model changes something random and you need another round.' });
  if (_RX_OUTSOURCE.test(t) && wc < 50) suggestions.push({ strong: 'Front-load your thinking', rest: ' — the model doesn\'t know your users, constraints or goals. Instead of asking what you should do, answer first: what exactly do you need, what are your constraints, and what does done look like?' });
  if (_RX_SCREENSHOT.test(t) && !_RX_CROP.test(t)) suggestions.push({ strong: 'Crop before uploading', rest: ' — a full-page screenshot (1000×1000 px) costs ~1,334 tokens. A crop of the specific component (200×200 px) costs ~54 tokens: 25× less. Always crop to just the relevant element.' });

  if (wc < 10) {
    const hint = _SHORT_PROMPT_HINTS[type] || 'Add more context.';
    suggestions.push({ strong: 'Prompt too short', rest: ` — ${hint} Vague prompts generate generic replies that require extra clarification rounds.` });
  }
  if (_RX_FILLER.test(t))                         suggestions.push({ strong: 'Remove courtesy phrases',       rest: ' — "please", "could you", "por favor", "podrías" add tokens without improving the output. Use direct imperatives: "Explain…", "List…".' });
  if (_RX_INTRO.test(trimmed))                    suggestions.push({ strong: 'Skip the greeting',             rest: ' — models don\'t have social state. Go straight to the instruction to save 5–10% of tokens.' });
  if ((t.match(_RX_VAGUE) || []).length >= 2)     suggestions.push({ strong: 'Replace vague expressions',     rest: ' — "kind of", "more or less", "something like" force the model to guess or ask for clarification. Be specific.' });
  if (type === 'text' && _RX_HIGH_VERB.test(trimmed))              suggestions.push({ strong: 'Consider a lower-energy verb',   rest: ' — "Analyze" / "Explain" generate long outputs (~20 Wh per response). "List", "Summarize", or "Define" can cut output by up to 60%.' });
  if (type === 'text' && wc > 30 && !_RX_OUT_LIMIT.test(t))        suggestions.push({ strong: 'Add an output limit',            rest: ' — e.g. "in 3 bullet points" or "under 150 words". Forces conciseness and removes filler. (~30–50% fewer output tokens)' });
  if (type === 'text' && wc > 50 && !_RX_FORMAT.test(t))           suggestions.push({ strong: 'Specify the output format',      rest: ' — table, list, JSON or numbered steps reduce ambiguity and often shorten the response. (~10–30% fewer output tokens)' });
  if (wc > 150 && !/\n/.test(text) && !text.includes('###') && !text.slice(0, 200).includes('-')) {
    suggestions.push({ strong: 'Add structure', rest: ' — long unformatted prompts are harder to follow. Separate Context, Task and Format with headers or line breaks. (~20–30% reduction + better response)' });
  }
  if (wc > 60) {
    const missing = [['role', _RX_ROLE], ['audience', _RX_AUDIENCE], ['tone', _RX_TONE]]
      .filter(([, rx]) => !rx.test(t)).map(([label]) => label);
    if (missing.length >= 2) suggestions.push({ strong: 'Incomplete ROCKS structure', rest: ` — missing: ${missing.join(', ')}. Adding role, audience and tone avoids 2–4 clarification rounds. E.g. "You are a… for beginners… in bullet points."` });
  }
  if (type === 'image' && !_RX_IMG_STYLE.test(t)) suggestions.push({ strong: 'Specify a visual style', rest: ' — without a style reference, image models produce generic results. Try "photorealistic", "digital illustration", "isometric 3D render". Each retry costs ~2–5× more energy than text.' });

  return suggestions;
}

// ─── Format helpers ───────────────────────────────────────
function fmt(n, decimals = 2) {
  return n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function fmtSeconds(s, action) {
  if (s < 60)    return `≈ ${s.toFixed(0)}s ${action}`;
  if (s < 3600)  return `≈ ${(s/60).toFixed(1)}min ${action}`;
  return `≈ ${(s/3600).toFixed(2)}h ${action}`;
}

// Returns a human-scale equivalent string, or '' if below threshold
function energyEquiv(kwh) {
  const s = kwh / LED_KW * 3600;
  return s >= 1 ? fmtSeconds(s, 'LED bulb') : '';
}

function co2Equiv(g) {
  const km = g / CAR_G_CO2_PER_KM;
  if (km >= 0.001) return `≈ ${km.toFixed(4)} km by car`;
  const searches = g / SEARCH_G_CO2;
  if (searches >= 0.01) return `≈ ${searches.toFixed(2)} Google searches`;
  return '';
}

function waterEquiv(ml) {
  const s = (ml / 1000) / TAP_L_PER_S;
  return s >= 1 ? fmtSeconds(s, 'tap running') : '';
}

// ─── Live token count ─────────────────────────────────────
promptInput.addEventListener('input', () => {
  const text   = promptInput.value.trim();
  cachedTokens = countTokens(text);
  const hasContent = text.length > 0;

  tokenCounter.textContent = `${cachedTokens.toLocaleString()} token${cachedTokens !== 1 ? 's' : ''}`;
  tokenCounter.classList.toggle('has-content', hasContent);
  analyzeBtn.disabled = !hasContent;
});

// ─── Exit animation helper ────────────────────────────────
function clearResults(callback) {
  const cards = resultsArea.querySelectorAll('.result-card');
  if (cards.length === 0) { callback(); return; }

  // Timeout safety net: if animationend never fires (e.g. prefers-reduced-motion,
  // animation already finished), invoke callback after the exit duration + buffer.
  const safety = setTimeout(callback, 250);
  let done = 0;
  cards.forEach(card => {
    card.classList.remove('visible');
    card.classList.add('exiting');
    card.addEventListener('animationend', () => {
      done++;
      if (done === cards.length) { clearTimeout(safety); callback(); }
    }, { once: true });
  });
}

// ─── Render results ───────────────────────────────────────
function renderResults(text) {
  const inputTokens  = cachedTokens;  // already computed by the input handler
  const outputTokens = Math.round(inputTokens * OUTPUT_RATIO);
  const totalTokens  = inputTokens + outputTokens;
  const energy_kwh   = (totalTokens / 1000) * KWH_PER_1K_TOKENS;
  const co2_g        = energy_kwh * CO2_KG_PER_KWH * 1000;
  const water_ml     = energy_kwh * WATER_L_PER_KWH * 1000;
  const cost         = (inputTokens  / 1000) * INPUT_PRICE_PER_1K
                     + (outputTokens / 1000) * OUTPUT_PRICE_PER_1K;
  const model        = recommendModel(text, inputTokens);
  const tips         = getSuggestions(text);

  const eEquiv = energyEquiv(energy_kwh);
  const cEquiv = co2Equiv(co2_g);
  const wEquiv = waterEquiv(water_ml);

  const group = document.createElement('div');
  group.className = 'results-group';

  // Card 1 — Metrics
  group.insertAdjacentHTML('beforeend', `
    <div class="result-card" role="region" aria-label="Resource metrics">
      <p class="card-label">Resource footprint</p>
      <div class="metrics-grid">
        <div class="metric-cell">
          <span class="metric-name">Energy</span>
          <span class="metric-value">${fmt(energy_kwh * 1000, 4)}</span>
          <span class="metric-unit">Wh</span>
          ${eEquiv ? `<span class="metric-equiv">${eEquiv}</span>` : ''}
        </div>
        <div class="metric-cell">
          <span class="metric-name">CO₂</span>
          <span class="metric-value">${fmt(co2_g, 4)}</span>
          <span class="metric-unit">grams</span>
          ${cEquiv ? `<span class="metric-equiv">${cEquiv}</span>` : ''}
        </div>
        <div class="metric-cell">
          <span class="metric-name">Water</span>
          <span class="metric-value">${fmt(water_ml, 3)}</span>
          <span class="metric-unit">ml</span>
          ${wEquiv ? `<span class="metric-equiv">${wEquiv}</span>` : ''}
        </div>
        <div class="metric-cell">
          <span class="metric-name">Est. cost</span>
          <span class="metric-value">$${fmt(cost, 5)}</span>
          <span class="metric-unit">USD</span>
        </div>
      </div>
    </div>`);

  // Card 2 — Summary (tokens + model recommendation)
  group.insertAdjacentHTML('beforeend', `
    <div class="result-card" role="region" aria-label="Prompt summary">
      <div class="card-inner">
        <div class="summary-row">
          <div class="summary-item">
            <span class="summary-label">Input tokens</span>
            <span class="summary-val">~${inputTokens.toLocaleString()}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Output est. (+40%)</span>
            <span class="summary-val">~${outputTokens.toLocaleString()}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Recommended model</span>
            <span class="model-badge model-badge--${model.tier}" aria-label="Recommended model: ${model.label}">
              <span class="model-dot" aria-hidden="true"></span>
              <span class="model-text">${model.label}</span>
            </span>
            <span class="model-reason">${model.reason}</span>
          </div>
        </div>
      </div>
    </div>`);

  // Card 3 — Suggestions (only if there are any)
  if (tips.length > 0) {
    const tipItems = tips.map(t => `
      <li class="suggestion-item">
        <span class="suggestion-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </span>
        <span class="suggestion-text"><strong>${t.strong}</strong>${t.rest}</span>
      </li>`).join('');

    group.insertAdjacentHTML('beforeend', `
      <div class="result-card" role="region" aria-label="Suggestions to reduce impact">
        <div class="card-inner">
          <p class="card-label">Ways to reduce impact</p>
          <ul class="suggestions-list" aria-label="Improvement suggestions">
            ${tipItems}
          </ul>
        </div>
      </div>`);
  }

  resultsArea.innerHTML = '';
  resultsArea.appendChild(group);

  // Trigger staggered enter animations on next frame
  requestAnimationFrame(() => {
    group.querySelectorAll('.result-card').forEach((card, i) => {
      card.style.animationDelay = `${i * 80}ms`;
      card.classList.add('visible');
    });
  });
}

// ─── Analyze button ───────────────────────────────────────
analyzeBtn.addEventListener('click', () => {
  const text = promptInput.value.trim();
  if (!text) return;

  // Enter analyzing state (icon swap)
  analyzeBtn.classList.add('analyzing');
  analyzeBtn.disabled = true;

  clearResults(() => {
    // Small deliberate pause — feels intentional, not instant
    setTimeout(() => {
      renderResults(text);
      analyzeBtn.classList.remove('analyzing');
      analyzeBtn.disabled = false;
    }, 320);
  });
});

// Also allow Enter+Cmd / Enter+Ctrl to submit
promptInput.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    if (!analyzeBtn.disabled) analyzeBtn.click();
  }
});

// Show placeholder hint when input is focused with no results yet
promptInput.addEventListener('focus', () => {
  if (resultsArea.querySelectorAll('.result-card').length === 0) {
    placeholder.classList.add('visible');
  }
});
promptInput.addEventListener('blur', () => {
  placeholder.classList.remove('visible');
});
