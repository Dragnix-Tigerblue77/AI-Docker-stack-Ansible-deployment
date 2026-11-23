<!--
SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
SPDX-License-Identifier: AGPL-3.0-only
-->

# Routage des modèles

Ce document dit quel modèle est où, à quel niveau de réflexion et pourquoi. Il est tenu à la main, et `.github/scripts/check_routing_document.py` fait échouer la CI s'il dit autre chose que le gabarit `templates/LiteLLM_config.yaml.j2` sur deux points : l'ordre des membres de chaque routeur et le niveau fixé d'une entrée. Les chiffres et les raisons, eux, sont du texte qu'une personne relit. Les contrats (`.github/LiteLLM_router_contracts.yaml`) restent la source des chiffres, relus chaque semaine : ceux d'ici sont ceux d'Artificial Analysis (indice d'intelligence et délai moyen avant le premier mot de la réponse) et d'Epoch AI lus le 2026-11-21, et ceux des limites gratuites aux dates que donne le registre des fournisseurs du README.

Les cascades ci-dessous sont celles du gabarit rendu avec la clé de tous les fournisseurs. Sans la clé d'un fournisseur, ses entrées disparaissent et l'ordre des autres ne change pas.

## Les règles en mots simples

**Une entrée est un modèle à un niveau de réflexion.** Plus le niveau est haut, plus le modèle réfléchit avant de répondre : le score monte, l'attente aussi. Artificial Analysis mesure un score (l'indice d'intelligence) et une attente (le délai moyen avant le premier mot de la réponse) pour chaque niveau d'un même modèle.

**Le niveau gardé par un routeur.** On part du niveau le plus bas et on monte d'un cran tant que chaque seconde d'attente en plus rapporte au moins un certain nombre de points de score. `Auto-Pro` en demande 0,2 par seconde (il a le temps), `Auto-Flash` 1, `Auto-Flash-Lite` 3 (il est fait pour aller vite). Exemple avec Gemini 4 Hydrogen, dont le niveau bas donne 26,9 points en 7,6 s, le moyen 41,2 en 13,0 s, le haut 50,8 en 21,5 s et le très haut 53,9 en 47,4 s : du bas au moyen, 14,3 points pour 5,4 s de plus font 2,6 points par seconde ; du moyen au haut, 1,1 ; du haut au très haut, 0,12. Donc `Auto-Pro` et `Auto-Flash` gardent le haut, le niveau par défaut de Google pour ce modèle qui remplace la lignée Flash, et `Auto-Flash-Lite` le bas. Gemini 3.8 Flash donne 22,5 points en 5,1 s (bas), 30,1 en 14,5 s (moyen) et 30,8 en 28,1 s (haut) : du bas au moyen 0,81 point par seconde, du moyen au haut 0,05. `Auto-Pro` garde le moyen, `Auto-Flash` et `Auto-Flash-Lite` le bas.

**`Auto-Pro`, `Auto-Flash`, `Auto-Code` et `Auto-Claude-Code` : le meilleur score d'abord.** Deux membres à moins de 2 points l'un de l'autre ne sont pas départagés par le score : le plus rapide passe devant. Pour `Auto-Code` et `Auto-Claude-Code`, le score est la position de code mesurée par Epoch AI. L'ordre de `Auto-Pro` et de `Auto-Flash` est celui du gabarit, écrit à la main : les contrats le comparent à leur propre ordre et le rapportent, sans rien changer.

**`Auto-Flash-Lite` : chaque seconde d'attente en plus doit rapporter au moins 3 points de score.** Le routeur sert les demandes simples et courtes, donc l'attente avant le premier mot de la réponse reste sa mesure ; mais entre deux modèles qui répondent à peu près aussi vite, le plus intelligent passe devant. Le score d'un membre est son indice moins 3 fois son délai en secondes (3 est le taux déjà validé entre les niveaux d'un même modèle, repris ici entre les modèles). L'ordre est :

1. les membres qui ont un indice et un délai, par score décroissant ;
2. les membres qui ont un délai mais pas d'indice, le plus rapide d'abord ;
3. les membres dont les chiffres ne s'appliquent pas à coup sûr (niveau non vérifié) ou qui n'en ont aucun : ils gardent leur place d'avant ;
4. les membres qui partagent le quota d'un membre de `Auto-Pro` ou de `Auto-Flash` (voir ci-dessous), dans le même ordre ;
5. le payant, tout à la fin.

**Un membre de `Auto-Flash-Lite` ne mange pas le quota de `Auto-Pro` ou de `Auto-Flash`.** Chez un fournisseur dont le quota gratuit est compté par modèle (voir « Les limites gratuites des fournisseurs » plus bas), un membre de `Auto-Flash-Lite` qui est le même modèle chez le même fournisseur (même identifiant de modèle, même adresse) qu'un membre de `Auto-Pro` ou de `Auto-Flash` dépense le même compteur : il passe après tous les membres de `Auto-Flash-Lite` qui ont un quota à eux. Le rapport de contrat trouve ces membres tout seul dans le gabarit, il n'y en a pas de liste tenue à la main.

