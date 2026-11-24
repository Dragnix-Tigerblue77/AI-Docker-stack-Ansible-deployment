<!--
SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
SPDX-License-Identifier: AGPL-3.0-only
-->

# Catalogue de la passerelle LiteLLM

> Ce fichier est généré par `python3 .github/scripts/generate_catalog.py` à partir du modèle de configuration de LiteLLM (`templates/LiteLLM_config.yaml.j2`) et des contrats des routeurs (`.github/LiteLLM_router_contracts.yaml`). Ne le modifiez pas à la main : la CI refuse un fichier qui n'est pas ce que ces sources produisent, et un changement de l'un ou de l'autre le régénère dans le même commit.

Ce catalogue dit tout ce que la passerelle sert : les groupes d'accès, les routeurs et leurs membres, les fournisseurs, et chaque modèle. Il décrit la configuration rendue avec la clé de tous les fournisseurs donnée.

## Sommaire

- [Les groupes d'accès et les types de LiteLLM](#les-groupes-daccès-et-les-types-de-litellm)
- [Les routeurs](#les-routeurs)
  - [`Auto`](#auto)
  - [`Auto-Pro`](#auto-pro)
  - [`Auto-Flash`](#auto-flash)
  - [`Auto-Flash-Lite`](#auto-flash-lite)
  - [`Auto-Code`](#auto-code)
  - [`Auto-Claude-Code`](#auto-claude-code)
  - [`Auto-STT`](#auto-stt)
  - [`Auto-TTS`](#auto-tts)
  - [`Auto-Decision`](#auto-decision)
  - [`Auto-Extraction`](#auto-extraction)
  - [`Auto-Fiction`](#auto-fiction)
- [Les fournisseurs](#les-fournisseurs)
  - [Les quotas que déclarent les contrats](#les-quotas-que-déclarent-les-contrats)
- [Les modèles](#les-modèles)

## Les groupes d'accès et les types de LiteLLM

Chaque entrée est dans le groupe de son type, ce qui permet de limiter une clé virtuelle à un type de modèles dans l'interface de LiteLLM. Les groupes sont des étiquettes que ce dépôt pose sur les entrées (`model_info.access_groups`), alors que le type est le `model_info.mode` de LiteLLM, un ensemble borné : une entrée sans `mode` est un modèle de conversation. Un routeur suit sa tête : une clé qui atteint l'entrée atteint les routeurs dont elle est la tête.

| Groupe | Type LiteLLM | Usage | Remarque |
| --- | --- | --- | --- |
| `LLM` | chat (aucun `mode`) | Texte : conversation et complétion | — |
| `STT` | `audio_transcription` | Transcription de la parole (`/audio/transcriptions`) | — |
| `TTS` | `audio_speech` | Synthèse vocale (`/audio/speech`) | — |
| `Embeddings` | `embedding` | Vecteurs d'un texte (`/embeddings`) | — |
| `Decisions` | `evaluation` | Décisions typées | — |
| `Extraction` | `extraction` | Extraction typée | — |
| `Images` | `image_generation` | Génération d'images (`/images/generations`) | — |
| `Videos` | `video_generation` | Génération de vidéos (`/videos`) | — |
| `Rerank` | `rerank` | Reclassement de documents (`/rerank`) | — |
| `Moderation` | `moderation` | Modération de contenu (`/moderations`) | — |
| `OCR` | `ocr` | Lecture du texte d'une image ou d'un PDF (`/ocr`) | — |
| `Fiction` | chat (aucun `mode`) | Texte : conversation et complétion | mis à part : seules les entrées qui lisent la clé de Aion Labs en font partie, et aucune clé qui n'a que `LLM` ne les atteint |

Ces groupes s'ajoutent au groupe du type : une entrée qui en porte un est aussi dans celui de son type, et la ligne dit sur quel groupe de type il se trouve.

| Groupe supplémentaire | Groupe de type |
| --- | --- |
| `Private-Data` | `Decisions` |
| `Private-Data` | `Embeddings` |
| `Private-Data` | `Extraction` |
| `Private-Data` | `Fiction` |
| `Private-Data` | `LLM` |
| `Private-Data` | `STT` |
| `Private-Data` | `TTS` |
| `Claude-Code` | `LLM` |
| `Public-Data-Only` | `Embeddings` |
| `Public-Data-Only` | `LLM` |
| `Public-Data-Only` | `STT` |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les routeurs

Un routeur est un nom que le client écrit et derrière lequel LiteLLM essaie les membres de sa cascade dans l'ordre, en passant au suivant quand un membre échoue. Les cascades ci-dessous sont celles du modèle rendu avec la clé de tous les fournisseurs : sans la clé d'un fournisseur, ses entrées disparaissent et l'ordre des autres ne change pas. Le rôle d'un routeur est la première phrase du commentaire qui ouvre sa cascade dans le modèle, en anglais comme lui ; le reste vient des contrats des routeurs. Les membres d'une cascade sont dans l'ordre de ses lignes, le premier d'abord.

| Routeur | Rôle | Tête |
| --- | --- | --- |
| `Auto` | Aiguille chaque requête vers `Auto-Flash-Lite`, `Auto-Flash`, `Auto-Pro` selon sa complexité | — |
| `Auto-Pro` | Pure reasoning, multi-step logic, architecture | `gemini-4-hydrogen` |
| `Auto-Flash` | Balanced daily driver | `gemini-4-hydrogen` |
| `Auto-Flash-Lite` | Simple, short asks | `gemini-3-5-flash-lite` |
| `Auto-Code` | Refactoring, Ansible playbooks, Bash/Python scripts | `gemini-4-hydrogen` |
| `Auto-Claude-Code` | 100% agentic CLI (strict tool/function calling, 128k+ context) | `gemini-4-hydrogen` |
| `Auto-STT` | Speech to text, for "/audio/transcriptions" | `whisper-large-v3-groq` |
| `Auto-TTS` | Text to speech, for /audio/speech | `gemini-3-8-flash-tts` |
| `Auto-Decision` | Clef's typed decisions, for "/v1/systemone" and "/v1/decisions" | `clef-cloudflare` |
| `Auto-Extraction` | Clairic's typed extraction, for "/v1/extraction" | `clairic-cloudflare` |
| `Auto-Fiction` | The role-play and fiction models of Aion Labs, and only those | `aion-3-5-aion-labs` |

### `Auto`

Cette entrée n'a pas de cascade : le routeur qu'elle choisit a la sienne.

| Complexité de la requête | Routeur choisi |
| --- | --- |
| `SIMPLE` | `Auto-Flash-Lite` |
| `MEDIUM` | `Auto-Flash` |
| `COMPLEX` | `Auto-Pro` |
| `REASONING` | `Auto-Pro` |

### `Auto-Pro`

- Classement : indice d'intelligence
- Derniers recours : `deepseek-v4-pro-direct`, `omniroute-free-reasoning`

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | `xhigh` | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| `gemini-3-8-flash` | Gemini | `high` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `beam-kilo` | Kilo | — | — |
| `nemotron-ultra-free` | OpenRouter | `high` | — |
| `nemotron-ultra-requesty` | Requesty | `max` | — |
| `nemotron-ultra-nvidia` | NVIDIA | — | — |
| `nemotron-ultra-kilo` | Kilo | `high` | — |
| `nemotron-reasoning-free` | OpenRouter | — | — |
| `nemotron-reasoning-requesty` | Requesty | `max` | — |
| `nemotron-reasoning-nvidia` | NVIDIA | — | — |
| `nemotron-reasoning-kilo` | Kilo | — | — |
| `nemotron-super-vl-free` | OpenRouter | — | — |
| `nemotron-super-vl-nvidia` | NVIDIA | — | — |
| `nemotron-super-vl-kilo` | Kilo | — | — |
| `hy4-flash-cent-ai` | Cent AI | — | — |
| `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| `qwen3-5-397b-ovh` | OVHcloud | — | — |
| `gpt-oss-120b-ovh` | OVHcloud | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | défaut : high | dernier recours |
| `omniroute-free-reasoning` | OmniRoute | — | dernier recours |

### `Auto-Flash`

- Classement : indice d'intelligence
- Derniers recours : `deepseek-flash-direct`, `omniroute-free-auto`, `openrouter-auto-free`

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | `xhigh` | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| `gemini-3-8-flash` | Gemini | `high` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `gemini-3-6-flash` | Gemini | `high` | — |
| `gemini-3-flash-preview` | Gemini | `high` | — |
| `gpt-oss-120b-groq` | Groq | défaut : medium | — |
| `gpt-oss-120b-cloudflare` | Cloudflare | défaut : medium | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `gemma-4-31b-gemini` | Gemini | — | — |
| `gemma-4-31b-free` | OpenRouter | — | — |
| `gemma-4-31b-requesty` | Requesty | `high` | — |
| `gemma-4-31b-nvidia` | NVIDIA | — | — |
| `particle-1-free` | OpenRouter | `xhigh` | — |
| `particle-1-kilo` | Kilo | `max` | — |
| `ernie-5-5-flash-free` | OpenRouter | `high` | — |
| `ernie-5-5-flash-kilo` | Kilo | `high` | — |
| `beam-kilo` | Kilo | — | — |
| `nemotron-super-vl-free` | OpenRouter | — | — |
| `nemotron-super-vl-nvidia` | NVIDIA | — | — |
| `muse-glimmer-nvidia` | NVIDIA | — | — |
| `nemotron-super-vl-kilo` | Kilo | — | — |
| `flint-kilo` | Kilo | — | — |
| `glyph-cluster-kilo` | Kilo | — | — |
| `dots-3-note-preview-free` | OpenRouter | — | — |
| `dots-3-note-preview-kilo` | Kilo | — | — |
| `openrouter-auto-free` | OpenRouter | — | dernier recours |
| `hy4-flash-cent-ai` | Cent AI | — | — |
| `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| `qwen3-5-397b-ovh` | OVHcloud | — | — |
| `gpt-oss-120b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| `qwen3-6-35b-ovh` | OVHcloud | — | — |
| `nemotron3-omni-30b-ovh` | OVHcloud | — | — |
| `mistral-small-3-2-ovh` | OVHcloud | — | — |
| `mistral-medium` | Mistral | — | — |
| `mistral-small` | Mistral | — | — |
| `ministral-14b` | Mistral | — | — |
| `ministral-8b` | Mistral | — | — |
| `deepseek-flash-direct` | DeepSeek | défaut : high | dernier recours |
| `omniroute-free-auto` | OmniRoute | — | dernier recours |

### `Auto-Flash-Lite`

- Classement : indice d'intelligence, moins le temps jusqu'au premier jeton de la réponse
- Quota partagé avec : `Auto-Pro`, `Auto-Flash` : un membre qui est le même modèle chez le même fournisseur que l'un de leurs membres passe en dernier
- Derniers recours : `ministral-3b`, `omniroute-free-fast`

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-3-5-flash-lite` | Gemini | défaut : minimal | — |
| `gemini-3-1-flash-lite` | Gemini | défaut : minimal | — |
| `lfm-3-1-7b-free` | OpenRouter | — | — |
| `lfm-3-1-7b-kilo` | Kilo | — | — |
| `nemotron-lightning-free` | OpenRouter | — | — |
| `nemotron-lightning-requesty` | Requesty | — | — |
| `nemotron-lightning-nvidia` | NVIDIA | — | — |
| `nemotron-lightning-kilo` | Kilo | — | — |
| `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare | — | — |
| `gemma-3-4b-nvidia` | NVIDIA | — | — |
| `llama-3-3-70b-cloudflare` | Cloudflare | — | — |
| `gemma-3-12b-nvidia` | NVIDIA | — | — |
| `gpt-oss-20b-groq` | Groq | défaut : medium | — |
| `gpt-oss-20b-cloudflare` | Cloudflare | défaut : medium | — |
| `gemma-4-26b-gemini` | Gemini | — | — |
| `gemma-4-26b-free` | OpenRouter | — | — |
| `gemma-4-26b-cloudflare` | Cloudflare | — | — |
| `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare | — | — |
| `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare | — | — |
| `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare | — | — |
| `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare | — | — |
| `granite-4-0-h-micro-cloudflare` | Cloudflare | — | — |
| `nemotron-bolt-e4b-nvidia` | NVIDIA | — | — |
| `gpt-oss-20b-ovh` | OVHcloud | — | — |
| `gemma-4-26b-ovh` | OVHcloud | — | — |
| `nemotron3-nano-30b-ovh` | OVHcloud | — | — |
| `qwen3-5-9b-ovh` | OVHcloud | — | — |
| `olala-mini-ovh` | OVHcloud | — | — |
| `gemini-3-8-flash-low` | Gemini | `low` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `gemini-4-hydrogen-low` | Gemini | `low` | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `hy4-flash-cent-ai` | Cent AI | — | — |
| `ministral-3b` | Mistral | — | dernier recours |
| `omniroute-free-fast` | OmniRoute | — | dernier recours |

### `Auto-Code`

- Classement : position dans les benchmarks de code
- Derniers recours : `deepseek-v4-pro-direct`, `omniroute-free-code`

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | `xhigh` | — |
| `gemini-3-8-flash` | Gemini | `high` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `gemini-3-6-flash` | Gemini | `high` | — |
| `muse-glimmer-nvidia` | NVIDIA | — | — |
| `laguna-xs-2-1-nvidia` | NVIDIA | — | — |
| `glm-4-7-flash-cloudflare` | Cloudflare | — | — |
| `glm-4-7-flash-zai` | Zai | — | — |
| `deepseek-v4-1-flash-ovh` | OVHcloud | — | — |
| `qwen3-5-397b-ovh` | OVHcloud | — | — |
| `gpt-oss-120b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-ovh` | OVHcloud | — | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| `qwen3-6-35b-ovh` | OVHcloud | — | — |
| `laguna-xs-2-1-ovh` | OVHcloud | — | — |
| `codestral` | Mistral | — | — |
| `codestral-2508` | Mistral | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | défaut : high | dernier recours |
| `omniroute-free-code` | OmniRoute | — | dernier recours |

### `Auto-Claude-Code`

- Dérive de : `Auto-Code`, ordonné de la même façon, sans les membres qui ne répondent pas aux exigences ci-dessous
- Exige des membres : les appels d'outils

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | `xhigh` | — |
| `gemini-3-8-flash` | Gemini | `high` | — |
| `gemini-3-7-flash` | Gemini | — | — |
| `glm-5-3-flash-nvidia` | NVIDIA | défaut : max | — |
| `kimi-k3-1-pro-nvidia` | NVIDIA | — | — |
| `step-5-preview-nvidia` | NVIDIA | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | — | — |
| `mistral-large-4-nvidia` | NVIDIA | défaut : high | — |
| `qwen3-8-27b-groq` | Groq | défaut : non-reasoning | — |
| `gemini-3-6-flash` | Gemini | `high` | — |
| `muse-glimmer-nvidia` | NVIDIA | — | — |
| `laguna-xs-2-1-nvidia` | NVIDIA | — | — |
| `glm-4-7-flash-cloudflare` | Cloudflare | — | — |
| `glm-4-7-flash-zai` | Zai | — | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | défaut : xhigh | — |
| `codestral` | Mistral | — | — |
| `codestral-2508` | Mistral | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | défaut : high | — |

### `Auto-STT`


| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `whisper-large-v3-groq` | Groq | — | — |
| `whisper-large-v3-turbo-groq` | Groq | — | — |
| `gemini-3-5-transcribe` | Gemini | — | — |
| `voxtral-mini-mistral` | Mistral | — | — |

### `Auto-TTS`


| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `gemini-3-8-flash-tts` | Gemini | — | — |
| `gemini-3-8-flash-lite-tts` | Gemini | — | — |

### `Auto-Decision`


| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `clef-cloudflare` | Cloudflare | — | — |
| `clef-omni-cloudflare` | Cloudflare | — | — |
| `clef-flash-cloudflare` | Cloudflare | — | — |

### `Auto-Extraction`


| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `clairic-cloudflare` | Cloudflare | — | — |
| `clairic-flash-cloudflare` | Cloudflare | — | — |

### `Auto-Fiction`

- Classement : indice d'intelligence

| Entrée | Fournisseur | Niveau | Remarque |
| --- | --- | --- | --- |
| `aion-3-5-aion-labs` | Aion Labs | — | — |
| `aion-3-5-mini-aion-labs` | Aion Labs | — | — |
| `aion-3-0-aion-labs` | Aion Labs | — | — |
| `aion-3-0-mini-aion-labs` | Aion Labs | — | — |
| `aion-2-0-aion-labs` | Aion Labs | — | — |
| `aion-rp-llama-3-1-8b-aion-labs` | Aion Labs | — | — |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les fournisseurs

Un fournisseur est celui que lit l'entrée : la clé dont la variable est donnée, ou une passerelle qui n'en demande aucune. Un fournisseur dont la clé n'est pas donnée n'a aucune entrée dans la configuration rendue.

| Fournisseur | Variable de la clé |
| --- | --- |
| Gemini | `Artificial_Intelligence_LiteLLM_Gemini_API_key` |
| Mistral | `Artificial_Intelligence_LiteLLM_Mistral_API_key` |
| Groq | `Artificial_Intelligence_LiteLLM_Groq_API_key` |
| OpenRouter | `Artificial_Intelligence_LiteLLM_OpenRouter_API_key` |
| DeepSeek | `Artificial_Intelligence_LiteLLM_DeepSeek_API_key` |
| Cloudflare | `Artificial_Intelligence_LiteLLM_Cloudflare_API_key` |
| Zai | `Artificial_Intelligence_LiteLLM_Zai_API_key` |
| Requesty | `Artificial_Intelligence_LiteLLM_Requesty_API_key` |
| NVIDIA | `Artificial_Intelligence_LiteLLM_NVIDIA_API_key` |
| Cent AI | `Artificial_Intelligence_LiteLLM_Cent_AI_API_key` |
| Aion Labs | `Artificial_Intelligence_LiteLLM_Aion_Labs_API_key` |
| Kilo | sans clé |
| OVHcloud | sans clé |
| OmniRoute | sans clé |

Les routeurs où figure chaque fournisseur, une ligne par routeur :

| Fournisseur | Routeur |
| --- | --- |
| Gemini | `Auto-Pro` |
| Gemini | `Auto-Flash` |
| Gemini | `Auto-Flash-Lite` |
| Gemini | `Auto-Code` |
| Gemini | `Auto-Claude-Code` |
| Gemini | `Auto-STT` |
| Gemini | `Auto-TTS` |
| Mistral | `Auto-Flash` |
| Mistral | `Auto-Flash-Lite` |
| Mistral | `Auto-Code` |
| Mistral | `Auto-Claude-Code` |
| Mistral | `Auto-STT` |
| Groq | `Auto-Flash` |
| Groq | `Auto-Flash-Lite` |
| Groq | `Auto-Code` |
| Groq | `Auto-Claude-Code` |
| Groq | `Auto-STT` |
| OpenRouter | `Auto-Pro` |
| OpenRouter | `Auto-Flash` |
| OpenRouter | `Auto-Flash-Lite` |
| DeepSeek | `Auto-Pro` |
| DeepSeek | `Auto-Flash` |
| DeepSeek | `Auto-Code` |
| DeepSeek | `Auto-Claude-Code` |
| Cloudflare | `Auto-Flash` |
| Cloudflare | `Auto-Flash-Lite` |
| Cloudflare | `Auto-Code` |
| Cloudflare | `Auto-Claude-Code` |
| Cloudflare | `Auto-Decision` |
| Cloudflare | `Auto-Extraction` |
| Zai | `Auto-Code` |
| Zai | `Auto-Claude-Code` |
| Requesty | `Auto-Pro` |
| Requesty | `Auto-Flash` |
| Requesty | `Auto-Flash-Lite` |
| NVIDIA | `Auto-Pro` |
| NVIDIA | `Auto-Flash` |
| NVIDIA | `Auto-Flash-Lite` |
| NVIDIA | `Auto-Code` |
| NVIDIA | `Auto-Claude-Code` |
| Cent AI | `Auto-Pro` |
| Cent AI | `Auto-Flash` |
| Cent AI | `Auto-Flash-Lite` |
| Aion Labs | `Auto-Fiction` |
| Kilo | `Auto-Pro` |
| Kilo | `Auto-Flash` |
| Kilo | `Auto-Flash-Lite` |
| OVHcloud | `Auto-Pro` |
| OVHcloud | `Auto-Flash` |
| OVHcloud | `Auto-Flash-Lite` |
| OVHcloud | `Auto-Code` |
| OmniRoute | `Auto-Pro` |
| OmniRoute | `Auto-Flash` |
| OmniRoute | `Auto-Flash-Lite` |
| OmniRoute | `Auto-Code` |

### Les quotas que déclarent les contrats

Ce que dit `.github/LiteLLM_router_contracts.yaml`, tel quel, des limites de chaque fournisseur : ce sont des déclarations datées, qu'aucun contrôle ne vérifie.

- **Gemini** : Free tier, counted per Google project and per model, not per API key, and the daily quotas reset at midnight Pacific time, per ai.google.dev/gemini-api/docs/rate-limits (read 2026-11-22). The page of the rate limits of Google AI Studio for the gateway's project, free tier, read 2026-11-22, gives requests per minute / tokens per minute / requests per day per model: Gemini 4 Hydrogen, Gemini 3.8 Flash, Gemini 3.6 Flash, Gemini 3 Flash and Gemini 2.5 Flash 5 / 250K / 20; Gemini 3.5 Flash-Lite and Gemini 3.1 Flash-Lite 15 / 250K / 500; Gemini 2.5 Flash-Lite 10 / 250K / 20; Gemma 4 31B and Gemma 4 26B 30 / 16K / 14,400; Gemini Embedding 1 and 2 100 / 30K / 1,000; the text-to-speech models 3 / 10K / 10; Gemini 3.5 Transcribe 3 / 10K / 25; Gemini 3.1 Pro, Gemini 2.5 Pro and Gemini 4 Argon, Neon and Carbon 0, not served on the free tier; Gemini 3.7 Flash is not on that page. Every entry of one model draws on that model's quota: gemini-4-hydrogen and gemini-4-hydrogen-low share one 20 requests a day, and so do gemini-3-8-flash and gemini-3-8-flash-low
- **Mistral** : Paid, a prepaid balance: Free mode no longer includes the API, per docs.mistral.ai/admin/billing-usage/usage-limits (read 2026-11-21); per-model limits only in the account's admin panel
- **Groq** : Free plan, 30 requests and 8K tokens per minute for these models, per console.groq.com/docs/rate-limits as the template quotes it (checked 2026-09-27)
- **OpenRouter** : 20 requests per minute and 50 per day, 1000 once 10 credits are bought, counted across every :free model of the account together, per openrouter.ai/docs/api_reference/limits as the template quotes it (checked 2026-09-27)
- **DeepSeek** : No free quota: a prepaid balance, per api-docs.deepseek.com/faq as the template quotes it (checked 2026-09-27)
- **Cloudflare** : 10,000 neurons a day for the whole account, shared by all its models, and 300 requests per minute for text generation, per developers.cloudflare.com/workers-ai/platform/pricing/ and .../platform/limits/ (read 2026-11-22); the models routed are deduced free from the pricing page's list of paid ones, and confirmed on no account
- **Zai** : unknown: Z AI publishes no limit outside the account's console (docs.z.ai, read 2026-11-22), and the one-request-at-a-time limit a third party cites is not verified
- **Requesty** : 200 requests a day and 20 a minute for a new organization (1,000 and 60 for one that pays), counted across every free model of the organization together, per the Free models page of the Requesty docs (read 2026-11-22), which also says the models are free for now and that a change will be announced in the changelog ahead of time
- **NVIDIA** : 40 requests per minute, shown on the account page (read 2026-11-22); no credit count, daily cap or end date is shown there or on any other page read, the API trial terms of service included
- **Cent AI** : no limit stated: the home page says "Free until Nov 30 · no daily limit" (read 2026-11-22) and nothing of what follows the 30th, when the model may be billed; a spending limit set on the key keeps a billed call from costing anything, since the call then fails and the cascade moves on
- **Aion Labs** : 15 requests a minute, 20,000 tokens a minute and 20,000 tokens a day for the whole account, all models together, on the free tier of the Rate Limits page of its documentation (read 2026-11-23); its terms of 2026-10-17 call free use "a courtesy that we may change or withdraw at any time"
- **Kilo** : Anonymous, no key and no account: 200 requests per hour per IP address, for the free models only, per the Authentication and Models and providers pages of the Kilo gateway documentation (read 2026-11-22); the free models' availability changes, and each flags that prompts may be trained on
- **OVHcloud** : Anonymous, no key and no account: 2 requests per minute per IP address and per model, observed from the maintainer's network on 2026-11-22 (a second call within the minute answered 429) and written on no page read, so one pool per entry, shared by the whole house; with a key, 400 a minute, but a payment method on a Public Cloud project is required and no spend cap exists (OVHcloud AI Endpoints page, read 2026-11-22)
- **OmniRoute** : No quota: local and keyless

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)

## Les modèles

Une ligne par entrée de la liste des modèles, dans l'ordre du modèle. La fenêtre de contexte et la réponse la plus longue sont celles que le fournisseur sert, `model_info.max_input_tokens` et `model_info.max_output_tokens`. Le niveau est le `reasoning_effort` que le modèle fixe, sinon celui auquel les contrats disent que le fournisseur appelle l'entrée par défaut. Un tiret veut dire qu'aucune source ne donne la valeur. L'indice d'intelligence et le temps jusqu'au premier jeton n'ont pas de colonne : ils viennent d'Artificial Analysis, que la vérification hebdomadaire des modèles lit en ligne, et aucun fichier du dépôt ne les garde.

| Entrée | Fournisseur | Type | Groupes | Routeurs | Niveau | Contexte | Sortie max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gemini-4-hydrogen` | Gemini | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | `xhigh` | 1 048 576 | 65 536 |
| `gemini-4-hydrogen-low` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | `low` | 1 048 576 | 65 536 |
| `gemini-3-8-flash` | Gemini | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | `high` | 1 048 576 | 65 536 |
| `gemini-3-8-flash-low` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | `low` | 1 048 576 | 65 536 |
| `gemini-3-7-flash` | Gemini | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code` | — | 1 048 576 | 65 536 |
| `gemini-3-6-flash` | Gemini | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | `high` | 1 048 576 | 65 536 |
| `gemini-3-5-flash-lite` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | défaut : minimal | 1 048 576 | 65 536 |
| `gemini-3-1-flash-lite` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | défaut : minimal | 1 048 576 | 65 536 |
| `gemini-3-flash-preview` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash` | `high` | 1 048 576 | 65 536 |
| `gemma-4-31b-gemini` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — |
| `gemma-4-26b-gemini` | Gemini | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | — |
| `gemini-embedding-2` | Gemini | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — |
| `gemini-3-8-flash-tts` | Gemini | `audio_speech` | `TTS`, `Private-Data` | `Auto-TTS` | — | — | — |
| `gemini-3-8-flash-lite-tts` | Gemini | `audio_speech` | `TTS`, `Private-Data` | `Auto-TTS` | — | — | — |
| `gemini-3-5-transcribe` | Gemini | `audio_transcription` | `STT`, `Private-Data` | `Auto-STT` | — | — | — |
| `codestral` | Mistral | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 128 000 | — |
| `codestral-2508` | Mistral | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 128 000 | — |
| `mistral-medium` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — |
| `mistral-small` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — |
| `ministral-14b` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — |
| `ministral-8b` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 262 144 | — |
| `ministral-3b` | Mistral | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | — |
| `mistral-embed` | Mistral | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — |
| `voxtral-mini-mistral` | Mistral | `audio_transcription` | `STT`, `Private-Data` | `Auto-STT` | — | — | — |
| `gpt-oss-120b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | défaut : medium | 131 072 | 65 536 |
| `gpt-oss-20b-groq` | Groq | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | défaut : medium | 131 072 | 65 536 |
| `qwen3-8-27b-groq` | Groq | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code` | défaut : non-reasoning | 131 072 | 16 384 |
| `whisper-large-v3-groq` | Groq | `audio_transcription` | `STT`, `Public-Data-Only` | `Auto-STT` | — | — | — |
| `whisper-large-v3-turbo-groq` | Groq | `audio_transcription` | `STT`, `Public-Data-Only` | `Auto-STT` | — | — | — |
| `deepseek-v4-pro-direct` | DeepSeek | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Code`, `Auto-Claude-Code` | défaut : high | 1 000 000 | 393 216 |
| `deepseek-flash-direct` | DeepSeek | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | défaut : high | 1 000 000 | 393 216 |
| `nemotron-ultra-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `high` | 1 000 000 | 65 536 |
| `nemotron-reasoning-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 256 000 | 65 536 |
| `nemotron-lightning-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 000 000 | 65 536 |
| `nemotron-super-vl-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 000 000 | 131 072 |
| `gemma-4-31b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 32 768 |
| `gemma-4-26b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 32 768 |
| `openrouter-auto-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | — | — |
| `particle-1-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `xhigh` | 1 048 576 | 131 072 |
| `ernie-5-5-flash-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `high` | 1 024 000 | 921 600 |
| `lfm-3-1-7b-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 8 192 |
| `dots-3-note-preview-free` | OpenRouter | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 512 000 | 460 800 |
| `nemotron-3-embed-1b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — |
| `nemotron-3-5-embed-1b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — |
| `nemotron-3-5-embed-8b-free` | OpenRouter | `embedding` | `Embeddings`, `Public-Data-Only` | — | — | — | — |
| `gpt-oss-120b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash` | défaut : medium | 128 000 | — |
| `gpt-oss-20b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | défaut : medium | 128 000 | — |
| `gemma-4-26b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 256 000 | — |
| `llama-3-3-70b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 24 000 | — |
| `glm-4-7-flash-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 131 072 | — |
| `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — |
| `clef-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — |
| `clef-omni-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — |
| `clef-flash-cloudflare` | Cloudflare | `evaluation` | `Decisions`, `Private-Data` | `Auto-Decision` | — | — | — |
| `clairic-cloudflare` | Cloudflare | `extraction` | `Extraction`, `Private-Data` | `Auto-Extraction` | — | — | — |
| `clairic-flash-cloudflare` | Cloudflare | `extraction` | `Extraction`, `Private-Data` | `Auto-Extraction` | — | — | — |
| `granite-4-0-h-micro-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 131 000 | — |
| `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — |
| `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 131 000 | — |
| `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 128 000 | — |
| `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 32 768 | — |
| `qwen3-8-27b-cloudflare` | Cloudflare | chat | `LLM`, `Private-Data`, `Claude-Code` | `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | défaut : xhigh | 262 144 | — |
| `bge-m3-cloudflare` | Cloudflare | `embedding` | `Embeddings`, `Private-Data` | — | — | — | — |
| `glm-4-7-flash-zai` | Zai | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 200 000 | 128 000 |
| `nemotron-ultra-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `high` | 1 000 000 | 65 536 |
| `nemotron-reasoning-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 256 000 | 65 536 |
| `nemotron-lightning-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 000 000 | 65 536 |
| `nemotron-super-vl-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 000 000 | 131 072 |
| `particle-1-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `max` | 1 048 576 | 131 072 |
| `ernie-5-5-flash-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `high` | 1 024 000 | 921 600 |
| `lfm-3-1-7b-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 262 144 | 8 192 |
| `beam-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 048 576 | 131 072 |
| `flint-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | 235 929 |
| `glyph-cluster-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 256 000 | 256 000 |
| `dots-3-note-preview-kilo` | Kilo | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 512 000 | 460 800 |
| `deepseek-v4-1-flash-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Pro`, `Auto-Flash`, `Auto-Code` | — | 1 048 576 | 262 144 |
| `qwen3-5-397b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Pro`, `Auto-Flash`, `Auto-Code` | — | 262 144 | 262 144 |
| `gpt-oss-120b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Pro`, `Auto-Flash`, `Auto-Code` | — | 131 072 | 131 072 |
| `qwen3-8-27b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash`, `Auto-Code` | — | 262 144 | 262 144 |
| `qwen3-6-35b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash`, `Auto-Code` | — | 262 144 | 65 536 |
| `nemotron3-omni-30b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 131 072 | 65 536 |
| `mistral-small-3-2-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash` | — | 131 072 | 131 072 |
| `gpt-oss-20b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 131 072 | 65 536 |
| `gemma-4-26b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | 65 536 |
| `nemotron3-nano-30b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | 65 536 |
| `qwen3-5-9b-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 262 144 | 65 536 |
| `olala-mini-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Flash-Lite` | — | 32 768 | 16 384 |
| `laguna-xs-2-1-ovh` | OVHcloud | chat | `LLM`, `Private-Data` | `Auto-Code` | — | 131 072 | 65 536 |
| `nemotron-ultra-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `max` | 1 048 576 | 65 536 |
| `nemotron-reasoning-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | `max` | 131 072 | 20 480 |
| `nemotron-lightning-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 048 576 | 65 536 |
| `gemma-4-31b-requesty` | Requesty | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | `high` | 262 144 | 8 192 |
| `kimi-k3-1-pro-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | — | 1 048 576 | — |
| `mistral-large-4-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | défaut : high | 1 048 576 | — |
| `nemotron-ultra-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 1 048 576 | — |
| `nemotron-reasoning-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | 262 144 | — |
| `nemotron-lightning-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 1 048 576 | — |
| `nemotron-super-vl-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash` | — | 1 048 576 | — |
| `nemotron-bolt-e4b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | 65 536 | — |
| `glm-5-3-flash-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | défaut : max | — | — |
| `minimax-m3-1-flash-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | — | 1 000 000 | — |
| `step-5-preview-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | — | 1 000 000 | 1 000 000 |
| `laguna-xs-2-1-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Code`, `Auto-Claude-Code` | — | 262 144 | — |
| `muse-glimmer-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only`, `Claude-Code` | `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` | — | 131 072 | — |
| `gemma-4-31b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | 262 144 | — |
| `gemma-3-12b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | — | — |
| `gemma-3-4b-nvidia` | NVIDIA | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | — | — |
| `hy4-flash-cent-ai` | Cent AI | chat | `LLM`, `Public-Data-Only` | `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` | — | 1 048 576 | — |
| `aion-3-5-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 262 144 | 32 768 |
| `aion-3-5-mini-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 262 144 | 32 768 |
| `aion-3-0-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 |
| `aion-3-0-mini-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 |
| `aion-2-0-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 131 072 | 32 768 |
| `aion-rp-llama-3-1-8b-aion-labs` | Aion Labs | chat | `Fiction`, `Private-Data` | `Auto-Fiction` | — | 32 768 | 32 768 |
| `omniroute-free-auto` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Flash` | — | — | — |
| `omniroute-free-code` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Code` | — | — | — |
| `omniroute-free-reasoning` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Pro` | — | — | — |
| `omniroute-free-fast` | OmniRoute | chat | `LLM`, `Public-Data-Only` | `Auto-Flash-Lite` | — | — | — |
| `omniroute-free-vision` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — |
| `omniroute-vision` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — |
| `omniroute-multimodal` | OmniRoute | chat | `LLM`, `Public-Data-Only` | — | — | — | — |
| `Auto` | LiteLLM | chat | `LLM`, `Public-Data-Only` | — | — | — | — |

[↑ Retour en haut](#catalogue-de-la-passerelle-litellm)
