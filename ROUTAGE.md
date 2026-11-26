<!--
SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
SPDX-License-Identifier: AGPL-3.0-only
-->

# Routage des modèles

Ce document dit quel modèle est où, à quel niveau de réflexion et pourquoi. Il est tenu à la main, et `.github/scripts/check_routing_document.py` fait échouer la CI s'il dit autre chose que le gabarit `templates/LiteLLM_config.yaml.j2` sur deux points : l'ordre des membres de chaque routeur et le niveau fixé d'une entrée. Les chiffres et les raisons, eux, sont du texte qu'une personne relit. Les contrats (`.github/LiteLLM_router_contracts.yaml`) restent la source des chiffres, relus à chaque exécution : ceux d'ici sont ceux d'Artificial Analysis (indice d'intelligence et délai moyen avant le premier mot de la réponse) et d'Epoch AI lus le 2026-11-21, et ceux des limites gratuites aux dates que donne le registre des fournisseurs du README.

Les cascades ci-dessous sont celles du gabarit rendu avec la clé de tous les fournisseurs. Sans la clé d'un fournisseur, ses entrées disparaissent et l'ordre des autres ne change pas.

## Les règles en mots simples

**Une entrée est un modèle à un niveau de réflexion.** Plus le niveau est haut, plus le modèle réfléchit avant de répondre : le score monte, l'attente aussi. Artificial Analysis mesure un score (l'indice d'intelligence) et une attente (le délai moyen avant le premier mot de la réponse) pour chaque niveau d'un même modèle.

**Le niveau que garderait un routeur, rapporté et plus appliqué.** Les contrats calculent encore, pour leur rapport, le niveau qu'un routeur garderait si chaque seconde d'attente en plus devait rapporter au moins un certain nombre de points de score : 0,2 par seconde pour `Auto-Pro`, 1 pour `Auto-Flash`, 3 pour `Auto-Flash-Lite`. Exemple avec Gemini 4 Hydrogen, dont le niveau bas donne 26,9 points en 7,6 s, le moyen 41,2 en 13,0 s, le haut 50,8 en 21,5 s et le très haut 53,9 en 47,4 s : du bas au moyen, 14,3 points pour 5,4 s de plus font 2,6 points par seconde ; du moyen au haut, 1,1 ; du haut au très haut, 0,12. Gemini 3.8 Flash donne 22,5 points en 5,1 s (bas), 30,1 en 14,5 s (moyen) et 30,8 en 28,1 s (haut) : du bas au moyen 0,81 point par seconde, du moyen au haut 0,05. Le niveau que le gabarit fixe suit désormais la règle ci-dessous.

**`Auto-Pro`, `Auto-Flash`, `Auto-Code` et `Auto-Claude-Code` : le meilleur score d'abord.** Deux membres à moins de 2 points l'un de l'autre ne sont pas départagés par le score : le plus rapide passe devant. Pour `Auto-Code` et `Auto-Claude-Code`, le score est la position de code mesurée par Epoch AI. L'ordre de `Auto-Pro` et de `Auto-Flash` est celui du gabarit, écrit à la main : les contrats le comparent à leur propre ordre et le rapportent, sans rien changer.

**`Auto-Flash-Lite` : chaque seconde d'attente en plus doit rapporter au moins 3 points de score.** Le routeur sert les demandes simples et courtes, donc l'attente avant le premier mot de la réponse reste sa mesure ; mais entre deux modèles qui répondent à peu près aussi vite, le plus intelligent passe devant. Le score d'un membre est son indice moins 3 fois son délai en secondes (3 est le taux déjà validé entre les niveaux d'un même modèle, repris ici entre les modèles). L'ordre est :

1. les membres qui ont un indice et un délai, par score décroissant ;
2. les membres qui ont un délai mais pas d'indice, le plus rapide d'abord ;
3. les membres dont les chiffres ne s'appliquent pas à coup sûr (niveau non vérifié) ou qui n'en ont aucun : ils gardent leur place d'avant ;
4. les membres qui partagent le quota d'un membre de `Auto-Pro` ou de `Auto-Flash` (voir ci-dessous), dans le même ordre ;
5. le payant, tout à la fin.

**Un membre de `Auto-Flash-Lite` ne mange pas le quota de `Auto-Pro` ou de `Auto-Flash`.** Chez un fournisseur dont le quota gratuit est compté par modèle (voir « Les limites gratuites des fournisseurs » plus bas), un membre de `Auto-Flash-Lite` qui est le même modèle chez le même fournisseur (même identifiant de modèle, même adresse) qu'un membre de `Auto-Pro` ou de `Auto-Flash` dépense le même compteur : il passe après tous les membres de `Auto-Flash-Lite` qui ont un quota à eux. Le rapport de contrat trouve ces membres tout seul dans le gabarit, il n'y en a pas de liste tenue à la main.

**Plusieurs modèles d'un même fournisseur restent dans un même routeur, même quand son quota est compté pour tout le compte.** Quand le quota du compte est épuisé, chacun répond par un refus et la cascade passe au suivant : le second ne coûte qu'un refus d'une fraction de seconde. Mais le routeur passe aussi au membre suivant quand un seul modèle échoue, parce qu'il est en panne ou retiré, que la demande dépasse son contexte ou qu'il tarde à répondre, et là le second modèle du même fournisseur répond. LiteLLM ne sait pas faire la différence pour en tirer parti : il met en pause une entrée qui a échoué, jamais tout son fournisseur (lu dans son code le 2026-11-23). Décision du mainteneur du 2026-11-23.

**Sauf les versions anciennes d'une même gamme.** Chez un fournisseur dont le quota est commun à tous ses modèles (un crédit, un solde, un compte ou une adresse IP), seule la dernière version de chaque gamme est routée : une version ancienne ne rapporte aucun quota, puisqu'elle puise dans le même compteur, et la dernière de sa gamme répond mieux. Une version ancienne reste routée, placée par son chiffre, si elle apporte ce qu'aucune version plus récente de sa gamme restée routée n'a : une fenêtre plus grande, la lecture des images, les appels d'outils, ou le même texte pour au moins 10 % de moins du compteur commun (son prix au jeton, ou l'unité du quota, fois les jetons que compte son tokenizer, d'après les pages du fournisseur ; les jetons de réflexion, qu'aucune page ne donne, ne comptent pas). Elle est comparée à chacune de ces versions plus récentes, et non à la dernière seule : une version ancienne qu'une version intermédiaire couvre déjà est commentée aussi. Le but est le plus de quota gratuit et la meilleure réponse pour ce qu'une requête en consomme. Les autres versions anciennes restent dans le gabarit, commentées avec la version qui les remplace. Les gammes différentes d'un même fournisseur, elles, restent ensemble, pour la raison du paragraphe précédent. Règle du mainteneur du 2026-11-25, la comparaison à toutes les versions plus récentes du 2026-11-26.

**`Auto-Fiction` : les modèles de jeu de rôle d'Aion Labs, à part.** Aion Labs les décrit comme réglés pour le jeu de rôle et la narration, y compris les « thèmes adultes et sombres », et n'en modère aucun. Ils sont donc dans un groupe d'accès à eux, `Fiction`, et non dans `LLM`, et dans un routeur à eux, `Auto-Fiction`, qui ne tient qu'eux : aucun autre routeur n'en tient un, et une clé qui a `LLM` ne les atteint pas. Aucun chiffre ne les place, l'ordre est donc écrit à la main, du plus récent et du plus grand au plus petit. Une clé les atteint quand `Fiction` ou `Auto-Fiction` est nommé dans ses modèles.

**`Auto-Paid` : les modèles d'Anthropic, payés sur un crédit, à part.** Anthropic n'a pas d'offre gratuite : chaque appel est payé sur le solde de l'organisation de la clé, que le crédit mensuel d'un forfait Claude Max, Ultra ou Team alimente, et ce crédit ne couvre pas Claude Code. Ses modèles sont donc dans un routeur à eux, `Auto-Paid`, qui ne tient qu'eux, et dans aucun autre : un routeur gratuit dépenserait le crédit à chaque demande de chaque application, et l'agent Claude Code atteint les routeurs gratuits. Ils restent dans le groupe `LLM`, si bien qu'un compte LibreChat les choisit aussi par leur nom. Le crédit étant un quota commun à tous ses modèles, seule la dernière version de chaque gamme (Fable, Opus, Sonnet, Haiku) y est. L'ordre est celui de l'indice de capacités d'Epoch AI, converti et estimé comme ailleurs, faute d'indice d'Artificial Analysis lu au niveau où chaque modèle est appelé.

**Les groupes de données : `Private-Data` et `Public-Data-Only`.** Chaque entrée porte, après son groupe de type, un de ces deux groupes, d'après ce que les conditions de son fournisseur disent de ce qu'on lui envoie (la table et les phrases sont dans le README, « Les groupes de données »). Une clé pour des données privées reçoit `Private-Data` par son nom et aucun routeur : un routeur est dans aucun groupe, et les cascades ci-dessous mélangent les deux groupes, si bien qu'un repli pourrait quitter les entrées `Private-Data` (non vérifié sur une passerelle réelle).

**Les niveaux fixés : ils suivent la façon dont le fournisseur compte la gratuité.** Décision du mainteneur du 2026-11-24 :