**Plusieurs modèles d'un même fournisseur restent dans un même routeur, même quand son quota est compté pour tout le compte.** Quand le quota du compte est épuisé, chacun répond par un refus et la cascade passe au suivant : le second ne coûte qu'un refus d'une fraction de seconde. Mais le routeur passe aussi au membre suivant quand un seul modèle échoue, parce qu'il est en panne ou retiré, que la demande dépasse son contexte ou qu'il tarde à répondre, et là le second modèle du même fournisseur répond. LiteLLM ne sait pas faire la différence pour en tirer parti : il met en pause une entrée qui a échoué, jamais tout son fournisseur (lu dans son code le 2026-11-23). Décision du mainteneur du 2026-11-23.

**Les niveaux fixés.** Seules les entrées Gemini dont Artificial Analysis mesure les niveaux (Gemini 4 Hydrogen et Gemini 3.8 Flash) ont un niveau fixé, avec une entrée par niveau dont un routeur a besoin, nommée `<entrée>-<niveau>` (le nom sans suffixe porte le niveau que garde `Auto-Pro`). Ce niveau n'est qu'une valeur par défaut : si un client envoie son propre niveau, c'est le sien qui compte. Claude Code en envoie toujours un, donc `Auto-Claude-Code` n'est pas piloté par ces niveaux ; LibreChat et n8n n'en envoient pas, ils reçoivent le niveau fixé. Les autres entrées n'ont pas de niveau fixé :

- chez OpenRouter, NVIDIA, OVHcloud, Kilo et Requesty (facturés à la requête), on ne sait pas si le fournisseur tient compte du niveau que LiteLLM lui envoie : « non fixé : non vérifié chez ce fournisseur » ;
- chez Groq, Cloudflare, DeepSeek en direct et Mistral (facturés au jeton, au neurone ou sur un solde prépayé), réfléchir plus coûterait de l'argent ou du quota : on n'y touche pas, c'est « défaut du fournisseur ».

| Modèle | `Auto-Pro`, `Auto-Code`, `Auto-Claude-Code` (0,2) | `Auto-Flash` (1) | `Auto-Flash-Lite` (3) |
| --- | --- | --- | --- |
| Gemini 4 Hydrogen | `high` : `gemini-4-hydrogen` | `high` : `gemini-4-hydrogen` | `low` : `gemini-4-hydrogen-low` |
| Gemini 3.8 Flash | `medium` : `gemini-3-8-flash` | `low` : `gemini-3-8-flash-low` | `low` : `gemini-3-8-flash-low` |

## Les limites gratuites des fournisseurs

Un seul tableau pour tous les fournisseurs que la passerelle appelle et pour tous les types de modèles. La colonne « Comptée par » dit ce qui partage un même compteur : un modèle (ses entrées seules), un compte (toutes les entrées du fournisseur ensemble) ou une adresse IP. Les chiffres viennent du registre des fournisseurs du README, qui donne la page lue et sa date pour chacun ; ceux de Google sont ceux de la page des limites de Google AI Studio du projet de la passerelle, niveau sans frais, lue le 2026-11-22.

