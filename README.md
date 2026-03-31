# eco-ai

A command-line tool to estimate the ecological impact of your AI prompts and improve how you write them.

It calculates energy consumption, CO₂ emissions, water usage, and API cost — all **locally**, without sending any data to external servers.

---

## Installation

Requires **Python ≥ 3.8**. Pick the method that suits you:

| Method | Command | Notes |
|--------|---------|-------|
| **pipx** ⭐ | `pipx install eco-ai` | Recommended — isolated install, no conflicts |
| **pip** | `pip install eco-ai` | Use inside a virtual environment |
| **uv** | `uv tool install eco-ai` | Fastest option if you already use uv |

> **Don't have Python yet?** Download it from [python.org/downloads](https://www.python.org/downloads/) — no custom settings needed during install.

<details>
<summary>Manual install (for contributors)</summary>

```bash
git clone https://github.com/your-username/eco-ai.git
cd eco-ai
pip install -e .
```

</details>

Verify the install:

```bash
eco-ai --help
```

---

## Usage

```bash
eco-ai analyze "Explain what climate change is and what its main causes are"
```

eco-ai will show you:
- The **estimated ecological impact** of your prompt (energy, CO₂, water, and API cost)
- The **detected task type** and its energy consumption level
- **Concrete suggestions** to reduce the impact by rewriting your prompt more efficiently
- The **recommended AI model** based on the complexity of your request

### Other commands

```bash
# Compare the impact of the same prompt across all available models
eco-ai compare "your prompt here"

# List all available models and their prices
eco-ai models

# Interactive usage guide
eco-ai guide

# Change the language of suggestions (es / en)
eco-ai config --lang en
```

### Options for `analyze`

| Option | Description | Default |
|--------|-------------|---------|
| `-m / --model` | Reference model for the calculation | Claude Sonnet 4.6 |
| `-f / --file` | Read the prompt from a text file | — |
| `-t / --output-type` | Expected output type: `auto`, `text`, `image`, `code`, `pdf`, `artifact` | auto |
| `--output-ratio` | Estimated fraction of output tokens relative to input | 0.4 |
| `--lang` | Prompt language (`es` or `en`) | Saved config |
| `--verbose` | Show bibliographic references for each suggestion | — |
| `--no-tips` | Show only metrics, no suggestions | — |
| `-y / --yes` | Skip the privacy consent screen | — |

---

## Supported models

| Tier | Models |
|------|--------|
| small | Claude Haiku 4.5, GPT-4o mini |
| medium | Claude Sonnet 4.6, Claude Sonnet 4, Gemini 1.5 Pro |
| large | Claude Opus 4.6, Claude Opus 4, GPT-4o, Llama 3 70B |

---

## How it works

1. **Tokenisation** — counts tokens using `tiktoken` (cl100k_base) or approximates with words × 1.3
2. **Energy metrics** — estimates kWh based on the model tier (Luccioni et al., 2023)
3. **CO₂** — converts energy to emissions using a cloud provider emission factor (IEA, 2023)
4. **Water** — estimates data centre cooling consumption (Microsoft Sustainability Report, 2023)
5. **Prompt analysis** — detects high-energy verbs, missing output limits, incomplete ROCKS structure, courtesy phrases, vague language, and more
6. **Model recommendation** — suggests the most appropriate tier based on the prompt's complexity

---

## Sources

- Luccioni et al. (2023) *Power Hungry Processing: Scrutinizing Energy Use in NLP*
- Liu et al. (2023) *Lost in the Middle: How Language Models Use Long Contexts*
- Min et al. (2022) *Rethinking the Role of Demonstrations in Few-Shot Prompting*
- Webson & Pavlick (2021) *Do Prompt-Based Models Really Understand the Meaning of Their Prompts?*
- Anthropic Prompt Engineering Guide (2024)

---

## Privacy

All analysis happens on your device. Your prompt text is never sent to any external server.

---

## License

MIT © [Maria Prokhorova](https://github.com/your-username)