- chez un fournisseur qui compte des **requêtes** (Google Gemini, OpenRouter, Kilo Gateway, Requesty), le niveau le plus haut que le modèle accepte : réfléchir plus ne coûte que du temps ;
- chez un fournisseur qui compte des **jetons** (Groq, Aion Labs, Cloudflare et ses neurones), aucun niveau : c'est « défaut du fournisseur », l'équilibre que le concepteur du modèle a choisi. Monter le niveau coûte du quota, ce que les mesures suivantes chiffrent et qui reste le relevé de ce coût (chez Groq : 8 jetons de réflexion en `low`, 562 en `high` pour une même question ; chez Cloudflare, à travers la passerelle le 2026-11-24, gpt-oss-120b et gpt-oss-20b ont produit 42 et 60 jetons en `low`, 135 et 143 par défaut et 280 et 262 en `high`) ;
- chez un fournisseur **payant** (Mistral, DeepSeek en direct, Anthropic), aucun niveau : le client décide, c'est « défaut du fournisseur » ;
- `Auto-Flash-Lite` est classé sur le délai, donc une entrée qu'il tient n'est jamais montée : un modèle qu'il partage avec un autre routeur a une entrée par niveau, nommée `<entrée>-<niveau>`, le nom sans suffixe portant le plus haut ;
- un niveau n'est fixé que là où l'on sait quelles valeurs le modèle accepte, et `check_compose_template.py` tient chaque niveau à ces valeurs, modèle par modèle : une valeur refusée est une erreur immédiate, et l'entrée ne servirait jamais. LiteLLM ne transmet aucun niveau à NVIDIA ni à Z AI, et à Cloudflare seulement si l'entrée le nomme dans `allowed_openai_params`, ce qu'aucune entrée ne fait puisque ce fournisseur compte des neurones ; aucune page ne donne ces valeurs pour les modèles d'OVHcloud et de Cent AI : ces entrées disent « non fixé », avec la raison ;
- une entrée dont le niveau est plus lent que l'attente du routeur (90 s avant le premier mot) a une attente à elle : `gemini-4-hydrogen` en `xhigh` attend 180 s, plus de deux fois son délai médian de 76 s, et 240 s une réponse sans flux.

Ce niveau n'est qu'une valeur par défaut : si un client envoie son propre niveau, c'est le sien qui compte. Claude Code en envoie toujours un, donc `Auto-Claude-Code` n'est pas piloté par ces niveaux ; LibreChat et n8n n'en envoient pas, ils reçoivent le niveau fixé. Les titres de LibreChat, des réponses courtes qu'un modèle qui réfléchit pourrait laisser vides, sont demandés à `Auto-Flash-Lite`.