| Fournisseur | Modèles | Limite gratuite | Comptée par | Remise à zéro |
| --- | --- | --- | --- | --- |
| Google Gemini | Gemini 4 Hydrogen, Gemini 3.8 Flash, 3.6 Flash, 3 Flash, 2.5 Flash | 5 requêtes par minute, 250 000 jetons par minute, 20 requêtes par jour | modèle et projet | minuit, heure du Pacifique |
| Google Gemini | Gemini 3.5 Flash-Lite, 3.1 Flash-Lite | 15 par minute, 250 000 jetons par minute, 500 par jour | modèle et projet | minuit, heure du Pacifique |
| Google Gemini | Gemini 2.5 Flash-Lite | 10 par minute, 250 000 jetons par minute, 20 par jour | modèle et projet | minuit, heure du Pacifique |
| Google Gemini | Gemma 4 31B, Gemma 4 26B | 30 par minute, 16 000 jetons par minute, 14 400 par jour | modèle et projet | minuit, heure du Pacifique |
| Google Gemini | Gemini Embedding 1 et 2 | 100 par minute, 30 000 jetons par minute, 1 000 par jour | modèle et projet | minuit, heure du Pacifique |
| Google Gemini | Synthèse vocale : 3.8 Flash TTS, 3.8 Flash Lite TTS, 3.1 Flash TTS, 2.5 Flash TTS | 3 par minute, 10 000 jetons par minute, 10 par jour | modèle et projet | minuit, heure du Pacifique |
| Google Gemini | Gemini 3.5 Transcribe | 3 par minute, 10 000 jetons par minute, 25 par jour | modèle et projet | minuit, heure du Pacifique |
| Google Gemini | Gemini 3.1 Pro, 2.5 Pro, Gemini 4 Argon, Neon et Carbon | aucune : pas servis en gratuit | — | — |
| Groq | gpt-oss, qwen3.8-27b | 30 requêtes par minute, 8 000 jetons par minute ; par jour : non relevé | modèle et organisation | non relevé |
| Groq | whisper-large-v3, whisper-large-v3-turbo | 20 requêtes par minute, 7 200 secondes d'audio par heure (plan non établi), 25 Mo par fichier | modèle et organisation | non relevé |
| Cloudflare Workers AI | tous | 10 000 « neurons » par jour ; texte : 300 requêtes par minute | compte | 00:00 UTC |
| NVIDIA API Catalog | tous | 40 requêtes par minute ; plafond quotidien inconnu | compte | — |
| OpenRouter | modèles `:free` | 20 requêtes par minute, 50 par jour (1 000 une fois 10 crédits achetés) | compte | non relevé |
| Requesty | modèles gratuits | 20 requêtes par minute, 200 par jour | organisation | non relevé |
| Kilo Gateway | modèles gratuits, sans clé | 200 requêtes par heure | adresse IP | — |
| OVHcloud AI Endpoints | modèles sans clé | 2 requêtes par minute, observées, écrites sur aucune page | adresse IP et modèle | — |
| Z AI | GLM-4.7-Flash | non publiées hors de la console du compte : inconnues | — | — |
| Cent AI | `hy4-flash:free` | aucune annoncée ; gratuit jusqu'au 30 novembre, la suite est inconnue | — | — |
| Mistral | tous | aucune : payant, sur un solde prépayé | — | — |
| DeepSeek | tous | aucune : payant, sur un solde prépayé | — | — |
| OmniRoute | tous | agrégateur local, aucun quota | — | — |

Gemini 3.7 Flash ne figure pas du tout dans la liste de la page de Google.

Ce que ça change, en clair :

- **Quand le compteur est celui d'un modèle**, toutes les entrées de ce modèle chez ce fournisseur le partagent, quel que soit leur niveau de réflexion. Par exemple, les têtes de `Auto-Pro` et de `Auto-Flash` n'ont que 20 requêtes par jour : `gemini-4-hydrogen`, `gemini-4-hydrogen-low` et `gemini-4-hydrogen-xhigh` puisent dans les mêmes 20, et `gemini-3-8-flash` et `gemini-3-8-flash-low` dans les mêmes 20 aussi. L'entrée `gemini-4-hydrogen-xhigh` dépense donc les 20 requêtes du jour de la tête de `Auto-Pro` et de `Auto-Flash`. Les deux Flash-Lite ont 500 requêtes par jour chacun : c'est pourquoi ils ouvrent `Auto-Flash-Lite` et pourquoi les entrées Hydrogen et 3.8 Flash y sont en dernier.
- **Quand le compteur est celui d'un compte ou d'une adresse IP**, toutes les entrées du fournisseur le partagent, quel que soit le modèle : une fois épuisé, chacune répond par un refus, et la cascade passe au membre suivant.

## Les routeurs

Dans chaque tableau, « Niveau » dit ce que fixe le gabarit : un niveau entre apostrophes inversées s'il en fixe un, sinon « défaut du fournisseur » ou « non fixé : non vérifié chez ce fournisseur ». « Indice » et « Délai » sont ceux du niveau où l'entrée est appelée, « (estimé) » marquant un indice tiré de l'indice de capacités d'Epoch AI faute d'indice d'Artificial Analysis. Un tiret veut dire qu'aucun chiffre ne s'applique.

### `Auto-Pro`

