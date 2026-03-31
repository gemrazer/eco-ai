"""
Métricas de impacto ecológico basadas en investigación publicada.

Fuentes:
- Luccioni et al. (2023) "Power Hungry Processing" — energía por token de inferencia
- Strubell et al. (2019) — CO2 de entrenamiento/inferencia NLP
- Microsoft Sustainability Report 2023 — agua en centros de datos
- IEA Global Energy & CO2 Status 2023 — factor de emisión eléctrica
"""

from dataclasses import dataclass, field
from typing import Optional

from .config import Lang


# --- Constantes de referencia ---

# --- Tabla de equivalencias cotidianas ---
#
# Energía: bombilla LED estándar 10 W
#   kWh / 0.010 kW = horas encendida → × 3600 = segundos
#
# Agua: grifo doméstico ≈ 5 L/min = 0.0833 L/s
#   ml / 1000 / 0.0833 = segundos con el grifo abierto
#
# Solo se muestra cuando el equivalente es ≥ 1 segundo (sin sentido mostrar
# fracciones de segundo como equivalencia cotidiana).
_LED_KW      = 0.010          # 10 W LED
_TAP_L_PER_S = 5 / 60         # 5 L/min → L/s
_MIN_SECONDS = 1.0            # umbral mínimo para mostrar la equivalencia


def _fmt_seconds(seconds: float, action_es: str, action_en: str, lang: Lang) -> str:
    """Formatea segundos como '≈ Xs/Xmin/Xh <acción>' en el idioma indicado."""
    action = action_es if lang == Lang.ES else action_en
    if seconds < 60:
        return f"≈ {seconds:.0f} s {action}"
    minutes = seconds / 60
    if minutes < 60:
        return f"≈ {minutes:.1f} min {action}"
    return f"≈ {seconds / 3600:.2f} h {action}"

# Energía media de inferencia por 1 000 tokens (kWh)
# Modelos grandes tipo GPT-4 / Claude Opus: ~0.001–0.003 kWh / 1K tokens
# Modelos medianos tipo GPT-3.5 / Claude Haiku: ~0.0003 kWh / 1K tokens
# Fuente: Luccioni et al. 2023, estimaciones conservadoras
ENERGY_KWH_PER_1K_TOKENS = {
    "large":   0.0030,   # GPT-4, Claude Opus, Llama 70B
    "medium":  0.0008,   # GPT-3.5, Claude Sonnet, Llama 13B
    "small":   0.0003,   # Claude Haiku, Mistral 7B, modelos ligeros
}

# Factor de emisión de CO₂ por kWh (kg CO₂e / kWh)
# Promedio global 2023 ≈ 0.38 kg, servidores de nube ≈ 0.2–0.4 kg
CO2_KG_PER_KWH = 0.30  # valor moderado-realista para grandes nubes (AWS, Azure, GCP)

# Uso de agua por kWh en centros de datos (litros / kWh)
# Cooling towers: ~1.8 L/kWh  |  air-cooled: ~0.2 L/kWh  |  media: ~0.9 L/kWh
WATER_L_PER_KWH = 0.90

# Precios por 1 000 tokens (USD), input/output — marzo 2026
MODEL_PRICES_USD = {
    "Claude Opus 4.6":   {"input": 0.015,  "output": 0.075},
    "Claude Sonnet 4.6": {"input": 0.003,  "output": 0.015},
    "Claude Haiku 4.5":  {"input": 0.00025,"output": 0.00125},
    "Claude Opus 4":     {"input": 0.015,  "output": 0.075},
    "Claude Sonnet 4":   {"input": 0.003,  "output": 0.015},
    "Claude Haiku 4":    {"input": 0.00025,"output": 0.00125},
    "GPT-4o":            {"input": 0.005,  "output": 0.015},
    "GPT-4o mini":       {"input": 0.00015,"output": 0.0006},
    "Gemini 1.5 Pro":    {"input": 0.00125,"output": 0.005},
    "Llama 3 70B (API)": {"input": 0.00059,"output": 0.00079},
}