| Modèle | `Auto-Pro`, `Auto-Code`, `Auto-Claude-Code` | `Auto-Flash` | `Auto-Flash-Lite` |
| --- | --- | --- | --- |
| Gemini 4 Hydrogen | `xhigh` : `gemini-4-hydrogen` | `xhigh` : `gemini-4-hydrogen` | `low` : `gemini-4-hydrogen-low` |
| Gemini 3.8 Flash | `high` : `gemini-3-8-flash` | `high` : `gemini-3-8-flash` | `low` : `gemini-3-8-flash-low` |

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
| Groq | gpt-oss, qwen3.8-27b | 30 requêtes par minute, 8 000 jetons par minute ; 1 000 requêtes et 200 000 jetons par jour (page des limites relue le 2026-11-24). Les jetons de raisonnement comptent dans le quota de jetons (sonde du 2026-11-22 : effort bas, 8 jetons de raisonnement ; haut, 562) ; une valeur d'effort que Groq ne liste pas peut recevoir un 400 | modèle et organisation | non relevé |
| Groq | whisper-large-v3, whisper-large-v3-turbo | 20 requêtes par minute, 7 200 secondes d'audio par heure (plan non établi), 25 Mo par fichier | modèle et organisation | non relevé |
| Cloudflare Workers AI | tous | 10 000 « neurons » par jour ; texte : 300 requêtes par minute | compte | 00:00 UTC |
| NVIDIA API Catalog | tous | 40 requêtes par minute ; plafond quotidien inconnu | compte | — |
| OpenRouter | modèles `:free` | 20 requêtes par minute, 50 par jour (1 000 une fois 10 crédits achetés) | compte | non relevé |
| Requesty | modèles gratuits | 20 requêtes par minute, 200 par jour | organisation | non relevé |
| Kilo Gateway | modèles gratuits, sans clé | 200 requêtes par heure | adresse IP | — |
| OVHcloud AI Endpoints | modèles sans clé | 2 requêtes par minute, observées, écrites sur aucune page | adresse IP et modèle | — |
| Z AI | GLM-4.7-Flash | non publiées hors de la console du compte : inconnues | — | — |
| Cent AI | `hy4-flash:free` | aucune annoncée ; gratuit jusqu'au 30 novembre, la suite est inconnue | — | — |
| Aion Labs | six modèles de jeu de rôle, `Auto-Fiction` seul | 15 requêtes par minute, 20 000 jetons par minute et 20 000 jetons par jour, tous les modèles ensemble | compte | non relevé |
| Vercel AI Gateway | sous-ensemble de modèles, `Auto-Pro`, `Auto-Flash` et `Auto-Flash-Lite` seuls | crédit gratuit mensuel commun à toutes ses entrées, dont le montant n'est publié sur aucune page lue (une version plus ancienne des pages disait 5 $ tous les 30 jours, sans renouvellement observé) ; limites par modèle abaissées, non chiffrées ; 402 une fois le crédit épuisé | compte | non relevé |
| Anthropic | modèles Claude, `Auto-Paid` seul | aucune : payant, sur le solde de l'organisation de la clé, que le crédit mensuel d'un forfait Claude Max (100 $), Ultra (200 $) ou Team (jusqu'à 500 $) alimente ; ce crédit expire à la fin de chaque cycle de facturation et ne couvre pas Claude Code ; sans autre crédit, une demande est refusée une fois le crédit dépensé | organisation | chaque cycle de facturation du forfait |
| Mistral | tous | aucune : payant, sur un solde prépayé | compte | — |
| DeepSeek | tous | aucune : payant, sur un solde prépayé | compte | — |
| OmniRoute | tous | agrégateur local, aucun quota | — | — |

Gemini 3.7 Flash ne figure pas du tout dans la liste de la page de Google : son point d'accès route vers Gemini 3.8 Flash (page des dépréciations, lue le 2026-11-24) et on ne sait pas s'il a un compteur à lui. Il est donc placé juste derrière Gemini 3.8 Flash, comme un jumeau : si le compteur est partagé, la place coûte un refus immédiat, s'il est à lui, elle donne 20 requêtes de plus par jour. Pour trancher, envoyer une requête à `gemini-3-7-flash` et regarder quel compteur bouge dans la page d'utilisation d'AI Studio.

Ce que ça change, en clair :

- **Quand le compteur est celui d'un modèle**, toutes les entrées de ce modèle chez ce fournisseur le partagent, quel que soit leur niveau de réflexion. Par exemple, les têtes de `Auto-Pro` et de `Auto-Flash` n'ont que 20 requêtes par jour : `gemini-4-hydrogen` et `gemini-4-hydrogen-low` puisent dans les mêmes 20, et `gemini-3-8-flash` et `gemini-3-8-flash-low` dans les mêmes 20 aussi. Les deux Flash-Lite ont 500 requêtes par jour chacun : c'est pourquoi ils ouvrent `Auto-Flash-Lite` et pourquoi les entrées Hydrogen et 3.8 Flash y sont en dernier.
- **Quand le compteur est celui d'un compte ou d'une adresse IP**, toutes les entrées du fournisseur le partagent, quel que soit le modèle : une fois épuisé, chacune répond par un refus, et la cascade passe au membre suivant.

## Les routeurs

Dans chaque tableau, « Niveau » dit ce que fixe le gabarit : un niveau entre apostrophes inversées s'il en fixe un, sinon « défaut du fournisseur » ou « non fixé », suivi de la raison. « Indice » et « Délai » sont ceux du niveau où l'entrée est appelée, « (estimé) » marquant un indice tiré de l'indice de capacités d'Epoch AI faute d'indice d'Artificial Analysis. Un tiret veut dire qu'aucun chiffre ne s'applique.

`Auto` n'a pas de tableau : il n'a aucun membre à lui. C'est une entrée qui choisit, pour chaque requête, entre `Auto-Flash-Lite` (niveau `SIMPLE`), `Auto-Flash` (`MEDIUM`) et `Auto-Pro` (`COMPLEX` et `REASONING`) par le classement heuristique de LiteLLM, et la cascade qui s'applique ensuite est celle du routeur choisi, décrite ci-dessous. Elle ne change aucune cascade, et `README.md` dit comment elle se comporte.

### `Auto-Pro`

Tête : `gemini-4-hydrogen`, au niveau `xhigh`. Raisonnement long, le temps n'est pas borné.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Google AI Studio | à la requête, quota par modèle | `xhigh` | 53,9 | 47,4 s | niveau le plus haut du modèle, compté à la requête ; 76 s de délai médian, d'où une attente de 180 s à lui ; meilleur indice du routeur |
| 2 | `kimi-k3-1-pro-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 46,5 | 155,1 s | deuxième meilleur indice, mais 155 s en moyenne avant la première réponse, au-delà des 90 s de patience : point ouvert |
| 3 | `gemini-3-8-flash` | Google AI Studio | à la requête, quota par modèle | `high` | 30,8 | 28,1 s | niveau le plus haut du modèle, compté à la requête ; 28,1 s, sous l'attente du routeur |
| 4 | `gemini-3-7-flash` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 30,8 (estimé) | — | jumeau de `gemini-3-8-flash` : son point d'accès route vers ce modèle et son compteur n'est pas établi, d'où une place juste derrière lui |
| 5 | `inkling-2-small-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 30,6 | 43,2 s | indice 30,6 en 43,2 s |
| 6 | `ling-3-1-flash-requesty` | Requesty | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 30,0 | — | indice 30 d'Artificial Analysis (Ling 3.1 Flash 1019, rapproché par le nom, sans délai publié) : placé par son indice, derrière la 3.8 Flash |
| 7 | `step-5-preview-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 28,5 | 37,9 s | indice 28,5 en 37,9 s |
| 8 | `minimax-m3-1-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 29,1 | 52,0 s | indice 29,1 en 52,0 s |
| 9 | `minimax-m3-1-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 29,1 | 52,0 s | même modèle que `minimax-m3-1-flash-nvidia` chez un autre fournisseur, quota à part ; indice 29,1 en 52,0 s |
| 10 | `mistral-large-4-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 26,1 | 71,3 s | indice 26,1 en 71,3 s |
| 11 | `glm-5-3-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 27,8 | 87,3 s | indice 27,8 en 87,3 s |
| 12 | `ling-3-1-flash-1019-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 29,6 | — | indice 29,6, délai inconnu |
| 13 | `muse-spark-open-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 24,9 | 11,0 s | indice 24,9 en 11,0 s |
| 14 | `mimo-v2-6-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 26,7 | 48,6 s | indice 26,7 en 48,6 s |
| 15 | `gpt-5-2-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 24,6 (estimé) | 54,5 s | indice 24,6 (estimé) en 54,5 s |
| 16 | `gpt-5-2-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 24,6 (estimé) | 54,5 s | indice 24,6 (estimé) en 54,5 s |
| 17 | `beam-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : Kilo ne prend pas `reasoning_effort` pour ce modèle | 17,7 | 10,8 s | indice 17,7 en 10,8 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 18 | `nemotron-ultra-free` | OpenRouter (:free) | à la requête, compteur commun | `high` | 11,8 | 8,0 s | indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 19 | `nemotron-ultra-requesty` | Requesty | à la requête, compteur commun | `max` | 11,8 | 8,0 s | même modèle que `nemotron-ultra-free` chez un autre fournisseur, quota à part ; indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 20 | `nemotron-ultra-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 11,8 | 8,0 s | même modèle que `nemotron-ultra-free` chez un autre fournisseur, quota à part ; indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 21 | `nemotron-ultra-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 11,8 | 8,0 s | même modèle que `nemotron-ultra-free` chez un autre fournisseur, quota à part ; indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 22 | `nemotron-ultra-kilo` | Kilo Gateway | à la requête, par adresse IP | `high` | 11,8 | 8,0 s | même modèle que `nemotron-ultra-free` chez un autre fournisseur, quota à part ; indice 11,8 en 8,0 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 23 | `nemotron-reasoning-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : aucun niveau publié pour ce modèle | — | — | pas d'indice : garde sa place historique |
| 24 | `nemotron-reasoning-requesty` | Requesty | à la requête, compteur commun | `max` | — | — | même modèle que `nemotron-reasoning-free` chez un autre fournisseur, quota à part ; pas d'indice : garde sa place historique |
| 25 | `nemotron-reasoning-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | même modèle que `nemotron-reasoning-free` chez un autre fournisseur, quota à part ; pas d'indice : garde sa place historique |
| 26 | `nemotron-reasoning-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : aucun niveau publié pour ce modèle | — | — | même modèle que `nemotron-reasoning-free` chez un autre fournisseur, quota à part ; pas d'indice : garde sa place historique |
| 27 | `nemotron-super-vl-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : aucun niveau publié pour ce modèle | 13,6 | 12,4 s | indice 13,6 en 12,4 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 28 | `nemotron-super-vl-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 29 | `nemotron-super-vl-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 30 | `nemotron-super-vl-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : aucun niveau publié pour ce modèle | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 31 | `hy4-flash-cent-ai` | Cent AI | gratuit jusqu'au 30 novembre, la suite n'est pas annoncée | non fixé : valeurs acceptées non publiées | — | — | aucun chiffre publié : derrière les membres gratuits auxquels on ne peut pas le comparer, avant OVHcloud |
| 32 | `deepseek-v4-1-flash-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | 32,0 (estimé) | 21,1 s | indice 32,0 en 21,1 s |
| 33 | `qwen3-5-397b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | — | — | aucun chiffre publié : garde sa place historique |
| 34 | `gpt-oss-120b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | 4,2 (estimé) | 10,3 s | indice 4,2 en 10,3 s ; sous le plancher de `Auto-Pro`, mais garde sa place du gabarit |
| 35 | `deepseek-v4-pro-direct` | DeepSeek | prépayé | défaut du fournisseur | 20,8 | 48,8 s | payant : après tous les gratuits |
| 36 | `omniroute-free-reasoning` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | routeur local sans clé et sans chiffre : tout à la fin |

### `Auto-Flash`

Tête : `gemini-4-hydrogen`, au niveau `xhigh`, comme `Auto-Pro`. L'assistant de tous les jours : le meilleur score, au prix d'une attente plus longue.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Google AI Studio | à la requête, quota par modèle | `xhigh` | 53,9 | 47,4 s | niveau le plus haut du modèle, compté à la requête ; 76 s de délai médian, d'où une attente de 180 s à lui ; meilleur indice du routeur |
| 2 | `kimi-k3-1-pro-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 46,5 | 155,1 s | deuxième place gardée du gabarit : à 1 point par seconde il serait bien plus bas, et 155 s dépassent les 90 s de patience : point ouvert |
| 3 | `gemini-3-8-flash` | Google AI Studio | à la requête, quota par modèle | `high` | 30,8 | 28,1 s | niveau le plus haut du modèle, compté à la requête ; 28,1 s, sous l'attente du routeur |
| 4 | `gemini-3-7-flash` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 30,8 (estimé) | — | jumeau de `gemini-3-8-flash` : son point d'accès route vers ce modèle et son compteur n'est pas établi, d'où une place juste derrière lui |
| 5 | `inkling-2-small-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 30,6 | 43,2 s | indice 30,6 en 43,2 s |
| 6 | `ling-3-1-flash-requesty` | Requesty | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 30,0 | — | indice 30 d'Artificial Analysis (Ling 3.1 Flash 1019, rapproché par le nom, sans délai publié) : placé par son indice, avant les entrées de NVIDIA de moins de 29 |
| 7 | `step-5-preview-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 28,5 | 37,9 s | indice 28,5 en 37,9 s |
| 8 | `minimax-m3-1-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 29,1 | 52,0 s | indice 29,1 en 52,0 s |
| 9 | `minimax-m3-1-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 29,1 | 52,0 s | même modèle que `minimax-m3-1-flash-nvidia` chez un autre fournisseur, quota à part ; indice 29,1 en 52,0 s |
| 10 | `mistral-large-4-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 26,1 | 71,3 s | indice 26,1 en 71,3 s |
| 11 | `glm-5-3-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 27,8 | 87,3 s | indice 27,8 en 87,3 s |
| 12 | `ling-3-1-flash-1019-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 29,6 | — | indice 29,6, délai inconnu |
| 13 | `muse-spark-open-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 24,9 | 11,0 s | indice 24,9 en 11,0 s |
| 14 | `mimo-v2-6-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 26,7 | 48,6 s | indice 26,7 en 48,6 s |
| 15 | `gemini-3-6-flash` | Google AI Studio | à la requête, quota par modèle | `high` | 25,6 (estimé) | 12,6 s | niveau le plus haut du modèle, le seul qu'Artificial Analysis mesure ; indice 25,6 en 12,6 s |
| 16 | `gpt-5-2-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 24,6 (estimé) | 54,5 s | indice 24,6 (estimé) en 54,5 s |
| 17 | `gpt-5-2-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 24,6 (estimé) | 54,5 s | indice 24,6 (estimé) en 54,5 s |
| 18 | `gemini-3-flash-preview` | Google AI Studio | à la requête, quota par modèle | `high` | 21,5 (estimé) | 6,3 s | niveau le plus haut du modèle, et son défaut ; indice 21,5 en 6,3 s |
| 19 | `kimi-k2-7-code-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 19,5 (estimé) | 36,5 s | indice 19,5 (estimé) en 36,5 s |
| 20 | `gpt-5-1-thinking-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 19,1 (estimé) | — | indice 19,1 (estimé), délai inconnu |
| 21 | `gpt-5-1-thinking-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 19,1 (estimé) | — | indice 19,1 (estimé), délai inconnu |
| 22 | `qwen3-6-plus-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 15,4 (estimé) | 36,2 s | indice 15,4 (estimé) en 36,2 s |
| 23 | `inkling-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 14,5 (estimé) | 17,9 s | indice 14,5 (estimé) en 17,9 s |
| 24 | `o3-pro-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 12,8 (estimé) | — | indice 12,8 (estimé), délai inconnu |
| 25 | `qwen3-5-plus-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 12,5 (estimé) | — | indice 12,5 (estimé), délai inconnu |
| 26 | `o3-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 12,0 (estimé) | 7,9 s | indice 12,0 (estimé) en 7,9 s |
| 27 | `o3-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 12,0 (estimé) | 7,9 s | indice 12,0 (estimé) en 7,9 s |
| 28 | `qwen3-6-27b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 11,7 (estimé) | 42,1 s | indice 11,7 (estimé) en 42,1 s |
| 29 | `gpt-5-4-nano-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 11,3 (estimé) | 36,4 s | indice 11,3 (estimé) en 36,4 s |
| 30 | `deepseek-v3-2-thinking-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 11,2 (estimé) | 17,9 s | indice 11,2 (estimé) en 17,9 s |
| 31 | `gpt-5-mini-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 10,9 (estimé) | 51,1 s | indice 10,9 (estimé) en 51,1 s |
| 32 | `gpt-5-mini-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 10,9 (estimé) | 51,1 s | indice 10,9 (estimé) en 51,1 s |
| 33 | `o4-mini-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 10,0 (estimé) | 15,7 s | indice 10,0 (estimé) en 15,7 s |
| 34 | `gpt-oss-120b-groq` | Groq | au jeton | défaut du fournisseur | 4,2 (estimé) | 10,3 s | indice 4,2 en 10,3 s |
| 35 | `gpt-oss-120b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | 4,2 (estimé) | 10,3 s | même modèle que `gpt-oss-120b-groq` chez un autre fournisseur, quota à part ; indice 4,2 en 10,3 s |
| 36 | `gpt-oss-120b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 4,2 (estimé) | 10,3 s | même modèle que `gpt-oss-120b-ovh` chez un autre fournisseur, quota à part ; indice 4,2 (estimé) en 10,3 s |
| 37 | `qwen3-8-27b-groq` | Groq | au jeton | défaut du fournisseur : ne réfléchit pas par défaut, et `Auto-Flash-Lite` ne monte pas de niveau | 10,0 | 5,1 s | indice 10,0 en 5,1 s |
| 38 | `gemma-4-31b-gemini` | Google AI Studio | à la requête, quota par modèle | non fixé : LiteLLM envoie à Gemma un budget que Google ne documente pas | 8,7 (estimé) | 35,4 s | indice 8,7 en 35,4 s |
| 39 | `gemma-4-31b-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : aucun niveau publié pour ce modèle | 8,7 (estimé) | 35,4 s | même modèle que `gemma-4-31b-gemini` chez un autre fournisseur, quota à part ; indice 8,7 en 35,4 s |
| 40 | `gemma-4-31b-requesty` | Requesty | à la requête, compteur commun | `high` | 8,7 (estimé) | 35,4 s | même modèle que `gemma-4-31b-gemini` chez un autre fournisseur, quota à part ; indice 8,7 en 35,4 s |
| 41 | `gemma-4-31b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 8,7 (estimé) | 35,4 s | même modèle que `gemma-4-31b-gemini` chez un autre fournisseur, quota à part ; indice 8,7 en 35,4 s |
| 42 | `qwen3-6-35b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 8,7 (estimé) | — | indice 8,7 (estimé), délai inconnu |
| 43 | `qwen3-5-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 8,4 (estimé) | — | indice 8,4 (estimé), délai inconnu |
| 44 | `glm-4-7-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 7,8 (estimé) | 29,6 s | indice 7,8 (estimé) en 29,6 s |
| 45 | `kimi-k2-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 5,5 (estimé) | 3,5 s | indice 5,5 (estimé) en 3,5 s |
| 46 | `deepseek-v3-1-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 5,0 (estimé) | 8,2 s | indice 5,0 (estimé) en 8,2 s |
| 47 | `gemini-2-5-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 4,9 (estimé) | 11,2 s | indice 4,9 (estimé) en 11,2 s |
| 48 | `mistral-medium-3-5-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 4,6 | 26,8 s | indice 4,6 en 26,8 s |
| 49 | `gpt-5-nano-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 2,9 (estimé) | 55,1 s | indice 2,9 (estimé) en 55,1 s |
| 50 | `particle-1-free` | OpenRouter (:free) | à la requête, compteur commun | `xhigh` | — | — | aucun chiffre publié : garde sa place historique |
| 51 | `particle-1-kilo` | Kilo Gateway | à la requête, par adresse IP | `max` | — | — | aucun chiffre publié : garde sa place historique |
| 52 | `ernie-5-5-flash-free` | OpenRouter (:free) | à la requête, compteur commun | `high` | — | — | aucun chiffre publié : garde sa place historique |
| 53 | `ernie-5-5-flash-kilo` | Kilo Gateway | à la requête, par adresse IP | `high` | — | — | aucun chiffre publié : garde sa place historique |
| 54 | `beam-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : Kilo ne prend pas `reasoning_effort` pour ce modèle | 17,7 | 10,8 s | indice 17,7 en 10,8 s |
| 55 | `nemotron-super-vl-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : aucun niveau publié pour ce modèle | 13,6 | 12,4 s | indice 13,6 en 12,4 s |
| 56 | `nemotron-super-vl-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s |
| 57 | `nemotron-super-vl-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s |
| 58 | `muse-glimmer-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 6,3 | 23,7 s | indice 6,3 en 23,7 s |
| 59 | `muse-glimmer-requesty` | Requesty | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | 6,3 | 23,7 s | même modèle que `muse-glimmer-nvidia` chez un autre fournisseur, quota à part ; indice 6,3 en 23,7 s |
| 60 | `nemotron-super-vl-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : aucun niveau publié pour ce modèle | 13,6 | 12,4 s | même modèle que `nemotron-super-vl-free` chez un autre fournisseur, quota à part ; indice 13,6 en 12,4 s |
| 61 | `flint-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place historique, devant son jumeau |
| 62 | `flint-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : aucun niveau publié pour ce modèle | — | — | aucun chiffre publié : garde sa place historique |
| 63 | `glyph-cluster-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : Kilo ne prend pas `reasoning_effort` pour ce modèle | — | — | aucun chiffre publié : garde sa place historique |
| 64 | `dots-3-note-preview-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : aucun niveau publié pour ce modèle | — | — | aucun chiffre publié : derrière les membres gratuits auxquels on ne peut pas le comparer, avant le routeur gratuit d'OpenRouter ; gratuit jusqu'au 31 décembre |
| 65 | `dots-3-note-preview-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : aucun niveau publié pour ce modèle | — | — | même modèle que `dots-3-note-preview-free` chez un autre fournisseur ; aucun chiffre publié : derrière lui ; gratuit jusqu'au 31 décembre |
| 66 | `openrouter-auto-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : routeur qui choisit un modèle par requête | — | — | aucun chiffre publié : garde sa place historique |
| 67 | `kilo-auto-free` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | routeur gratuit de Kilo, qui choisit un modèle par requête : aucun chiffre publié, derrière le routeur gratuit d'OpenRouter |
| 68 | `kilo-openrouter-free` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | routeur gratuit d'OpenRouter appelé par Kilo : le compteur par adresse IP de Kilo et non celui du compte OpenRouter ; aucun chiffre publié |
| 69 | `ling-3-2-flash-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié ; refusé par le pool amont partagé la plupart du temps, d'où sa place en fin des gratuits |
| 70 | `ling-3-2-flash-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | même modèle que `ling-3-2-flash-free` chez un autre fournisseur ; aucun chiffre publié ; mêmes refus du pool amont |
| 71 | `hy4-flash-cent-ai` | Cent AI | gratuit jusqu'au 30 novembre, la suite n'est pas annoncée | non fixé : valeurs acceptées non publiées | — | — | aucun chiffre publié : derrière les membres gratuits auxquels on ne peut pas le comparer, avant OVHcloud |
| 72 | `qwen-3-14b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 0,0 (estimé) | — | indice 0,0 (estimé), délai inconnu ; sous le plancher de `Auto-Flash`, mais garde sa place du gabarit |
| 73 | `qwen-3-30b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 0,0 (estimé) | — | indice 0,0 (estimé), délai inconnu ; sous le plancher de `Auto-Flash`, mais garde sa place du gabarit |
| 74 | `qwen-3-32b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 0,4 (estimé) | — | indice 0,4 (estimé), délai inconnu ; sous le plancher de `Auto-Flash`, mais garde sa place du gabarit |
| 75 | `qwen3-coder-30b-a3b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 76 | `qwen3-vl-instruct-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 77 | `qwen3-7-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 78 | `qwen3-8-omni-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 79 | `nova-2-lite-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 80 | `seed-2-1-turbo-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 81 | `apex-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 82 | `glimpse-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 83 | `mercury-3-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 84 | `ling-3-0-flash-fin-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 85 | `ling-3-0-flash-sante-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 86 | `ling-3-0-flash-vl-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 87 | `schematron-v2-small-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 88 | `schematron-v2-turbo-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 89 | `interfaze-beta-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 90 | `lfm2-5-24b-a2b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 91 | `longcat-2-5-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 92 | `llama-3-1-8b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 0,0 (estimé) | — | indice 0,0 (estimé), délai inconnu ; sous le plancher de `Auto-Flash`, mais garde sa place du gabarit |
| 93 | `muse-ember-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 36,0 | 5,4 s | indice 36,0 en 5,4 s |
| 94 | `codestral-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 95 | `ministral-14b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 96 | `ministral-3b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 97 | `ministral-8b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 98 | `mistral-nemo-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 0,0 (estimé) | — | indice 0,0 (estimé), délai inconnu ; sous le plancher de `Auto-Flash`, mais garde sa place du gabarit |
| 99 | `toast-1-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 100 | `morph-v3-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 101 | `morph-v3-large-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 102 | `nemotron-3-super-120b-a12b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 103 | `nemotron-nano-12b-v2-vl-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 104 | `nemotron-nano-9b-v2-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 105 | `gpt-5-1-codex-max-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 106 | `gpt-oss-safeguard-120b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 107 | `gpt-oss-safeguard-20b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 108 | `ultramarine-1-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 109 | `sonar-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 110 | `arrow-2-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 111 | `arrow-2-telos-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 112 | `flint-v1-0-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 113 | `scaledown-summarize-1-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 114 | `hy-mt2-lite-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 115 | `hy-mt2-plus-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 116 | `hy-mt2-pro-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 117 | `hy4-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 118 | `glm-4-5v-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 5,7 s | pas de chiffre |
| 119 | `glm-4-7-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 36,2 s | pas de chiffre |
| 120 | `glm-4-7-flashx-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 121 | `glm-5v-turbo-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | pas de chiffre |
| 122 | `mistral-small-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 4,3 | 14,9 s | indice 4,3 en 14,9 s |
| 123 | `deepseek-v4-1-flash-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | 32,0 (estimé) | 21,1 s | indice 32,0 en 21,1 s |
| 124 | `qwen3-5-397b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | — | — | aucun chiffre publié : garde sa place historique |
| 125 | `gpt-oss-120b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | 4,2 (estimé) | 10,3 s | même modèle que `gpt-oss-120b-groq` chez un autre fournisseur, quota à part ; indice 4,2 en 10,3 s |
| 126 | `llama-3-3-70b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre relu : « Being retired » (fin de vie le 2027-02-10), servi jusque-là ; après les gros modèles d'OVHcloud |
| 127 | `qwen3-8-27b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | 21,9 (estimé) | — | indice 21,9, délai inconnu |
| 128 | `qwen3-6-27b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre relu : « Being retired » (fin de vie le 2027-02-10), servi jusque-là ; derrière le modèle qui le remplace |
| 129 | `qwen3-8-27b-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 20,1 | 135,4 s | même modèle que ses jumeaux, chez un autre fournisseur ; réfléchit en Xhigh par défaut, 135 s avant la réponse, au-delà des 90 s de patience : un repli de plus, juste derrière eux |
| 130 | `qwen3-6-35b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | — | — | aucun chiffre publié : garde sa place historique |
| 131 | `nemotron3-omni-30b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | — | — | pas d'indice : garde sa place historique |
| 132 | `mistral-small-3-2-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | — | — | aucun chiffre publié : garde sa place historique |
| 133 | `mistral-medium` | Mistral | prépayé | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr (indice 4,6 en 26,8 s) : au-dessus du plancher de `Auto-Flash` (indice de capacités 141,6 contre 140,8 pour Gemini 2.5 Flash), sous celui de `Auto-Pro` ; devant `mistral-small`, le plus petit |
| 134 | `mistral-small` | Mistral | prépayé | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 135 | `ministral-14b` | Mistral | prépayé | défaut du fournisseur | — | 2,3 s | pas d'indice : garde sa place historique |
| 136 | `ministral-8b` | Mistral | prépayé | défaut du fournisseur | — | 2,0 s | pas d'indice : garde sa place historique |
| 137 | `deepseek-flash-direct` | DeepSeek | prépayé | défaut du fournisseur | 28,6 | 21,1 s | payant : après tous les gratuits |
| 138 | `omniroute-free-auto` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | routeur local sans clé et sans chiffre : tout à la fin |

### `Auto-Flash-Lite`

Tête : `gemini-3-5-flash-lite`. Demandes simples et courtes : le score moins 3 points par seconde d'attente, puis les membres sans indice, puis ceux qui partagent un quota.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-3-5-flash-lite` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 11,7 | 4,6 s | score -2,1 (indice 11,7 moins 3 fois 4,6 s) : le meilleur des membres qui ont leur propre quota ; 500 requêtes par jour, le sien |
| 2 | `gemini-3-1-flash-lite` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 6,2 | 3,2 s | score -3,4 (indice 6,2 moins 3 fois 3,2 s) ; 500 requêtes par jour, le sien |
| 3 | `lfm-3-1-7b-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | 6,0 | 13,8 s | score -35,3 (indice 6,0 moins 3 fois 13,8 s) |
| 4 | `lfm-3-1-7b-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | 6,0 | 13,8 s | score -35,3 (indice 6,0 moins 3 fois 13,8 s) ; même modèle que `lfm-3-1-7b-free` chez un autre fournisseur |
| 5 | `nemotron-lightning-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | 5,5 | 17,7 s | score -47,5 (indice 5,5 moins 3 fois 17,7 s) |
| 6 | `nemotron-lightning-requesty` | Requesty | à la requête, compteur commun | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | 5,5 | 17,7 s | score -47,5 (indice 5,5 moins 3 fois 17,7 s) ; même modèle que `nemotron-lightning-free` chez un autre fournisseur |
| 7 | `nemotron-lightning-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | 5,5 | 17,7 s | score -47,5 (indice 5,5 moins 3 fois 17,7 s) ; même modèle que `nemotron-lightning-free` chez un autre fournisseur |
| 8 | `nemotron-lightning-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | 5,5 | 17,7 s | même modèle que `nemotron-lightning-free` chez un autre fournisseur, quota à part ; indice 5,5 en 17,7 s |
| 9 | `nemotron-lightning-kilo` | Kilo Gateway | à la requête, par adresse IP | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | 5,5 | 17,7 s | score -47,5 (indice 5,5 moins 3 fois 17,7 s) ; même modèle que `nemotron-lightning-free` chez un autre fournisseur |
| 10 | `gemini-2-5-flash-lite-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 0,4 s | même modèle que `gemini-2-5-flash-lite` chez un autre fournisseur, quota à part ; niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant |
| 11 | `gpt-4-1-nano-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 0,9 s | un délai de 0,9 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 12 | `llama-4-scout-17b-16e-instruct-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | 1,1 s | un délai de 1,1 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 13 | `llama-4-scout-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,1 s | même modèle que `llama-4-scout-17b-16e-instruct-cloudflare` chez un autre fournisseur, quota à part ; un délai de 1,1 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 14 | `llama-4-maverick-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,2 s | un délai de 1,2 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 15 | `nova-micro-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,3 s | un délai de 1,3 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 16 | `qwen3-next-80b-a3b-instruct-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,3 s | un délai de 1,3 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 17 | `qwen3-coder-next-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,5 s | un délai de 1,5 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 18 | `gpt-4-1-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,7 s | un délai de 1,7 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 19 | `gpt-4-1-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,7 s | un délai de 1,7 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 20 | `gpt-4-1-mini-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,8 s | un délai de 1,8 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 21 | `gpt-4-1-mini-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,8 s | un délai de 1,8 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 22 | `gemma-3-4b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | 1,9 s | un délai de 1,9 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 23 | `gpt-4o-mini-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,9 s | un délai de 1,9 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 24 | `gpt-4o-mini-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,9 s | un délai de 1,9 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 25 | `nova-lite-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 1,9 s | un délai de 1,9 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 26 | `gpt-4o-fast-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 2,2 s | un délai de 2,2 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 27 | `gpt-4o-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 2,2 s | un délai de 2,2 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 28 | `llama-3-3-70b-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | 2,3 s | un délai de 2,3 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 29 | `llama-3-3-70b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 2,3 s | même modèle que `llama-3-3-70b-cloudflare` chez un autre fournisseur, quota à part ; un délai de 2,3 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 30 | `gemma-3-12b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | 3,1 s | un délai de 3,1 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 31 | `nova-pro-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 3,1 s | un délai de 3,1 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 32 | `mistral-large-3-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 4,2 s | un délai de 4,2 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 33 | `command-a-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 6,5 s | un délai de 6,5 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 34 | `ling-3-0-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 7,7 s | un délai de 7,7 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 35 | `gpt-5-1-codex-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 8,2 s | un délai de 8,2 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 36 | `gpt-5-1-codex-mini-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 8,4 s | un délai de 8,4 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 37 | `glm-4-5-air-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 12,5 s | un délai de 12,5 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 38 | `deepseek-r1-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 14,7 s | un délai de 14,7 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 39 | `step-3-7-flash-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 15,9 s | un délai de 15,9 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 40 | `minimax-m2-7-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 18,0 s | un délai de 18,0 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 41 | `minimax-m2-5-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 22,0 s | un délai de 22,0 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 42 | `hy3-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 33,6 s | un délai de 33,6 s et pas d'indice : après ceux qui ont les deux, le plus rapide d'abord |
| 43 | `gpt-oss-20b-groq` | Groq | au jeton | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant |
| 44 | `gpt-oss-20b-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gpt-oss-20b-groq` chez un autre fournisseur |
| 45 | `gpt-oss-20b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 36,6 s | même modèle que `gpt-oss-20b-groq` chez un autre fournisseur, quota à part ; niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant |
| 46 | `gemma-4-26b-gemini` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant |
| 47 | `gemma-4-26b-free` | OpenRouter (:free) | à la requête, compteur commun | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gemma-4-26b-gemini` chez un autre fournisseur |
| 48 | `gemma-4-26b-vercel` | Vercel AI Gateway | crédit gratuit mensuel, compteur commun | non fixé : non vérifié chez ce fournisseur | — | 34,3 s | même modèle que `gemma-4-26b-free` chez un autre fournisseur, quota à part ; niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant |
| 49 | `gemma-4-26b-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gemma-4-26b-gemini` chez un autre fournisseur |
| 50 | `qwen2-5-coder-32b-instruct-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | aucun chiffre d'Artificial Analysis ; seul l'indice de capacités d'Epoch AI le note (118,7) : en tête des membres Cloudflare sans chiffre |
| 51 | `phonellm-mini-alpha-2-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | aucun chiffre publié : parmi les derniers membres gratuits, par taille (30B) ; pas de phase de raisonnement |
| 52 | `gemma-sea-lion-v4-27b-it-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | aucun chiffre publié : parmi les derniers membres gratuits, par taille |
| 53 | `mistral-small-3-1-24b-instruct-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | aucun chiffre publié pour cette version : parmi les derniers membres gratuits, par taille |
| 54 | `llama-3-2-11b-vision-instruct-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | aucun chiffre publié : parmi les derniers membres gratuits, par taille ; échoue tant que la licence de Meta n'est pas acceptée sur le compte |
| 55 | `mistral-7b-instruct-v0-2-lora-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | aucun chiffre publié : parmi les derniers membres gratuits, par taille (7B) ; 15 000 jetons de contexte, que les vérifications préalables du routeur lui épargnent quand la demande ne tient pas, et aucun appel d'outils |
| 56 | `granite-4-0-h-micro-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | aucun chiffre publié : parmi les derniers membres gratuits, le plus petit |
| 57 | `nemotron-bolt-e4b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont |
| 58 | `nemotron-3-nano-30b-requesty` | Requesty | à la requête, compteur commun | non fixé : non vérifié chez ce fournisseur | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont, devant OVHcloud ; même modèle que `nemotron3-nano-30b-ovh` |
| 59 | `gpt-oss-20b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gpt-oss-20b-groq` chez un autre fournisseur |
| 60 | `gemma-4-26b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place d'avant ; même modèle que `gemma-4-26b-gemini` chez un autre fournisseur |
| 61 | `nemotron3-nano-30b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont |
| 62 | `qwen3-5-9b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont |
| 63 | `olala-mini-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : `Auto-Flash-Lite` ne monte pas de niveau | — | — | aucun chiffre publié : garde sa place d'avant, après ceux qui en ont |
| 64 | `gemini-3-8-flash-low` | Google AI Studio | à la requête, quota par modèle | `low` | 22,5 | 5,1 s | niveau gardé par `Auto-Flash-Lite` : `low`, car `medium` rapporte 0,81 point par seconde, moins que les 3 demandés ; score 7,3, le meilleur du routeur, mais même modèle que la deuxième place de `Auto-Pro` et que `Auto-Flash` : dans les derniers pour ne pas manger leurs 20 requêtes par jour |
| 65 | `gemini-3-7-flash` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | — | — | ni indice ni délai (un routeur qui tient au temps n'utilise aucune estimation) : jumeau de `gemini-3-8-flash-low`, son point d'accès route vers ce modèle et son compteur n'est pas établi, d'où une place juste derrière lui |
| 66 | `gemini-4-hydrogen-low` | Google AI Studio | à la requête, quota par modèle | `low` | 26,9 | 7,6 s | niveau gardé par `Auto-Flash-Lite` : `low`, car `medium` rapporte 2,6 points par seconde, moins que les 3 demandés ; score 4,0, mais même modèle que la tête de `Auto-Pro` : dans les derniers pour ne pas manger ses 20 requêtes par jour |
| 67 | `qwen3-8-27b-groq` | Groq | au jeton | défaut du fournisseur : ne réfléchit pas par défaut, et `Auto-Flash-Lite` ne monte pas de niveau | 10,0 | 5,1 s | score -5,2, mais c'est la même entrée que celle de `Auto-Flash` : même quota, donc dans les derniers |
| 68 | `hy4-flash-cent-ai` | Cent AI | gratuit jusqu'au 30 novembre, la suite n'est pas annoncée | non fixé : valeurs acceptées non publiées | — | — | aucun chiffre publié, et c'est la même entrée que celle de `Auto-Flash` : même quota, donc dans les derniers |
| 69 | `ministral-3b` | Mistral | prépayé | défaut du fournisseur | — | 1,7 s | payant : après les gratuits |
| 70 | `omniroute-free-fast` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | routeur local sans clé et sans chiffre : tout à la fin, après le payant |

### `Auto-Code`

Tête : `gemini-4-hydrogen`, au niveau `xhigh`. Classé par position de code (Epoch AI, plus petite = meilleure).

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Position de code | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Google AI Studio | à la requête, quota par modèle | `xhigh` | 53,9 | 9 % | 47,4 s | niveau le plus haut du modèle, compté à la requête ; 76 s de délai médian, d'où une attente de 180 s à lui ; meilleur indice du routeur |
| 2 | `gemini-3-8-flash` | Google AI Studio | à la requête, quota par modèle | `high` | 30,8 | 17 % | 28,1 s | niveau le plus haut du modèle, compté à la requête ; 28,1 s, sous l'attente du routeur |
| 3 | `gemini-3-7-flash` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 30,8 (estimé) | 46 % | — | jumeau de `gemini-3-8-flash` : son point d'accès route vers ce modèle et son compteur n'est pas établi, d'où une place juste derrière lui |
| 4 | `glm-5-3-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 27,8 | 68 % | 87,3 s | indice 27,8 en 87,3 s |
| 5 | `kimi-k3-1-pro-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 46,5 | 14 % (estimé) | 155,1 s | place du gabarit ; 155 s en moyenne avant la première réponse, au-delà des 90 s de patience : point ouvert |
| 6 | `step-5-preview-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 28,5 | 33 % (estimé) | 37,9 s | indice 28,5 en 37,9 s |
| 7 | `minimax-m3-1-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 29,1 | 32 % (estimé) | 52,0 s | indice 29,1 en 52,0 s |
| 8 | `mistral-large-4-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 26,1 | 36 % (estimé) | 71,3 s | indice 26,1 en 71,3 s |
| 9 | `qwen3-8-27b-groq` | Groq | au jeton | défaut du fournisseur : ne réfléchit pas par défaut, et `Auto-Flash-Lite` ne monte pas de niveau | 10,0 | 71 % (estimé) | 5,1 s | indice 10,0 en 5,1 s |
| 10 | `gemini-3-6-flash` | Google AI Studio | à la requête, quota par modèle | `high` | 25,6 (estimé) | 72 % | 12,6 s | niveau le plus haut du modèle, le seul qu'Artificial Analysis mesure ; indice 25,6 en 12,6 s |
| 11 | `muse-glimmer-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 6,3 | 80 % (estimé) | 23,7 s | indice 6,3 en 23,7 s |
| 12 | `laguna-xs-2-1-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 13 | `glm-4-7-flash-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 14 | `glm-4-7-flash-zai` | Z AI | à la requête, limite non publiée | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | — | même modèle que `glm-4-7-flash-cloudflare` chez un autre fournisseur, quota à part ; niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 15 | `glm-4-5-flash-zai` | Z AI | à la requête, limite non publiée | non fixé : non vérifié chez ce fournisseur | — | — | — | aucun chiffre publié : fin des membres gratuits à clé, derrière son frère ; même compte et même limite non publiée |
| 16 | `phonellm-mini-alpha-2-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | — | aucun chiffre publié : fin des membres gratuits à clé, 262 140 jetons de contexte et appels d'outils |
| 17 | `deepseek-v4-1-flash-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | 32,0 (estimé) | 29 % (estimé) | 21,1 s | indice 32,0 en 21,1 s |
| 18 | `qwen3-5-397b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | — | — | — | aucun chiffre publié : garde sa place historique |
| 19 | `gpt-oss-120b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | 4,2 (estimé) | 84 % | 10,3 s | indice 4,2 en 10,3 s ; sous le plancher de `Auto-Code`, mais garde sa place du gabarit |
| 20 | `qwen3-8-27b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | 21,9 (estimé) | 43 % (estimé) | — | indice 21,9, délai inconnu |
| 21 | `qwen3-8-27b-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 20,1 | — | 135,4 s | même modèle que ses jumeaux, chez un autre fournisseur ; réfléchit en Xhigh par défaut, 135 s avant la réponse, au-delà des 90 s de patience : un repli de plus, juste derrière eux |
| 22 | `qwen3-6-35b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | — | — | — | aucun chiffre publié : garde sa place historique |
| 23 | `laguna-xs-2-1-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : valeurs acceptées non publiées | — | — | — | aucun chiffre publié : garde sa place historique |
| 24 | `codestral` | Mistral | prépayé | défaut du fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 25 | `codestral-2508` | Mistral | prépayé | défaut du fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 26 | `deepseek-v4-pro-direct` | DeepSeek | prépayé | défaut du fournisseur | 20,8 | 22 % | 48,8 s | payant : après tous les gratuits |
| 27 | `omniroute-free-code` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | — | routeur local sans clé et sans chiffre : tout à la fin |

### `Auto-Claude-Code`

Tête : `gemini-4-hydrogen`, au niveau `xhigh`. La cascade de `Auto-Code` sans les membres qui ne prennent pas les appels d'outils, dans le même ordre. Ses membres, et eux seuls, sont aussi dans le groupe d'accès `Claude-Code`, celui de la clé de l'agent : LiteLLM vérifie la clé avant chaque secours, et cette clé n'atteint ainsi que des modèles qui prennent les appels d'outils.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Position de code | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `gemini-4-hydrogen` | Google AI Studio | à la requête, quota par modèle | `xhigh` | 53,9 | 9 % | 47,4 s | niveau le plus haut du modèle, compté à la requête ; 76 s de délai médian, d'où une attente de 180 s à lui ; meilleur indice du routeur |
| 2 | `gemini-3-8-flash` | Google AI Studio | à la requête, quota par modèle | `high` | 30,8 | 17 % | 28,1 s | niveau le plus haut du modèle, compté à la requête ; 28,1 s, sous l'attente du routeur |
| 3 | `gemini-3-7-flash` | Google AI Studio | à la requête, quota par modèle | défaut du fournisseur | 30,8 (estimé) | 46 % | — | jumeau de `gemini-3-8-flash` : son point d'accès route vers ce modèle et son compteur n'est pas établi, d'où une place juste derrière lui |
| 4 | `glm-5-3-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 27,8 | 68 % | 87,3 s | indice 27,8 en 87,3 s |
| 5 | `kimi-k3-1-pro-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 46,5 | 14 % (estimé) | 155,1 s | place du gabarit ; 155 s en moyenne avant la première réponse, au-delà des 90 s de patience : point ouvert |
| 6 | `step-5-preview-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 28,5 | 33 % (estimé) | 37,9 s | indice 28,5 en 37,9 s |
| 7 | `minimax-m3-1-flash-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 29,1 | 32 % (estimé) | 52,0 s | indice 29,1 en 52,0 s |
| 8 | `mistral-large-4-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 26,1 | 36 % (estimé) | 71,3 s | indice 26,1 en 71,3 s |
| 9 | `qwen3-8-27b-groq` | Groq | au jeton | défaut du fournisseur : ne réfléchit pas par défaut, et `Auto-Flash-Lite` ne monte pas de niveau | 10,0 | 71 % (estimé) | 5,1 s | indice 10,0 en 5,1 s |
| 10 | `gemini-3-6-flash` | Google AI Studio | à la requête, quota par modèle | `high` | 25,6 (estimé) | 72 % | 12,6 s | niveau le plus haut du modèle, le seul qu'Artificial Analysis mesure ; indice 25,6 en 12,6 s |
| 11 | `muse-glimmer-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 6,3 | 80 % (estimé) | 23,7 s | indice 6,3 en 23,7 s |
| 12 | `laguna-xs-2-1-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 13 | `glm-4-7-flash-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | — | niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 14 | `glm-4-7-flash-zai` | Z AI | à la requête, limite non publiée | non fixé : LiteLLM ne le transmet pas à ce fournisseur | — | — | — | même modèle que `glm-4-7-flash-cloudflare` chez un autre fournisseur, quota à part ; niveau non vérifié, les chiffres du modèle ne s'appliquent pas à coup sûr : garde sa place historique |
| 15 | `glm-4-5-flash-zai` | Z AI | à la requête, limite non publiée | non fixé : non vérifié chez ce fournisseur | — | — | — | aucun chiffre publié : derrière son frère ; même compte et même limite non publiée ; 128 000 jetons de contexte, le minimum du routeur |
| 16 | `phonellm-mini-alpha-2-cloudflare` | Cloudflare Workers AI | au neurone | défaut du fournisseur | — | — | — | aucun chiffre publié : 262 140 jetons de contexte et appels d'outils |
| 17 | `qwen3-8-27b-cloudflare` | Cloudflare Workers AI | au neurone | non fixé : LiteLLM ne le transmet pas à ce fournisseur | 20,1 | — | 135,4 s | même modèle que ses jumeaux, chez un autre fournisseur ; réfléchit en Xhigh par défaut, 135 s avant la réponse, au-delà des 90 s de patience : un repli de plus, à la place que lui donne l'ordre de `Auto-Code` |
| 18 | `codestral` | Mistral | prépayé | défaut du fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 19 | `codestral-2508` | Mistral | prépayé | défaut du fournisseur | — | — | — | aucun chiffre publié : garde sa place historique |
| 20 | `deepseek-v4-pro-direct` | DeepSeek | prépayé | défaut du fournisseur | 20,8 | 22 % | 48,8 s | payant : après tous les gratuits, seul payant de ce routeur |

### `Auto-Fiction`

Tête : `aion-3-5-aion-labs`. Les modèles routés d'Aion Labs et eux seuls, dans le groupe d'accès `Fiction`, du plus récent et du plus grand au plus petit : la dernière version de chaque gamme, Aion et Aion Mini, et Aion RP Llama 3.1 8B. Les versions plus anciennes, Aion 3.0, Aion 3.0 Mini et Aion 2.0, restent commentées dans le gabarit, remplacées par Aion 3.5 et Aion 3.5 Mini : le quota compte les jetons de tous les modèles ensemble, aucune page ne dit qu'un tokenizer en compte moins qu'un autre, et elles n'ont ni fenêtre plus grande, ni lecture d'images, ni appels d'outils en plus (catalogue relu le 2026-11-26). Aucun chiffre ne les place, l'ordre est celui de la main. Le quota gratuit est celui du compte, tous les modèles ensemble : une fois les 20 000 jetons du jour dépensés, chacun répond par un refus, et la cascade n'a plus de membre.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `aion-3-5-aion-labs` | Aion Labs | au jeton, quota du compte | défaut du fournisseur | — | — | le plus récent et le plus grand : famille GLM, 262 144 jetons de contexte ; aucun chiffre publié |
| 2 | `aion-3-5-mini-aion-labs` | Aion Labs | au jeton, quota du compte | défaut du fournisseur | — | — | son petit frère, même contexte ; aucun chiffre publié |
| 3 | `aion-rp-llama-3-1-8b-aion-labs` | Aion Labs | au jeton, quota du compte | défaut du fournisseur : ne réfléchit pas | — | — | variante de Llama 3.1 8B, la seule qui ne raisonne pas et ne prend pas les appels d'outils, 32 768 jetons de contexte ; aucun chiffre publié |

### `Auto-Paid`

Tête : `claude-fable-5-2-anthropic`. La dernière version de chaque gamme d'Anthropic et elles seules, du meilleur indice de capacités d'Epoch AI au moins bon ; les versions plus anciennes sont commentées dans le gabarit, avec celle qui les remplace. Chaque demande est payée sur le même crédit : une fois dépensé, chacun répond par un refus, et la cascade n'a plus de membre. Chaque entrée demande la mise en cache automatique du début de la demande, qui coûte 1,25 fois le prix d'entrée à l'écriture et 0,1 fois ou moins à chaque lecture dans les cinq minutes, et attend dix minutes : Artificial Analysis mesure jusqu'à 334 s avant le premier mot (Claude Opus 5.5 au niveau le plus haut). Les prix sont ceux de la page des tarifs d'Anthropic, lue le 2026-11-25.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `claude-fable-5-2-anthropic` | Anthropic | au jeton, sur le crédit du compte (8 $ / 40 $ le million) | défaut du fournisseur (high, réflexion toujours active) | 65,2 (estimé) | — | dernier Fable ; indice de capacités d'Epoch AI 173,4, le plus haut ; le modèle d'Anthropic pour le raisonnement exigeant et les longues tâches d'agent |
| 2 | `claude-opus-5-5-anthropic` | Anthropic | au jeton, sur le crédit du compte (4 $ / 20 $ le million) | défaut du fournisseur (medium, réflexion toujours active) | 54,0 (estimé) | — | dernier Opus ; indice de capacités 168,67 ; le modèle par lequel Anthropic conseille de commencer |
| 3 | `claude-sonnet-5-5-anthropic` | Anthropic | au jeton, sur le crédit du compte (2 $ / 10 $ le million) | défaut du fournisseur (high, réflexion active par défaut) | 49,0 (estimé) | — | dernier Sonnet ; indice de capacités 166,6 |
| 4 | `claude-haiku-5-5-anthropic` | Anthropic | au jeton, sur le crédit du compte (0,10 $ / 0,50 $ le million jusqu'à 100 000 jetons de demande, cinq fois plus au-delà) | défaut du fournisseur (medium, réflexion active par défaut) | 34,2 (estimé) | — | dernier Haiku ; indice de capacités 160,33 ; le plus rapide d'Anthropic |

### Entrées appelées par leur nom

Aucune cascade, aucun alias : on les appelle par leur nom. Aucun chiffre ne les place, ou aucun routeur ne peut les tenir (un niveau sous ce que demande chaque routeur, un modèle de garde ou de traduction qui ne répond pas comme un modèle de conversation) ; elles sont dans la liste pour qu'une personne choisisse dans la liste entière. Ce sont les seules entrées d'un mode qui a un routeur à n'être dans aucune cascade : `check_compose_template.py` refuse toute autre, et `check_routing_document.py` vérifie que cette section liste exactement celles qu'il déclare.

| Rang | Entrée | Fournisseur | Facturation | Niveau | Indice | Délai | Raison |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `omniroute-free-vision` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | la catégorie `vision` d'OmniRoute : un filtre qui ne garde, parmi les fournisseurs qu'il a connectés, que les modèles capables de lire une image ; aucun routeur ne prend d'images, d'où l'appel par le nom ; jamais appelée pour de bon |
| 2 | `omniroute-vision` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | la route `auto/vision` d'OmniRoute, des modèles capables de lire une image, aux poids équilibrés ; aucun routeur ne prend d'images, d'où l'appel par le nom ; jamais appelée pour de bon |
| 3 | `omniroute-multimodal` | OmniRoute (local) | sans quota | défaut du fournisseur | — | — | la route `auto/multimodal` d'OmniRoute, des modèles capables de lire une image, aux poids équilibrés ; aucun routeur ne prend d'images, d'où l'appel par le nom ; jamais appelée pour de bon |
| 4 | `gemini-flash-latest` | Google AI Studio | à la requête, quota non établi | défaut du fournisseur | — | — | alias que Google fait pointer sur chaque nouvelle version Flash : suit les sorties sans modifier le gabarit ; version derrière l'alias et quota non lus |
| 5 | `gemini-flash-lite-latest` | Google AI Studio | à la requête, quota non établi | défaut du fournisseur | — | — | l'alias équivalent pour la ligne Flash-Lite |
| 6 | `glm-4-6v-flash-zai` | Z AI | à la requête, limite non publiée | non fixé : non vérifié chez ce fournisseur | — | — | modèle de vision gratuit : aucun routeur qui exige un contexte ou des outils ne le tient, ni contexte ni outils n'étant lus |
| 7 | `olala-summarise-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | modèle spécialisé dans le résumé |
| 8 | `olala-translate-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | modèle spécialisé dans la traduction : demande un champ `source_language` dans le corps de la requête |
| 9 | `qwen3-vl-30b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | modèle de vision, 32K jetons de contexte |
| 10 | `qwen2-5-vl-72b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | modèle de vision sans appels d'outils |
| 11 | `qwen3guard-gen-0-6b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | modèle de garde : répond un verdict sur un texte |
| 12 | `qwen3guard-gen-8b-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : non vérifié chez ce fournisseur | — | — | modèle de garde : répond un verdict sur un texte |
| 13 | `cosmos-reason2-8b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | modèle de vision et de raisonnement physique, sans appels d'outils sur sa fiche |
| 14 | `ising-calibration-1-5-31b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | modèle d'étalonnage quantique, sans appels d'outils sur sa fiche |
| 15 | `riva-translate-4b-instruct-v2-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | modèle de traduction, sans appels d'outils sur sa fiche |
| 16 | `nemoguard-topic-control-8b-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | modèle de garde : répond un verdict sur un texte |
| 17 | `nemotron-safety-guard-8b-v3-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | modèle de garde : répond un verdict sur un texte |
| 18 | `nemotron-3-5-content-safety-nvidia` | NVIDIA | à la requête, 40 par minute | non fixé : non vérifié chez ce fournisseur | — | — | modèle de garde : répond un verdict sur un texte |
| 19 | `whisper-large-v3-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : sans objet pour la parole | — | — | transcription, jamais essayée : `Auto-STT` n'en tient aucune, parce que ce routeur n'existe que si un fournisseur à clé peut répondre, ce qu'un membre sans clé changerait |
| 20 | `whisper-large-v3-turbo-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : sans objet pour la parole | — | — | la version turbo du précédent, mêmes raisons, jamais essayée |
| 21 | `nvr-tts-en-us-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : sans objet pour la parole | — | — | voix Riva de NVIDIA en anglais, sans voix française, jamais essayée : `Auto-TTS` n'en tient aucune, parce que ce routeur n'existe que si un fournisseur à clé peut répondre |
| 22 | `nvr-tts-es-es-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : sans objet pour la parole | — | — | voix Riva de NVIDIA en espagnol, mêmes raisons |
| 23 | `nvr-tts-it-it-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : sans objet pour la parole | — | — | voix Riva de NVIDIA en italien, mêmes raisons |
| 24 | `nvr-tts-de-de-ovh` | OVHcloud | à la requête, par adresse IP | non fixé : sans objet pour la parole | — | — | voix Riva de NVIDIA en allemand, mêmes raisons |
| 25 | `voxtral-mini-tts-mistral` | Mistral | prépayé | défaut du fournisseur | — | — | synthèse vocale de Mistral : ses voix françaises se demandent par leur identifiant, ce que ne peut pas faire une cascade partagée avec les membres de Gemini, qui prennent les noms de voix d'OpenAI |
| 26 | `orpheus-v1-english-groq` | Groq | à la requête, 10 par minute et 100 par jour | défaut du fournisseur | — | — | synthèse vocale sans voix française, que demande `Auto-TTS` ; jamais essayée : aucune page lue ne confirme la route de LiteLLM pour cet identifiant |
| 27 | `orpheus-arabic-saudi-groq` | Groq | à la requête, 10 par minute et 100 par jour | défaut du fournisseur | — | — | synthèse vocale en arabe, sans voix française, mêmes raisons ; même quota que le précédent |

## Ce qui a été regardé et n'a pas été créé

Des niveaux que la règle demanderait, mais qu'on ne peut pas fixer aujourd'hui.

| Candidat | Ce que la règle demande | Pourquoi pas |
| --- | --- | --- |
| Les entrées NVIDIA (GLM-5.3-Flash, Mistral Large 4, Kimi K3.1 Pro...) | le niveau le plus haut | LiteLLM ne transmet pas `reasoning_effort` à `nvidia_nim/` ; GLM-5.3-Flash est déjà à `max` par défaut |
| GLM-4.7-Flash chez Z AI | — | LiteLLM ne transmet que `thinking`, allumé ou éteint |
| Les entrées OVHcloud (DeepSeek V4.1 Flash, gpt-oss...) et Cent AI | le niveau le plus haut | aucune page lue ne dit quelles valeurs ces modèles acceptent |
| `beam-kilo` et `glyph-cluster-kilo` | `max` et `xhigh` | le catalogue de Kilo donne leurs niveaux, mais pas `reasoning_effort` parmi leurs paramètres, et c'est ce champ que LiteLLM envoie |
| Gemma 4 chez Google, Gemini 2.5 Flash, Gemini 3.7 Flash | le niveau le plus haut | LiteLLM envoie un budget de réflexion à Gemma et aux Gemini 2.5, que la page de Google ne documente pas ; Gemini 3.7 Flash n'a pas de ligne sur cette page |
| DeepSeek V4.1 Flash sans réflexion | 18,5 points en 1,0 s, soit un score de 15,4 | meilleur score de `Auto-Flash-Lite` sur le papier, mais on n'a pas vérifié qu'OVHcloud sait couper la réflexion, et ses 2 requêtes par minute le rendent mauvais en tête |

## Les points ouverts

1. **`kimi-k3-1-pro-nvidia` dans `Auto-Pro` et `Auto-Flash`.** Son indice (46,5) est le deuxième de `Auto-Pro`, mais il met 155 s en moyenne avant son premier mot, au-delà des 90 s de patience du routeur (médiane de 71 s). L'ordre des contrats, au niveau gardé, le mettrait en tête de `Auto-Flash` ; il n'a pas été appliqué. Il garde la deuxième place du gabarit dans `Auto-Pro` et dans `Auto-Flash`, et la décision est à prendre : le descendre, ou le garder.
2. **Les niveaux fixés ne sont que des valeurs par défaut.** Tout client qui envoie son propre niveau l'emporte, et Claude Code en envoie toujours un : `Auto-Claude-Code` ne tient donc pas le niveau que garde son contrat.
3. **Les niveaux montés sans chiffre.** `particle-1-free` (`xhigh`), `particle-1-kilo` (`max`) et les deux Nemotron de Requesty (`max`) n'ont aucun délai mesuré à ce niveau : ils gardent l'attente du routeur, et un niveau trop lent serait abandonné et passerait au suivant.
4. **Les 20 requêtes par jour de Hydrogen et de 3.8 Flash.** Les têtes de `Auto-Pro` et de `Auto-Flash` s'épuisent vite : la cascade passe alors au membre suivant.
5. **Dans `Auto-Flash-Lite`, les membres sans chiffres passent avant `gemini-3-8-flash-low`**, parce que la règle veut que les membres à quota partagé viennent après tous ceux qui ont un quota à eux, même ceux dont les chiffres ne s'appliquent pas. À revoir si on préfère que Gemini 3.8 Flash, à 5,1 s, passe devant des modèles de 34 s ou sans chiffre.
6. **Le payant `ministral-3b` précède `omniroute-free-fast`** dans `Auto-Flash-Lite`, comme les payants précèdent l'entrée locale dans `Auto-Pro` et `Auto-Flash` : le contrat les déclare en dernier recours, dans cet ordre.
7. **`Auto-Paid` est classé sur des indices estimés.** Artificial Analysis publie un enregistrement par niveau de chaque modèle Claude, mais aucun indice n'a été lu au niveau où chaque entrée est appelée : l'ordre suit l'indice de capacités d'Epoch AI, et la veille de modèles le comparera aux chiffres d'Artificial Analysis.

## Tenir ce document à jour

Une pull request qui change l'ordre d'une cascade ou le niveau fixé d'une entrée change ce document dans la même pull request. Pour vérifier avant de pousser :

```bash
python3 .github/scripts/check_routing_document.py
```