Tête : `gemini-4-hydrogen`, au niveau `high`. Raisonnement long, le temps n'est pas borné.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Google AI Studio | à la requête, quota par modèle | `high` | 50,8 | 21,5 s | niveau gardé par `Auto-Pro` : passer de `high` à `xhigh` rapporte 0,12 point par seconde, moins que les 0,2 demandés ; meilleur indice du routeur |
| 2 | `kimi-k3-1-pro-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 46,5 | 155,1 s | deuxième meilleur indice, mais 155 s en moyenne avant la première réponse, au-delà des 90 s de patience : point ouvert |
| 3 | `gemini-3-8-flash` | Google AI Studio | à la requête, quota par modèle | `medium` | 30,1 | 14,5 s | niveau gardé par `Auto-Pro` : `medium`, car `high` rapporte 0,05 point par seconde, moins que les 0,2 demandés |
| 4 | `step-5-preview-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 28,5 | 37,9 s | indice 28,5 en 37,9 s |
| 5 | `minimax-m3-1-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 29,1 | 52,0 s | indice 29,1 en 52,0 s |
| 6 | `mistral-large-4-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 26,1 | 71,3 s | indice 26,1 en 71,3 s |
| 7 | `glm-5-3-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 27,8 | 87,3 s | indice 27,8 en 87,3 s |
| 8 | `beam-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 17,7 | 10,8 s | indice 17,7 en 10,8 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 9 | `nemotron-ultra-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 11,8 | 8,0 s | indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 10 | `nemotron-ultra-requesty` | Requesty | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 11,8 | 8,0 s | même modèle que `nemotron-ultra-free` chez un autre fournisseur, quota à part ; indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 11 | `nemotron-ultra-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 11,8 | 8,0 s | même modèle que `nemotron-ultra-free` chez un autre fournisseur, quota à part ; indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 12 | `nemotron-ultra-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 11,8 | 8,0 s | même modèle que `nemotron-ultra-free` chez un autre fournisseur, quota à part ; indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 13 | `nemotron-reasoning-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas d'indice : garde sa place historique |
| 14 | `nemotron-reasoning-requesty` | Requesty | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | même modèle que `nemotron-reasoning-free` chez un autre fournisseur, quota à part ; pas d'indice : garde sa place historique |
| 15 | `nemotron-reasoning-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | même modèle que `nemotron-reasoning-free` chez un autre fournisseur, quota à part ; pas d'indice : garde sa place historique |
| 16 | `nemotron-reasoning-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | même modèle que `nemotron-reasoning-free` chez un autre fournisseur, quota à part ; pas d'indice : garde sa place historique |
| 17 | `nemotron-super-vl-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 13,6 | 12,4 s | indice 13,6 en 12,4 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 18 | `nemotron-super-vl-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 19 | `nemotron-super-vl-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 20 | `hy4-flash-cent-ai` | Cent AI | gratuit jusqu'au 30 novembre, la suite n'est pas annoncée | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : derrière les membres gratuits auxquels on ne peut pas le comparer, avant OVHcloud |
| 21 | `deepseek-v4-1-flash-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 32,0 (estimé) | 21,1 s | indice 32,0 en 21,1 s |
| 22 | `qwen3-5-397b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 23 | `gpt-oss-120b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 4,2 (estimé) | 10,3 s | indice 4,2 en 10,3 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 24 | `deepseek-v4-pro-direct` | DeepSeek | prépayé | défaut du fournisseur | 20,8 | 48,8 s | payant : après tous les gratuits |
| 25 | `omniroute-free-reasoning` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | routeur local sans clé et sans chiffre : tout à la fin |

### `Auto-Flash`