MODEL_TIER = {
    "Claude Opus 4.6":   "large",
    "Claude Sonnet 4.6": "medium",
    "Claude Haiku 4.5":  "small",
    "Claude Opus 4":     "large",
    "Claude Sonnet 4":   "medium",
    "Claude Haiku 4":    "small",
    "GPT-4o":            "large",
    "GPT-4o mini":       "small",
    "Gemini 1.5 Pro":    "medium",
    "Llama 3 70B (API)": "large",
}


@dataclass
class EcoImpact:
    tokens: int
    energy_kwh: float
    co2_g: float
    water_ml: float
    cost_usd: Optional[float]
    model: str
    lang: Lang = field(default=Lang.ES)

    @property
    def co2_equiv(self) -> str:
        """Convierte gramos de CO₂ a equivalentes cotidianos."""
        # ~170 g CO₂ = 1 km en coche; ~0.14 g = 1 búsqueda Google (estimación)
        km_car = self.co2_g / 170
        if km_car >= 0.001:
            return (
                f"≈ {km_car:.4f} km en coche"
                if self.lang == Lang.ES else
                f"≈ {km_car:.4f} km by car"
            )
        searches = self.co2_g / 0.14
        if searches >= 0.01:
            return (
                f"≈ {searches:.2f} búsquedas en Google"
                if self.lang == Lang.ES else
                f"≈ {searches:.2f} Google searches"
            )
        return (
            "< 0.01 búsquedas en Google"
            if self.lang == Lang.ES else
            "< 0.01 Google searches"
        )

    @property
    def water_equiv(self) -> str:
        if self.water_ml >= 1000:
            return f"{self.water_ml/1000:.3f} L"
        if self.water_ml >= 0.01:
            return f"{self.water_ml:.2f} mL"
        return "< 0.01 mL"

    @property
    def energy_time_equiv(self) -> str:
        """Equivalencia cotidiana de energía: segundos con una bombilla LED (10 W).
        Devuelve cadena vacía si el equivalente es menor de 1 segundo."""
        seconds = self.energy_kwh / _LED_KW * 3600
        if seconds < _MIN_SECONDS:
            return ""
        return _fmt_seconds(seconds, "con una bombilla LED encendida", "with an LED bulb on", self.lang)

    @property
    def water_time_equiv(self) -> str:
        """Equivalencia cotidiana de agua: segundos con el grifo abierto (5 L/min).
        Devuelve cadena vacía si el equivalente es menor de 1 segundo."""
        seconds = (self.water_ml / 1000) / _TAP_L_PER_S
        if seconds < _MIN_SECONDS:
            return ""
        return _fmt_seconds(seconds, "con el grifo abierto", "with the tap running", self.lang)


def calculate_impact(tokens: int, model: str, output_ratio: float = 0.4, lang: Lang = Lang.ES) -> EcoImpact:
    """
    Estima el impacto ecológico dado el número de tokens de entrada.

    output_ratio: fracción estimada de tokens de salida respecto a los de entrada.
    """
    tier = MODEL_TIER.get(model, "medium")
    energy_per_1k = ENERGY_KWH_PER_1K_TOKENS[tier]

    output_tokens = int(tokens * output_ratio)
    total_tokens = tokens + output_tokens

    energy_kwh = (total_tokens / 1000) * energy_per_1k
    co2_g = energy_kwh * CO2_KG_PER_KWH * 1000  # kg → g
    water_ml = energy_kwh * WATER_L_PER_KWH * 1000  # L → mL

    cost_usd = None
    if model in MODEL_PRICES_USD:
        prices = MODEL_PRICES_USD[model]
        cost_usd = (tokens / 1000) * prices["input"] + (output_tokens / 1000) * prices["output"]

    return EcoImpact(
        tokens=tokens,
        energy_kwh=energy_kwh,
        co2_g=co2_g,
        water_ml=water_ml,
        cost_usd=cost_usd,
        model=model,
        lang=lang,
    )