Tête : `gemini-4-hydrogen`, au niveau `high`, comme `Auto-Pro`. L'assistant de tous les jours : le meilleur score, au prix d'une attente plus longue.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Google AI Studio | à la requête, quota par modèle | `high` | 50,8 | 21,5 s | niveau gardé par `Auto-Flash` : `high`, car passer de `medium` à `high` rapporte 1,1 point par seconde, plus que le 1 demandé, et `xhigh` 0,12 ; même entrée que la tête de `Auto-Pro` |
| 2 | `kimi-k3-1-pro-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 46,5 | 155,1 s | deuxième place gardée du gabarit : à 1 point par seconde il serait bien plus bas, et 155 s dépassent les 90 s de patience : point ouvert |
| 3 | `gemini-3-8-flash-low` | Google AI Studio | à la requête, quota par modèle | `low` | 22,5 | 5,1 s | niveau gardé par `Auto-Flash` : `low`, car `medium` rapporte 0,81 point par seconde, moins que le 1 demandé |
| 4 | `step-5-preview-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 28,5 | 37,9 s | indice 28,5 en 37,9 s |
| 5 | `minimax-m3-1-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 29,1 | 52,0 s | indice 29,1 en 52,0 s |
| 6 | `mistral-large-4-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 26,1 | 71,3 s | indice 26,1 en 71,3 s |
| 7 | `glm-5-3-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 27,8 | 87,3 s | indice 27,8 en 87,3 s |
| 8 | `gemini-3-6-flash` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 25,6 (estimé) | 12,6 s | indice 25,6 en 12,6 s |
| 9 | `gemini-3-flash-preview` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 21,5 (estimé) | 6,3 s | indice 21,5 en 6,3 s |
| 10 | `gpt-oss-120b-groq` | Groq | au jeton | défaut du fournisseur | 4,2 (estimé) | 10,3 s | indice 4,2 en 10,3 s |
| 11 | `gpt-oss-120b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | 4,2 (estimé) | 10,3 s | même modèle que `gpt-oss-120b-groq` chez un autre fournisseur, quota à part ; indice 4,2 en 10,3 s |
| 12 | `qwen3-8-27b-groq` | Groq | au jeton | défaut du fournisseur | 10,0 | 5,1 s | indice 10,0 en 5,1 s |
| 13 | `gemma-4-31b-gemini` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 8,7 (estimé) | 35,4 s | indice 8,7 en 35,4 s |
| 14 | `gemma-4-31b-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 8,7 (estimé) | 35,4 s | même modèle que `gemma-4-31b-gemini` chez un autre fournisseur, quota à part ; indice 8,7 en 35,4 s |
| 15 | `gemma-4-31b-requesty` | Requesty | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 8,7 (estimé) | 35,4 s | même modèle que `gemma-4-31b-gemini` chez un autre fournisseur, quota à part ; indice 8,7 en 35,4 s |
| 16 | `gemma-4-31b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 8,7 (estimé) | 35,4 s | même modèle que `gemma-4-31b-gemini` chez un autre fournisseur, quota à part ; indice 8,7 en 35,4 s |
| 17 | `particle-1-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 18 | `particle-1-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 19 | `ernie-5-5-flash-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 20 | `ernie-5-5-flash-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 21 | `beam-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 17,7 | 10,8 s | indice 17,7 en 10,8 s |
| 22 | `nemotron-super-vl-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 13,6 | 12,4 s | indice 13,6 en 12,4 s |
| 23 | `nemotron-super-vl-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s |
| 24 | `muse-glimmer-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 6,3 | 23,7 s | indice 6,3 en 23,7 s |
| 25 | `nemotron-super-vl-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s |
| 26 | `flint-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 27 | `glyph-cluster-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 28 | `dots-3-note-preview-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : derrière les membres gratuits auxquels on ne peut pas le comparer, avant le routeur gratuit d'OpenRouter ; gratuit jusqu'au 31 décembre |
| 29 | `dots-3-note-preview-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | même modèle que `dots-3-note-preview-free` chez un autre fournisseur ; aucun chiffre publié : derrière lui ; gratuit jusqu'au 31 décembre |
| 30 | `openrouter-auto-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 31 | `hy4-flash-cent-ai` | Cent AI | gratuit jusqu'au 30 novembre, la suite n'est pas annoncée | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : derrière les membres gratuits auxquels on ne peut pas le comparer, avant OVHcloud |
| 32 | `deepseek-v4-1-flash-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 32,0 (estimé) | 21,1 s | indice 32,0 en 21,1 s |
| 33 | `qwen3-5-397b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 34 | `gpt-oss-120b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 4,2 (estimé) | 10,3 s | même modèle que `gpt-oss-120b-groq` chez un autre fournisseur, quota à part ; indice 4,2 en 10,3 s |
| 35 | `qwen3-8-27b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 21,9 (estimé) | — | indice 21,9, délai inconnu |
| 36 | `qwen3-8-27b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | 20,1 | 135,4 s | même modèle que ses jumeaux, chez un autre fournisseur ; réfléchit en Xhigh par défaut, 135 s avant la réponse, au-delà des 90 s de patience : un repli de plus, juste derrière eux |
| 37 | `qwen3-6-35b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 38 | `nemotron3-omni-30b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | pas d'indice : garde sa place historique |
| 39 | `mistral-small-3-2-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique |
| 40 | `mistral-small` | Mistral | prépayé | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 41 | `ministral-14b` | Mistral | prépayé | défaut du fournisseur | — | 2,3 s | pas d'indice : garde sa place historique |
| 42 | `ministral-8b` | Mistral | prépayé | défaut du fournisseur | — | 2,0 s | pas d'indice : garde sa place historique |
| 43 | `deepseek-flash-direct` | DeepSeek | prépayé | défaut du fournisseur | 28,6 | 21,1 s | payant : après tous les gratuits |
| 44 | `omniroute-free-auto` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | routeur local sans clé et sans chiffre : tout à la fin |

### `Auto-Flash-Lite`

Tête : `gemini-3-5-flash-lite`. Demandes simples et courtes : le score moins 3 points par seconde d'attente, puis les membres sans indice, puis ceux qui partagent un quota.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-3-5-flash-lite` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 11,7 | 4,6 s | score -2,1 (indice 11,7 moins 3 fois 4,6 s) : le meilleur des membres qui ont leur propre quota ; 500 requêtes par jour, le sien |
| 2 | `gemini-3-1-flash-lite` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 6,2 | 3,2 s | score -3,4 (indice 6,2 moins 3 fois 3,2 s) ; 500 requêtes par jour, le sien |
| 3 | `lfm-3-1-7b-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 6,0 | 13,8 s | score -35,3 (indice 6,0 moins 3 fois 13,8 s) |
| 4 | `lfm-3-1-7b-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 6,0 | 13,8 s | score -35,3 (indice 6,0 moins 3 fois 13,8 s) ; même modèle que `lfm-3-1-7b-free` chez un autre fournisseur |
| 5 | `nemotron-lightning-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 5,5 | 17,7 s | score -47,5 (indice 5,5 moins 3 fois 17,7 s) |
| 6 | `nemotron-lightning-requesty` | Requesty | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 5,5 | 17,7 s | score -47,5 (indice 5,5 moins 3 fois 17,7 s) ; même modèle que `nemotron-lightning-free` chez un autre fournisseur |
| 7 | `nemotron-lightning-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 5,5 | 17,7 s | score -47,5 (indice 5,5 moins 3 fois 17,7 s) ; même modèle que `nemotron-lightning-free` chez un autre fournisseur |
| 8 | `nemotron-lightning-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 5,5 | 17,7 s | score -47,5 (indice 5,5 moins 3 fois 17,7 s) ; même modèle que `nemotron-lightning-free` chez un autre fournisseur |
| 9 | `gemini-2-5-flash-lite` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | — | 0,4 s | un délai de 0,4 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 10 | `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | 1,1 s | un délai de 1,1 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 11 | `gemma-3-4b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | 1,9 s | un délai de 1,9 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 12 | `llama-3-3-70b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | 2,3 s | un délai de 2,3 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 13 | `gemma-3-12b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | 3,1 s | un délai de 3,1 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 14 | `gpt-oss-20b-groq` | Groq | au jeton | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant |
| 15 | `gpt-oss-20b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gpt-oss-20b-groq` chez un autre fournisseur |
| 16 | `gemma-4-26b-gemini` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant |
| 17 | `gemma-4-26b-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gemma-4-26b-gemini` chez un autre fournisseur |
| 18 | `gemma-4-26b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gemma-4-26b-gemini` chez un autre fournisseur |
| 19 | `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | aucun chiffre d'Artificial Analysis ; seul l'indice de capacités d'Epoch AI le note (118,7) : en tête des membres Cloudflare sans chiffre |
| 20 | `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | aucun chiffre publié : parmi les derniers membres gratuits, par taille |
| 21 | `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | aucun chiffre publié pour cette version : parmi les derniers membres gratuits, par taille |
| 22 | `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | aucun chiffre publié : parmi les derniers membres gratuits, par taille ; échoue tant que la licence de Meta n'est pas acceptée sur le compte |
| 23 | `granite-4-0-h-micro-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | aucun chiffre publié : parmi les derniers membres gratuits, le plus petit |
| 24 | `nemotron-bolt-e4b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont |
| 25 | `gpt-oss-20b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gpt-oss-20b-groq` chez un autre fournisseur |
| 26 | `gemma-4-26b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gemma-4-26b-gemini` chez un autre fournisseur |
| 27 | `nemotron3-nano-30b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont |
| 28 | `qwen3-5-9b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont |
| 29 | `olala-mini-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont |
| 30 | `gemini-3-8-flash-low` | Google AI Studio | à la requête, quota par modèle | `low` | 22,5 | 5,1 s | niveau gardé par `Auto-Flash-Lite` : `low`, car `medium` rapporte 0,81 point par seconde, moins que les 3 demandés ; score 7,3, le meilleur du routeur, mais même modèle que la deuxième place de `Auto-Pro` et que `Auto-Flash` : dans les derniers pour ne pas manger leurs 20 requêtes par jour |
| 31 | `gemini-4-hydrogen-low` | Google AI Studio | à la requête, quota par modèle | `low` | 26,9 | 7,6 s | niveau gardé par `Auto-Flash-Lite` : `low`, car `medium` rapporte 2,6 points par seconde, moins que les 3 demandés ; score 4,0, mais même modèle que la tête de `Auto-Pro` : dans les derniers pour ne pas manger ses 20 requêtes par jour |
| 32 | `qwen3-8-27b-groq` | Groq | au jeton | défaut du fournisseur | 10,0 | 5,1 s | score -5,2, mais c'est la même entrée que celle de `Auto-Flash` : même quota, donc dans les derniers |
| 33 | `hy4-flash-cent-ai` | Cent AI | gratuit jusqu'au 30 novembre, la suite n'est pas annoncée | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié, et c'est la même entrée que celle de `Auto-Flash` : même quota, donc dans les derniers |
| 34 | `ministral-3b` | Mistral | prépayé | défaut du fournisseur | — | 1,7 s | payant : tout à la fin, après les gratuits |

### `Auto-Code`

Tête : `gemini-4-hydrogen`, au niveau `high`. Classé par position de code (Epoch AI, plus petite = meilleure).

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Position de code | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Google AI Studio | à la requête, quota par modèle | `high` | 50,8 | 9 % | 21,5 s | niveau gardé par `Auto-Code` (même taux que `Auto-Pro`) ; meilleure position de code du routeur |
| 2 | `gemini-3-8-flash` | Google AI Studio | à la requête, quota par modèle | `medium` | 30,1 | 17 % | 14,5 s | niveau gardé par `Auto-Code` (même taux que `Auto-Pro`) : `medium` |
| 3 | `glm-5-3-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 27,8 | 68 % | 87,3 s | indice 27,8 en 87,3 s |
| 4 | `kimi-k3-1-pro-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 46,5 | 14 % (estimé) | 155,1 s | place du gabarit ; 155 s en moyenne avant la première réponse, au-delà des 90 s de patience : point ouvert |
| 5 | `step-5-preview-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 28,5 | 33 % (estimé) | 37,9 s | indice 28,5 en 37,9 s |
| 6 | `minimax-m3-1-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 29,1 | 32 % (estimé) | 52,0 s | indice 29,1 en 52,0 s |
| 7 | `mistral-large-4-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 26,1 | 36 % (estimé) | 71,3 s | indice 26,1 en 71,3 s |
| 8 | `qwen3-8-27b-groq` | Groq | au jeton | défaut du fournisseur | 10,0 | 71 % (estimé) | 5,1 s | indice 10,0 en 5,1 s |
| 9 | `gemini-3-6-flash` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 25,6 (estimé) | 72 % | 12,6 s | indice 25,6 en 12,6 s |
| 10 | `muse-glimmer-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 6,3 | 80 % (estimé) | 23,7 s | indice 6,3 en 23,7 s |
| 11 | `laguna-xs-2-1-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 12 | `glm-4-7-flash-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 13 | `glm-4-7-flash-zai` | Z AI | à la requête, limite non publiée | non fixé : non vérifié chez ce fournisseur | — | — | — | même modèle que `glm-4-7-flash-cloudflare` chez un autre fournisseur, quota à part ; niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 14 | `deepseek-v4-1-flash-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 32,0 (estimé) | 29 % (estimé) | 21,1 s | indice 32,0 en 21,1 s |
| 15 | `qwen3-5-397b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 16 | `gpt-oss-120b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 4,2 (estimé) | 84 % | 10,3 s | indice 4,2 en 10,3 s ; sous le plancher de `Auto-Code`, mais garde sa place du gabarit |
| 17 | `qwen3-8-27b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | 21,9 (estimé) | 43 % (estimé) | — | indice 21,9, délai inconnu |
| 18 | `qwen3-8-27b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | 20,1 | — | 135,4 s | même modèle que ses jumeaux, chez un autre fournisseur ; réfléchit en Xhigh par défaut, 135 s avant la réponse, au-delà des 90 s de patience : un repli de plus, juste derrière eux |
| 19 | `qwen3-6-35b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 20 | `laguna-xs-2-1-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 21 | `codestral` | Mistral | prépayé | défaut du fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 22 | `codestral-2508` | Mistral | prépayé | défaut du fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 23 | `deepseek-v4-pro-direct` | DeepSeek | prépayé | défaut du fournisseur | 20,8 | 22 % | 48,8 s | payant : après tous les gratuits |
| 24 | `omniroute-free-code` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | — | routeur local sans clé et sans chiffre : tout à la fin |

### `Auto-Claude-Code`

Tête : `gemini-4-hydrogen`, au niveau `high`. La cascade de `Auto-Code` sans les membres qui ne prennent pas les appels d'outils, dans le même ordre.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Position de code | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Google AI Studio | à la requête, quota par modèle | `high` | 50,8 | 9 % | 21,5 s | niveau gardé (même taux que `Auto-Pro`) ; meilleure position de code, appelle les outils |
| 2 | `gemini-3-8-flash` | Google AI Studio | à la requête, quota par modèle | `medium` | 30,1 | 17 % | 14,5 s | niveau gardé (même taux que `Auto-Pro`) : `medium` |
| 3 | `glm-5-3-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 27,8 | 68 % | 87,3 s | indice 27,8 en 87,3 s |
| 4 | `kimi-k3-1-pro-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 46,5 | 14 % (estimé) | 155,1 s | place du gabarit ; 155 s en moyenne avant la première réponse, au-delà des 90 s de patience : point ouvert |
| 5 | `step-5-preview-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 28,5 | 33 % (estimé) | 37,9 s | indice 28,5 en 37,9 s |
| 6 | `minimax-m3-1-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 29,1 | 32 % (estimé) | 52,0 s | indice 29,1 en 52,0 s |
| 7 | `mistral-large-4-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 26,1 | 36 % (estimé) | 71,3 s | indice 26,1 en 71,3 s |
| 8 | `qwen3-8-27b-groq` | Groq | au jeton | défaut du fournisseur | 10,0 | 71 % (estimé) | 5,1 s | indice 10,0 en 5,1 s |
| 9 | `gemini-3-6-flash` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 25,6 (estimé) | 72 % | 12,6 s | indice 25,6 en 12,6 s |
| 10 | `muse-glimmer-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | 6,3 | 80 % (estimé) | 23,7 s | indice 6,3 en 23,7 s |
| 11 | `laguna-xs-2-1-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 12 | `glm-4-7-flash-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 13 | `glm-4-7-flash-zai` | Z AI | à la requête, limite non publiée | non fixé : non vérifié chez ce fournisseur | — | — | — | même modèle que `glm-4-7-flash-cloudflare` chez un autre fournisseur, quota à part ; niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 14 | `qwen3-8-27b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | 20,1 | — | 135,4 s | même modèle que ses jumeaux, chez un autre fournisseur ; réfléchit en Xhigh par défaut, 135 s avant la réponse, au-delà des 90 s de patience : un repli de plus, à la place que lui donne l'ordre de `Auto-Code` |
| 15 | `codestral` | Mistral | prépayé | défaut du fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 16 | `codestral-2508` | Mistral | prépayé | défaut du fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 17 | `deepseek-v4-pro-direct` | DeepSeek | prépayé | défaut du fournisseur | 20,8 | 22 % | 48,8 s | payant : après tous les gratuits, seul payant de ce routeur |

### Entrées appelées par leur nom

Aucune cascade, aucun alias : on les appelle par leur nom, et elles n'ont pas de place à gagner.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen-xhigh` | Google AI Studio | à la requête, quota par modèle | `xhigh` | 53,9 | 47,4 s | niveau le plus haut de Gemini 4 Hydrogen : 3,1 points de plus que `high` pour 25,9 s de plus, soit 0,12 point par seconde, sous ce que demande n'importe quel routeur ; délai médian de 76 s, d'où une patience de 180 s au lieu de 90 s, et un repli sur `gemini-4-hydrogen` ; dépense les mêmes 20 requêtes par jour que la tête de `Auto-Pro` et de `Auto-Flash` |

## Ce qui a été regardé et n'a pas été créé

Aucune de ces montées de niveau n'atteint les 0,2 point par seconde que `Auto-Pro` demande, et aucune n'est dans une cascade.

| Candidat | Gain | Attente en plus | Points par seconde | Pourquoi pas |
| --- | --- | --- | --- | --- |
| DeepSeek V4.1 Flash au niveau `max` | +4,0 points | +23,6 s | 0,17 | niveau non vérifié chez OVHcloud, où il est servi |
| Mistral Large 4 au niveau `high` | +3,0 points | +22,4 s | 0,13 | niveau non vérifié chez NVIDIA, où il est servi |
| Qwen3.8 27B au niveau `xhigh` | +2,6 points | +109,7 s | 0,02 | 135 s en moyenne avant la réponse, au-delà des 90 s de patience |
| Gemini 3.8 Flash au niveau `high` | +0,7 point | +13,6 s | 0,05 | le gain ne vaut pas l'attente |
| DeepSeek V4.1 Flash sans réflexion | 18,5 points en 1,0 s, soit un score de 15,4 | — | — | meilleur score de `Auto-Flash-Lite` sur le papier, mais on n'a pas vérifié qu'OVHcloud sait couper la réflexion, et ses 2 requêtes par minute le rendent mauvais en tête |

## Les points ouverts

1. **`kimi-k3-1-pro-nvidia` dans `Auto-Pro` et `Auto-Flash`.** Son indice (46,5) est le deuxième de `Auto-Pro`, mais il met 155 s en moyenne avant son premier mot, au-delà des 90 s de patience du routeur (médiane de 71 s). L'ordre des contrats, au niveau gardé, le mettrait en tête de `Auto-Flash` ; il n'a pas été appliqué. Il garde la deuxième place du gabarit dans `Auto-Pro` et dans `Auto-Flash`, et la décision est à prendre : le descendre, ou le garder.
2. **Les niveaux fixés ne sont que des valeurs par défaut.** Tout client qui envoie son propre niveau l'emporte, et Claude Code en envoie toujours un : `Auto-Claude-Code` ne tient donc pas le niveau que garde son contrat.
3. **Chez OpenRouter, NVIDIA, OVHcloud, Kilo et Requesty, rien n'est fixé** tant qu'on n'a pas vérifié que le fournisseur tient compte du niveau que LiteLLM lui envoie. Tant que ce n'est pas fait, le niveau gardé par le contrat y reste un simple rapport.
4. **Les 20 requêtes par jour de Hydrogen et de 3.8 Flash.** Les têtes de `Auto-Pro` et de `Auto-Flash` s'épuisent vite, `gemini-4-hydrogen-xhigh` dépense les mêmes : la cascade passe alors au membre suivant.
5. **Dans `Auto-Flash-Lite`, les membres sans chiffres passent avant `gemini-3-8-flash-low`**, parce que la règle veut que les membres à quota partagé viennent après tous ceux qui ont un quota à eux, même ceux dont les chiffres ne s'appliquent pas. À revoir si on préfère que Gemini 3.8 Flash, à 5,1 s, passe devant des modèles de 34 s ou sans chiffre.
6. **Le payant `ministral-3b` reste le dernier** de `Auto-Flash-Lite`, comme tous les payants du gabarit : le contrat le déclare en dernier recours.

## Tenir ce document à jour

Une pull request qui change l'ordre d'une cascade ou le niveau fixé d'une entrée change ce document dans la même pull request. Pour vérifier avant de pousser :

```bash
python3 .github/scripts/check_routing_document.py
```
