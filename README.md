<!--
SPDX-FileCopyrightText: 2026 Tigerblue77 and the AI Docker stack Ansible deployment contributors
SPDX-License-Identifier: AGPL-3.0-only
-->

# AI-Docker-stack

Déploiement Ansible du stack **Artificial Intelligence** : la stack Docker qui regroupe toutes
les briques liées à l'IA du homelab. Passerelle LLM, base vectorielle, reranker, conteneur Claude Code,
agents et connecteurs y vivront dans un seul stack.

**Ce dépôt est le rôle Ansible `deploy_Artificial_Intelligence_Docker_stack`, et rien d'autre autour de lui : il rend le
`docker-compose` du stack et délègue son déploiement au rôle que l'appelant désigne.** `tasks/`,
`defaults/`, `templates/` et le reste vivent à sa racine plutôt que sous un `roles/<nom>/` à lui : c'est
ce qui permet à un appelant de l'installer directement, par Galaxy ou par un submodule, et d'avoir le
checkout résolu comme le rôle lui-même -- sans une couche de dossier en plus qui n'existe que pour ce
dépôt et que personne d'autre n'a de raison de reproduire.

## Ce que contient ce dépôt

Un rôle, le playbook d'exemple qui montre comment l'appeler, et de quoi vérifier les deux.

```
playbook.Artificial_Intelligence.example.yaml                     l'appel du rôle, commenté
defaults/, tasks/, templates/, files/,        le rôle lui-même : le docker-compose du stack,
handlers/, vars/, meta/                       ses variables, sa configuration LiteLLM/LibreChat
.ansible-lint                                 ce que « conforme » veut dire ici
.github/scripts/check_compose_template.py     rend le template et le tient à ses conventions
```

Un rôle et rien d'autre, et c'est délibéré : **le dépôt fournit le stack, pas la mécanique qui le déploie.** Cette
mécanique appartient à l'appelant : un rôle à lui, pour Swarm ou pour Compose, qui n'a qu'à remplir le
contrat décrit plus bas.

Le modèle commenté du template (`templates/Artificial_Intelligence.docker-compose.yml.j2`), placé
après les services, porte les conventions qu'un bloc de service doit tenir : image sans tag (ou, pour
une base de données, épinglée avec sa raison), limite mémoire facultative (aucune par défaut), `deploy.restart_policy.condition: any`, aucun port publié pour un
service interne, aucun secret en clair. Elles sont écrites là plutôt que dans un document séparé
parce que c'est là qu'on les oublie.

## Un rôle paramétrable, pas un rôle spécifique

Le rôle ne présuppose **ni machine, ni domaine, ni compte, ni orchestrateur**. Tout ce qui identifie un
déploiement est une variable fournie par l'appelant : son inventaire, ses FQDN, les labels de son reverse
proxy, son réseau publié, et jusqu'au nom du rôle chargé de déployer le stack.

C'est ce qui permet à deux personnes de déployer le même stack sur deux estates qui n'ont rien en commun,
sans forker. Il n'y a donc dans ce dépôt aucune adresse IP, aucun nom d'hôte et aucun domaine.

## Prérequis

- Un rôle capable de déployer le stack, nommé par `Artificial_Intelligence_Docker_stack_deployment_role_name`, et résoluble
  depuis le `roles_path` de l'appelant. Ce dépôt n'en fournit aucun : voir « Le contrat du rôle de
  déploiement » plus bas.
- La collection `community.docker` (`requirements.yml`, à la racine du dépôt), depuis #76 : le compte
  admin de LibreChat s'y crée par `docker_host_info` et `docker_container_exec`, pas par
  `ansible.builtin.assert`/`include_role` comme le reste du rôle.
- **Sur le nœud géré** (pas sur celui qui lance Ansible, s'ils diffèrent) : le SDK Python `docker`
  (`pip install docker`). Les deux modules ci-dessus parlent à l'API du moteur Docker à travers lui,
  jamais à travers le CLI `docker` -- son absence échoue à l'intérieur du module, avec son propre
  message, plutôt que d'être vérifiée ici où il n'y a rien à vérifier avant que le module ne tourne.

## Comment l'appeler

```yaml
- role: deploy_Artificial_Intelligence_Docker_stack
  vars:
    Artificial_Intelligence_Docker_stack_deployment_role_name: "your_stack_deployment_role"
```

Le seul paramètre obligatoire est celui-là : le rôle qui déploie réellement le stack. Le contrat qu'il doit
remplir, la liste complète des variables et les raisons derrière les choix du template sont dans les
sections qui suivent.

## Variables du rôle

**Aucune variable ne porte une image ni son tag.** Une image flotte par défaut et s'écrit sans tag
(`image: redis`), puisque l'absence de tag *est* `latest` : le déployeur la récupère à chaque
exécution, donc chaque déploiement apporte la version courante et ses correctifs. Seules les bases de
données dont les données ne vivent que dans leur volume -- PostgreSQL, MongoDB, Qdrant -- sont épinglées,
en dur dans le template, avec leur raison au-dessus de la ligne `image:` : une montée de majeur tombe
sur une organisation des données que la nouvelle image ne lit pas. Une image se récupère, elle ne se
construit jamais ici : aucun service ne porte de clé `build:`, et `check_compose_template.py` en refuse une.

Le stack porte déjà plusieurs services -- la passerelle et sa base, Redis, OmniRoute, Qdrant, LibreChat
et sa base, l'agent Claude Code -- chacun arrivé par sa propre
issue de service, avec son bloc et ses variables. Ce que ce rôle apporte reste la forme plutôt que le
contenu : un rôle qui ne présuppose ni machine, ni domaine, ni compte, ni orchestrateur, et un template
dont les conventions sont écrites à l'endroit où on les oublie.

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_Docker_stack_deployment_role_name` | aucun | **Obligatoire.** Le rôle qui déploie réellement le stack. Sans défaut, délibérément : en avoir un présupposerait un orchestrateur. |
| `Artificial_Intelligence_Docker_stack_name` | `Artificial_Intelligence` | Le « namespace » du stack chez l'orchestrateur. Compose le normalise en minuscules pour son nom de projet. |
| `Artificial_Intelligence_Docker_compose_file_name` | `Artificial_Intelligence.docker-compose.yml` | Le template rendu, sans le suffixe `.j2`. |
| `Artificial_Intelligence_Docker_compose_file_destination_directory` | `/tmp/` | Où le fichier rendu atterrit sur le nœud géré, et aussi les configurations de LiteLLM et de LibreChat que leurs conteneurs montent. **Sous Compose**, ces deux fichiers sont relus à chaque démarrage de leur conteneur, et Debian 13 vide `/tmp` au démarrage puis après dix jours sans accès : Docker crée alors un répertoire vide à la place du fichier et le conteneur ne redémarre plus (#137). Un appelant sous Compose donne ici un répertoire persistant. **Sous Swarm**, c'est sans effet après le déploiement : les configurations sont copiées dans le cluster (#161). |
| `Artificial_Intelligence_Docker_compose_file_destination_path` | *dérivé des deux précédents* | Chemin complet. À ne surcharger que si l'on veut le découpler du répertoire. |
| `Artificial_Intelligence_server_time_zone` | `Etc/UTC` | Le `TZ` injecté dans chaque conteneur. Un appelant qui a déjà le sien le passe ici. |
| `Artificial_Intelligence_internal_Docker_network_name` | `Artificial_Intelligence_internal` | Le réseau que les services du stack utilisent entre eux. Déclaré par le stack, donc créé et détruit avec lui. |
| `Artificial_Intelligence_published_Docker_network_name` | `false` | Le réseau publié de l'appelant, celui où écoute son reverse proxy. |
| `Artificial_Intelligence_published_Docker_network_definition` | `false` | La déclaration de ce même réseau, telle qu'elle doit apparaître dans le bloc `networks:`. |
| `Artificial_Intelligence_LiteLLM_port_to_expose` · `Artificial_Intelligence_OmniRoute_port_to_expose` · `Artificial_Intelligence_LibreChat_port_to_expose` | `4000` / `20128` / `3080` | Le port d'hôte sur lequel chaque service web est publié ; le port du conteneur ne change pas. Celui de LiteLLM est aussi le port que les tâches `uri` du rôle appellent. |
| `Artificial_Intelligence_LibreChat_publish_in_host_mode` | `false` | `true` publie le port de LibreChat en `mode: host` (syntaxe longue) au lieu de la syntaxe courte : sous Swarm, le routing mesh masque l'adresse du client, qu'un appelant qui la décide ou la journalise doit conserver. |

Et celles que #1 apporte, pour la passerelle et sa base :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_PostgreSQL_password` | aucun | **Obligatoire.** Le mot de passe du rôle de LiteLLM, `Artificial_Intelligence_PostgreSQL_user` -- un rôle **ordinaire**, propriétaire de sa base et de rien d'autre, jamais superutilisateur (#159). Rendu depuis le vault de l'appelant. Sans défaut : un mot de passe par défaut est un mot de passe, et livré dans un dépôt, un mot de passe publié. |
| `Artificial_Intelligence_PostgreSQL_superuser` | `postgres` | Le superutilisateur du cluster (#159). Rien ne s'y connecte : il crée le rôle de LiteLLM à l'initialisation, et sert à un humain par `docker exec … psql`. Doit différer du rôle de LiteLLM. |
| `Artificial_Intelligence_PostgreSQL_superuser_password` | aucun | **Obligatoire** (#159). Rendu depuis le vault, et **différent** de `Artificial_Intelligence_PostgreSQL_password` : le rôle refuse la même valeur pour les deux. |
| `Artificial_Intelligence_LiteLLM_master_key` | aucun | **Obligatoire.** Administration **uniquement** : chaque consommateur reçoit sa propre clé virtuelle (#2). |
| `Artificial_Intelligence_LiteLLM_salt_key` | aucun | **Obligatoire** (#164). `LITELLM_SALT_KEY`, la clé qui chiffre en base ce que `/ui` enregistre. **Ne change plus jamais** une fois un identifiant enregistré, et **différente** de la clé maîtresse, ce que le rôle vérifie. Un déploiement existant ne reçoit pas une valeur neuve : voir « La clé de sel (#164) » plus bas. |
| `Artificial_Intelligence_LiteLLM_number_of_workers` | `4` | Chaque worker réplique la configuration : ce nombre multiplie l'empreinte mémoire. |
| `Artificial_Intelligence_LiteLLM_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`2g`) limite le service à cette taille, `false` n'en pose aucune. À dimensionner avec le nombre de workers. |
| `Artificial_Intelligence_PostgreSQL_database` · `Artificial_Intelligence_PostgreSQL_user` | `litellm` | Base et rôle de la passerelle. Le nom de base se limite aux lettres ASCII, aux chiffres et à `-` `.` `_` `~` `$` ; `tasks/main.yml` refuse le reste, parce que Prisma lit ce nom dans `DATABASE_URL` sans le décoder (#133). |
| `Artificial_Intelligence_PostgreSQL_data_Docker_volume_name` | `PostgreSQL_data` | Volume **nommé** : survivre à une recréation de conteneur est un critère d'acceptation. Tous les noms de volume par défaut sont écrits **sans** le préfixe du stack : Compose et Swarm le préfixent eux-mêmes du nom du stack, le volume déployé est donc `<nom du stack>_PostgreSQL_data`, soit `Artificial_Intelligence_PostgreSQL_data` avec le nom de stack par défaut. Renommer un volume après coup est une migration de données. |
| `Artificial_Intelligence_PostgreSQL_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`1g`) limite le service à cette taille, `false` n'en pose aucune. Voir « Pourquoi tout vit sous `deploy:` ». |
| `Artificial_Intelligence_LiteLLM_config_file_name` · `..._destination_path` | `LiteLLM_config.yaml` | La configuration de routage, montée en lecture seule. #2 en remplit le `model_list`. |
| `Artificial_Intelligence_LiteLLM_config_checksum` · `Artificial_Intelligence_LibreChat_config_checksum` | `false` | **Pas des réglages.** Le SHA-1 de chaque configuration montée, tel que le run vient de l'écrire : `tasks/main.yml` le passe lui-même au rôle de déploiement, et ce paramètre l'emporte sur tout sauf une *extra var*. Le nom de la config Docker qui porte chaque fichier en est dérivé (`..._config_Docker_name`). Voir « Une configuration modifiée recrée le conteneur qui la lit » plus bas (#161). |
| `Artificial_Intelligence_LiteLLM_UI_username` | `admin` | Le compte de connexion à `/ui`, dont le port est publié -- voir plus bas. |
| `Artificial_Intelligence_LiteLLM_UI_password` | aucun | **Obligatoire.** Rendu depuis le vault de l'appelant, comme les secrets ci-dessus. |
| `Artificial_Intelligence_LiteLLM_disable_env_credential_login` | `false` | Fait refuser à `/ui` la connexion par `UI_USERNAME`/`UI_PASSWORD` et par la clé maîtresse, que LiteLLM signale comme critique. **Le rôle refuse `true` tant que `Artificial_Intelligence_LiteLLM_admin_users` est vide** : sans administrateur en base, plus personne ne se connecte, et on revient en la remettant à `false`. Un booléen, jamais une chaîne (`tasks/main.yml` la refuse). Voir « La connexion par identifiants d'environnement ». |
| `Artificial_Intelligence_LiteLLM_internal_users` | `[]` | Une **liste**, jamais une paire de variables nommées (#103) : chaque `{username, email}` devient un compte `internal_user` à lui, self-service, avec une seule clé virtuelle qui atteint tous les modèles tant que #2 n'a pas construit l'isolation par compte (#114). Voir « Un compte par personne, pas une paire figée » plus bas. |
| `Artificial_Intelligence_LiteLLM_admin_users` | `[]` | Une **liste** de `{username, email}` : chaque entrée devient un compte `proxy_admin` de LiteLLM, **invité** par un lien à usage unique, sur lequel le run s'arrête une fois, et jamais doté d'un mot de passe par le rôle. Noms d'utilisateur et courriels distincts de ceux des comptes internes. Voir « Les administrateurs de `/ui`, invités et non dotés d'un mot de passe ». |
| `Artificial_Intelligence_LiteLLM_UI_URL` | `false` | L'adresse sur laquelle une personne ouvre LiteLLM, sur laquelle est construit le lien d'invitation d'un administrateur. `false` : celle du nœud telle que l'inventaire la donne (`ansible_host`, à défaut son nom) et le port publié, que seul Ansible connaît à l'exécution. Un appelant derrière un reverse proxy y met l'adresse qu'il sert, sans barre oblique finale. |
| `Artificial_Intelligence_LiteLLM_admin_API_URL` | *dérivé du port de LiteLLM* | **Pas un réglage.** Où les tâches `uri` du rôle joignent l'API d'administration de LiteLLM, depuis le nœud qui les exécute. |
| `Artificial_Intelligence_LibreChat_API_URL` | *dérivé du port de LibreChat* | **Pas un réglage.** Où les tâches `uri` du rôle joignent l'API de LibreChat, depuis le nœud qui les exécute, pour donner à un compte sa clé de la passerelle. |

Et celles que #2 apporte, pour le `model_list` du compte de la passerelle (voir plus bas pourquoi les
autres comptes n'ont pas les leurs ici) :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_LiteLLM_Gemini_API_key` | `""` | **Au moins une des onze clés fournisseurs** (Gemini, Mistral, Groq, OpenRouter, DeepSeek, Cloudflare, Z AI, Requesty, NVIDIA, Cent AI, Aion Labs), voir « Les clés fournisseurs » plus bas. Vide : aucune entrée Gemini dans la configuration. |
| `Artificial_Intelligence_LiteLLM_GitHub_API_key` | `""` | Optionnelle depuis le retrait de GitHub Models (#109, #119) : plus aucune entrée active du `model_list` ne la lit. |
| `Artificial_Intelligence_LiteLLM_Mistral_API_key` | `""` | Une des onze clés fournisseurs. Vide : aucune entrée Mistral. **Payant** : routé après tous les gratuits. |
| `Artificial_Intelligence_LiteLLM_Cerebras_API_key` | `""` | Optionnelle depuis que Cerebras n'a plus de palier gratuit (#200) : ses deux entrées sont commentées, plus aucune entrée active du `model_list` ne la lit. |
| `Artificial_Intelligence_LiteLLM_Groq_API_key` | `""` | Une des onze clés fournisseurs. Vide : aucune entrée Groq. |
| `Artificial_Intelligence_LiteLLM_OpenRouter_API_key` | `""` | Une des onze clés fournisseurs. Vide : aucune entrée OpenRouter. |
| `Artificial_Intelligence_LiteLLM_DeepSeek_API_key` | `""` | Une des onze clés fournisseurs. Le seul fournisseur **payant** de ce fichier -- l'API directe de DeepSeek n'a pas de palier gratuit permanent, contrairement à tous les autres. |
| `Artificial_Intelligence_LiteLLM_Cloudflare_API_key` | `""` | Une des onze clés fournisseurs : le jeton d'API de Cloudflare Workers AI. Vide : aucune entrée Cloudflare. À donner **avec** la variable suivante, ou pas du tout : le rôle refuse l'une sans l'autre. |
| `Artificial_Intelligence_LiteLLM_Cloudflare_account_ID` | `""` | L'identifiant du compte Cloudflare, que LiteLLM lit dans l'environnement du conteneur (`CLOUDFLARE_ACCOUNT_ID`) pour construire l'adresse du point d'accès : aucune entrée du `model_list` ne le nomme. **Un seul compte** : les conditions de Cloudflare interdisent d'en ouvrir un second pour doubler le quota. Voir « Cloudflare Workers AI : deux valeurs, un seul compte, et un quota en neurons » plus bas. |
| `Artificial_Intelligence_LiteLLM_Zai_API_key` | `""` | Une des onze clés fournisseurs : la clé d'API de Z AI (Zhipu), que le conteneur reçoit comme `ZAI_API_KEY`. Vide : aucune entrée Z AI. **Un seul compte.** Voir « Z AI : une clé, des limites inconnues » plus bas. |
| `Artificial_Intelligence_LiteLLM_Requesty_API_key` | `""` | Une des onze clés fournisseurs. Vide : aucune entrée Requesty. Gratuit « pour l'instant », dans un quota commun à tous ses modèles gratuits : voir « Requesty, une seconde source des modèles `:free` d'OpenRouter ». Un seul compte. |
| `Artificial_Intelligence_LiteLLM_NVIDIA_API_key` | `""` | Une des onze clés fournisseurs : la clé d'API du catalogue hébergé de NVIDIA, que le conteneur reçoit comme `NVIDIA_NIM_API_KEY`. Vide : aucune entrée NVIDIA. **Un service d'essai** dont les conditions interdisent la production et les données personnelles. Voir « NVIDIA : un service d'essai, des limites inconnues » plus bas. |
| `Artificial_Intelligence_LiteLLM_Cent_AI_API_key` | `""` | Une des onze clés fournisseurs : la clé d'API de Cent AI, que le conteneur reçoit comme `CENT_AI_API_KEY`. Vide : aucune entrée Cent AI. Un seul modèle gratuit, « jusqu'au 30 novembre » et sans suite annoncée : **donner à la clé une limite de dépense**, réglage de la page des clés de Cent AI, pour qu'un appel facturé échoue au lieu de coûter. Un seul compte. Voir « Cent AI : un modèle gratuit jusqu'au 30 novembre » plus bas. |
| `Artificial_Intelligence_LiteLLM_Aion_Labs_API_key` | `""` | Une des onze clés fournisseurs : la clé d'API d'Aion Labs, que le conteneur reçoit comme `AION_LABS_API_KEY`. Vide : aucune entrée Aion Labs ni routeur `Auto-Fiction`. Ses modèles, réglés pour le jeu de rôle et la narration et non modérés, sont dans le groupe d'accès `Fiction` et dans le seul routeur `Auto-Fiction` : aucune clé qui a `LLM` ni aucun autre routeur ne les atteint. Palier gratuit du compte : 20 000 jetons par jour, tous les modèles ensemble, « a courtesy that we may change or withdraw at any time » ; n'ajouter aucun crédit au compte. Un seul compte. Voir « Les modèles de jeu de rôle : le routeur `Auto-Fiction` et le groupe `Fiction` » plus bas. |

Et celles que #71 apporte, pour Redis :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_Redis_data_Docker_volume_name` | `Redis_data` | Volume nommé : `--save 60 1` sans volume derrière ne sert à rien. |
| `Artificial_Intelligence_Redis_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`256m`) limite le service à cette taille, `false` n'en pose aucune. |
| `Artificial_Intelligence_Redis_password` | aucun | **Obligatoire.** `--requirepass` serait vide sinon. |

Et celles que #73 apporte, pour OmniRoute :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_OmniRoute_data_Docker_volume_name` | `OmniRoute_data` | Volume nommé pour son magasin SQLite. |
| `Artificial_Intelligence_OmniRoute_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`2g`) limite le service à cette taille, `false` n'en pose aucune. À dimensionner si l'usage dépasse le simple dernier recours. |
| `Artificial_Intelligence_OmniRoute_dashboard_password` | aucun | **Obligatoire.** Remplace le `CHANGEME` de l'image. |

Et celles que #3 apporte, pour Qdrant :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_Qdrant_data_Docker_volume_name` | `Qdrant_data` | Volume nommé pour `/qdrant/storage`. |
| `Artificial_Intelligence_Qdrant_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`1g`) limite le service à cette taille, `false` n'en pose aucune. Le corpus visé par #3 est petit : une limite peut être généreuse. |
| `Artificial_Intelligence_Qdrant_API_key` | aucun | **Obligatoire.** Défense en profondeur, même sans port publié. |

Et celles que #13 apporte, pour l'agent Claude Code -- déployé **avec le reste du stack**,
comme tous les autres services ; `Artificial_Intelligence_Claude_code_enabled: false` le retire
pour un appelant qui n'en veut pas, et avec lui son volume et les tâches qui enregistrent sa clé :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_Claude_code_enabled` | `true` | Déploie le service. `false` le retire, lui et ses volumes ; le rôle n'enregistre alors aucune clé dans LiteLLM. |
| `Artificial_Intelligence_Claude_code_virtual_key` | aucun | **Obligatoire si activé.** La **valeur** de la clé virtuelle de l'agent, que l'appelant rend depuis son vault et que **le rôle enregistre lui-même dans LiteLLM** (voir « L'agent Claude Code »). Commence par `sk-`, au moins 16 caractères, jamais la clé maîtresse : le rôle refuse autrement. |
| `Artificial_Intelligence_Claude_code_GitHub_token` | `false` | **Facultatif** (#245) ; `false` veut dire « non fourni ». Jeton personnel, posé dans le conteneur en `GH_TOKEN` et `GITHUB_TOKEN` s'il est fourni, et absent de son environnement sinon. Claude Code les lit lui-même, sans `gh`, pour interroger l'API GitHub, dont son pied de page d'état de la PR de la branche ; sans jeton, ce pied de page n'a pas de repli dans l'image (voir « L'agent Claude Code »). Fourni, il doit être une chaîne non vide : une valeur vide ou qui n'est pas une chaîne fait échouer le rôle. |
| `Artificial_Intelligence_Claude_code_workspace_directory` | `false` | **Facultatif** ; `false` veut dire « non fourni » : le dossier de travail de l'agent est alors le volume nommé ci-dessous, sans rien à préparer sur l'hôte. Une chaîne est un chemin **absolu** de l'hôte, monté en bind à la place ; le rôle ne crée pas ce dossier, et le refuse s'il n'est pas absolu. |
| `Artificial_Intelligence_Claude_code_workspace_Docker_volume_name` | `Claude_code_workspace` | Le volume nommé monté sur `/workspace` quand le dossier hôte n'est pas fourni. Déclaré seulement dans ce cas. |
| `Artificial_Intelligence_Claude_code_model` | `Auto-Claude-Code` | L'alias que LiteLLM résout (#2) -- jamais un nom de modèle Anthropic littéral. C'est aussi la première entrée de la liste blanche de la clé de l'agent, et la valeur de **toutes** les variables de modèle de Claude Code posées dans le conteneur (#287, voir « L'agent Claude Code »). |
| `Artificial_Intelligence_Claude_code_additional_models` | `[Auto-Pro, Auto-Flash, Auto-Flash-Lite, Auto-Code]` | Les routeurs que l'agent peut aussi demander **par leur nom** (`/model Auto-Flash`), en plus de l'alias ci-dessus. Ils s'ajoutent à la liste blanche de la clé de l'agent et à rien d'autre : le conteneur continue de demander l'alias. `Auto` n'y est pas : sa clé ne porte que des routeurs, et `Auto` peut viser `Auto-Flash-Lite`, dont les membres ne sont pas tenus aux appels d'outils stricts de l'agent. Une liste de chaînes non vides, ou `[]` pour aucun ; `check_compose_template.py` la tient au niveau des routeurs du template. Le rôle ne réconcilie pas une clé qui existe : un changement n'atteint un agent déjà déployé qu'une fois sa clé supprimée depuis `/ui` (voir « L'agent Claude Code »). |
| `Artificial_Intelligence_Claude_code_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`2g`) limite le service à cette taille, `false` n'en pose aucune. |
| `Artificial_Intelligence_Claude_code_home_Docker_volume_name` | `Claude_code_home` | Le volume nommé du répertoire personnel **entier** -- voir plus bas pourquoi. |

Et celles que #76 apporte, pour LibreChat et sa base :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_LibreChat_creds_key` · `..._creds_IV` · `..._JWT_secret` · `..._JWT_refresh_secret` | aucun | **Obligatoires**, les quatre. Sans eux, LibreChat en génère des temporaires au premier démarrage. |
| `Artificial_Intelligence_LibreChat_allow_registration` | `false` | Fermé : le port est publié sur le LAN. Comptes créés via `create-user`. |
| `Artificial_Intelligence_LibreChat_session_cookie_secure` | `false` | Tant que LibreChat est servi en HTTP simple : l'image, en `NODE_ENV=production`, marque sinon ses cookies de session `Secure`, que le navigateur rejette en HTTP -- chaque rechargement et chaque expiration du jeton (15 min) ramène à la page de connexion. `true` le jour où un reverse proxy TLS est le seul accès. |
| `Artificial_Intelligence_LibreChat_uploads_Docker_volume_name` · `Artificial_Intelligence_MongoDB_LibreChat_data_Docker_volume_name` | `LibreChat_uploads` · `MongoDB_LibreChat_data` | Volumes nommés pour les pièces jointes et la base. |
| `Artificial_Intelligence_LibreChat_memory_limit` · `Artificial_Intelligence_MongoDB_LibreChat_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`1g`) limite le service à cette taille, `false` n'en pose aucune. / `512m` en exemple. |
| `Artificial_Intelligence_LibreChat_users` | aucun (`[]`) | **Obligatoire.** Liste de comptes LibreChat à créer, un dictionnaire par compte : `email`, `name`, `username`, `password` (chaînes non vides) et `admin` (booléen, `false` si absent) ; `admin: true` promeut le compte `ADMIN`. `gateway_key: true` (booléen, `false` si absent) donne au compte une clé de la passerelle à lui, faite et rangée par le rôle : voir « Une clé de la passerelle par compte LibreChat ». Voir plus bas. |
| `Artificial_Intelligence_LibreChat_gateway_key_models` | `[LLM, Auto-Pro, Auto-Flash, Auto-Flash-Lite, Auto-Code]` | Ce que la clé de la passerelle d'un compte LibreChat peut appeler, et donc ce que LibreChat liste pour ce compte : LiteLLM répond à `/v1/models` par la liste de la clé, un groupe d'accès étant remplacé par ses membres. `LLM` est le groupe des modèles de texte (ni transcription, ni voix, ni vecteurs), et un routeur n'étant dans aucun groupe, ceux qu'un chat doit proposer sont nommés ; `Auto-Claude-Code` est laissé à l'agent, et `Fiction` comme `Auto-Fiction` (les modèles de jeu de rôle d'Aion Labs) n'y sont pas : pour qu'un compte les atteigne, ajouter `Fiction` ou `Auto-Fiction` à cette liste, qui vaut pour la clé de chaque compte LibreChat. `Auto`, entrée du groupe `LLM`, est listée avec lui sans être nommée. Une liste non vide de chaînes non vides ; `check_compose_template.py` tient le défaut aux groupes et aux routeurs du template. Le rôle l'applique à **chaque** passage, à la clé qu'un compte a déjà comme à une nouvelle : changer la liste atteint donc une clé déployée sans la supprimer. |

`false` et non `''` pour les deux réseaux publiés plus haut, et pour le jeton GitHub facultatif de l'agent Claude Code
(#245) : ansible-core 2.19 refuse un test de vérité sur autre chose qu'un booléen, donc « renseigné » s'écrit
`is string`.

Les secrets qui doivent différer entre eux (le mot de passe du superutilisateur et celui du rôle de LiteLLM, la clé de sel et la clé maîtresse, la clé virtuelle de l'agent et la clé maîtresse) sont comparés après que chacun a été reconnu comme fourni, et **pas avec `--check`** : un appelant dont la récupération des secrets ne peut pas lire le vault pendant un essai à blanc met un même substitut à la place de tous, et ces substituts sont alors égaux sans qu'aucun secret ne soit faux. Que chacun soit fourni, lui, est vérifié aussi avec `--check`.

Les deux réseaux se renseignent **ensemble ou pas du tout**, et le rôle le refuse autrement : n'en donner qu'un
produit soit un `docker-compose` qui référence un réseau non déclaré -- que l'orchestrateur ne signale
qu'au déploiement -- soit un réseau déclaré que personne n'utilise.

Trois ports hôte apparaissent dans ce rôle : le `4000` de LiteLLM (#1), le `20128` d'OmniRoute (#73) et
le `3080` de LibreChat (#76), chacun sous mot de passe ou compte nominatif -- voir plus bas pourquoi
chacun est une exception plutôt qu'une habitude. Les autres services internes se joignent par le réseau
du stack, et les rares interfaces web pensées pour passer par un reverse proxy le feront par celui de
l'appelant. Le jour où un autre port devra malgré tout être publié, il faudra qu'il esquive la liste
`kRestrictedPorts` de Chromium -- un port restreint est refusé *dans* le navigateur, avant que la
connexion ne le quitte, donc le service reste sain et ses journaux restent vides.

## OmniRoute -- le repli gratuit et sans clé (#73)

**Aucune clé de fournisseur n'est jamais connectée à ce service, et c'est le point central.** Il sert de
dernier recours à plusieurs cascades de repli de la passerelle (#2) : quand tous les fournisseurs à clé sont
épuisés, la requête atterrit ici plutôt que d'échouer. `check_LiteLLM_account_isolation.py` (#32)
reconnaît une entrée dont la clé est une chaîne littérale -- jamais `os.environ/...` -- comme
délibérément partagée entre tous les comptes, précisément parce qu'il n'y a aucun quota derrière elle à
protéger.

**L'image est la variante `latest-web`, et c'est nécessaire.** L'image légère n'embarque pas de navigateur : le
fournisseur anonyme `cfp` (Cloudflare Playground) en pilote un et échoue sans, ce qui laissait les combos `auto/*`
sans réponse. La variante `-web` ajoute Chromium et Playwright, et le tag flotte comme `latest`. Les appels d'outils
des fournisseurs sans clé d'OmniRoute sont émulés depuis le prompt ou ignorés, ce qui est la raison pour laquelle
`Auto-Claude-Code` n'a pas `omniroute-free-code`.

**Le mot de passe du tableau de bord est obligatoire, sans défaut.** L'image démarre avec `CHANGEME` si
rien n'est fourni -- documenté en amont comme volontairement faible pour forcer un changement. Traité
comme le mot de passe `/ui` de LiteLLM (#1) : vaulté, jamais laissé à son défaut.

**Les fournisseurs sans clé d'OmniRoute examinés le 2026-11-22**, aucun n'étant mis dans une cascade. Les volontaires et les exploitants inconnus sont écartés pour la même raison que Gonka : des prompts traités par des opérateurs qu'aucun contrat ne lie. Page de UncloseAI relue le 2026-11-24 : elle ne nomme toujours pas d'exploitant et ne dit rien de la journalisation ; le reste vient des essais du 2026-11-22.

| Fournisseur | Ce qui a été relevé | Verdict |
| --- | --- | --- |
| `unc` (UncloseAI) | Cartes graphiques de particuliers, aucune entité juridique nommée ; prompts échantillonnés et lus, adresses IP conservées un an ; bêta publique, inscription des clés fermée | Hors des cascades |
| `ddgw` (chat de DuckDuckGo) | Une poignée de modèles, aucun appel d'outils annoncé, des 502 aux essais | Hors des cascades |
| `aihorde` | Cartes graphiques de volontaires, aucune avec appels d'outils | Hors des cascades |
| `cfp` | Modèles annoncés avec appels d'outils, mais appels d'outils seulement émulés aux essais | Hors des cascades |

## Qdrant -- déployé, pas encore rempli (#3)

**Périmètre volontairement partiel.** #3 déploie le serveur ; il ne crée aucune collection. Les créer
demande une dimension de vecteur, et cette dimension dépend du modèle d'embedding que #21 n'a pas
encore choisi -- en créer une maintenant serait deviner, exactement le genre de désalignement
silencieux que #3 met en garde contre. #21 crée les collections une fois le modèle choisi.

**Aucun `healthcheck:` ici, et c'est délibéré.** L'image officielle n'embarque ni sonde propre ni
outil pour en écrire une -- pas de `curl`, pas d'interpréteur, un durcissement amont volontaire, pas
un oubli. Un `CMD` qui nomme un binaire absent échouerait à chaque contrôle, rendant le service
*unhealthy* en permanence pour une raison étrangère à Qdrant lui-même -- exactement le piège que le
modèle commenté du template met en garde contre.

## LibreChat -- l'interface humaine du stack Artificial Intelligence (#76)

**`librechat.yaml` (`files/librechat/`) est copié, pas rendu.** Rien n'y a besoin de Jinja, et il ne
porte aucun secret : son `apiKey` vaut `"user_provided"` depuis #103, chaque compte LibreChat
saisissant lui-même sa propre clé de la passerelle, par l'**engrenage à côté du nom de l'endpoint** (tant qu'aucune clé n'est saisie, LibreChat répond « Aucune clé trouvée » et ne montre que la liste `default` du fichier ; avec une clé il liste les modèles de la passerelle) -- Ansible n'a rien à y interpoler. Repris du POC
fonctionnel de tigerblue77, avec trois corrections : deux identifiants de modèles absents du
`model_list` réel de #2, et une `apiKey` qui portait la clé maîtresse de la passerelle plutôt qu'une
clé virtuelle dédiée.

**L'inscription est fermée.** Le port `3080` est publié sur le LAN, et une inscription ouverte y
donnerait à n'importe qui sur le réseau un accès aux quotas des deux comptes.

**Les quatre secrets de chiffrement sont obligatoires.** Sans eux, LibreChat en génère des temporaires
au premier démarrage et les écrit dans son propre volume -- ce que sa documentation déconseille
explicitement en production, précisément parce que rien ne les vaulte nulle part.

**Les comptes de `Artificial_Intelligence_LibreChat_users` se créent tout seuls.** Une fois le stack
déployé, le rôle exécute lui-même `npm run create-user` dans le conteneur `librechat` pour chaque entrée,
puis promeut `ADMIN` celles qui portent `admin: true` par une écriture directe dans MongoDB
(`mongosh ... updateOne`) plutôt que de compter sur le comportement « le premier compte est admin » de
LibreChat -- des retours d'expérience amont le signalent silencieusement inopérant, ce qui en aurait fait
une hypothèse plutôt qu'un fait. Un compte qui existe déjà n'est pas touché (`create-user` le refuse, et le
rôle lit ce refus sur la sortie standard comme sur la sortie d'erreur), donc un compte créé à la main avant
le premier passage reste intact. La promotion filtre sur l'e-mail en minuscules, LibreChat les stockant
ainsi. Le mot de passe voyage en argument de la commande : la tâche est en `no_log`, ce qui le garde hors
des journaux d'Ansible, mais il reste visible un instant dans la liste des processus du conteneur.

Techniquement, deux choses ont été vérifiées en direct plutôt que supposées avant d'écrire ces tâches :

- **`create-user` se bloque si on lui répond par une entrée standard multi-lignes.** Le script ouvre
  une nouvelle interface `readline` par question et la ferme aussitôt après ; si toute la réponse
  arrive d'un coup (comme le fait un `docker exec -i` alimenté par un `printf | ...`), les lignes au-delà
  de la première se perdent entre deux interfaces, et le script attend indéfiniment une question à
  laquelle il a déjà, sans le savoir, reçu une réponse. La solution qui évite complètement le problème :
  passer le mot de passe en 4ᵉ argument positionnel et `--email-verified=true` en option, ce que le
  script lit avant de songer à demander l'un ou l'autre -- aucune invite ne se déclenche.
- **Le conteneur est trouvé par une étiquette que le template pose lui-même**,
  `artificial_intelligence.service=librechat`, et non par un nom deviné ni par une étiquette du
  déployeur. Le nommage ne fait contrat nulle part -- Compose écrit `<projet>-<service>-<n>`, Swarm
  `<stack>_<service>.<n>.<id de tâche>` -- et les étiquettes que chaque déployeur pose ne sont pas les
  mêmes non plus : `com.docker.compose.*` sous `docker compose up`, `com.docker.swarm.*` et
  `com.docker.stack.namespace` sous `docker stack deploy`, sans une seule de l'autre famille dans un
  cas comme dans l'autre. Ce filtre lisait la paire Compose jusqu'à ce qu'un déploiement Swarm en aval
  le mesure sur son nœud géré : la panne est **muette**, le filtre ne correspond à rien, le bloc se
  saute exactement comme son `when` le prévoit, et LibreChat monte sans aucun des deux comptes pendant
  que `ALLOW_REGISTRATION` vaut `false` -- une interface de chat où personne ne peut se connecter,
  sans que rien n'ait échoué.

  Les deux étiquettes sont déclarées dans le template sous `labels` et **non** sous `deploy.labels`,
  pour qu'elles se posent sur le **conteneur** : `deploy.labels` étiquette l'objet *service*, `labels`
  les conteneurs, et `docker compose up` comme `docker stack deploy` les y posent. Rien ne change pour
  la cible Compose -- Compose les applique comme avant, et ses propres étiquettes canoniques sont
  toujours là, simplement ce n'est plus elles que cette tâche lit.

- **Cela suppose toujours un nœud unique.** Sous un Swarm multi-nœuds, le nœud qui exécute cette tâche
  n'est pas forcément celui qui héberge le conteneur `librechat`, et ce rôle n'interroge pas l'API
  Swarm pour le savoir : il ne trouve alors rien et se saute proprement plutôt que d'agir sur le démon
  du mauvais nœud. Cela reste à faire le jour où la cible est un Swarm multi-nœuds.

La mécanique de création de compte a été vérifiée contre un vrai `docker compose up` de ces deux services
(création, ré-exécution idempotente, cas « compte déjà existant », promotion `ADMIN` idempotente), pas
seulement lue dans la documentation amont. Ce que ce `docker compose up` ne pouvait pas montrer, et ce
qui a coûté la correction ci-dessus, c'est précisément l'étiquette : sous Compose l'ancien filtre
fonctionne, et c'est sous Swarm qu'il ne trouve rien.

## Le contrat du rôle de déploiement

Ce rôle rend le stack, il ne le déploie pas. `Artificial_Intelligence_Docker_stack_deployment_role_name` nomme celui qui s'en
charge, et ce rôle-là doit :

1. **rendre `{{ Docker_compose_file_name }}.j2` depuis le `templates/` de son appelant**, c'est-à-dire
   depuis celui du rôle Artificial Intelligence. C'est le point qui fait tenir tout le reste : un dépôt peut fournir un stack
   sans fournir la mécanique qui le déploie ;
2. lire `Docker_stack_name`, `Docker_compose_file_destination_path` et
   `Docker_compose_file_destination_directory`, que `tasks/main.yml` lui passe en paramètres
   d'`include_role`. Les deux autres qu'il reçoit par le même chemin, les sommes de contrôle des
   configurations montées (#161), ne lui demandent rien : c'est le template qui les lit ;
3. écrire le fichier rendu en **`0600` et avec `diff: false`**. Il porte en clair les secrets des
   services, qu'Ansible y interpole -- mots de passe des bases et des interfaces, clé maîtresse de la
   passerelle, clés des fournisseurs, clés et jetons des services. `/tmp` est le premier endroit où
   tout compte de la machine regarde, et `--diff` imprimerait le fichier *entier* dans la sortie du
   run, donc dans tout ce qui la capture ;
4. **récupérer les images à chaque exécution**, puisque la plupart des images du stack flottent.
   `docker stack deploy` résout les empreintes à chaque appel ; Compose, lui, ne télécharge une image
   que si elle manque en local, et un déployeur Compose doit donc la récupérer explicitement
   (`docker compose pull`, `pull: always`). Sans cela, une image sans tag garde la première qu'elle a
   eue, pour toujours.

Et une cinquième obligation, qui pèse sur l'**appelant** et non sur le rôle nommé : **ce que ce rôle-là
exige en plus, c'est à l'appelant de le fournir.** Ni ce rôle-ci ni ses `assert` ne peuvent le deviner —
le rôle de déploiement est désigné par une variable, donc son contenu est inconnu au moment où les
vérifications tournent.

Ce n'est pas théorique : un rôle de déploiement peut remplir les obligations ci-dessus **sans
modification** et lire pourtant une variable qu'il ne définit pas, déclarée dans les `vars:` du playbook
qui l'appelle d'habitude. Elle est alors en portée quand c'est ce playbook qui appelle, et **absente
partout ailleurs**. Un appelant qui ne la déclare pas échoue au déploiement, sur une variable non
définie, à l'intérieur d'un rôle d'un autre dépôt, portant un nom qui n'apparaît nulle part dans l'appel
qu'il a écrit.

Les deux rôles rendent en plus deux faits que les issues de service voudront lire :
`Docker_stack_first_deployment`, qui dit si le stack est déployé pour la première fois sur cette machine,
et `Docker_stack_deployment_state`.

**Ce rôle demande au rôle de déploiement d'attendre que le stack ait convergé**, avec
`Docker_stack_deployment_detached: false` et `Docker_stack_deployment_timeout_in_seconds: 1800`, les
deux paramètres par lesquels un rôle de déploiement Swarm attend que chaque service tourne, et soit sain
quand il a un healthcheck, avant de rendre la main. Tout ce qui suit le déploiement parle à ce qu'il
vient de déployer : l'API d'administration de LiteLLM, puis `docker exec` dans LibreChat et sa MongoDB.
Un rôle de déploiement qui ne connaît pas ces deux paramètres les ignore ; l'attente décrite juste
après reste alors la seule protection.

**Le rôle attend ensuite lui-même la passerelle (#295)**, une seule fois, avant d'appeler son API
d'administration : il interroge `/health/readiness`, qui ne teste que la connexion à la base et n'appelle
aucun modèle, pendant trois minutes au plus (36 essais, 5 secondes d'écart). Un premier démarrage a été
mesuré à environ 45 secondes, le temps des migrations de Prisma. L'attente est sautée en `--check`, et quand
ni les comptes internes ni l'agent Claude Code n'appellent la passerelle.

## La passerelle et sa base (#1)

Deux services, et deux fichiers rendus sur le nœud : le `docker-compose` -- qui porte leurs
secrets, interpolés directement par Ansible -- et la configuration de routage de LiteLLM, montée en
lecture seule et sans secret propre.

**Une configuration modifiée recrée le conteneur qui la lit (#161).** LiteLLM ne lit
`LiteLLM_config.yaml` qu'au démarrage, LibreChat fait de même avec `librechat.yaml`. Montés en bind
mounts, changer l'un ne changeait rien au fichier compose, qui n'en porte que le chemin -- or c'est lui
seul que `docker compose up` et `docker stack deploy` comparent : le conteneur continuait de tourner sur
l'ancienne configuration pendant qu'Ansible affichait `changed`, et il ne voyait même pas le nouveau
fichier, écrit par renommage sous un nouvel inode. Mesuré avec LiteLLM 1.100.0 : même conteneur, même
`StartedAt`, anciens noms de modèles dans `/v1/models`. Chaque fichier est donc monté comme une **config
Docker**, dont le nom porte le contenu : `LiteLLM_config-<8 premiers caractères du SHA-1>`, et
`LibreChat_config-<…>`. `tasks/main.yml` passe le SHA-1 de chaque fichier au rôle de déploiement, en
paramètre d'`include_role`, et le template en tire le nom de la config, au niveau supérieur et dans le
service qui la monte. Une config Swarm est immuable : un fichier modifié est un nouveau nom, donc une mise
à jour ordinaire du service, et Compose recrée un conteneur dont la source de `configs` a changé. Un run
`--check` sur le point de changer un fichier utilise le nom sans suffixe, le module ne rendant pas de
somme de contrôle dans ce cas. Sous Swarm, les anciennes configs restent sur le nœud tant que personne ne
les supprime (`docker config rm`) ; sous Compose, rien ne s'accumule.

**Le port `4000` est publié, à rebours du choix initial de #1 -- décision de Dragnix, validée par
tigerblue77 le 07/09/2026 : le compromis (HTTP sans TLS, authentification basique seule, port ouvert
sur tout le LAN) est accepté tel quel, sur un LAN jugé de confiance.** `/ui` est l'endroit où se
connectent l'administrateur et chaque compte de `Artificial_Intelligence_LiteLLM_internal_users` -- ces
derniers pour gérer leurs propres clés virtuelles et voir leur consommation (#103) -- et doit donc être
joignable depuis un simple navigateur du LAN, avant même qu'un reverse proxy existe pour le faire à sa
place. La raison avancée à l'origine ne tient plus : chaque compte devait y ajouter ses propres clés
fournisseur, comme les autres bases auto-hébergées de cette estate sont déployées vides puis peuplées
en direct, mais #107 a établi qu'un compte `internal_user` ne peut pas ajouter de modèle. Les clés
fournisseur restent donc des entrées du `model_list` gérées par l'administrateur. Le coût n'est pas nul : pas de TLS, et l'authentification `UI_USERNAME` / `UI_PASSWORD` (voir
`Artificial_Intelligence_LiteLLM_UI_password` plus haut) comme seule chose entre le LAN et le conteneur qui porte la clé
maîtresse et les clés fournisseur des deux comptes. Un reverse proxy devant `/ui` reste la suite logique,
pas une clause de style.

**La connexion par identifiants d'environnement : l'alerte critique de LiteLLM et comment la lever.** Sur un
déploiement neuf, `UI_USERNAME`/`UI_PASSWORD` est la seule porte de `/ui`, et le tableau de bord de LiteLLM la signale
dans *Deployment health* comme critique : un secret partagé, permanent, en clair dans l'environnement du conteneur,
qu'on ne peut pas révoquer par personne et qui ne dit pas qui a fait quoi
([le guide de LiteLLM](https://docs.litellm.ai/docs/proxy/ui)). Garder l'alerte est un choix défendable pour un
administrateur unique sur un LAN de confiance, c'est pourquoi `Artificial_Intelligence_LiteLLM_disable_env_credential_login`
vaut `false` par défaut et que le rendu de la configuration est alors identique à celui d'avant. Pour la lever, dans
l'ordre :

1. Déclarer l'administrateur dans `Artificial_Intelligence_LiteLLM_admin_users` (voir « Les administrateurs de `/ui`,
   invités et non dotés d'un mot de passe ») et lancer le rôle : le run s'arrête sur le lien d'invitation, une seule fois.
2. Ouvrir le lien, choisir son mot de passe, puis **tester cette connexion** : se déconnecter, se reconnecter avec son
   courriel.
3. Passer la variable à `true` et redéployer. La configuration change, donc le conteneur de la passerelle est recréé
   (nom de la Docker config suffixé de la somme de contrôle du fichier).
4. `/ui` répond 401 à `UI_USERNAME`/`UI_PASSWORD` et à la clé maîtresse, et l'alerte disparaît. Seule la page de
   connexion est concernée : les utilisateurs de la base, dont les `Artificial_Intelligence_LiteLLM_internal_users`,
   et l'API (donc les tâches de ce rôle, qui l'appellent avec la clé maîtresse) ne changent pas.

Sur un **déploiement neuf**, les étapes 1 à 3 peuvent se faire en un seul run : le compte est créé par l'API, que
l'interrupteur ne touche pas, et le lien s'affiche avant qu'on ait besoin de se connecter. Le rôle refuse la variable à
`true` sans administrateur déclaré, mais il ne peut pas voir si la personne a déjà choisi son mot de passe : tant qu'elle
ne l'a pas fait, plus personne ne se connecte. On s'en sort en remettant la variable à `false` et en redéployant, ou, sur
une pile qu'on peut refaire, en repartant de zéro pour obtenir un nouveau lien. D'où les deux variables d'identifiants qui
restent **obligatoires et posées** même quand elle vaut `true` : inertes alors, elles sont ce qui rend l'accès.

**La clé de sel (#164) chiffre ce que `/ui` enregistre, et ne change plus jamais.** Avec
`STORE_MODEL_IN_DB`, LiteLLM garde en base ce que `/ui` ou son API d'administration lui confient -- les
`litellm_params` d'un modèle, clé fournisseur comprise, les identifiants de `/credentials`, les
variables d'environnement et les identifiants MCP, entre autres -- chiffrés avec `LITELLM_SALT_KEY`, et
**à défaut avec la clé maîtresse**. Le rôle passe donc `Artificial_Intelligence_LiteLLM_salt_key`,
obligatoire, et refuse qu'elle soit vide ou égale à la clé maîtresse. C'est ce qui permet à la clé
maîtresse de changer : en changeant sa variable et en redéployant, **jamais** par `POST /key/regenerate` et
`new_master_key`, qui re-chiffre tout sous la nouvelle clé maîtresse alors que LiteLLM continue de
déchiffrer avec la clé de sel. Mesuré sur LiteLLM `v1.100.0` : sans clé de sel, changer la clé maîtresse
fait disparaître du routage chaque modèle enregistré (`Invalid model name`), le conteneur reste sain et
seul son log dit pourquoi ; avec, les mêmes modèles répondent et le fournisseur reçoit la bonne clé.
L'image n'est plus épinglée à ce tag, mais le code n'a pas bougé sur ce point : `v1.105.0` choisit la clé
de la même façon (relu le 11/10/2026). La clé de sel, elle, n'a aucune rotation documentée : la changer
perd tout, de la même façon -- « Do not change it after adding a model », dit la
[page « Production Best Practices »](https://docs.litellm.ai/docs/proxy/prod) de LiteLLM.

**Migrer un déploiement qui a tourné sans elle.** Ses identifiants sont chiffrés avec la clé maîtresse,
et une clé de sel neuve les rendrait illisibles. Sur une base où rien n'a été enregistré, il n'y a rien
à migrer : une valeur neuve suffit (`openssl rand -hex 32`). Sinon, au même déploiement, la clé de sel
reçoit la valeur **actuelle** de la clé maîtresse -- celle qui chiffre déjà la base -- et la clé
maîtresse une valeur neuve, puisque le rôle refuse les deux égales. C'est la voie que recommande la
documentation amont,
[« Rotating the Master Key »](https://docs.litellm.ai/docs/proxy/master_key_rotations). Si l'ancienne
clé maîtresse n'est plus sûre, elle ne doit pas devenir la clé de sel : avant de déployer, re-chiffrer
la base sous une clé de sel neuve, par l'API du LiteLLM **encore sans clé de sel** --
`POST /key/regenerate`, avec la clé maîtresse actuelle en `key` et la future clé de sel en
`new_master_key` ; la réponse contient cette valeur -- puis déployer aussitôt avec elle. Sauvegarder la
base d'abord : la page amont prévient qu'un échec partiel de ce chemin peut laisser des lignes non
re-chiffrées. Les deux voies sont mesurées sur `v1.100.0`. En dernier recours, ressaisir les identifiants
depuis `/ui`.
`LITELLM_MIGRATE_FROM_MASTER_KEY`, que LiteLLM apporte à partir de `v1.104.0` et que décrit la même page,
ne sert pas ici : il re-chiffre sous la **nouvelle clé maîtresse**, pour un déploiement **sans** clé de
sel, et LiteLLM le laisse sans effet dès que `LITELLM_SALT_KEY` est posée, ce que ce rôle fait toujours.

**Les secrets vivent dans le fichier compose, pas dans un `.env` à part.**
`Artificial_Intelligence_PostgreSQL_password` et `Artificial_Intelligence_LiteLLM_master_key` d'abord,
puis ceux que chaque issue de service a apportés depuis (voir les tableaux de variables plus haut) --
tous, sauf les mots de passe des comptes LibreChat, que seul `create-user` reçoit (#76). Ce
sont des variables du rôle, que l'appelant rend depuis son vault et qu'Ansible interpole au rendu,
comme le reste du template -- c'est ce qui permet à la même forme de servir Compose et Swarm sans y
toucher : Ansible rend ce fichier de la même façon quel que soit celui qui le lira ensuite. C'est aussi
pourquoi le fichier compose porte l'obligation `0600` / `diff: false` du contrat du rôle de
déploiement : elle existe depuis #31, précisément pour le jour où le template interpolerait un secret.

**Et chaque `$` d'une valeur y est doublé (#155).** Compose -- comme `docker stack deploy` -- relit le
fichier rendu avec sa propre interpolation `$VAR` / `${VAR}`, après Ansible : un `$` resté simple y est
lu comme le début d'une variable à lui, remplacée par ce qu'elle vaut dans son environnement, le plus
souvent rien, avec un simple avertissement. Mesuré avec Compose v5.1.1 : `sk-Ab$cd9` arrivait dans le
conteneur en `sk-Ab`, `sk-Ab$HOME` en `sk-Ab/root`, et `${` suivi d'un chiffre fait refuser le fichier
entier. Le template écrit donc toute valeur de l'appelant dont la grammaire admet un `$` -- secrets,
identifiants, alias de modèle, chemins d'hôte -- avec `| replace('$', '$$')`, que Compose ramène à un
`$` unique. Restent sans : noms d'objets Docker, limites mémoire, nombres et
fuseau horaire, dont la grammaire exclut le `$`. Côté appelant, rien à échapper : une valeur du vault se
donne telle quelle, et doublée à la main elle arriverait fausse.

**Puis écrite en chaîne JSON, sans guillemets autour (#188).** Entre guillemets doubles YAML, un `"`
termine la chaîne et un `\` ouvre une séquence d'échappement. Mesuré avec la même version de Compose et
avec `docker stack config` : `ab"cd` et `ab\qcd` faisaient refuser le fichier entier, `ab\tcd` arrivait
avec une tabulation, `ab\x41cd` en `abAcd`, `ab\\cd` avec un seul `\`. Le template écrit donc chacune de
ces valeurs `{{ variable | replace('$', '$$') | to_json(ensure_ascii=False) }}` : une chaîne JSON est un
scalaire YAML entre guillemets doubles valide, où tout ce que YAML interpréterait est échappé.
`ensure_ascii=False` n'est pas un détail : sans lui, `to_json` -- comme le `tojson` de Jinja -- écrit un
emoji en paire de substitution, que Compose et Swarm refusent. Là encore, rien à échapper côté appelant.

**La clé maîtresse ne sort pas du conteneur.** Elle sert à l'administration depuis Ansible, à rien
d'autre. Open WebUI, N8N, le conteneur Claude Code et le bot Discord reçoivent chacun une clé virtuelle
portant sa propre liste blanche de modèles — c'est #2 qui les crée. Un client qui détient la clé maîtresse
rend inutile tout le travail d'isolation de #2.

**Une migration de schéma qui échoue arrête LiteLLM, au lieu de le laisser servir sur l'ancien
schéma.** LiteLLM applique ses migrations Prisma à chaque démarrage, et c'est une montée de tag -- celle
que le paragraphe suivant réclame -- qui en apporte de nouvelles. Par défaut, une migration en échec
est journalisée (« Database migration failed but continuing startup ») et le serveur démarre quand même :
`/health/liveliness`, et même `/health/readiness` qui ne teste que la connexion, répondent 200, la
politique de redémarrage n'a rien à rattraper, et c'est la première requête touchant une table absente
qui échoue. Le template passe donc `--enforce_prisma_migration_check` : une migration en échec fait
sortir le conteneur (code 1), la politique `condition: any` le relance, et la boucle de redémarrage
reste visible jusqu'à ce que la cause soit levée -- la migration passe alors au démarrage suivant, sans
autre intervention. Le prix : un échec passager coûte lui aussi un redémarrage. Si la boucle apparaît
après une montée de tag, la migration en cause se lit dans les journaux du service `litellm`, sous
`Error: P30…` ; retirer l'option pour que le service « démarre » ne ferait que rendre l'échec muet.

**LiteLLM n'est pas le superutilisateur de sa base (#159).** L'image officielle fait de `POSTGRES_USER`
le superutilisateur d'amorçage, et ce rôle ne peut jamais perdre l'attribut. LiteLLM se connectait avec
lui : une injection SQL préalable à toute authentification (LiteLLM en a connu une en 2026) lui
donnait `COPY … PROGRAM` -- un shell dans le conteneur `postgres` -- et la lecture de tout fichier du
serveur. Il se connecte désormais avec un rôle ordinaire (`LOGIN`, rien d'autre), propriétaire de sa
base et donc, depuis PostgreSQL 15, de son schéma
`public` : c'est tout ce dont les migrations Prisma ont besoin, vérifié en direct avec LiteLLM
v1.100.0 (161 migrations appliquées ; `COPY … PROGRAM`, `pg_read_file` et `CREATE EXTENSION dblink`
refusés). Le superutilisateur est un autre rôle, `Artificial_Intelligence_PostgreSQL_superuser`, avec
son propre mot de passe.

Ce rôle est créé au premier démarrage par un script de `/docker-entrypoint-initdb.d/` que la `command:`
du service `postgres` écrit dans le conteneur avant de passer la main à l'entrypoint de l'image. Ni
fichier monté (un montage `bind` exige le chemin sur le nœud qui exécute la tâche, et `/tmp` ne garde
pas un fichier, #137), ni `configs.content` (que `docker stack` refuse).

**PostgreSQL 15 au minimum**, et rien ne le vérifie : le majeur est écrit en dur dans le template
(`image: postgres:18`), et le descendre sous 15 est une édition de ce fichier. Le script lit ses
valeurs avec `\getenv`, apparu dans le `psql` de 15, et c'est 15 qui confie le schéma `public` à
`pg_database_owner`. En dessous, l'échec est silencieux et ne se résorbe pas -- mesuré avec
`14-alpine` : le premier démarrage initialise le répertoire de données puis s'arrête sur `invalid
command \getenv`, les redémarrages suivants sautent l'initialisation, et PostgreSQL tourne, sonde de
santé au vert, sans aucun rôle avec lequel LiteLLM puisse se connecter. Le rôle ne répare pas ce
volume ; il ne contient rien de LiteLLM, et le supprimer, tag relevé, est la seule sortie.
`15-alpine`, lui, a porté les 161 migrations de LiteLLM v1.100.0 sous son rôle ordinaire.

### Un volume créé avant le rôle dédié de LiteLLM

L'image n'exécute `/docker-entrypoint-initdb.d/` que sur un répertoire de données **vide**. Sur un volume
initialisé avant #159, rien ne change : le rôle de LiteLLM reste le superutilisateur d'amorçage,
LiteLLM continue de fonctionner, et le rôle `Artificial_Intelligence_PostgreSQL_superuser` n'existe pas
-- son mot de passe n'est lu nulle part. Rien ne casse, rien ne s'améliore. Aucune v1.0 n'ayant pu aboutir
à un déploiement (#126), seuls des volumes de banc d'essai sont concernés ; si leur contenu ne compte pas,
supprimer le volume et redéployer suffit.

Pour garder les données (clés virtuelles, comptes, consommation), vérifié de bout en bout sous Compose,
une clé créée avant la bascule retrouvée après :

```bash
# « litellm » est le défaut du rôle comme de la base : remplacer par les vôtres s'ils diffèrent.
# 1. Exporter, avec l'ancien superutilisateur -- le rôle de LiteLLM, sur le socket du conteneur
docker exec <conteneur postgres> pg_dump -U litellm --format=custom --no-owner --no-privileges litellm > litellm.dump
# 2. Arrêter le stack, puis supprimer SON volume PostgreSQL (docker volume ls pour son nom exact)
docker volume rm <volume PostgreSQL du stack>
# 3. Redéployer avec le rôle : l'initialisation crée le superutilisateur et le rôle de LiteLLM,
#    et LiteLLM migre une base vide
# 4. Arrêter LiteLLM (docker stop <conteneur litellm> sous Compose, docker service scale <stack>_litellm=0
#    sous Swarm), restaurer EN TANT QUE rôle de LiteLLM, qui possède ainsi tout ce qu'il restaure, puis
#    le relancer (docker start, ou scale à 1)
docker exec -i <conteneur postgres> pg_restore -U litellm -d litellm --clean --if-exists --no-owner --no-privileges --exit-on-error < litellm.dump
```

### Un point qui attend la bascule Swarm, et un qui ne l'attend plus

L'interpolation par Ansible plutôt que par un `.env` a réglé le premier problème d'elle-même : rendre
le fichier compose est le travail d'Ansible, pas de l'orchestrateur, donc la bascule Compose → Swarm ne
change rien à la façon dont les secrets y arrivent.

Ce qui reste à traiter à ce moment-là : **LiteLLM lit `os.environ/…`** pour sa clé maîtresse et son URL
de base, valeurs que le compose lui passe en clair via `environment:`. Swarm sait faire pareil, à
l'identique -- ce n'est donc pas un blocage -- mais le jour de la bascule est le bon moment pour se
demander si les secrets natifs de Swarm ne valent pas mieux que des variables en clair dans le fichier
rendu, question que Compose ne se pose de toute façon pas.

`depends_on` relève d'un registre voisin, et il s'écrit **sous sa forme courte**, une simple liste de
services. Compose démarre ces services d'abord, sans attendre qu'ils soient sains ; `docker stack deploy`
accepte la liste et l'ignore. La forme longue (`condition: service_healthy`), qui ferait attendre Compose,
n'est pas ignorée par Swarm, contrairement à ce que ce paragraphe affirmait jusqu'à #154 : docker/cli
valide le fichier contre son propre schéma, où `depends_on` est une liste de chaînes, et **refuse le
fichier entier** (`services.litellm.depends_on must be a list`) avant même de parler au démon.
`check_compose_template.py` refuse donc toute autre forme que la liste.

LiteLLM doit ainsi tolérer une base pas encore prête, sous les deux déployeurs, et c'est la politique de
redémarrage `any` qui rattrape le cas -- pas l'ordre de démarrage. Mesuré avec une base retenue 45 s :
le premier démarrage de LiteLLM échoue (`Application startup failed. Exiting.`), le conteneur est relancé
une fois, et le second devient sain. Ce que la relance ne rattrape pas : LiteLLM poursuit son démarrage
quand ses migrations échouent (`Database migration failed but continuing startup`), donc une base qui
se met à répondre entre cet échec et la connexion de démarrage le laisse tourner sur un schéma non
migré. C'est `ENFORCE_PRISMA_MIGRATION_CHECK` qui ferme cette fenêtre, sujet traité à part.

**La sonde de santé de `postgres` passe par TCP, sur le port de `DATABASE_URL`, et pas par le socket
Unix (#153).** Au premier démarrage, l'image initialise le volume sur un serveur temporaire qui
n'écoute que sur le socket ; une sonde par socket le déclarait sain alors que le port 5432 refusait
encore tout autre conteneur -- mesuré : `healthy` à 5 s, port ouvert à 21 s sur une initialisation
tenue ouverte 20 s. Une porte `service_healthy` ne vaut que ce que vaut la sonde, et la sonde ne
sert pas qu'à cette porte : c'est elle que lisent `docker compose ps`, `docker compose up --wait`,
et sous Swarm l'état des tâches et la surveillance d'une mise à jour. Le prix est qu'elle échoue
pendant toute l'initialisation : environ 35 s de marge avant `unhealthy` (`start_period` puis
`retries` × `interval`), contre une à deux secondes mesurées pour un premier démarrage ordinaire.

## Le `model_list` du compte de la passerelle (#2, périmètre v1)

`LiteLLM_config.yaml.j2` porte désormais le `model_list` réel du compte de la passerelle -- ses entrées actives, à
travers Gemini, Mistral, Groq, OpenRouter (`:free`), Kilo Gateway et OVHcloud AI Endpoints (sans clé), Cloudflare Workers AI, Z AI, NVIDIA, Cent AI, Aion Labs (à part, voir plus bas) et OmniRoute en
dernier recours -- repris de son propre POC fonctionnel plutôt que ré-inventé. DeepSeek s'y ajoute en accès direct, payant
comme Mistral : placé en dernier recours dans chaque cascade où il apparaît, juste
avant OmniRoute, qui reste le seul vraiment gratuit. La liste suit la règle posée par #169
(`CLAUDE.md`, « The model list keeps only what can be called ») : un modèle retiré par son fournisseur
est supprimé, un modèle servi mais délibérément non routé reste commenté avec sa raison, un nouveau
modèle est ajouté. #169 l'a appliquée à Groq, #200 à tous les autres (recensement du 2026-09-27) :
GitHub Models, fermé par GitHub le 2026-07-30 (#109), est supprimé et non plus archivé ; Cerebras n'a
plus de palier gratuit permanent (5 $ de crédit après ajout d'un moyen de paiement, expirés au bout
de 30 jours), ses deux modèles sont donc commentés comme ceux de SambaNova, et sa clé, restée une
variable facultative, n'est plus lue par aucune entrée active ; Mistral n'a plus de palier gratuit pour
l'API (le mode « Free » ne couvre que Vibe et Studio, vérifié le 2026-11-21) : il est payant et placé
après tous les gratuits. Les entrées `:free` d'OpenRouter
partagent une seule limite pour tout le compte : 20 requêtes par minute et 50 par jour, 1000 une fois
10 crédits achetés.

**Un seul compte dans ce `model_list`, et c'est un choix assumé, pas un oubli.** Les modèles d'un
autre compte y arriveront comme des entrées à lui, portant ses propres clés sous une étiquette que
l'appelant choisit (#107). Pas depuis sa propre connexion `/ui` : LiteLLM réserve l'ajout d'un modèle
(`/model/new`) à l'administrateur du proxy -- ou à un admin d'équipe, sur sa seule édition payante.
Aucun groupe d'accès ne désigne un compte : chaque entrée porte celui de son type de modèle (voir « Les
groupes d'accès » plus bas), car un nom de compte figé dans une étiquette d'autorisation romprait la
réutilisabilité de ce rôle pour qui l'installe. Une clé sans restriction voit donc **tous les modèles**,
y compris celles créées pour les comptes de la liste plus bas ; seule la clé d'un compte LibreChat est
limitée, aux modèles de texte.
Il reste davantage à faire : `rpm_limit` / `tpm_limit` par clé, le
test négatif inter-comptes exécutable -- resté ouvert sur #2, délibérément pas tenté ici, et quand il
arrivera l'identité d'un compte viendra d'une variable du rôle, jamais d'un nom écrit dans ce fichier.

**La clé d'API décide du compte, jamais le nom du modèle.** `check_LiteLLM_account_isolation.py` (#32)
attribue chaque entrée à un compte par le nom de sa variable d'environnement -- `os.environ/GEMINI_API_KEY`,
sans suffixe, est le compte par défaut, et `os.environ/GEMINI_API_KEY_<ÉTIQUETTE>` un autre compte dont l'appelant
choisit l'étiquette, jamais un nom de personne -- et non par le `model_name` ou par
`access_groups`, qui ne sont que des étiquettes. C'est pour cette convention que les clés fournisseur
sont exposées au conteneur sous un nom en `_API_KEY` plutôt que sous leur nom usuel (`GITHUB_TOKEN`
devient `GITHUB_API_KEY`, par exemple) : LiteLLM ne se soucie pas du nom de la variable, seul ce
contrôle en a besoin.

**OmniRoute n'appartient à personne, et c'est voulu.** Son `api_key` est une chaîne littérale, jamais
`os.environ/...` -- ce que la règle « aucun secret en clair, jamais » de ce dépôt rend sans ambiguïté :
une valeur littérale ne peut être qu'un marqueur pour un service qui n'a besoin d'aucune information
d'authentification, jamais un oubli. `check_LiteLLM_account_isolation.py` reconnaît maintenant cette
forme et l'exempte des règles 1 et 2 : il n'y a aucun quota à lui attribuer, donc aucun à protéger.

### Les groupes d'accès : limiter une clé à un type de modèles

Chaque entrée du `model_list` est dans **un groupe d'accès de type**, écrit dans son `model_info.access_groups` d'après son `model_info.mode`, à une exception près, voulue : les modèles de texte d'Aion Labs ont un groupe à eux, pour qu'aucune clé qui a `LLM` ne les atteigne. Elle est **aussi** dans exactement un des deux groupes de données, écrit après le premier : `["LLM", "Private-Data"]`, `["STT", "Public-Data-Only"]`. LiteLLM accepte une liste libre de groupes, et le second dit ce que le fournisseur fait de ce qu'on lui envoie (voir « Les groupes de données » plus bas).

| Groupe | Entrées |
| --- | --- |
| `LLM` | les modèles de texte (aucun `mode`), y compris ceux que les routeurs `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code` et `Auto-Claude-Code` placent en tête, et l'entrée `Auto` qui choisit entre trois de ces routeurs (voir « Choisir à la place du client : le routeur `Auto` ») |
| `Fiction` | les six modèles d'Aion Labs, réglés pour le jeu de rôle et la narration, qu'atteint le routeur `Auto-Fiction` et aucun autre (voir « Les modèles de jeu de rôle ») ; **jamais** dans `LLM` |
| `STT` | les modèles de transcription (`audio_transcription`) |
| `TTS` | les modèles de synthèse vocale (`audio_speech`) |
| `Embeddings` | les modèles de vecteurs (`embedding`) |
| `Decisions` | les modèles de décision de Cloudflare, Clef (`evaluation`), qu'atteint le routeur `Auto-Decision` |
| `Extraction` | les modèles d'extraction de Cloudflare, Clairic (`extraction`), qu'atteint le routeur `Auto-Extraction` |
| `Private-Data` | les entrées des fournisseurs auxquels on peut envoyer des données privées, quel que soit leur type (verdict par fournisseur plus bas) |
| `Public-Data-Only` | toutes les autres : ce que leurs conditions permettent (entraînement, journalisation, relecture humaine, exploitant inconnu, juridiction sans équivalence) ne les rend bonnes que pour des données qu'on accepterait de voir publiées |

En créant une clé dans `/ui`, on choisit un groupe plutôt que les modèles un à un : la clé atteint les modèles de ce type et aucun autre, par exemple `LLM` pour LibreChat, sans la voix. **Les routeurs suivent la tête de leur cascade** : un routeur est un alias de son premier membre, et LiteLLM laisse une clé appeler un alias quand l'entrée vers laquelle il se résout est autorisée (lu dans son code, pas encore essayé sur une passerelle réelle). `check_compose_template.py` tient chaque entrée à ses deux groupes, et le script de la veille de modèles écrit les entrées qu'il propose dans les groupes de leur fournisseur : `LLM` (ou `Fiction` pour Aion Labs) puis le groupe de données de ce fournisseur, `Public-Data-Only` pour un fournisseur qu'aucune ligne ne nomme.

La clé qu'un compte LibreChat reçoit de `gateway_key` est limitée au groupe `LLM` et aux routeurs de texte (`Artificial_Intelligence_LibreChat_gateway_key_models`), si bien que LibreChat ne liste pour ce compte que ce qu'il peut appeler : ni transcription, ni voix, ni vecteurs. Les routeurs sont nommés à côté du groupe parce que LiteLLM remplace un groupe par ses membres seulement (lu dans son code) : un routeur est l'alias de la tête de sa cascade et n'est dans aucun groupe, donc une clé limitée à `LLM` seul ne les listerait pas, tout en pouvant les appeler. `Auto` n'est pas un alias mais une entrée du groupe `LLM` : elle est listée avec lui, et n'a donc pas besoin d'être nommée.

#### Les groupes de données : `Private-Data` et `Public-Data-Only`

Les deux groupes disent ce que le fournisseur d'une entrée fait de ce qu'on lui envoie, lu dans **ses propres conditions** et pour l'offre que la passerelle utilise (relu le 2026-11-24). Un groupe LiteLLM est une **liste blanche** : une clé reçoit les groupes qu'elle peut appeler, il n'existe pas de liste noire, c'est pourquoi le groupe utile est le positif. `Private-Data` est celui qu'on donne à une clé ; `Public-Data-Only` est une étiquette visible que **aucune clé ne reçoit**.

Un fournisseur est `Private-Data` quand **tout** ce qui suit tient :

- ses conditions disent que les requêtes et les réponses ne servent ni à l'entraînement ni à l'amélioration de ses produits, sur l'offre utilisée ici ;
- aucune relecture humaine, hors ce que la surveillance des abus signale ;
- rien n'est conservé au-delà du traitement, ou seulement pour une période courte et annoncée de surveillance des abus ;
- l'exploitant est une société connue, liée par ces conditions (ni bénévole, ni réseau de GPU décentralisé) ;
- le traitement a lieu dans l'UE ou en Suisse, ou sous des conditions qui offrent des garanties équivalentes au RGPD (l'accord de traitement et les clauses contractuelles types, par exemple), que la ligne nomme.

Tout le reste est `Public-Data-Only`, et **un fournisseur dont les conditions n'ont pas pu être lues l'est par défaut**, avec la raison. `check_compose_template.py` porte la même table (`LITELLM_DATA_GROUPS`, une raison et une page par ligne), tient chaque entrée rendue, pour chaque ensemble de clés, au groupe de son fournisseur, et refuse une entrée qui n'en a aucun, qui en a deux ou dont le fournisseur n'a pas de ligne.

| Fournisseur | Groupe | Phrase décisive (pages relues le 2026-11-24) |
| --- | --- | --- |
| Google Gemini API (palier gratuit) | `Private-Data`, **sous condition** | « If you're in the European Economic Area, Switzerland, or the United Kingdom, the terms under "How Google uses Your Data" in "Paid Services" apply to all Services, including Google AI Studio and unpaid quota in the Gemini API, even though they are offered free of charge » : les conditions des services payants disent que Google « doesn't use your prompts » ni les réponses « to improve our products », que Google traite sous son accord de traitement (en sous-traitant) et journalise « for a limited period of time » pour la surveillance des abus, soit 55 jours, avec un accès humain réservé aux contenus signalés. Hors de ces trois régions, le contenu du palier gratuit sert à améliorer les produits et « human reviewers may read, annotate, and process your API input and output ». **Condition** : la clause vise un appelant dans l'EEE, en Suisse ou au Royaume-Uni, et les mêmes conditions disent « You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom » ([conditions](https://aistudio.google.com/docs/terms), [surveillance des abus](https://aistudio.google.com/docs/usage-policies)) |
| Mistral | `Private-Data`, **sous condition** | Société française. « Mistral AI will not use Customer Data or Outputs to train its artificial intelligence models except (a) when you (i) opted-in to training on a Mistral AI Product set to opt-out by default or (ii) have not opted-out of training on a Mistral AI Product set to opt-in by default [...] or (d) when Customer uses Labs or Preview Models », traitement comme sous-traitant sous l'accord de traitement. **Condition** : l'interrupteur « Data usage for improving our services » du panneau d'administration doit être éteint, ce que le rôle ne peut pas vérifier, et aucun modèle `labs-` ou en préversion ne doit être routé. Aucune page lue ne dit où l'API est hébergée ([conditions commerciales](https://legal.mistral.ai/terms/commercial-terms-of-service), [accord de traitement](https://legal.mistral.ai/terms/data-processing-addendum)) |
| Cloudflare Workers AI | `Private-Data` | « Cloudflare does not use Customer Content processed by Workers AI to train AI models. » et « Workers AI processes Customer Content only for as long as needed to provide the service » ; accord de traitement où « Cloudflare is a Processor », clauses contractuelles types et Data Privacy Framework. Le lieu de traitement n'est dit sur aucune page lue, et que l'accord couvre un compte gratuit n'est pas dit non plus ([usage des données](https://developers.cloudflare.com/workers-ai/platform/data-usage/), [accord](https://www.cloudflare.com/cloudflare-customer-dpa/)) |
| OVHcloud AI Endpoints | `Private-Data`, **à confirmer** | « Our AI Endpoints services are hosted and run in the European Union. », « Your data is never used to train our models, and we only keep what is strictly necessary for billing. » La page décrit le service avec clé ; pour l'accès anonyme que les entrées utilisent, la documentation dit seulement « we do not store user data » à côté de « Anonymous: 2 requests per minute, per IP and per model » ([service](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/), [prise en main](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-getting-started)) |
| Aion Labs | `Private-Data`, **à confirmer** | Société polonaise (Deep Forge sp. z o.o.) : « we do not store the content you send to the models through the API or browser chat » et « we do not use your content to train models », garanties du RGPD pour les transferts ; « Some of our providers are located outside the European Economic Area, mainly in the United States », sans dire lesquels traitent les requêtes ([confidentialité](https://www.aionlabs.ai/privacy/)) |
| Groq | `Public-Data-Only` | Contrat de services, 4.2 : pas d'entraînement sur les entrées et sorties, mais « All customer data is retained in Google Cloud Platform (GCP) buckets located in the United States », journaux d'abus et de fiabilité conservés « up to 30 days », et les conditions ne disent rien de la relecture humaine ni du palier gratuit (le contrat exclut les services en bêta de l'accord de traitement, et `qwen3.8-27b` est en préversion) ([vos données](https://console.groq.com/docs/your-data), [contrat](https://console.groq.com/docs/legal/services-agreement)) |
| DeepSeek | `Public-Data-Only` | « we directly collect, process and store your Personal Data in People's Republic of China », finalité « To improve and develop the Services and to train and improve our technology », conservé « as long as you have an account » ([politique](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)) |
| OpenRouter (`:free`) | `Public-Data-Only` | « Some Model Providers may use your Inputs and Outputs for model training or improvement. » OpenRouter ne choisit pas le fournisseur d'un modèle gratuit d'après sa politique de données, et ne dit rien des modèles gratuits en particulier ([confidentialité](https://openrouter.ai/privacy), [journalisation par les fournisseurs](https://openrouter.ai/docs/guides/privacy/provider-logging)) |
| Z AI | `Public-Data-Only` | « Customer Data is generally processed in Singapore. » Pour l'API, « we will not use your User Content for developing or improving Services unless you explicitly agree » et « The Company do not store any of the content », mais aucun mécanisme de transfert du RGPD n'est nommé et l'accord de traitement est écrit pour « business and enterprise users » ([confidentialité](https://docs.z.ai/legal-agreement/privacy-policy), [conditions](https://docs.z.ai/legal-agreement/terms-of-use.md)) |
| Requesty (modèles gratuits) | `Public-Data-Only` | La passerelle est à Francfort et ne garde pas les corps de requête, mais les modèles gratuits sont relayés à un fournisseur en amont dont aucune page lue ne dit qu'il est dans l'UE ni qu'il n'entraîne pas (passer par la passerelle européenne ne place pas le modèle en Europe, d'après les pages de Requesty), et ses propres conditions n'ont pas pu être lues (pages relues le 2026-11-22 et 2026-11-24) |
| NVIDIA API Catalog (essai) | `Public-Data-Only` | « NVIDIA will collect the following data, without identifying specific users [...]: [...] (iv) User Content and Generated Content to improve NVIDIA products and services, including AI models. Your use of the API Services will be logged for security, fraud or abuse monitoring and shared with third party service providers », données personnelles interdites, usage de production interdit (conditions d'essai, 3.3 et 4.3) |
| Cent AI | `Public-Data-Only` | « run as an individual business, not a company », conditions en « Version 0.1 (draft) », « Models are served by third-party model providers and sellers, not by Cent AI » dont « The provider's own terms and data practices also apply » ; bases de données en Malaisie ([conditions](https://cent-ai.dev/legal/terms), [confidentialité](https://cent-ai.dev/legal/privacy)) |
| Kilo Gateway | `Public-Data-Only` | « Auto Free may route your requests to providers that log prompts and outputs and use them to improve their services », et pour les points d'accès gratuits de NVIDIA « Trial use only - do not submit personal or confidential data » ([modèles et fournisseurs](https://kilo.ai/docs/gateway/models-and-providers), [conditions](https://kilo.ai/terms)) |
| OmniRoute | `Public-Data-Only` | Un routeur local qui envoie chaque requête au fournisseur gratuit sans clé qui répond, aucun n'étant choisi ni lu ; la documentation ne dit rien de la journalisation des requêtes ([dépôt](https://github.com/diegosouzapw/OmniRoute)) |

Les entrées d'embeddings, de transcription, de synthèse vocale, de décision et d'extraction suivent leur fournisseur : celles de Gemini, de Mistral et de Cloudflare sont `Private-Data`, celles de Groq sont `Public-Data-Only`. Cerebras et SambaNova n'ont aucune entrée active, et la table les range en `Public-Data-Only` faute d'en avoir lu les conditions.

**Donner à une clé les seuls modèles auxquels on peut envoyer des données privées.** Dans `/ui`, « Virtual Keys » puis « Create New Key », champ « Models » : choisir `Private-Data` et **rien d'autre** (la clé atteint alors les entrées de ce groupe, et seulement elles) ; ou, par l'API d'administration, `"models": ["Private-Data"]` dans l'appel à `/key/generate`. Cette lecture de la liste blanche vient du code de LiteLLM et **n'a pas été essayée sur une passerelle réelle**.

**Ne donner aucun routeur à une telle clé.** Les cascades des routeurs mélangent les deux groupes (Gemini ou NVIDIA en tête, `Public-Data-Only` derrière) et un repli, à notre connaissance, n'est pas soumis de nouveau à la liste de la clé (**non vérifié sur une passerelle réelle**) : une clé qui atteint un routeur dont la tête est `Private-Data` pourrait voir une requête retomber sur une entrée `Public-Data-Only`. Une clé `Private-Data` appelle donc les entrées par leur nom. Un routeur à lui, dont la cascade ne tiendrait que des entrées `Private-Data`, serait le moyen de lui en rendre un ; il n'existe pas.

**La liste des clés de LibreChat ne change pas.** `Artificial_Intelligence_LibreChat_gateway_key_models` garde son défaut (`LLM` et les routeurs de texte), qui atteint les deux groupes de données : LibreChat sert aussi des données qu'on accepterait publiées, et aucune raison n'est apparue de le restreindre. Surcharger la liste par `[Private-Data]` limiterait la clé de **chaque** compte LibreChat à ce groupe, sans routeur ; `check_compose_template.py` accepte les deux noms de groupe dans la liste.

### Les clés fournisseurs : au moins une, et seuls les fournisseurs dont la clé est donnée sont rendus (#296)

Le rôle exige **au moins une** des clés de fournisseurs (Gemini, Mistral, Groq, OpenRouter, DeepSeek, Cloudflare, Z AI, Requesty, NVIDIA, Cent AI, Aion Labs), et échoue en les
nommant toutes quand aucune n'est renseignée. Chaque personne choisit son fournisseur : le rôle n'impose ni
Mistral ni DeepSeek, qui sont payants, à qui n'en veut pas. Un fournisseur sans clé n'a **aucune entrée** dans
`LiteLLM_config.yaml.j2` et aucun emplacement dans les cascades : un modèle listé sans clé échouerait à chaque
requête qui le traverse, avant de passer le relais, et s'afficherait dans LibreChat sans jamais répondre.

Les cinq routeurs (`Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite`, `Auto-Code`, `Auto-Claude-Code`) ne sont des entrées du `model_list` pour
aucun fournisseur : un nom qui n'est ni une entrée ni un alias est refusé par le proxy même s'il a une cascade dans
`fallbacks` (mesuré sur LiteLLM 1.100.0), et le routeur est donc, quelles que soient les clés, l'**alias** du premier
modèle de sa cascade dont la clé est donnée. Aucun fournisseur n'est premier par la façon dont les noms sont
construits : l'ordre de la cascade, qui suit l'intelligence et la vitesse des modèles, décide seul. Le routeur garde sa
cascade ; quand aucun modèle de sa cascade n'a de clé ni n'en demande, il disparaît : `Auto-Claude-Code`
seul peut s'y trouver, depuis que les entrées sans clé de Kilo Gateway, d'OVHcloud et d'OmniRoute servent les quatre autres. LiteLLM liste les alias parmi les noms de modèles (`get_model_names`, lu dans son code),
donc LibreChat les propose toujours. À connaître :

- La cascade de `Auto-Claude-Code` n'admet que des modèles à appels d'outils stricts et à 128 000 jetons de contexte au moins
  (le commentaire de la cascade, dans le template, le dit). C'est la cascade de `Auto-Code`, membre pour membre et dans le
  même ordre, moins `omniroute-free-code` : OmniRoute choisit lui-même un modèle gratuit parmi ses fournisseurs, et sa
  documentation dit qu'un fournisseur gratuit peut émuler les appels d'outils depuis le prompt ou les ignorer, donc rien
  ne garantit ni les outils ni le contexte. `check_compose_template.py` tient les deux listes à cette égalité. Elle ne
  contient donc que des modèles de Gemini, Groq, NVIDIA, Cloudflare, Z AI, Mistral et DeepSeek : c'est ce qui y a été retenu, pas un
  constat que les autres fournisseurs n'en ont aucun qui convienne. Sans l'une de ces sept clés l'agent n'a aucun
  modèle, et le rôle refuse ce déploiement, sauf si l'agent est éteint
  (`Artificial_Intelligence_Claude_code_enabled: false`) ou demande un autre routeur
  (`Artificial_Intelligence_Claude_code_model`).
- La tête de cascade est atteinte par l'alias, puis listée de nouveau comme premier repli : une tête en échec coûte
  une tentative de plus, une fois par fenêtre de refroidissement (`cooldown_time`).
- Un routeur n'a qu'**un nom**, celui que tape un client (`Auto-Pro`, `Auto-Flash`...), et sa cascade est écrite sous ce nom : LiteLLM cherche les replis sous le nom qui a été demandé, donc un nom sans cascade ne retomberait sur rien quand la tête échoue. Deux noms pour un routeur seraient deux cascades à tenir au même niveau et un client qui choisit au hasard entre les deux : les anciens noms (`pro`, `flash`, `auto`, `auto-fast`, `auto-pro`...) n'existent plus, et `check_compose_template.py` refuse un routeur publié sous un autre nom que le sien.
- `check_compose_template.py` rend la configuration pour chaque ensemble non vide de clés, et tient chaque
  rendu aux règles ci-dessus ; en particulier, un alias de routeur doit pointer sur le premier membre de sa cascade.
  Il tient aussi le fichier compose à la même table : le conteneur de la passerelle doit recevoir chaque clé sous le
  nom que la configuration lit, qui n'est pas toujours celui du fournisseur (`NVIDIA_NIM_API_KEY`, pas
  `NVIDIA_API_KEY`).

#### NVIDIA : un service d'essai, des limites inconnues, et une place dans chaque cascade

NVIDIA offre, avec son « NVIDIA API Catalog », un accès hébergé à des modèles de plusieurs éditeurs : la page
d'accueil du catalogue (lue le 2026-11-22) annonce « Free inference with leading models », et les fiches de modèle
disent que « The trial service is governed by the NVIDIA API Trial Terms of Service ». C'est un fournisseur natif de
LiteLLM (préfixe `nvidia_nim/`). La clé (`Artificial_Intelligence_LiteLLM_NVIDIA_API_key`) arrive au conteneur sous le
nom `NVIDIA_NIM_API_KEY`, celui que LiteLLM cherche, et aucune entrée n'écrit d'`api_base` : le code de LiteLLM, lu le
2026-11-22, appelle de lui-même le point d'accès hébergé de NVIDIA. Que le conteneur reçoive chaque clé sous ce nom
exact est tenu par `check_compose_template.py`, qui ne tenait cela pour aucun fournisseur auparavant.

**Les conditions sont celles d'un service d'essai, et le mainteneur a choisi de s'en servir.** Les « NVIDIA API Trial
Terms of Service » (PDF lu le 2026-11-22) donnent l'accès « for limited trial purposes only and without use of the API
Service or Generated Content in production » et « for internal testing and evaluation purposes, not in production ».
NVIDIA peut collecter « User Content and Generated Content to improve NVIDIA products and services, including AI
models ». L'utilisateur ne doit fournir ni information confidentielle, ni donnée contrôlée ou sensible, ni donnée
personnelle « unless expressly permitted by an API Service ». Et le droit d'utiliser le service « terminates
automatically without notice from NVIDIA » si l'utilisateur manque au contrat. La passerelle sert toutes les
applications du homelab : le mainteneur accepte que ce qui y passe puisse entraîner les modèles de NVIDIA, que les
conditions interdisent les données personnelles, et que NVIDIA puisse couper la clé, un risque qu'il ne veut pas
anticiper.

**Une seule limite est connue : 40 requêtes par minute.** La page du compte du mainteneur l'affiche (« Your API Rate
Limit : Up to 40 rpm », lue le 2026-11-22 avant qu'une clé soit créée), et c'est un débit, pas un crédit. Aucun crédit,
plafond quotidien ni date de fin ne figure sur une page lue, celle du compte comprise, ni la façon d'obtenir la clé ;
les conditions d'essai disent seulement que l'usage « may be limited to a certain number of API access instances or by
API access duration ». La vérification par SMS, citée sur des forums, n'est **pas vérifiée**. Un plafond de crédits ou
de durée éventuel se lit à la création de la clé, et ce dépôt n'en affirme aucun. Que
chaque modèle routé soit gratuit n'est pas établi non plus : la page le dit du service, pas modèle par modèle, et
l'étiquette « Free Endpoint » de la page de découverte, lue sur sa première page de résultats seulement, ne porte pas
sur tous les modèles routés et n'est expliquée nulle part -- rien n'en est conclu.

**Ce qui a été vérifié, et ce qui ne l'a pas été.** La liste des modèles que le point d'accès sert (lue sans clé le
2026-11-22) contient tous les modèles ci-dessous. Les appels d'outils et le contexte de chacun sont ceux que sa fiche
déclare dans les données de sa page (lue le même jour) ; pour trois d'entre eux (Mistral Large 4, MiniMax-M3.1-Flash,
Nemotron 3.5 Super VL) le texte de la fiche dit jusqu'à 1 million de jetons et les données 262 144 : le plus petit est
retenu. Que LiteLLM transmet `tools` et `tool_choice` à ce fournisseur, et rend les appels d'outils en continu comme
en bloc, a été **mesuré** contre un serveur de remplacement, pour chaque entrée ci-dessous. Que la clé soit acceptée par
le point d'accès, et que chaque modèle réponde réellement à un appel d'outils à travers lui, n'a **pas** été essayé :
à confirmer au premier appel.

| Modèle (entrée) | Contexte | Indice d'Artificial Analysis | Où |
| --- | --- | --- | --- |
| Kimi K3.1 Pro (`kimi-k3-1-pro-nvidia`) | 1 048 576 | 46,5 | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` |
| Step 5 Preview (`step-5-preview-nvidia`) | 1 048 576 | 28,5 | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` |
| MiniMax-M3.1-Flash (`minimax-m3-1-flash-nvidia`) | 262 144 | 29,1 | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` |
| GLM-5.3-Flash (`glm-5-3-flash-nvidia`) | 1 048 576 | 27,8 | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` |
| Mistral Large 4 (`mistral-large-4-nvidia`) | 262 144 | 26,1 | `Auto-Pro`, `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` |
| Muse Glimmer (`muse-glimmer-nvidia`) | 131 072 | 6,3 | `Auto-Flash`, `Auto-Code`, `Auto-Claude-Code` |
| Laguna XS 2.1 (`laguna-xs-2-1-nvidia`) | 262 144 | aucun enregistrement | `Auto-Code`, `Auto-Claude-Code`, en fin des gratuits |
| Nemotron 3 Ultra (`nemotron-ultra-nvidia`) | 1 048 576 | 11,8 | `Auto-Pro`, derrière son jumeau OpenRouter |
| Nemotron 3 Nano Omni (`nemotron-reasoning-nvidia`) | 262 144 | aucun indice | `Auto-Pro`, derrière son jumeau OpenRouter |
| Nemotron 3.5 Super VL (`nemotron-super-vl-nvidia`) | 262 144 | 13,6 | `Auto-Pro` et `Auto-Flash`, derrière son jumeau OpenRouter |
| Gemma 4 31B (`gemma-4-31b-nvidia`) | 262 144 | estimé, aucun indice au niveau appelé | `Auto-Flash`, derrière ses deux jumeaux |
| Nemotron 3.5 Lightning (`nemotron-lightning-nvidia`) | 1 048 576 | 5,5 | `Auto-Flash-Lite`, derrière son jumeau OpenRouter |
| Nemotron 3.5 Bolt E4B (`nemotron-bolt-e4b-nvidia`) | 65 536 | aucun indice | `Auto-Flash-Lite`, en fin des gratuits |
| Gemma 3 12B et Gemma 3 4B (`gemma-3-12b-nvidia`, `gemma-3-4b-nvidia`) | inconnu | aucun indice, délais de 3,1 s et 1,9 s | `Auto-Flash-Lite`, placés par leur délai |

Chaque modèle est placé par les chiffres que les autres entrées suivent : l'indice d'Artificial Analysis (lu le
2026-11-21) pour `Auto-Pro` et `Auto-Flash`, les benchmarks de code d'Epoch AI là où ils existent pour `Auto-Code` et `Auto-Claude-Code`,
le délai avant le premier jeton pour `Auto-Flash-Lite`. Les modèles d'une famille que le fichier sert déjà (Nemotron,
Gemma) sont des sources de plus, chacune juste derrière son jumeau ; un modèle sans aucun chiffre ferme les gratuits
de ses cascades. Les planchers admettent chacun des modèles ci-dessus dans les routeurs où il est ; `Auto-Claude-Code` demande
des appels d'outils déclarés et 128 000 jetons de contexte au moins, d'où l'absence de Nemotron 3.5 Bolt E4B et des deux
Gemma 3 (le contexte de Muse Glimmer est tout juste suffisant). Les noms des entrées portent le suffixe `-nvidia`.

**À surveiller : deux modèles sont lents à répondre.** Artificial Analysis mesure environ 155 s avant le premier jeton de
réponse pour Kimi K3.1 Pro et 87 s pour GLM-5.3-Flash (lu le 2026-11-21, à l'effort de ses sondes), contre 90 s pour le
`stream_timeout` du routeur : à ce niveau, le routeur peut abandonner Kimi avant qu'il réponde. Ils sont pourtant placés
par leur capacité, la règle des contrats de routeur ne fixant aucun budget de temps. Si l'usage montre qu'ils expirent
presque toujours, ce délai ou leur place est à revoir.

Vus le même jour dans la liste du point d'accès et non routés : un modèle de vision, un modèle de calibration quantique
et un modèle de traduction dont les fiches ne listent aucun appel de fonction, puis, d'après leurs noms seulement, des
filtres de sécurité et de données personnelles, des modèles de recherche d'information et d'embeddings, un modèle CLIP,
un détecteur de vidéo et un modèle de complétion de code. Les modèles d'embeddings n'ont aucune route de discussion
à occuper.

#### Cent AI : un modèle gratuit jusqu'au 30 novembre, et ce qui suit est inconnu

Cent AI est un revendeur de modèles. LiteLLM n'a pas de fournisseur de ce nom : l'entrée `hy4-flash-cent-ai` s'écrit
`openai/hy4-flash:free` avec `api_base: https://api.cent-ai.dev/v1`, comme celles de Requesty, et le `:free` part chez
Cent AI avec le reste de l'identifiant. La clé (`Artificial_Intelligence_LiteLLM_Cent_AI_API_key`, de la forme `cai_...`)
arrive au conteneur sous le nom `CENT_AI_API_KEY`. Un appel réel a répondu le 2026-11-22, d'après l'essai du mainteneur ;
les appels d'outils à travers elle n'ont pas été essayés.

**Ce qu'on ignore : la suite du 30 novembre.** La page d'accueil de Cent AI (lue le 2026-11-22) annonce « Free until
Nov 30 · no daily limit » et ne dit rien de ce qui suit. Le catalogue liste le modèle à 0 $ ; il sera probablement
facturé à son tarif ensuite, ce qui n'est **pas vérifié**. Le mainteneur a décidé de le router maintenant et de
regarder de nouveau le 1er décembre. **À faire avant : donner à la clé une limite de dépense**, réglage de la page des
clés de Cent AI. Un appel facturé échoue alors au lieu de coûter, et la cascade passe au membre suivant : sans cette
limite, rien dans ce dépôt n'empêche une facture.

**Un seul modèle est routable.** Le site tire aussi chaque jour au hasard un modèle gratuit « événement », sous un
identifiant qui change tous les jours : il n'est pas routable, et aucune entrée ne le nomme.

**Les risques, que le mainteneur a acceptés.** L'opérateur est un particulier dont les conditions sont un brouillon ;
les requêtes sont relayées vers des fournisseurs qu'il ne nomme pas ; les prompts atteignent donc un tiers, et la
passerelle sert toutes les applications du homelab. Un seul compte.

**Ce modèle raisonne avant de répondre : ne pas plafonner `max_tokens` bas.** Avec 20, la réponse a été coupée
(`finish_reason` à `length`). Aucune entrée ne règle `max_tokens`, et un appel doit en laisser au moins 200.

**Où il est placé : en queue des gratuits de `Auto-Pro`, `Auto-Flash` et `Auto-Flash-Lite`, faute de chiffre.** C'est le Hy4 Flash de
Tencent d'après son nom seulement. Artificial Analysis n'a aucun enregistrement de ce nom (son seul enregistrement récent
de Tencent, « Tencent Hy4 », est un autre modèle), et ni l'indice de capacités ni les benchmarks de code d'Epoch AI ne le
contiennent (lus le 2026-11-21) : aucun chiffre ne le place, et les contrats de routeur le rangent « sans
enregistrement », comme `flint-kilo` ou `nemotron-bolt-e4b-nvidia`. Il ferme donc les gratuits à clé, derrière ceux qui
ont un chiffre ou un jumeau et devant ceux d'OVHcloud, sans en déplacer aucun. Il n'est ni dans `Auto-Code` ni dans
`Auto-Claude-Code` : ses appels d'outils ne sont pas essayés, et `Auto-Claude-Code` n'admet que des appels d'outils déclarés. Le
contrôle de dérive lit le catalogue de Cent AI : un modèle qui le quitte est supprimé.

#### Cloudflare Workers AI : deux valeurs, un seul compte, et un quota en neurons

Cloudflare est le seul fournisseur qui demande **deux valeurs** : le jeton d'API
(`Artificial_Intelligence_LiteLLM_Cloudflare_API_key`, lu par les entrées comme `os.environ/CLOUDFLARE_API_KEY`) et
l'identifiant du compte (`Artificial_Intelligence_LiteLLM_Cloudflare_account_ID`, exposé au conteneur comme
`CLOUDFLARE_ACCOUNT_ID`). L'adresse du point d'accès contient l'identifiant, et LiteLLM la construit lui-même depuis
cette variable d'environnement : aucune entrée n'écrit d'`api_base`, donc aucun identifiant ne figure dans ce dépôt. La seule exception est `bge-m3-cloudflare`, dont le fournisseur `cloudflare/` n'a pas de route d'embeddings : le rôle construit l'adresse depuis le même identifiant dans `CLOUDFLARE_EMBEDDINGS_API_BASE`, et l'entrée la lit en entier. Le
rôle refuse l'une des deux valeurs sans l'autre, et ne rend aucune entrée Cloudflare quand les deux sont vides. Le jeton
compte pour « au moins une des onze clés » et pour l'agent Claude Code, dont la cascade `Auto-Claude-Code` a un membre
Cloudflare.

**Un seul compte, et ce n'est pas un réglage.** Les conditions de Cloudflare (*Self-Serve Subscription Agreement*, lues
le 2026-11-22) interdisent d'utiliser le service « in a manner that violates or is intended to circumvent
Service-specific usage limits, quotas » : ouvrir un second compte pour doubler les 10 000 neurons quotidiens en est un.
Aucune entrée d'un second compte Cloudflare n'est donc prévue, alors que les autres fournisseurs savent en porter
plusieurs (clé suffixée par une étiquette).

**Où le quota compte.** Les 10 000 neurons par jour sont **un seul compteur pour tous les modèles Cloudflare du
compte**, remis à zéro à 00:00 UTC ; les 300 requêtes par minute du texte sont l'autre limite. Ce que 10 000 neurons
achètent se lit dans la table des tarifs, en prix par million de jetons rapporté en neurons (calcul : 10 000 divisé par
le prix en neurons par million de jetons ; l'un ou l'autre de l'entrée et de la sortie, jamais les deux à la fois) :

| Modèle routé | Jetons d'entrée par jour au plus | Jetons de sortie par jour au plus | Cascades |
| --- | --- | --- | --- |
| `gpt-oss-120b-cloudflare` | environ 314 000 | environ 147 000 | `Auto-Flash`, derrière `gpt-oss-120b-groq` |
| `gpt-oss-20b-cloudflare` | environ 550 000 | environ 367 000 | `Auto-Flash-Lite`, derrière `gpt-oss-20b-groq` |
| `gemma-4-26b-cloudflare` | environ 1 100 000 | environ 367 000 | `Auto-Flash-Lite`, derrière les deux autres sources |
| `llama-3-3-70b-cloudflare` | environ 375 000 | environ 49 000 | `Auto-Flash-Lite`, placé par son délai |
| `llama-4-scout-17b-16e-instruct-cloudflare` | environ 407 000 | environ 129 000 | `Auto-Flash-Lite`, placé par son délai |
| `qwen2-5-coder-32b-instruct-cloudflare` | environ 167 000 | environ 110 000 | `Auto-Flash-Lite`, parmi les derniers membres gratuits, faute de chiffre |
| `gemma-sea-lion-v4-27b-it-cloudflare` | environ 314 000 | environ 198 000 | `Auto-Flash-Lite`, parmi les derniers membres gratuits, faute de chiffre |
| `mistral-small-3-1-24b-instruct-cloudflare` | environ 313 000 | environ 198 000 | `Auto-Flash-Lite`, parmi les derniers membres gratuits, faute de chiffre |
| `llama-3-2-11b-vision-instruct-cloudflare` | environ 2 245 000 | environ 163 000 | `Auto-Flash-Lite`, parmi les derniers membres gratuits, faute de chiffre ; licence de Meta à accepter une fois sur le compte |
| `granite-4-0-h-micro-cloudflare` | environ 6 471 000 | environ 982 000 | `Auto-Flash-Lite`, parmi les derniers membres gratuits, faute de chiffre |
| `qwen3-8-27b-cloudflare` | environ 244 000 | environ 34 000 | `Auto-Flash`, `Auto-Code` et `Auto-Claude-Code`, derrière ses jumeaux de Groq et d'OVHcloud ; réfléchit en Xhigh par défaut, ce qui use vite la sortie |
| `glm-4-7-flash-cloudflare` | environ 1 818 000 | environ 275 000 | `Auto-Code` et `Auto-Claude-Code`, dernier membre gratuit |

Un agent qui renvoie son historique à chaque requête use l'entrée très vite : à 50 000 jetons de contexte par requête,
le quota d'une journée fait environ 36 requêtes de `glm-4-7-flash-cloudflare` et 6 de `gpt-oss-120b-cloudflare`, sorties
non comptées. C'est pourquoi chaque modèle Cloudflare est placé **derrière** les autres sources du même modèle, ou en
queue des membres gratuits pour les modèles qu'aucun autre fournisseur ne sert ici : la cascade n'y arrive que quand les
autres ont échoué. Les raisonneurs (`gpt-oss`, `glm-4-7-flash`) dépensent en plus des jetons de sortie pour raisonner.
Les modèles placés sont **déduits gratuits** (la page des tarifs nomme ceux qui exigent un moyen de paiement, et ils
n'en font pas partie) et **à confirmer sur le compte** : le tableau de bord Cloudflare montre les neurons consommés.

#### Z AI : une clé, des limites inconnues, et la fin des cascades `Auto-Code` et `Auto-Claude-Code`

Z AI (Zhipu) est un fournisseur natif de LiteLLM (préfixe `zai/`) : la clé
(`Artificial_Intelligence_LiteLLM_Zai_API_key`) arrive aux entrées comme `os.environ/ZAI_API_KEY`, et aucune entrée
n'écrit d'`api_base`. Le code de LiteLLM, lu le 2026-11-22, appelle de lui-même le point d'accès **général** de Z AI ;
l'autre, celui du « coding plan », que la page « Introduction » de sa documentation réserve aux outils officiellement
pris en charge, n'est donc jamais atteint par ce fichier. Laquelle des deux adresses sert les modèles gratuits n'est
dite par aucune page lue, et la clé n'a pas été essayée contre elle : **à confirmer au premier appel**.

Un seul modèle est routé : `glm-4-7-flash-zai` (`zai/glm-4.7-flash`), en queue des membres gratuits de `Auto-Code` et de
`Auto-Claude-Code`, devant les payants. La table de modèles de LiteLLM lui donne 200 000 jetons de contexte, les appels
d'outils et le choix d'outil, et un prix nul ; la page « GLM-4.7 » de la documentation de Z AI donne le même contexte et
liste les appels de fonction pour toute la famille, sans le dire par modèle. Il remplit donc les deux conditions de
`Auto-Claude-Code` (appels d'outils, 128 000 jetons au moins) **d'après ces deux sources, sans essai réel**. Ni Artificial
Analysis ni Epoch AI ne lui donnent de chiffre (lu le 2026-11-21) : rien ne le classe face aux membres qui le précèdent,
et la fin des gratuits est la place d'un modèle non mesuré. C'est un modèle qui raisonne : Artificial Analysis mesure
environ 25 secondes avant le premier jeton de réponse pour sa fiche « Reasoning », d'où cette place.

Les deux autres modèles gratuits de la page des tarifs ne sont pas routés. **GLM-4.5-Flash** vient du même compte et de
la même limite non publiée que GLM-4.7-Flash : une place derrière lui ne s'essaierait que quand le premier a échoué pour
une raison qu'il partage, et aucun des deux classements ne le mesure. **GLM-4.6V-Flash** est un modèle de vision, absent
de la table de LiteLLM, et aucune page lue ne donne son contexte ni ses outils.

**Les limites ne sont pas connues.** Z AI ne les publie pas hors de la console du compte (la page de documentation qui les
annonçait répond 404, celle des limites est une coquille d'application) : ni requêtes par minute, ni jetons, ni
simultanéité. Une limite d'une requête simultanée, citée par un tiers, n'est **pas vérifiée**. Elles se lisent dans la
console du compte, et ce dépôt n'en affirme aucune. Les conditions (« Terms of Use », mises à jour le 2026-04-14)
interdisent de partager ou de divulguer ses clés, et n'ont rien donné sur une passerelle ou sur plusieurs comptes : la clé
est celle du compte de la passerelle, et aucune autre n'est prévue. Le contenu des clients de l'API n'est pas utilisé pour
améliorer les services sans accord (article IV.7), l'accord de traitement des données dit qu'il n'est pas stocké, et le
traitement se fait en général à Singapour. Une carte ou un téléphone exigé à l'inscription, une date d'arrêt des modèles gratuits :
aucune page lue n'en parle.

### Chaque jour : une pull request pour ce qui se supprime, deux pour ce qui s'ajoute, une issue pour un catalogue illisible

La règle du `model_list` ne se tient pas seule : les fournisseurs retirent et publient des modèles
sans prévenir ce fichier. `check_LiteLLM_model_drift.py` en tient la moitié qui se lit dans le
fichier à chaque pull request, en le lisant **rendu** par Jinja2 seul, toutes les clés de
fournisseur données (il lui faut PyYAML et Jinja2, épinglés dans `requirements.txt`) -- chaque place
de cascade et chaque alias nomment une entrée active, aucun nom n'est déclaré deux fois, chaque entrée
commentée dit au-dessus d'elle qu'elle est « not routed », et pourquoi. L'autre moitié,
`.github/workflows/LiteLLM_model_drift.yml` la lit chaque jour à 07:17 UTC (8 h 17 à Paris en hiver,
9 h 17 en été) dans le catalogue des fournisseurs. Chaque jour, pour qu'un modèle qu'un fournisseur
publie ou retire attende au plus un jour avant qu'une pull request le propose ou le supprime ; à 07:17
parce que ce n'est pas le haut de l'heure, quand tous les workflows planifiés de GitHub démarrent en
même temps, et que ce qu'il propose est prêt avant l'usage de la pile (de 17 h à 22 h en semaine, de
10 h à 22 h le week-end et les jours fériés).

Le rapport entier, section « Contrats par routeur » comprise, va dans le **résumé du run** (l'onglet
*Summary* de l'exécution), qui ne notifie personne. Le résumé donne aussi, dans une section à part, les
entrées actives dont la fiche (`max_input_tokens`, `max_output_tokens`, `supports_vision`) dit autre chose
que le catalogue de leur fournisseur, quand ce catalogue publie le champ : rien n'en est modifié, et une
personne corrige la fiche à la main. Ce qu'une personne doit lire va dans le corps de la pull request qu'il
concerne, assignée à tigerblue77 : les retraits annoncés dans celle des
suppressions, les modèles redevenus gratuits sur OpenRouter dans celle des modèles prêts (dans celle
des modèles à vérifier quand la première n'est pas ouverte), et les nouveaux modèles qu'aucun ajout ne
peut porter -- un identifiant d'une autre forme, un fournisseur sans entrée, au-delà du plafond, un
corps trop long --, avec leur entrée à compléter et la raison, dans celle des modèles à vérifier. Une
exécution sans pull request pour le porter, cela n'est que dans le résumé.

**Une issue, et pour une seule chose : un catalogue qui reste illisible.** Un catalogue qui ne se lit
pas (une erreur HTTP, pas de réponse, une réponse illisible) est relu le même jour à 09:17, 11:17 et
13:17 UTC ; une reprise ne refait le run que si la tentative d'avant n'a pas pu lire un catalogue, et
se termine sinon en quelques secondes sans rien faire. Si la quatrième tentative ne le lit toujours
pas, le workflow ouvre l'issue « Catalogue de fournisseur illisible pour la liste de modèles LiteLLM »,
assignée à tigerblue77, ou rouvre la même, avec les fournisseurs, la classe de leur statut HTTP (jamais
une clé ni une réponse) et l'heure des trois tentatives précédentes ; la première exécution qui lit
chaque catalogue la ferme. Une clé absente n'est pas un échec de lecture : le résumé dit le fournisseur
« non couvert ». Une exécution lancée à la main est une seule tentative : elle peut fermer l'issue,
jamais l'ouvrir. D'une tentative à l'autre, rien n'est gardé que GitHub ne garde déjà : le numéro de la
tentative est la place de la planification qui l'a lancée, et ce qu'a donné la précédente est le nom
d'un artefact de son run, lu par un job sans clé et au jeton en lecture seule.

Une seule sorte de constat se traite sans jugement, et le workflow la traite lui-même, **sans IA** :
un modèle que son fournisseur ne liste plus (et, chez ceux dont l'API sait répondre pour un modèle
donné, qui répond à son tour qu'il n'existe pas : une liste peut omettre un modèle encore servi).
`check_LiteLLM_model_drift.py --online --apply` le supprime du `model_list` avec ses places dans les quatre listes de repli, et avec la raison écrite
au-dessus quand elle ne motivait que lui (une raison partagée avec une entrée qui reste est
conservée). Le workflow en fait **une seule pull request**, sur la branche
`claude/LiteLLM-model-drift-removals`, assignée à tigerblue77 : son corps cite, pour chaque
suppression, le fournisseur, l'identifiant, le catalogue lu et la date. Elle est ouverte avec le jeton
d'une App GitHub quand le dépôt en configure une (voir plus bas), et GitHub en lance alors lui-même les
contrôles, `sign-off` compris ; sans App, le workflow écrit avec son propre jeton, qui ne déclenche rien,
et relance lui-même `ansible-ci.yml` et `gitleaks.yml` sur la branche, mais les runs de la pull request
attendent l'approbation d'une personne et la fusion aussi. Elle est réécrite à chaque exécution qui trouve quelque chose à
supprimer (titre et corps compris : une modification à la main est perdue), et fermée avec un commentaire quand plus rien ne se supprime --
sauf si un fournisseur n'a pas pu être lu ou n'a pas de clé, ou si un modèle retiré n'a pas pu être
supprimé, car « rien à supprimer » voudrait alors dire « rien vu » ou « rien que je puisse
supprimer ».

**Elle se fusionne seule, à des conditions qui tiennent toutes à ce que GitHub dit d'elle** et à rien
de ce que le workflow y a écrit, sauf une : `.github/workflows/dependabot-auto-merge.yml`, le même qui
fusionne les mises à jour de Dependabot, la fusionne quand elle est ouverte par le bot Actions ou par
l'App du workflow (dont la variable `MODEL_DRIFT_APP_SLUG` donne le nom) et porte un seul commit, celui
du bot Actions dans les deux cas ; qu'elle ne touche que le modèle de configuration et n'y ajoute aucune ligne ; que les
lignes qu'elle retire sont, une à une, des entrées de modèle entières, les places de cascade qui
nomment une entrée retirée dans la même pull request, des commentaires ou des lignes vides, et rien
d'autre (un réglage, une adresse ou le modèle d'une entrée qui reste n'en sont pas) ; qu'elle
supprime une entrée au moins et cinq au plus (les entrées commentées comptent), en deux cents lignes
au plus ; que son corps n'a pas de section « À relire » (voir plus bas) ; que sa branche contient
tout `main`, faute de quoi les contrôles n'ont pas tourné sur l'arbre qui serait fusionné ; et que
chaque contrôle que le jeu de règles nomme est vert sur son dernier commit. Le contrôle `sign-off`
n'est pas attendu s'il n'a pas démarré : il lit les commits d'une pull request que GitHub ne lance
jamais pour une pull request ouverte avec le jeton du workflow (il le lance pour celle de l'App, et il
doit alors être vert), et il certifie le droit de soumettre ce qu'un commit ajoute, ce que celui-ci ne
fait pas. Une pull request qui sort de ces conditions
reste ouverte et attend tigerblue77, comme avant ; les deux plafonds sont `REMOVALS_MAX_ENTRIES` et
`REMOVALS_MAX_LINES` dans le workflow de fusion, et `check_auto_merge_gate.py` joue ces conditions
contre des pull requests inventées : celles qui doivent fusionner et, une à une, celles qui ne le
doivent pas.

**Un commit de quelqu'un d'autre sur la branche arrête tout, et l'exécution échoue pour le dire**,
chaque jour, jusqu'à ce que la branche soit supprimée (le workflow la refait alors depuis
`main`) : écraser le travail d'une personne, ou fermer ce sur quoi elle travaille, est la seule chose
qu'une tâche planifiée ne doit pas faire. Un commit de fusion, comme celui du bouton
« Update branch », n'est le travail de personne : le workflow reconstruit la branche sans lui. Le
commit d'une personne qu'une fusion « squash » ou « rebase » de la pull request n'a pas fait entrer
dans l'historique de `main` continue de compter, tant que la branche n'est pas supprimée.

Quand une suppression retire le premier modèle d'un fournisseur dans la table `head`, la pull request **ajoute** des
lignes (les lignes de la table, réécrites) : elle ne se fusionne pas seule, une personne relit ces lignes, que le corps
de la pull request liste. Le job qui pousse, seul à détenir un jeton qui écrit, n'accepte une ligne changée que sous
cette forme, et seulement avec des noms d'entrées du fichier et des fournisseurs que le modèle déclare
(`check_drift_publish_guard.py` joue cette règle).

Ce que le workflow ne supprime pas est listé, avec la raison, dans la pull request des suppressions et
dans le résumé du run, et la liste complète en est
dans la docstring de `check_LiteLLM_model_drift.py` (« DELETING WHAT A PROVIDER HAS RETIRED ») : un
routeur virtuel (`Auto-Pro`, `Auto-Flash`...), un modèle qu'un alias désigne, la dernière cible d'une cascade (pour chaque jeu de clés de fournisseur,
pas sur leur union), un modèle que le modèle de configuration nomme dans une instruction Jinja (rien ici ne sait
modifier ce qu'une instruction calcule, hors les lignes de la table `head`, qui dit quel modèle un routeur désigne et
que l'outil réécrit à partir des cascades quand elles redonnent exactement la table telle qu'elle est), un fichier dont la lecture sans rendu ne donne pas les mêmes entrées que son
rendu (un `else`, une boucle qui répète une entrée), un catalogue vide ou qui omet plus de la
moitié des identifiants du fichier pour son fournisseur, à partir de trois (une réponse tronquée ressemble à un retrait
massif), et tout ce dont le résultat, relu, n'est pas le fichier d'origine moins la suppression.
Les instructions Jinja qui entourent une entrée supprimée restent : le bloc d'un fournisseur dont
la dernière entrée part est laissé vide, et le rendu n'en change pas.

Aucun commentaire n'est réécrit, et la relecture du résultat porte sur la structure du fichier, pas
sur sa prose : la pull request liste donc, sous « À relire », ce qu'une suppression a pu rendre faux
-- le commentaire au-dessus d'une entrée active supprimée, la raison gardée au-dessus des entrées
commentées qui restent d'un groupe dont certaines sont parties (elle peut les compter), l'en-tête
d'une section restée sans entrée, et toute ligne de commentaire qui cite un nom ou un identifiant
supprimé. Une pull request qui a cette section ne se fusionne pas seule : c'est ce qui laisse à une
personne de quoi relire, et la moitié environ des suppressions n'en laissent aucune. Elles partent,
elles, sans que personne n'ait rien à faire.

Tout le reste se décide à la main, et c'est voulu : ajouter un modèle est un choix (gratuit ? dans
quelle cascade, à quel rang ?), un retrait seulement annoncé n'en est pas encore un, un modèle
redevenu gratuit rouvre une raison que quelqu'un a écrite -- et la règle veut que chaque affirmation
de la liste cite la page du fournisseur et la date de la vérification. Un modèle examiné et écarté
cesse d'être signalé par une ligne `# drift-ignore: <fournisseur>/<id> -- <raison>` dans le fichier.

**Un retrait annoncé a deux sources, et l'une vérifie l'autre.** Beaucoup de fournisseurs n'annoncent
rien dans leur API (celle de Google ne publie aucune dépréciation), alors que la carte des prix publique
de LiteLLM (`model_prices_and_context_window.json`, dans son dépôt GitHub) porte une `deprecation_date`
pour les modèles qu'elle sait condamnés. Le contrôle lit cette carte une fois par run, sans clé et sans
jamais appeler un modèle, et rapproche pour chaque entrée, active ou commentée, le signal du fournisseur
et la date de la carte. Les deux se taisent : rien. Une seule des deux sources annonce (l'autre se tait
ou ne connaît pas le modèle) : le retrait est annoncé, et la ligne dit laquelle l'a dit. Les deux
annoncent le même jour : une alerte qui cite les deux. Elles se contredisent (deux jours différents, ou
le fournisseur qui indique le modèle actif, `active: true` chez Groq ou `deprecated: false` chez
Cerebras, SambaNova et Cloudflare, contre une date de la carte) : la plus proche est retenue, et un
**avertissement** nomme les deux sources et ce que chacune dit, dans le résumé et dans le corps de la
pull request des suppressions. Une date dépassée alors que le fournisseur liste toujours le modèle reste
une alerte, qui le dit. La carte ne supprime jamais rien : la suppression ne dépend que du catalogue du
fournisseur, et une carte illisible est l'erreur de cette source seule, dite dans le résumé, sans effet
sur les suppressions, les reprises ni l'issue, et sans cacher ce que les fournisseurs annoncent
eux-mêmes. Les entrées que LiteLLM atteint par `openai/<id>` chez Kilo Gateway, Requesty, Cent AI et
Aion Labs n'ont pas de clé dans la carte et ne sont pas rapprochées.

**Les nouveaux modèles de tous les usages sont signalés, chacun avec son usage.** Aucun filtre n'écarte un
modèle parce qu'il sert à autre chose que le chat : un nouveau modèle de transcription, de synthèse
vocale, d'embeddings, d'image ou de modération est listé comme les autres, dans les mêmes sections
(« Nouveaux modèles gratuits » ou « à examiner », selon que l'API du fournisseur dit la gratuité ou non), et
sa ligne dit son usage. L'usage vient du catalogue quand il le dit (la tâche chez Cloudflare, les
modalités de sortie chez OpenRouter et Kilo Gateway, les méthodes chez Gemini, `completion_chat` chez
Mistral) et de l'identifiant sinon (`USAGE_MARKERS` dans `check_LiteLLM_model_drift.py`) ; un modèle
que ni l'un ni l'autre ne classe est dit « unclassified ». Seul un modèle de chat va plus loin : le
classement d'Artificial Analysis, les pull requests d'ajout et l'entrée à coller ne portent que lui.
L'entrée des autres usages s'écrit à la main, et la ligne donne le `model_info.mode` qu'elle demande
quand le fichier en a un (`audio_transcription`, `audio_speech`, `embedding`).

**Les ajouts arrivent en deux pull requests, qu'aucune fusion automatique ne prend.** Le workflow les
tient à jour comme celle des suppressions (`main` plus un commit du bot Actions, refaite à chaque
exécution, écrite avec le jeton de l'App quand il y en a une, assignée à tigerblue77), chacune sur sa
branche, et `dependabot-auto-merge.yml`, qui ne reconnaît que la branche des suppressions, ne fusionne
ni l'une ni l'autre (`check_auto_merge_gate.py` joue les deux branches contre lui). Elles se partagent
les modèles selon ce que l'exécution sait d'eux, jamais selon leur fournisseur :

- **`claude/LiteLLM-model-additions`, les modèles prêts** : ceux dont l'exécution tient toutes les
  informations qu'un ajout demande -- une gratuité que l'API du fournisseur dit elle-même (aujourd'hui
  les modèles `:free` d'OpenRouter à 0 $ et les modèles `isFree` de Kilo Gateway) et un chiffre du classement
  d'Artificial Analysis rapproché de façon sûre : la fin de l'identifiant, sans `:free`, s'écrit à la
  casse et à la ponctuation près comme le slug ou le nom d'une seule entrée du classement, qui ne porte
  aucune marque de variante entre parenthèses (« (Reasoning) », « (Xhigh) »...). Un fournisseur dont la
  gratuité deviendrait lisible dans son API y arriverait sans que la règle change ;
- **`claude/LiteLLM-model-additions-to-verify`, les modèles à vérifier, en brouillon** : tous ceux à qui
  il manque au moins une de ces informations, quel que soit leur fournisseur -- une gratuité que l'API
  ne dit pas (tous les fournisseurs autres qu'OpenRouter aujourd'hui), aucun chiffre du classement, un
  rapprochement approximatif ou ambigu. Son corps dit, pour chaque modèle, ce qui manque et comment
  l'obtenir : la page de tarifs à ouvrir et ce qu'il faut y chercher, l'endroit du classement où le
  chercher, une commande qui lit le modèle dans le catalogue du fournisseur sans rien afficher de
  secret (celles qui demandent une clé se lancent en root sur la machine qui fait tourner la pile, et
  lisent la clé dans le conteneur LiteLLM), le commentaire daté à écrire au-dessus de l'entrée, et la
  ligne `drift-ignore` toute prête si la réponse est non. Là où GitHub refuse un brouillon, comme sur
  un dépôt privé de son plan gratuit, elle est ouverte prête à relire, et son corps seul dit d'attendre.

Le commit ajoute chaque entrée après la dernière entrée de son fournisseur (la dernière active, sinon la
dernière commentée), dont elle reprend la clé et l'`api_base`, sous un commentaire qui dit d'où elle
vient et quand ; elle est commentée, avec une raison provisoire, chez un fournisseur qui n'a aucune
entrée active. Ni l'une ni l'autre ne la met dans une cascade : le corps donne ses chiffres et sa place
suggérée dans chaque routeur (voir le classement ci-dessous), une suggestion calculée sur un classement
lui-même en révision, et un modèle que le classement ne mesure pas n'est pas placé, mais nommé avec la
ligne `drift-ignore` qui l'écarte. Pour **garder** un modèle, on fusionne,
après avoir ajouté, dans un commit sur la branche, son nom aux cascades voulues ; pour l'**écarter**, on
remplace son entrée par sa ligne `drift-ignore` avant de fusionner. Un modèle fusionné ou écarté ne
revient plus ; fermer sans fusionner ne décide rien, la pull request revient le lendemain. Un
commit d'une personne fige la branche : tant que sa pull request est ouverte, le workflow n'y touche
plus, sans échouer ; une fois qu'elle est fermée sans être fusionnée, l'exécution échoue jusqu'à ce que
la branche soit supprimée. Une case cochée dans le corps reste cochée tant que sa ligne ne change pas, et
une exécution qui ne change que les dates des commentaires ne pousse rien (aucun contrôle ne repart) : chaque
entrée garde le jour où elle a été proposée.
Chacune se ferme, avec un commentaire, quand plus rien n'est à proposer, sauf si une source dont elle
dépend (un catalogue, ou le classement pour celle des modèles prêts) n'a pas pu être lue. Le job qui écrit ne reçoit, par modèle, qu'un fournisseur, un identifiant et un
nom, qu'il valide, et construit lui-même le fichier ; il ne pousse que si c'est le texte que le script
a construit et relu (`check_drift_publish_guard.py` tient les deux au même résultat).

**Le classement des nouveaux modèles.** Où placer un nouveau modèle dans une cascade se décide sur des
chiffres que quelqu'un allait chercher à la main : avec le secret `MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY`,
les pull requests d'ajout (et le résumé du run, pour un nouveau modèle qu'aucune ne porte) donnent pour chaque nouveau
modèle son indice d'intelligence, son indice de code, sa vitesse de sortie et son prix mixte, lus dans l'API
gratuite d'Artificial Analysis (<https://artificialanalysis.ai/>, la source est citée avec le jour de la lecture,
comme ses conditions d'utilisation le demandent), puis
une **place suggérée** par routeur : avant le premier membre de la cascade que le classement note plus bas sur le
chiffre qui compte (intelligence pour `Auto-Pro`, `Auto-Flash` et `Auto-Claude-Code`, code pour `Auto-Code`, vitesse pour
`Auto-Flash-Lite`), sinon après le dernier. Pour `Auto-Flash` et `Auto-Flash-Lite`, dont la cascade est choisie pour sa
rapidité, un modèle plus lent que le plus lent des membres dont la vitesse est connue n'a pas de place
suggérée, et un modèle dont la vitesse est inconnue est dit « pas évalué » ; une vitesse de 0 est lue comme
non mesurée (déduit des réponses observées : l'API ne documente pas ce qu'elle envoie dans ce cas). Ce n'est
qu'une suggestion, que rien n'applique : elle ne juge pas le reste de l'éligibilité (appels d'outils et contexte
pour `Auto-Claude-Code`, gratuité, variante d'effort de raisonnement sur laquelle un rapprochement peut tomber),
ni le regroupement par fournisseur que la cascade garde aussi. Le rapprochement entre l'identifiant du fournisseur et le nom du classement est une
**supposition** -- l'identifiant, puis le nom du fournisseur, doivent s'écrire comme exactement une entrée du
classement, à la casse et à la ponctuation près, au moins quatre caractères -- et chaque ligne est marquée
« à vérifier ». Sans le secret, le résumé dit « non couvert » comme pour n'importe quelle clé, et aucun modèle n'est placé ;
une lecture qui échoue est signalée et ne change ni le statut du run, ni ce qui est supprimé. Les réponses simulées du test
suivent la forme que documente l'API (aucune clé n'était disponible pour en enregistrer une vraie).

**Où chaque modèle est placé, à quel niveau de réflexion et pourquoi** : `ROUTAGE.md`, à la racine, écrit à la main. Il dit les
règles en mots simples (le niveau que garde chaque routeur, le classement de `Auto-Flash-Lite` par indice moins délai pondéré, la
règle du quota partagé, les limites gratuites de Google), puis, par routeur, l'ordre de la cascade avec le niveau fixé de
chaque entrée, et les points ouverts. Seuls l'ordre des membres et les niveaux fixés y sont tenus au gabarit, par
`check_routing_document.py`, qui échoue sinon ; les tableaux ne sont pas recopiés ici.

**Les contrats par routeur.** `.github/LiteLLM_router_contracts.yaml` dit ce que chaque routeur exige : un plancher,
écrit comme une ancre (« au moins aussi bon que tel modèle », dont le chiffre est lu à chaque exécution et jamais copié
dans le fichier), sur l'une de deux échelles, ou aucun plancher. Sur l'indice d'intelligence (plus il est grand,
meilleur c'est), l'ancre nomme soit une entrée du modèle de configuration, lue dans le classement d'Artificial Analysis,
soit un modèle de l'indice de capacités d'Epoch AI. Sur l'échelle de code (plus la position est petite, meilleur c'est),
qui est celle de `Auto-Code` et de `Auto-Claude-Code`, l'ancre nomme les versions de modèle des benchmarks d'Epoch AI qui
représentent un modèle (`code_epoch`). Un plancher sur l'indice peut porter une `margin`, en points d'indice (0 si elle
est omise) : un membre est conforme tant que son chiffre n'est pas plus de la marge sous le plancher, et le rapport dit
la marge partout où il dit le plancher. Le fichier dit aussi le gain d'indice qu'un niveau de raisonnement de plus doit
apporter pour valoir qu'on y monte (`min_points_per_second`), la façon d'ordonner les membres, les membres exemptés du
plancher à dessein (le « dernier recours »), et, pour chaque entrée du modèle de configuration, l'enregistrement
d'Artificial Analysis qui la décrit au niveau de raisonnement où elle est appelée, avec la page du fournisseur qui donne
ce niveau, ou « unknown ». **Il n'y a aucun budget de temps** : le but est d'utiliser au maximum les modèles gratuits,
un modèle lent n'est donc jamais écarté parce qu'il est lent. L'éligibilité tient au plancher (et aux appels d'outils
pour `Auto-Claude-Code`) ; le délai moyen avant le premier jeton de la réponse ne sert qu'à ordonner : `Auto-Flash-Lite` classe ses
membres par leur indice moins `min_points_per_second` fois ce délai (les membres sans indice après ceux qui ont les deux,
le plus rapide d'abord, et ceux qui partagent leur quota avec un membre de `Auto-Pro` ou de `Auto-Flash` après tous les autres), les
autres routeurs la meilleure qualité, et le délai départage deux membres dont la qualité diffère de moins de la marge du
routeur (`tie_margin_points`). L'unité de routage est « modèle + niveau » : on monte les niveaux
d'un modèle depuis le plus bas, et on passe au suivant tant qu'il apporte au moins `min_points_per_second` points
d'indice par seconde de plus (un routeur qui tient au temps en demande plus). `Auto-Claude-Code` dérive de `Auto-Code` (même
classement, sa cascade est celle de `Auto-Code` sans les membres qui ne prennent pas d'outils). `Auto-Code` se classe sur la
**position de code**, lue par l'exécution en ligne dans les données d'Epoch AI (`benchmark_data.zip`,
<https://epoch.ai/benchmarks>, CC BY 4.0, citées dans le résumé avec le jour de la lecture), sans WebDev Arena : la
qualité d'une interface web est du design, pas du code. Dans chacun de cinq benchmarks (DeepSWE, SWE-bench Verified,
CursorBench, Terminal-Bench, ALE-Bench), la position d'un score est (1 + le nombre de modèles du fichier dont le score
est strictement meilleur) / le nombre de modèles du fichier, en pourcentage : plus elle est petite, meilleur est le
modèle, et les variantes d'effort d'un modèle comptent chacune pour un modèle. La position d'un membre dans un benchmark
est celle du meilleur score parmi les versions que son entrée y liste, et sa position de code est la médiane de ses
positions, sur deux benchmarks au moins, sinon il n'en a pas ; elle ne dépend d'aucune cascade. Un membre qui n'a pas de
position de code mais a un indice d'intelligence (celui du classement, ou l'estimation tirée de l'indice de capacités)
reçoit une position **estimée**, par la conversion que déclare le fichier (`code_fallback` : des points indice-position
reliés par des segments, bornés aux deux bouts sans extrapolation), marquée « estimé » partout, jugée contre le plancher
comme les autres et sans délai propre ; un membre qui n'a ni l'un ni l'autre reste où il est, signalé inclassable. Les
membres qui ont une position viennent en premier, la plus petite en tête, le délai départageant deux membres dont les
positions diffèrent de moins de `tie_margin_points` (un membre estimé n'a pas de délai et passe après), et le dernier
recours et les membres sous le plancher restent en queue. Une lecture qui échoue est signalée « non lue » dans la
section : le plancher de `Auto-Code` est alors introuvable et ne juge personne, et l'indice d'intelligence ordonne toute la
cascade ; l'exécution hors ligne ne lit rien. L'**indice de capacités** d'Epoch AI (ECI) est lu dans la même archive (le
membre `epoch_capabilities_index/eci_scores.csv`, mêmes plafonds, même liste de noms permis, même citation) : il couvre
presque tous les modèles qu'Artificial Analysis n'a pas notés, et le fichier dit comment le ramener à l'échelle de
l'indice d'intelligence (des points de calibration reliés par une droite, prolongée au-delà de ses extrémités par la
pente du dernier segment et jamais sous 0). Tout chiffre ainsi obtenu est une **estimation**, marquée « estimé »
partout. Les planchers de `Auto-Pro` et de `Auto-Flash` y sont ancrés : `Auto-Pro` doit être au moins aussi bon que Gemini 3 Pro et
`Auto-Flash` que Gemini 2.5 Flash, avec une marge de 2 points, parce que l'indice ne donne qu'un chiffre par modèle, avec un
intervalle d'environ deux points, si bien qu'un modèle à moins de cette marge du plancher ne s'en distingue pas. `Auto-Code`
et `Auto-Claude-Code` ont pour plancher la position de code de Gemini 2.5 Flash, sans marge, et `Auto-Flash-Lite` n'a aucun
plancher (tout membre qui répond est admis, et l'indice moins le délai pondéré ordonne). Un membre pour lequel
le classement n'a pas d'indice au niveau où il est appelé est placé sur l'estimation du modèle que nomme son entrée
(`eci`) ; l'indice du classement l'emporte partout où il existe, et un routeur qui tient au temps n'utilise aucune
estimation. Si l'archive ou l'indice n'est pas lu, une ancre sur l'indice est introuvable, ne juge personne, et le résumé
le dit ; un nom que l'indice ne contient plus est listé comme périmé, sans jamais être un échec. Le mainteneur a
**validé** le fichier le 2026-11-22 (son champ `status`) ; le quota et la disponibilité des fournisseurs y restent
déclarés sans rien imposer. Le résumé de chaque run porte une section « Contrats par routeur » : par routeur, un tableau
des membres (chiffres, niveau appelé, niveau retenu, verdict), l'ordre que le contrat donnerait comparé à l'ordre
actuel, pour `Auto-Code` et `Auto-Claude-Code` la position de chaque membre dans chaque benchmark et sa position de code (« 18 %
», ou « 56 % (estimé) »), l'effet de chaque plancher proposé (un membre sous le plancher passe au dernier recours, il
n'est pas retiré), puis les entrées sans correspondance, celles sans enregistrement, les correspondances dont
l'enregistrement a disparu et celles appelées à un niveau que le classement ne couvre pas. C'est un rapport : il ne
change aucune cascade, aucune entrée, aucune ligne `head`, ne retire aucun membre (un membre sans indice ni position
reste où il est, signalé inclassable, tant qu'aucune estimation ne le couvre), ne change pas le statut du run et ne
bloque pas la pull request de suppression. Seule l'exécution hors ligne, celle de la CI, échoue, et seulement sur la
forme du fichier (un routeur qui n'existe pas, un nombre qui n'en est pas un, une valeur sans raison, une ancre mal
formée ou un plancher sur deux échelles, une conversion de l'indice en position qui ne va pas dans le bon sens, une
ligne ou un fichier mal formé, une clé écrite deux fois). Un nom que le fichier garde et qui n'est plus une entrée du
modèle n'est **pas** un échec : la suppression se fusionne seule quand la CI est verte, et supprimer une
entrée met presque toujours une ligne dans ce cas. L'exécution hors ligne affiche alors une ligne d'avis et sort en 0,
et le résumé liste ces « correspondances sans entrée », qu'une personne retire du fichier.

**Une condition, une seule fois**, tant que le workflow écrit avec son propre jeton (pas d'App
configurée, voir plus bas) : cocher *Allow GitHub Actions to create and approve pull requests*
dans *Settings → Actions → General → Workflow permissions*
(<https://github.com/Dragnix-Tigerblue77/AI-Docker-stack-Ansible-deployment/settings/actions>), ou,
si la case est grisée, le même réglage au niveau de l'organisation. Tant qu'elle ne l'est pas, le
workflow pousse les branches, écrit son résumé et échoue à l'étape qui ouvre les pull requests, en
nommant ce réglage et en donnant son lien.

**Facultatif : une App GitHub qui ouvre les pull requests.** Un push et une pull request faits avec le jeton
du workflow ne lancent aucun workflow : GitHub garde les runs de la pull request jusqu'à ce qu'une
personne les approuve, ne lance jamais `sign-off`, et n'avertit pas `dependabot-auto-merge.yml` d'un run
que ce jeton a lancé à la main, qui ne voit alors jamais la pull request. Avec une App, les branches et les
pull requests (celle des suppressions comme celles des ajouts) sont écrites avec son jeton, restreint à
*Contents* et *Pull requests* en lecture et écriture (l'assignation, qui est celle d'une issue, se fait
avec le jeton du workflow) : GitHub lance lui-même les contrôles, la fusion automatique les voit (et ne
prend que celle des suppressions), et le workflow n'en relance plus aucun à la main.
Pour l'activer : une App GitHub installée sur ce dépôt avec ces deux permissions de dépôt, la variable
`MODEL_DRIFT_APP_CLIENT_ID` (l'identifiant client affiché sur la page de l'App, pas son identifiant
d'App), la variable `MODEL_DRIFT_APP_SLUG` (son nom court, que seule la
fusion automatique lit) et le secret `MODEL_DRIFT_APP_PRIVATE_KEY`. Sans la première variable, le workflow
fait ce qu'il faisait avant. La clé privée n'atteint que `publish`, qui n'extrait rien du dépôt et n'y
exécute aucun script ; l'issue des catalogues illisibles garde le jeton du workflow.

**Tout fournisseur que le `model_list` route est lu**, un fournisseur à clé compris, et le mode hors ligne du
contrôle échoue sur une entrée active d'un fournisseur qu'aucune lecture ne couvre, en la nommant : un modèle que
l'un d'eux retire ne reste donc jamais inaperçu. Seules les routes virtuelles d'OmniRoute (`openai/auto/...`,
choisies par la machine elle-même et listées par aucun catalogue) et le routeur `Auto`, qui n'appelle que
d'autres routeurs, en sont exemptés.

| Fournisseur | Catalogue lu | Secret | Ce que l'API dit de la gratuité |
| --- | --- | --- | --- |
| OpenRouter | `openrouter.ai/api/v1/models` | aucun | `:free` et un prix de 0 |
| Cerebras | `api.cerebras.ai/public/v1/models` | aucun | rien |
| SambaNova | `api.sambanova.ai/v1/models` | aucun | rien |
| Gemini | `generativelanguage.googleapis.com/v1beta/models` | `MODEL_DRIFT_GEMINI_API_KEY` | rien |
| Groq | `api.groq.com/openai/v1/models` | `MODEL_DRIFT_GROQ_API_KEY` | rien |
| Mistral | `api.mistral.ai/v1/models` | `MODEL_DRIFT_MISTRAL_API_KEY` | rien |
| DeepSeek | `api.deepseek.com/models` | `MODEL_DRIFT_DEEPSEEK_API_KEY` | rien |
| Cloudflare Workers AI | `api.cloudflare.com/client/v4/accounts/<compte>/ai/models/search` | `MODEL_DRIFT_CLOUDFLARE_API_KEY` et `MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID` | rien |
| Kilo Gateway | `ai-gateway.kilo.ai/api/v1/models` | aucun | le drapeau `isFree` |
| NVIDIA | `integrate.api.nvidia.com/v1/models` | aucun | rien |
| OVHcloud | `oai.endpoints.kepler.ai.cloud.ovh.net/v1/models` | aucun | un prix par jeton, qui ne dit rien de l'accès sans clé des entrées : rien |
| Requesty | `router.eu.requesty.ai/v1/models` | aucun | `input_price` et `output_price` à 0 |
| Z AI | `api.z.ai/api/paas/v4/models` | `MODEL_DRIFT_ZAI_API_KEY` | rien |
| Cent AI | `api.cent-ai.dev/v1/models` | `MODEL_DRIFT_CENT_AI_API_KEY` | rien |
| Aion Labs | `api.aionlabs.ai/v1/models` | aucun | rien : l'allocation gratuite est celle du compte, et le catalogue donne un prix à chaque modèle |

Dans une ligne `drift-ignore`, le fournisseur s'écrit `openrouter`, `cerebras`, `sambanova`, `gemini`, `groq`, `mistral`, `deepseek`, `cloudflare`, `kilo`, `nvidia`, `ovhcloud`, `requesty`, `zai`, `centai` ou `aionlabs`, et l'identifiant est celui du catalogue, pas celui du `model:` de l'entrée (`nvidia/<id>` pour une entrée `nvidia_nim/<id>`).

Pour couvrir ceux qui demandent un secret, créer dans *Settings → Secrets and variables → Actions* ceux du tableau, dont
**deux** pour Cloudflare Workers AI : `MODEL_DRIFT_CLOUDFLARE_API_KEY`, un jeton d'API du compte dont la seule
permission est *Account → Workers AI → Read*, et `MODEL_DRIFT_CLOUDFLARE_ACCOUNT_ID`, l'identifiant du compte
(32 caractères hexadécimaux), que l'adresse du catalogue contient et que le contrôle remplace par `***` partout
où un message pourrait l'afficher, comme une clé. Chacun est facultatif, de préférence une clé dédiée, révocable
sans toucher à celles de LiteLLM, et les deux de Cloudflare vont ensemble : l'un sans l'autre, le résumé dit
lequel manque. Le contrôle n'appelle aucun modèle, à une exception près (Z AI, ci-dessous) : une requête de liste par
fournisseur et par exécution, aucun jeton dépensé, et les clés ne voyagent que dans des en-têtes. Sans l'un d'eux, le résumé dit à chaque exécution que son
fournisseur est « non couvert », et ce n'est pas une lecture ratée : aucune issue, aucune reprise. Les entrées
d'OmniRoute sont listées dans le résumé comme « d'aucun catalogue lu ici ».

Les catalogues de Z AI et de Cent AI répondent `401` sans clé, et aucune session de ce dépôt n'en détient une : seul
le run de la veille, qui tient les clés, les lit, pour la première fois le 2026-11-24. Le contrôle les lit comme la liste au format OpenAI que l'on attend d'elles
(`{"data": [{"id": ...}]}`) ; une réponse d'une autre forme est l'erreur de ce fournisseur, jamais un retrait.

**Le catalogue de Z AI omet ses modèles gratuits « Flash »** (GLM-4.7-Flash, GLM-4.5-Flash et GLM-4.6V-Flash n'y figurent pas, alors
que Z AI les sert : un appel à GLM-4.7-Flash a reçu, le 2026-11-24, un `429` de code `1305`, une surcharge, et non l'erreur d'un modèle
inconnu). Pour ce fournisseur, une entrée absente du catalogue ne prouve donc pas un retrait, et Z AI n'a pas de route qui réponde pour
un seul modèle : pour chaque entrée **active** que la liste omet, le contrôle regarde d'abord la page des tarifs de Z AI (plus bas), qui
liste ses modèles gratuits en Markdown et ne coûte aucune requête du quota : un modèle qu'elle nomme est servi, sans aucun appel. Un jour
normal, tous les modèles routés y sont, et le contrôle n'appelle donc rien. Seul un modèle que ni la liste ni cette page ne nomment (ou
une page illisible ce jour-là) est interrogé par la requête la moins chère qui prouve qu'un modèle existe, une complétion de chat de
`max_tokens: 1` avec la clé `MODEL_DRIFT_ZAI_API_KEY`, gratuite pour les modèles routés. La page des codes d'erreur de Z AI (<https://docs.z.ai/api-reference/api-code>, lue le 2026-11-24)
décide de la réponse : `200` et tout `429` (limites, solde, forfait : jamais un modèle inconnu) disent que le modèle est servi, et le
résumé le liste à part, dans « Absents de la liste, mais toujours servis », sans que l'exécution sorte en échec ; `400` avec le code `1211`
(« Unknown Model ») est le seul code que cette page donne pour un modèle qui n'existe pas, et fait de l'entrée un retrait, supprimé
comme les autres sous `--apply` ; toute autre réponse (`401`, `5xx`, délai dépassé, code inconnu, corps inattendu) ne tranche rien, et
l'entrée reste une alerte (« NOTICE ») qui dit ce que Z AI a répondu. Une entrée **commentée** n'est jamais interrogée (c'est une entrée
non routée, souvent pour son prix, et un appel pourrait coûter) : son absence reste une alerte, sans suppression. Les fournisseurs dans
ce cas sont déclarés dans `INCOMPLETE_CATALOGUES`, en tête de `.github/scripts/check_LiteLLM_model_drift.py`, chacun avec sa raison ;
aucun autre n'est connu pour omettre des modèles qu'il sert.

Les nouveaux modèles gratuits de Z AI sont masqués par la même omission. Le contrôle lit donc la page des tarifs, que la
documentation de Z AI sert en Markdown (<https://docs.z.ai/guides/overview/pricing.md>, lue le 2026-11-24) : un modèle dont les colonnes
« Input » et « Output » valent `Free` est proposé comme nouveau, à examiner, avec la mention « listed free on its pricing page ». Ce
n'est pas une gratuité lue dans l'API : la page nomme les modèles par leur nom d'affichage (l'identifiant est ce nom en minuscules), et sa
mise en page peut changer. Une page sans tableau de prix lisible est l'erreur de ce fournisseur, jamais un retrait ; la clé n'est pas
envoyée à cette page, qui est publique.

La réponse du catalogue de Cloudflare n'est pas documentée par son API, qui type chaque modèle « unknown » : le
contrôle lit la forme que lisent la documentation de ses modèles et son outil en ligne de commande, et aucune
exécution n'a lu la réponse réelle. Un modèle est retiré quand il a quitté la liste, demandée avec les modèles
dépréciés que l'API garde trois mois après leur date ; une date de dépréciation annoncée (propriété
`planned_deprecation_date`) ou un indicateur `deprecated` est une alerte, comme chez les autres fournisseurs. La
gratuité d'un modèle Cloudflare ne se lit nulle part : la page des tarifs la dit en prose, par la note qui nomme les
modèles qui exigent un moyen de facturation payant, et le contrôle n'en invente pas la lecture. Un nouveau modèle est
donc seulement proposé à vérifier, jamais prêt. Un secret de plus, `MODEL_DRIFT_ARTIFICIAL_ANALYSIS_API_KEY`, n'est
celui d'aucun fournisseur : c'est la clé gratuite d'Artificial Analysis (1 000 requêtes par jour, une par run), qui
alimente le classement ci-dessus, et il est tenu par `read` comme les autres, jamais par `publish`.

Le workflow tient les clés des fournisseurs et un jeton qui écrit, et aucun travail ne doit tenir
ce jeton à côté de code que personne n'a relu (une mise à jour de PyYAML ou de Jinja2, que Dependabot
fusionne seule, en est). Il se fait donc en **deux travaux** reliés par un artefact : `read` (les clés, un
jeton en lecture seule, le script) et `publish` (le jeton qui écrit, aucune clé de fournisseur, aucun
script du dépôt). Le découpage borne le jeton qui écrit : un `read` compromis peut au pire lui faire ouvrir une
pull request qui supprime des lignes du fichier, et cette pull request peut se fusionner seule (voir
plus haut), à des conditions qui bornent les lignes retirées (cinq entrées et deux cents lignes au plus,
et rien d'autre que des entrées de modèle, leurs places de cascade, des commentaires et des lignes vides),
dans un commit que git garde et qu'un `revert` défait -- jamais une ligne ajoutée. Il peut aussi lui faire
ouvrir les deux pull requests d'ajout, avec des entrées d'une forme fixe, calquées sur celles du fichier (une
clé et une adresse qu'il a déjà, un identifiant et un nom d'une orthographe étroite), qu'une personne seule
fusionne. Il ne garde pas les clés de PyYAML et de Jinja2, avec qui elles
partagent `read` : c'est pourquoi elles doivent être dédiées et révocables, comme dit plus haut. L'en-tête du workflow développe le pourquoi. Il ne
s'exécute que sur `main`, jamais sur une pull request : cela protège d'un lancement fait par erreur
depuis une autre branche, pas d'une personne qui peut pousser sur le dépôt, `main` n'y étant pas
plus protégée qu'une autre branche.

### Les fournisseurs gratuits examinés, ceux retenus et ceux écartés

Ce registre existe pour qu'un fournisseur déjà regardé ne soit pas ré-examiné de zéro : chaque ligne dit ce que l'offre gratuite est, ses limites, le verdict et la page officielle lue, relue le 2026-11-21 sauf mention contraire. Les commentaires du `model_list` de `LiteLLM_config.yaml.j2` restent la source de ce qui est **déjà routé** et de la raison de chaque modèle commenté ; ce registre les résume, il ne les remplace pas, et ne porte aucun chiffre que le template ne donne pas.

**Critères.** Un palier gratuit qui dure, pas un crédit unique ; l'exigence d'une carte bancaire ou d'un téléphone ; des limites publiées ; un point d'accès compatible OpenAI ou un fournisseur natif de LiteLLM ; la politique sur les données et l'entraînement ; les conditions sur l'usage derrière une passerelle, l'automatisation et les comptes multiples. La position du mainteneur : l'entraînement sur les prompts est accepté quand il ne peut pas être désactivé, et les modèles en préversion conviennent. Une carte bancaire exigée n'écarte pas un fournisseur tant que la dépense peut être plafonnée à 0 $ ou que le compte est prépayé et vide : elle se note, elle ne tranche pas. Un dépôt jusqu'à 10 € est de même considéré (plafond fixé par le mainteneur le 2026-11-22), à condition d'être unique et supposé valable à vie : ni abonnement, ni recharge, ni crédit qui expire dans un an ou deux. C'est soit un ticket d'entrée, un crédit qui reste sur le compte et lève une limite, soit un crédit dépensé en jetons, qui ne se retient que comme réserve payante et jamais comme palier gratuit : la ligne dit alors ce que le dépôt achète, s'il expire ou se rembourse, et si cela vaut son prix. Tout palier gratuit qui dure est pris, qu'il batte ou non ce qui est déjà routé : la passerelle sert toutes les applications du homelab, pas le seul agent Claude Code, et diversifier les quotas compte autant que le meilleur modèle. Ne sont écartés que les essais limités dans le temps (30 jours, par exemple) et les quotas uniques, sauf s'ils sont énormes, et ce qui fait d'une offre à date un essai est ce qui est annoncé après elle. Gratuit jusqu'à une date, sans rien d'annoncé après : on le prend, et on le revoit à cette date. Gratuit jusqu'à une date, puis payant à un prix annoncé : c'est un essai, on l'écarte. Le risque qu'un fournisseur coupe une clé n'est pas anticipé, et un chemin réservé aux données sensibles est refusé : presque tout ce que traite la passerelle en contient un peu. La page d'un fournisseur est relue avant son ajout, jamais prise de ce registre.

**Groupe 1 -- utilisés aujourd'hui** (état du template, vérifications datées dans ses commentaires).

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Google Gemini API | Palier gratuit « Standard », modèles Flash et Gemma 4 | Les modèles « Not available » en gratuit (gamme Pro, Gemini 4 Argon) sont commentés, non routés | Routé, tête des cascades |
| Groq | Palier gratuit | 30 requêtes par minute, 1K par jour, 8K jetons par minute et 200K par jour (gpt-oss, qwen3.8-27b ; page des limites relue le 2026-11-24, dont le texte lu ne sépare pas nettement le palier gratuit du palier Developer : à confirmer sur la page des limites du compte) ; qwen3.8-27b est en préversion. Les jetons de raisonnement comptent dans le quota de jetons (sonde du 2026-11-22 : `reasoning_effort` bas a consommé 8 jetons de raisonnement, haut 562, et `x-ratelimit-remaining-tokens` a baissé d'autant ; la page n'en parle pas) ; une valeur d'effort que Groq ne liste pas peut recevoir un 400 | Routé |
| Cloudflare Workers AI | 10 000 « neurons » par jour sans frais, pour tout le compte, remis à zéro à 00:00 UTC ; point d'accès compatible OpenAI et fournisseur natif de LiteLLM (préfixe `cloudflare/`) | Texte : 300 requêtes par minute. La page des tarifs (relue le 2026-11-24) nomme les modèles à accès payant (Kimi K2.6 et K2.7, GLM-5.x, DeepSeek V4.x, Inkling) : ils ne s'ouvrent qu'avec l'abonnement Workers Paid (à partir de 5 $ par mois) ou avec des crédits prépayés d'AI Gateway (facturation unifiée, prix par million de jetons sur cette page) ; une carte bancaire seule n'ouvre rien. La voie des crédits est du crédit dépensé, une réserve payante, jamais un palier gratuit. Aucun de ces modèles n'est routé (les pages de GLM-5.3 et d'Inkling 2 Small disent « Paid access required »). EuroLLM 9B (`eurollm-9b-it`) et Apertus v1.5 8B sont écartés : leurs pages ne donnent aucun prix et renvoient à un même formulaire de demande d'accès, fermé le 2026-11-24. Les modèles routés n'y figurent pas et seraient donc gratuits : **déduction, à confirmer sur le compte**. Écarté : nemotron-3-120b (sa page dit « Deprecated 11/20/2026 »). Qwen3.8 27B est routé (`qwen3-8-27b-cloudflare`) mais en repli de ses jumeaux : absent de la table de modèles de LiteLLM le 2026-11-22, il réfléchit en Xhigh par défaut et rien ne l'abaisse (sur une question difficile, `reasoning_effort` bas ou très haut et `enable_thinking` désactivé ont donné chacun 1 770 à 2 616 jetons et 81 à 109 s) | Routé (page relue le 2026-11-22) : deuxième source derrière Groq pour gpt-oss, troisième pour gemma-4-26b, en queue des membres gratuits pour llama-3.3-70b (`Auto-Flash-Lite`) et glm-4.7-flash (`Auto-Code`, `Auto-Claude-Code`) ; les autres entrées Cloudflare du template sont détaillées dans la section dédiée. Ne s'entraîne pas sur le contenu client et ne le conserve pas pour l'inférence standard ; un seul compte, en ouvrir un second pour doubler le quota tombe sous la clause contre le contournement des quotas. Lu par le contrôle de dérive (secrets `MODEL_DRIFT_CLOUDFLARE_*`) : un modèle qui a quitté le catalogue est supprimé, un retrait annoncé est signalé |
| OpenRouter | Trois modèles `:free` au catalogue public des embeddings (`/api/v1/embeddings/models`, lu le 2026-11-24), à tarif 0 en entrée comme en sortie : `nvidia/nemotron-3.5-embed-1b:free` et `nvidia/nemotron-3.5-embed-8b:free` (multilingues, 32 768 jetons, texte et images de pages), `nvidia/nemotron-3-embed-1b:free` (4 096 jetons, texte) ; la route d'embeddings d'OpenRouter existe dans LiteLLM (source lue le 2026-11-24, non essayée) | Les limites des modèles gratuits d'OpenRouter, déjà au registre du texte : 20 requêtes par minute et 50 par jour pour tout le compte, 1 000 par jour une fois 10 crédits achetés, partagées avec les modèles de texte gratuits ; taille du vecteur non lue sur une page | `nemotron-3-embed-1b-free`, `nemotron-3-5-embed-1b-free` et `nemotron-3-5-embed-8b-free` routés par leur nom, avec la clé que le rôle connaît déjà. Chaque page de modèle dit de ne pas envoyer d'information confidentielle ou personnelle à ce point d'accès gratuit, que l'usage est journalisé et qu'NVIDIA collecte et emploie ce qui est envoyé selon ses conditions d'essai : pas pour des documents privés. Le contrôle de dérive retire une entrée que le catalogue ne liste plus, comme toute entrée OpenRouter |
| Z AI (Zhipu) | GLM-4.7-Flash, GLM-4.5-Flash et GLM-4.6V-Flash gratuits d'après la page « Pricing » (lue le 2026-11-22) ; fournisseur natif de LiteLLM (préfixe `zai/`) | Non publiées hors de la console du compte : **inconnues ici** (une limite d'une requête simultanée, citée par un tiers, n'est **pas vérifiée**). Seul GLM-4.7-Flash est routé ; GLM-4.5-Flash (même compte, même limite, aucun classement) et GLM-4.6V-Flash (vision, absent de la table de LiteLLM) sont écartés | Routé (pages relues le 2026-11-22) : fin des cascades `Auto-Code` et `Auto-Claude-Code`, devant les payants, modèle non mesuré. Les conditions interdisent de partager les clés, et n'ont rien donné sur les passerelles ni sur les comptes multiples ; contenu des clients de l'API non utilisé pour améliorer les services sans accord, non stocké d'après l'accord de traitement, traitement généralement à Singapour. Carte ou téléphone à l'inscription, date d'arrêt des modèles gratuits : aucune page lue n'en parle. Lu par le contrôle de dérive (secret `MODEL_DRIFT_ZAI_API_KEY`) : son catalogue omet les modèles gratuits, donc une entrée active absente est vérifiée sur la page des tarifs de Z AI, puis par un appel d'un jeton, et supprimée sur le code 1211 (voir la section de la dérive) |
| NVIDIA API Catalog (build) | Inférence « gratuite » d'essai sur les modèles du catalogue, annoncée pour le service et non modèle par modèle ; fournisseur natif de LiteLLM (préfixe `nvidia_nim/`) | 40 requêtes par minute, affichées sur la page du compte (lue le 2026-11-22) ; aucun crédit, plafond quotidien ni date de fin sur une page lue : **inconnus ici** | Routé (pages lues le 2026-11-22), un compte à créer. Conditions d'un service d'essai : « limited trial purposes only and without use ... in production », contenu collecté pour améliorer les produits NVIDIA, modèles d'IA compris, données personnelles interdites. Le mainteneur choisit de s'en servir malgré tout et accepte le risque d'une clé coupée. Clé après vérification par SMS, d'après les forums seulement. Lu par le contrôle de dérive, dont le catalogue est public : un modèle qui a quitté le catalogue est supprimé, un nouveau est proposé à vérifier |
| Mistral La Plateforme | Aucune pour l'API : le mode « Free » ne couvre que Vibe et Studio, et une clé d'API exige la facturation activée et le paiement à l'usage (documentation lue le 2026-11-21) | Solde prépayé ; limites par modèle visibles seulement dans la console du compte | Routé en queue, après tous les gratuits, clé facultative, comme DeepSeek |
| OpenRouter (modèles `:free`) | Modèles `:free` du catalogue | 20 requêtes par minute et 50 par jour pour tout le compte, 1000 par jour une fois 10 crédits achetés | Routé, après le fournisseur d'origine du même modèle |
| Kilo Gateway | Modèles gratuits sans clé ni compte : le catalogue du service, lisible sans authentification, marque chacun comme gratuit ; point d'accès compatible OpenAI (pages lues le 2026-11-22) | 200 requêtes par heure et par IP, pour tous ces modèles ensemble ; les modèles gratuits changent, et le catalogue marque chacun comme pouvant être entraîné sur les prompts | Routé sans clé, derrière son jumeau OpenRouter quand il en a un. Aucun compte n'est utilisé, donc la clause « un compte par entité » ne joue pas ; prompts journalisés et utilisés pour l'entraînement, accepté ; conditions lues, non validées |
| OVHcloud AI Endpoints | Modèles de texte sans clé ni compte, dont les fiches annoncent les appels d'outils ; point d'accès compatible OpenAI (pages lues le 2026-11-22) | 2 requêtes par minute, par IP et par modèle, observées depuis le réseau du mainteneur et écrites sur aucune page lue ; avec une clé, 400 par minute, mais un moyen de paiement sur un projet Public Cloud est exigé et aucun plafond de dépense n'existe | Routé sans clé, en queue des listes gratuites, derrière Kilo et devant les fournisseurs payants, jamais dans `Auto-Claude-Code`. Hébergé dans l'UE, « Your data is never used to train our models », rétention zéro d'après la page du service payant : que l'accès anonyme y soit tenu n'est pas vérifié. Essayé le 2026-11-22 : un appel anonyme à gpt-oss-120b a répondu depuis le réseau du mainteneur, un second dans la minute a reçu un 429 |
| Cerebras | 5 $ de crédit après ajout d'un moyen de paiement, expirés au bout de 30 jours ; pas de palier gratuit permanent | Carte exigée | Examiné, non routé (entrées commentées) |
| SambaNova | Palier gratuit sans moyen de paiement lié, d'après la page des limites : 20 requêtes par minute, 20 par jour et 200 000 jetons par jour, par modèle (gpt-oss-120b, gemma-4-31B-it) ; la page des plans dit au contraire d'ajouter un moyen de paiement et d'acheter des crédits ; avec une carte liée, palier Developer : 60 par minute, 12 000 par jour et par modèle, 20 millions de jetons par jour au total, paiement à l'usage (pages relues le 2026-11-22) | Essais du 2026-11-22. Sans carte liée : gpt-oss-120b, gemma-4-31B-it et MiniMax-M3.1-Flash répondent par une erreur de moyen de paiement manquant (code tronqué à `PAYMENT_METHOD`, solde de 0 unité). Avec une carte liée et aucun crédit acheté : gpt-oss-120b répond ; gemma-4-31B-it et MiniMax-M3.1-Flash répondent par une erreur de crédits épuisés (code tronqué à `CREDITS_EXHAUS`) ; GLM-5.3 par une erreur de moyen de paiement. Plus tard le même jour, cinq appels de gpt-oss-120b espacés de 70 secondes répondent tous par l'erreur de crédits épuisés (code `CREDITS_EXHAUSTED`, solde de 0 unité) : ce n'est pas une limite de débit, et le compte n'a jamais reçu de crédit, aucun n'ayant été acheté. L'hypothèse du quota gratuit de la page des limites (20 requêtes par jour et par modèle) est écartée : un premier appel de gpt-oss-120b le 2026-11-23, après la remise à zéro quotidienne, répond HTTP 402 `CREDITS_EXHAUSTED` (« You have run out of credits. Add more at https://cloud.sambanova.ai/plans/billing to continue. »), avec la même carte liée et toujours aucun crédit acheté. Sans carte, l'erreur est celle du moyen de paiement manquant ; avec carte et sans crédit, c'est celle des crédits épuisés : aucun des deux états ne sert le palier gratuit de la page des limites. Le compte est prépayé et ne propose aucun plafond de dépense : un solde à 0 ne laisse rien à débiter, ce que l'erreur à solde nul confirme | Écarté, non routé (tranché le 2026-11-23) : une carte liée sans achat n'ouvre aucun quota qui se renouvelle, c'est un solde prépayé qui s'épuise, donc aucun palier gratuit durable ; les pages ne disent ni le minimum d'achat ni l'expiration des crédits, et un dépôt n'achèterait que des jetons (voir les dépôts jusqu'à 10 € plus bas). À relire si la page des plans change |
| DeepSeek | Aucun : solde prépayé, accepté par PayPal, carte, Alipay ou WeChat Pay | Payant | Routé en tout dernier recours avant OmniRoute, payant comme Mistral, clé facultative |
| Requesty (modèles gratuits) | Passerelle qui relaie vers le fournisseur de chaque modèle ; pas de carte pour les modèles gratuits ; pas de fournisseur LiteLLM de ce nom, point d'accès compatible OpenAI | 200 requêtes par jour et 20 par minute pour une organisation neuve, pour tous ses modèles gratuits ensemble ; gratuit « pour l'instant » | Routé, derrière le jumeau `:free` d'OpenRouter, pour les seuls modèles que le `model_list` sert déjà par OpenRouter. Lu par le contrôle de dérive, dont le catalogue est public et donne le prix d'entrée et de sortie de chaque modèle : un modèle qui n'est plus à 0 est signalé, jamais supprimé |
| Cent AI (modèle gratuit) | Revendeur ; un modèle gratuit, `hy4-flash:free`, annoncé « Free until Nov 30 · no daily limit » (page d'accueil lue le 2026-11-22) ; point d'accès compatible OpenAI, pas de fournisseur LiteLLM de ce nom | Aucune limite annoncée ; rien n'est dit de la suite du 30 novembre, où le modèle sera probablement facturé à son tarif (non vérifié). Le modèle gratuit « événement » du jour, tiré au hasard sous un identifiant qui change chaque jour, n'est pas routable | Routé, en queue des gratuits de `Auto-Pro`, `Auto-Flash` et `Auto-Flash-Lite`, à revoir le 1er décembre. Opérateur particulier aux conditions en brouillon, requêtes relayées vers des fournisseurs non nommés : le mainteneur accepte ces risques. Une limite de dépense sur la clé fait échouer un appel facturé au lieu de le payer. Lu par le contrôle de dérive (secret `MODEL_DRIFT_CENT_AI_API_KEY`) : un modèle qui a quitté le catalogue est supprimé |
| Aion Labs (modèles de jeu de rôle) | Palier gratuit à l'inscription : l'allocation du compte, et non le prix d'un modèle (le catalogue en donne un à chacun) ; les clés d'API s'activent en vérifiant une carte bancaire, jamais débitée, une carte par compte gratuit (page « Rate limits » lue le 2026-11-23) ; point d'accès compatible OpenAI, aucun fournisseur LiteLLM de ce nom | 15 requêtes par minute, 20 000 jetons par minute et 20 000 jetons par jour pour tout le compte, tous les modèles ensemble, soit quelques requêtes avec des modèles qui raisonnent ; « free use before any purchase is a courtesy that we may change or withdraw at any time » (conditions du 2026-10-17, lues le 2026-11-23), un retrait de modèle ou de limite annoncé 14 jours avant « where we are able to give it » | Routé **à part** : dans le groupe d'accès `Fiction` et dans le seul routeur `Auto-Fiction`, jamais dans `LLM` ni dans une autre cascade, parce que ces modèles sont réglés pour le jeu de rôle et la narration, thèmes adultes et sombres compris, et ne sont pas modérés (voir « Les modèles de jeu de rôle »). Tout palier gratuit qui dure est pris, qu'il batte ou non ce qui est déjà routé. Un seul compte, partage de la clé interdit et passerelle permise (conditions, section 4) ; la carte n'est jamais débitée d'après la page, et le compte reste sans crédit. Ne stocke pas le contenu des requêtes et ne s'en sert pas pour entraîner des modèles (politique de confidentialité) ; société polonaise. **Lu par le contrôle de dérive** : catalogue public sans clé |
| OmniRoute | Agrégateur local, sans clé | Aucun quota à protéger | Dernier recours des cascades |

#### Gemini : conditions et quotas du palier gratuit

Ce qui suit est écrit une fois ici, et les autres sections de ce document y renvoient. Conditions et pages lues le 2026-11-22 ; aucune conclusion juridique n'en est tirée, c'est à l'appelant de les confronter à son propre déploiement.

**Les données.** Les conditions additionnelles de l'API Gemini (« Effective March 23, 2026 », [ai.google.dev/gemini-api/terms](https://ai.google.dev/gemini-api/terms)) distinguent selon la région. Hors de l'Espace économique européen (EEE), de la Suisse et du Royaume-Uni, Google utilise le contenu envoyé sur le quota non payant pour améliorer ses produits, et « human reviewers may read, annotate, and process your API input and output » : on n'y envoie ni information sensible, confidentielle ou personnelle, ni document de tiers. Dans ces trois régions, « the terms under "How Google uses Your Data" in "Paid Services" apply to all Services, including Google AI Studio and unpaid quota in the Gemini API, even though they are offered free of charge » : Google n'y utilise alors ni les requêtes ni les réponses pour améliorer ses produits. Toute mention, dans ce document, d'un contenu réutilisé ou lu par des relecteurs sur le palier gratuit vaut donc **hors de ces trois régions seulement**.

**Les restrictions d'usage**, citées telles quelles :

- « Use of Google AI Studio and Gemini API is for developers building with Google AI models for professional or business purposes, not for consumer use. »
- « You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom. » C'est la phrase qui vise une passerelle partagée avec d'autres personnes dans ces régions.
  Le rôle route quand même le palier gratuit, décision prise le 2026-11-24 : pour un usage privé, le risque est accepté, et au pire Google coupe la clé. Un appelant qui ouvre sa passerelle à d'autres personnes dans ces régions tranche pour lui-même : passer aux services payants, ou ne pas donner les modèles Gemini aux clés de ces personnes.
- « You must be 18 years of age or older to use the APIs. You also will not use the Services as part of a website, application, or other service [...] that is directed towards or is likely to be accessed by individuals under the age of 18. »

**Plusieurs projets.** Les limites s'appliquent par projet et non par clé ([rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)), et les conditions générales des API de Google (page « Google APIs Terms of Service », « Last modified: November 9, 2021 », section 2(d)) disent : « You agree to, and will not attempt to circumvent, such limitations documented with each API. » Ouvrir plusieurs projets pour multiplier le quota gratuit d'une même application est ce que cette clause interdit ; des projets séparés pour des environnements séparés ne le sont pas.

**Les quotas**, lus le 2026-11-22 dans la page des limites de Google AI Studio pour un projet au niveau sans frais. Ils sont par projet et par modèle, et les quotas quotidiens se remettent à zéro à minuit, heure du Pacifique.

| Modèles | Requêtes par minute | Jetons par minute | Requêtes par jour |
| --- | --- | --- | --- |
| Gemini 4 Hydrogen | 5 | 250 K | 20 |
| Gemini 3.8 Flash, 3.6 Flash, 3 Flash, 2.5 Flash (chacun) | 5 | 250 K | 20 |
| Gemini 3.5 Flash-Lite, 3.1 Flash-Lite (chacun) | 15 | 250 K | 500 |
| Gemini 2.5 Flash-Lite | 10 | 250 K | 20 |
| Gemma 4 31B, 26B (chacun) | 30 | 16 K | 14 400 |
| Gemini Embedding 1, 2 (chacun) | 100 | 30 K | 1 000 |
| Synthèse vocale : 3.8 Flash TTS, 3.8 Flash Lite TTS, 3.1 Flash TTS, 2.5 Flash TTS (chacun) | 3 | 10 K | 10 |
| Gemini 3.5 Transcribe | 3 | 10 K | 25 |
| Modèles de l'API Live | aucune limite | 65 K ou 20 K | aucune limite |
| Gemini 3.1 Pro, 2.5 Pro, Gemini 4 Argon, Neon, Carbon | 0 | 0 | 0 : non servis en gratuit |

**La facturation.** La page de facturation de l'API Gemini (relue le 2026-11-24, [aistudio.google.com/docs/billing](https://aistudio.google.com/docs/billing)) dit que les nouveaux utilisateurs sont par défaut en prépayé (le prépayé étant annoncé obligatoire pour les nouveaux comptes à partir du 2026-03-23) et, à solde nul, « all API keys in all projects linked to that billing account will stop working simultaneously » : les requêtes échouent en 402, et « Your projects aren't automatically downgraded to the Free Tier ». La facturation ne doit donc pas être liée au projet de la clé gratuite : à solde nul, cette clé s'arrêterait au lieu de retomber sur le palier gratuit. Délier la facturation d'un projet le ramène au palier gratuit.

Les 20 requêtes par jour de Gemini 4 Hydrogen sont des quotas d'API, par projet. Le chat d'AI Studio sans clé n'y est pas compté : les deux ne se comparent pas.

Pages officielles lues :

- Google Gemini API : [Pricing](https://ai.google.dev/gemini-api/docs/pricing), [Additional Terms of Service](https://ai.google.dev/gemini-api/terms), [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits), « Google APIs Terms of Service » (sur le site des développeurs de Google)
- Groq : [Rate limits](https://console.groq.com/docs/rate-limits)
- Cloudflare Workers AI : [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/), [Limits](https://developers.cloudflare.com/workers-ai/platform/limits/), [Data usage](https://developers.cloudflare.com/workers-ai/platform/data-usage/), [Terms](https://www.cloudflare.com/terms/)
- Z AI (Zhipu) : [Pricing](https://docs.z.ai/guides/overview/pricing), [Terms of use](https://docs.z.ai/legal-agreement/terms-of-use.md)
- NVIDIA API Catalog : page d'accueil du catalogue, fiches de ses modèles et [API Trial Terms of Service](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf) (PDF)
- Cent AI : page d'accueil du service, lue le 2026-11-22
- Aion Labs : [Rate limits](https://www.aionlabs.ai/docs/rate-limits/), [Pricing](https://www.aionlabs.ai/pricing/), [Terms](https://www.aionlabs.ai/terms/) et [Privacy](https://www.aionlabs.ai/privacy/), lues le 2026-11-23, et son [catalogue](https://api.aionlabs.ai/v1/models)
- Mistral : [Pricing](https://mistral.ai/pricing)
- OpenRouter : [Limits](https://openrouter.ai/docs/api_reference/limits)
- Kilo Gateway : [Models and providers](https://kilo.ai/docs/gateway/models-and-providers), [Authentication](https://kilo.ai/docs/gateway/authentication), [Terms](https://kilo.ai/terms)
- OVHcloud AI Endpoints : [Getting started](https://docs.ovhcloud.com/en/guides/public-cloud/ai-machine-learning/ai-endpoints-getting-started), [AI Endpoints](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/), [Catalogue](https://www.ovhcloud.com/en/public-cloud/ai-endpoints/catalog/)
- Cerebras : [Rate limits](https://inference-docs.cerebras.ai/support/rate-limits)
- SambaNova : [Plans](https://cloud.sambanova.ai/plans)
- DeepSeek : [FAQ](https://api-docs.deepseek.com/faq)
- Requesty : pages « Free models », « Billing », « Quickstart » et « Data privacy » de sa documentation, relues le 2026-11-22

**Groupe 2 -- à ajouter, par ordre de préférence.** Aucun pour l'instant.

**Groupe 3 -- écartés, avec la raison.**

| Fournisseur | Ce qui est offert | Raison de l'écart |
| --- | --- | --- |

| Cohere (clés d'essai) | 1 000 appels par mois, 20 requêtes par minute par modèle de chat, soit environ 33 appels par jour | Trop étroit ; comptes multiples et usage en « service bureau » interdits ; page des conditions datée de 2022, peut-être périmée |
| GitHub Models | Fermé le 2026-07-30 | Plus de service |
| OpenCode Zen | Des modèles de chat gratuits (« Free-tier chat models require OpenCode ») ; ids gratuits temporaires (« for a limited time »), certains entraînés sur les données (page relue le 2026-11-24) | Inutilisable derrière la passerelle : l'accès exige OpenCode lui-même ; les crédits servent aux modèles payants |
| IteraCompute | Une allocation mensuelle « Auto » en jetons, annoncée à 30 millions sur Qwen3.8-27B ; la page des conditions (relue le 2026-11-24) dit que la promotion gratuite est terminée et que Qwen3.8-27B est retiré | Promotion terminée |
| Nscale | Aucun palier gratuit trouvé ; documentation : prépayé en libre-service, « a minimum of $5 of credit » (relue le 2026-11-24) | Pas de palier gratuit |
| AWS (Bedrock, Nova, Kiro, Q Developer, au-delà de Polly) | Bedrock et Nova : rien de gratuit au-delà du crédit de départ. Transcribe, Translate, Comprehend, Rekognition : essais de 12 mois. Textract : 3 mois. SageMaker : 2 mois. Kiro : palier gratuit de 50 crédits par mois, sans API, et ses conditions interdisent de passer par un autre outil que ses interfaces. Un compte neuf reçoit un plan gratuit de 100 $, jusqu'à 200 $ avec des activités, qui se ferme au bout de six mois ou crédits épuisés, sauf passage au plan payant | Crédits uniques et essais limités dans le temps ; aucune API pour Kiro |
| Hugging Face Inference Providers | Aucun crédit mensuel pour les comptes gratuits | Pas d'offre gratuite |
| Chutes | Aucune : « We do not offer a free tier at this time » | Pas d'offre gratuite |
| Ollama Cloud | Aucune | Pas de plan gratuit sur la page des tarifs |
| Moonshot / Kimi | Aucune | Recharge minimale de 1 dollar « to prevent abuse » |
| Alibaba Model Studio / DashScope | Quota unique d'environ 1 million de jetons par modèle, valable 90 jours | Crédit unique, et pas pour les comptes neufs |
| SiliconFlow | Crédit unique de 1 dollar | Crédit unique, aucun modèle gratuit listé |
| Scaleway Generative APIs | 1 million de jetons gratuits, une fois | Crédit unique, limites liées à un moyen de paiement valide ; lu dans un résumé de recherche, les pages directes ont répondu 403 |
| Hyperbolic | Palier « Free » par défaut, avec un crédit de 1 $ après vérification d'un téléphone, une seule fois par personne ; les requêtes sont refusées quand le solde est épuisé (pages lues le 2026-11-22) | 60 requêtes par minute sur le plan Free d'après la page des comptes, 300 par clé d'après la page d'inférence : les deux ne concordent pas | Crédit unique, pas de palier gratuit durable ; les conditions interdisent de créer plusieurs comptes pour contourner les limites. Point d'accès compatible OpenAI, aucun fournisseur LiteLLM nommé |
| Novita AI | « Free to start » et un bon d'inscription dont le montant et la durée ne sont pas publiés, révoqué en cas de comptes multiples depuis le même appareil (pages lues le 2026-11-22) | Limites par palier de recharge, chiffres absents du texte lu | Aucune offre gratuite durable prouvée ; les conditions et la politique de confidentialité n'ont pas rendu leur corps, donc rien n'est établi sur les données |
| AI21 | Crédit de 10 $ pour un compte neuf, sans carte : 7 jours d'après la page des tarifs, trois mois d'après la documentation (pages lues le 2026-11-22) | Jamba Large et Jamba Mini : 200 requêtes par minute | Crédit unique ; pas de point d'accès compatible OpenAI ni de fournisseur LiteLLM nommé ; la revente est interdite. Ne s'entraîne pas sur les entrées et sorties |
| Nebius Token Factory | Aucune ; des codes promotionnels ponctuels et, pour des startups financées, jusqu'à 50 000 $ de crédits (pages lues le 2026-11-22) | Limites dynamiques, valeurs par défaut non publiées | Pas de palier gratuit, et une carte bancaire est exigée pour finir l'inscription. Ne s'entraîne pas sur le contenu, mais garde les entrées et sorties sauf si la rétention zéro est activée |
| Vercel AI Gateway | Crédit mensuel gratuit sur un sous-ensemble de modèles | Limites « not fixed », montant non lu ; apporter sa propre clé est réservé aux plans payants |
| Fireworks | Un crédit de 1 $ une seule fois ; sans moyen de paiement, 10 requêtes par minute puis « Your account will be suspended until you add a payment method » ; aucun modèle serverless gratuit listé (pages relues le 2026-11-22) | Ne journalise pas les prompts des modèles ouverts sans accord explicite | Crédit unique, carte exigée pour continuer ; fournisseur `fireworks_ai/` de LiteLLM |
| Together AI | « doesn't currently offer free trials » : au moins 15 $ de crédits à acheter avant de créer une clé ; un seul modèle gratuit affiché, un « Ternary Bonsai 27B » dont le contexte et les outils ne sont pas lus (pages relues le 2026-11-22) | Garde par défaut les prompts et les réponses et peut s'en servir pour améliorer ses produits ; la rétention zéro se règle dans les paramètres de l'organisation | Pas de palier gratuit, achat préalable ; fournisseur `together_ai/` de LiteLLM |

Pages officielles lues :

- Cohere : [Rate limits](https://docs.cohere.com/docs/rate-limits)
- Cohere : [Terms of use](https://www.cohere.com/terms-of-use)
- GitHub Models : [Prototyping with AI models](https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models)
- OpenCode Zen : [Zen](https://opencode.ai/docs/zen/), IteraCompute : [conditions de la promotion](https://www.iteracompute.com/free-tier-terms/), Nscale : [documentation](https://docs.nscale.com/)
- AWS : [Free Tier](https://aws.amazon.com/free/), [Choosing a plan](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html), les pages de tarifs de [Transcribe](https://aws.amazon.com/transcribe/pricing/), [Translate](https://aws.amazon.com/translate/pricing/), [Comprehend](https://aws.amazon.com/comprehend/pricing/), [Rekognition](https://aws.amazon.com/rekognition/pricing/), [Textract](https://aws.amazon.com/textract/pricing/) et [SageMaker](https://aws.amazon.com/sagemaker/ai/pricing/), et [Kiro](https://kiro.dev/pricing/)

[itsfree.ai](https://itsfree.ai/) n'est pas un fournisseur : c'est un annuaire statique, tenu par un seul développeur, sans API, qui sert de source de pistes (page relue le 2026-11-24).
- Hugging Face Inference Providers : [Pricing](https://huggingface.co/docs/inference-providers/pricing)
- Chutes : [Pricing](https://chutes.ai/pricing)
- Ollama Cloud : [Pricing](https://ollama.com/pricing)
- Moonshot / Kimi : [Limits](https://platform.kimi.ai/docs/pricing/limits)
- Alibaba Model Studio : [New free quota](https://www.alibabacloud.com/help/en/model-studio/new-free-quota)
- SiliconFlow : [Pricing](https://www.siliconflow.com/pricing)
- Vercel AI Gateway : [Pricing](https://vercel.com/docs/ai-gateway/pricing)
- Hyperbolic : pages « Account management » et « Inference overview » de sa documentation, et ses conditions d'utilisation
- Novita AI : pages « Rate limits » et « FAQ » de sa documentation
- AI21 : page « Pricing », page « Usage and cost » de sa documentation et ses conditions d'utilisation
- Nebius Token Factory : pages « Billing » et « Legal quick guide » de la documentation de Token Factory
- Fireworks : pages « Pricing », « Account quotas », « What happens when I finish my $1 credit » et « Data handling » de sa documentation
- Together AI : pages « Pricing », « Billing and credits » et « Privacy and security » de sa documentation

**Groupe 4 -- pistes non vérifiées.** Aucune n'est un verdict.

| Fournisseur | Ce qui a été vu | Ce qui manque |
| --- | --- | --- |
| LLM7, Pollinations, AxForge, Gonka Broker, GitCode | Pages officielles vides ou sans chiffres | Tout |
| ModelScope (Alibaba) | La page officielle des limites (lue le 2026-11-22) exige un compte lié à un compte Alibaba Cloud ayant passé la vérification d'identité ; le quota de 2 000 appels par jour n'y figure plus, l'usage se compte en « magicube » (0,5 à 2 par appel selon le modèle) sans que le montant gratuit y soit publié (une sonde tierce de septembre 2026 dit 200 par jour) ; gratuit, non commercial, « pas pour des tâches en ligne à forte concurrence ou sous SLA » | Si la vérification d'identité accepte un étranger (en Chine elle demande normalement une pièce d'identité chinoise), les conditions, et le lieu de traitement des données (probablement la Chine) |

Pages officielles lues :

- Together AI : [Pricing](https://www.together.ai/pricing)
- Fireworks : [Rate limits](https://docs.fireworks.ai/guides/quotas_usage/rate-limits)

#### Kilo Gateway : des modèles gratuits sans clé, une limite par adresse IP

`LiteLLM_config.yaml.j2` route aussi des modèles gratuits de Kilo Gateway, **sans clé et sans compte**. Comme celles d'OmniRoute, ses entrées sont toujours rendues, portent un `api_key` littéral et n'appartiennent à personne : `check_LiteLLM_account_isolation.py` les exempte pour la même raison. Aucune variable n'est ajoutée au rôle. Les pages citées ci-dessous sont celles du registre plus haut, lues le 2026-11-22.

- **Une limite par adresse IP, pour toute la machine.** La page « Authentication » de la documentation du service réserve l'accès anonyme aux modèles gratuits et le limite à 200 requêtes par heure et par adresse IP. C'est un seul compteur, partagé par toutes les entrées Kilo de toutes les cascades : un second quota à côté des 50 requêtes par jour d'OpenRouter, tant que le compteur et chaque modèle gratuit durent. La page « Models and providers » dit que la disponibilité des modèles gratuits change.
- **Les prompts sont journalisés et peuvent servir à l'entraînement.** Le catalogue marque chaque modèle gratuit comme pouvant être entraîné sur les prompts, la page « Models and providers » le dit de « Auto Free », et elle dit des points d'accès gratuits de NVIDIA : « Trial use only - do not submit personal or confidential data ». C'est accepté ici comme pour les autres modèles gratuits, et aucune voie n'est réservée aux données sensibles.
- **Les conditions sont lues, pas validées.** La page « Terms », mise à jour le 2026-11-02, limite un compte à une entité (aucun n'est utilisé) et interdit les outils d'aspiration automatique et le contournement des contrôles d'accès, ce qu'une passerelle qui appelle l'API documentée est tenue de ne pas être. Sa clause sur la licence des données n'a été lue que dans un résumé : **non vérifiée**.
- **L'en-tête `Authorization` est vidé.** Le fournisseur `openai/` de LiteLLM envoie `Authorization: Bearer <api_key>`, et le service a répondu `401 INVALID_TOKEN` à ce marqueur envoyé ainsi (essayé à la main), alors qu'il sert un appel dont l'en-tête est vide ou absent. Chaque entrée vide donc l'en-tête par `extra_headers`, et `check_compose_template.py` y tient toute entrée posée sur le point d'accès du service, faute de quoi le `401` ne se verrait qu'à l'exécution.
- **Où chaque modèle est placé.** Les modèles que le template sert déjà par OpenRouter et que le catalogue de Kilo liste gratuits (Nemotron 3 Ultra, Nemotron 3 Nano Omni, Nemotron 3.5 Lightning, Nemotron 3.5 Super VL, Particle-1, ERNIE 5.5 Flash et LFM 3 1.7B) ont leur entrée Kilo juste derrière leur jumeau, dans chaque cascade où il figure ; que ce soient les mêmes poids des deux côtés ne repose que sur l'identifiant. `beam-kilo` (Beam 1.0, de Reflection) n'a pas de jumeau : ses chiffres (Artificial Analysis et Epoch AI, lus le 2026-11-21) le placent devant les entrées Nemotron dans `Auto-Pro` et devant `nemotron-super-vl-free` dans `Auto-Flash`. `flint-kilo` et `glyph-cluster-kilo` n'ont aucun chiffre : ils terminent les entrées gratuites de `Auto-Flash`, suivis de `dots-3-note-preview-free` et de son jumeau `dots-3-note-preview-kilo` (Dots3-Note Preview, de Dots Studio : gratuit jusqu'au 31 décembre d'après les deux catalogues, aucun chiffre, lu le 2026-11-23). `Auto-Code` et `Auto-Claude-Code` n'ont aucune entrée Kilo : `Auto-Claude-Code` ne tient que des fournisseurs à clé, et Beam n'est noté par Epoch AI que sur un des cinq bancs de `Auto-Code`. Le modèle `ling-3.2-flash:free` reste commenté, avec sa raison : il n'a répondu à aucune des sept requêtes faites à la main le 2026-11-22, toutes refusées par un `429`.
- **Le contrôle de dérive lit cette liste.** Le catalogue de Kilo se lit sans clé et marque chaque modèle gratuit (`isFree`) : un modèle qu'il ne liste plus est supprimé par la pull request des suppressions, comme chez OpenRouter, sur sa seule liste, car Kilo ne documente aucune route pour interroger un modèle seul ; un modèle encore listé mais plus gratuit est signalé dans les retraits annoncés, et jamais supprimé ; un nouveau modèle gratuit est proposé par l'une des deux pull requests d'ajouts, avec son `api_key` littéral et l'en-tête `Authorization` vidé. `kilo-auto/free` et `openrouter/free`, qui choisissent un modèle à chaque requête, sont écartés par une ligne `drift-ignore` du template.

#### OVHcloud AI Endpoints : des modèles gratuits sans clé, deux requêtes par minute et par modèle

`LiteLLM_config.yaml.j2` route aussi des modèles de texte d'OVHcloud AI Endpoints, **sans clé et sans compte**, sur le modèle de Kilo Gateway : entrées toujours rendues, nommées `<modèle>-ovh`, `api_key` littéral, aucune variable ajoutée au rôle, exemptées par `check_LiteLLM_account_isolation.py` pour la même raison. Les pages citées sont celles du registre plus haut, lues le 2026-11-22.

- **Une limite par adresse IP et par modèle, partagée par toute la maison.** Le service répond sans clé à 2 requêtes par minute, par adresse IP et par modèle : un appel anonyme à gpt-oss-120b a répondu, un second dans la minute a reçu un `429`. Cette limite est une observation, **écrite sur aucune page lue**. Chaque entrée a son compteur, et chaque compteur est celui de l'adresse IP de la machine, donc de tout ce qui passe par la passerelle : deux requêtes simultanées sur le même modèle suffisent à épuiser son quota. C'est un dernier recours, pas une capacité.
- **Pourquoi sans clé.** Avec une clé le plafond passe à 400 requêtes par minute, mais une clé exige un moyen de paiement sur un projet Public Cloud et aucun plafond de dépense n'existe : le critère de la carte n'est pas rempli (voir le registre). Aucun compte n'est donc utilisé et aucune variable de clé n'existe.
- **Les données.** La page du service dit qu'il est « hosted and run in the European Union », que « your data is never used to train our models » et qu'OVHcloud ne garde que ce qui sert à la facturation (« zero data retention »). Cette page décrit le service payant : qu'elle vaille pour l'accès anonyme **n'est pas vérifié**, et les conditions d'usage de l'accès anonyme n'ont pas été lues.
- **L'en-tête `Authorization` est vidé, par précaution.** Chez Kilo, un jeton factice envoyé en `Bearer` a été refusé par un `401`. Que OVHcloud refuse aussi un jeton factice **n'a pas été essayé** contre son vrai point d'accès (l'adresse de la session est partagée et reçoit des `429`) : la forme sûre, l'en-tête vide, est donc celle de Kilo, et `check_compose_template.py` y tient toute entrée posée sur un point d'accès sans clé, Kilo et OVHcloud ensemble.
- **Quels modèles.** Seuls ceux dont la fiche du catalogue public annonce « Function Calling » et qui sont des modèles de conversation : DeepSeek V4.1 Flash, Qwen3.5 397B, gpt-oss-120b et gpt-oss-20b, Qwen3.8 27B, Qwen3.6 35B A3B, Qwen3.5 9B, Nemotron 3 Omni 30B et Nano 30B, Mistral Small 3.2, Gemma 4 26B A4B, Olala mini et Laguna XS 2.1. Que l'appel d'outils fonctionne réellement sur chacun n'a **pas été essayé** : la fiche l'annonce, rien d'autre. Laissés de côté : Llama 3.3 70B et Qwen3.6 27B, marqués « Being retired » (fin de vie le 2027-02-10, à remplacer le jour venu) ; Olala summarise et translate, spécialisés ; Qwen3-VL 30B, un modèle de vision à 32K de contexte ; Qwen2.5-VL 72B, retiré et sans appels d'outils ; les modèles de garde, d'embeddings, de parole et d'image.
- **Où chaque modèle est placé.** En queue des listes gratuites de `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` et `Auto-Code`, derrière tous les membres gratuits, Kilo compris, et devant les fournisseurs payants : 2 requêtes par minute en font le dernier recours gratuit, et la règle déjà suivie pour Kilo et OmniRoute est de mettre les gratuits avant les payants. Dans `Auto-Pro`, les trois plus gros (DeepSeek V4.1 Flash, Qwen3.5 397B, gpt-oss-120b) ; dans `Auto-Flash`, ces trois puis Qwen3.8 27B, Qwen3.6 35B, Nemotron 3 Omni et Mistral Small 3.2, après le routeur gratuit d'OpenRouter ; dans `Auto-Flash-Lite`, gpt-oss-20b, Gemma 4 26B, Nemotron 3 Nano, Qwen3.5 9B et Olala mini, après les entrées gratuites de Cloudflare ; dans `Auto-Code`, les cinq plus capables puis Laguna XS 2.1, après les entrées gratuites de Z AI. Les rangs suivent la taille des modèles : aucun chiffre d'Artificial Analysis ni d'Epoch AI n'a été relu pour eux, et le rapport des contrats par routeur dira, plancher par plancher, ce qui s'écarte. Comme aucun membre gratuit à clé ne les précède quand `Auto-Code` n'a que la clé de Mistral ou de DeepSeek, DeepSeek V4.1 Flash d'OVHcloud devient la tête de `Auto-Code` : la table `head` du template le dit.
- **Jamais dans `Auto-Claude-Code`.** Ce routeur ne tient que des fournisseurs à clé, et deux requêtes par minute ne portent pas un agent : `check_compose_template.py` refuse tout membre d'une entrée sans clé dans `Auto-Claude-Code`.
- **Le contrôle de dérive lit cette liste.** Le catalogue d'OVHcloud se lit sans clé : un modèle qu'il ne liste plus est supprimé par la pull request des suppressions, sur sa seule liste, et un nouveau modèle est proposé par la pull request des modèles à vérifier, jamais par celle des modèles prêts, car l'API donne un prix par jeton et ne dit rien de l'accès sans clé que les entrées utilisent. Une fin de vie annoncée (le 2027-02-10 pour deux modèles) n'est pas dans la réponse : elle reste à suivre à la main.

**Les dépôts jusqu'à 10 €, relus le 2026-11-22.** Taux supposé : 1 € = 1,15 $. Un crédit qui expire dans un an ou deux n'est pas « à vie » : il sort de la règle. « Environ N jours » veut dire un million de jetons par jour (quatre d'entrée pour un de sortie, sans remise de cache) au prix de la page citée : un ordre de grandeur. Les lignes marquées « résumé » viennent d'un résumé de page et non de la page elle-même.


| Fournisseur | Ce que le dépôt achète | Expiration, remboursement, plafond | Verdict |
| --- | --- | --- | --- |
| OpenRouter | 10 crédits achetés au total (achat minimal de 5 $, frais de 5,5 % avec un minimum de 0,80 $ : environ 10,80 $, soit 9,4 €, pour 10 $ de crédit) font passer les modèles `:free` de 50 à 1 000 requêtes par jour, 20 par minute dans les deux cas, pour tout le compte ; les modèles `:free` ne consomment pas le crédit | Le palier tient au total de crédits achetés et non au solde, d'après la page des limites ; le crédit lui-même peut expirer 365 jours après l'achat, ce qui ne devrait pas retirer le palier (lecture, non essayée) ; remboursement dans les 24 heures seulement, frais non remboursables ; plafond de dépense par clé possible | **Rentable.** Le seul dépôt qui multiplie par vingt un palier gratuit déjà routé, et le crédit reste une réserve payante très bon marché (environ 134 jours sur DeepSeek V4.1 Flash, d'après la liste de prix de l'API). Coût : environ 9,4 €, une fois. Le palier de 10 crédits ne rapporte qu'une fois les 50 requêtes par jour réellement atteintes, le crédit servant alors de marge. La clé que la passerelle utilise gagne à porter une limite de dépense de 0 $ sur OpenRouter (page des limites relue le 2026-11-24 : une clé dont la limite est épuisée reçoit un 402) : un modèle payant appelé par erreur ne peut alors pas dépenser le crédit |
| Google Gemini API | 5 $ minimum, prépayé (résumé) ; ouvre les modèles que le palier gratuit ne sert pas ; un projet gratuit peut rester à côté | Expire au bout de 12 mois, sans remboursement ; le solde est un arrêt dur | Non : le crédit expire au bout d'un an, ce qui sort de la règle du dépôt unique à vie, et c'est du crédit dépensé (environ 72 jours sur le modèle lite le moins cher, 15 sur le suivant), pas un palier gratuit de plus. Et ne jamais lier la facturation au projet de la clé gratuite : voir « La facturation » dans la section des quotas Gemini |
| OVHcloud AI Endpoints | Aucun dépôt : un moyen de paiement sur un projet Public Cloud, facturé à terme ; la clé fait passer 2 requêtes par minute par adresse IP et par modèle à 400 par minute | Aucun plafond de dépense trouvé | Non : sans plafond, le critère de la carte n'est pas rempli ; reste sans clé |
| Scaleway Generative APIs | Aucun dépôt, facturé à terme ; 200 000 jetons par minute et par modèle une fois le moyen de paiement validé | Alertes de facturation seulement, pas de plafond dur ; le million de jetons gratuits n'est pas dit mensuel | Non : rien de récurrent, aucun plafond |
| Cerebras | Le premier achat ouvre un niveau sans plafond de jetons par jour ; l'essai de 5 $ garde ses 30 jours | Crédits achetés valables un an, achats définitifs (résumé) ; minimum non trouvé | Non : le crédit expire au bout d'un an, et c'est du paiement à l'usage |
| Cloudflare Workers AI | Pas un dépôt : l'abonnement Workers Paid coûte 5 $ par mois et les 10 000 neurons gratuits par jour sont les mêmes qu'en gratuit ; l'abonnement ou des crédits prépayés d'AI Gateway (facturation unifiée) ouvrent seuls les modèles à accès payant (Inkling, GLM-5.x, Kimi K2.6 et K2.7, DeepSeek V4.x), une carte seule n'ouvre rien (page des tarifs relue le 2026-11-24) | Abonnement mensuel ; les crédits sont dépensés en jetons | Non : la voie des crédits est du crédit dépensé, une réserve payante, jamais un palier gratuit |
| SambaNova | Les crédits n'achètent que des jetons ; voir la ligne du registre pour l'essai du jour | Prépayé, le solde est le plafond ; minimum et expiration non lus | Non en ticket d'entrée ; à la limite en réserve payante (environ 39 jours sur gpt-oss-120b) |
| Fireworks | Un moyen de paiement et des crédits font passer de 10 à 6 000 requêtes par minute ; rien de récurrent (résumé) | Plafond de dépense mensuel ; minimum et expiration non lus | Non |
| Together AI | Premier achat de 15 $, au-dessus du plafond ; rien de gratuit | Aucune expiration affichée | Non |
| Vercel AI Gateway | Acheter des crédits fait passer au niveau payant et **fait perdre le crédit gratuit mensuel** ; ce crédit exige un moyen de paiement lié et son montant n'est pas publié sur les pages lues | | Ne pas déposer ; reste un candidat sans dépôt si lier une carte convient (non essayé) |
| Groq | Aucun dépôt : le plan Developer facture à terme et monte les limites (chiffres non lus) ; un plafond de dépense mensuel existe | Quitter le palier gratuit pour en profiter | À la limite : seulement si les limites du palier gratuit deviennent le goulot |
| Hugging Face, Ollama Cloud, DeepSeek, Mistral, SiliconFlow, Hyperbolic | Un dépôt n'achète que des jetons payants, aucune allocation récurrente | | Non |
| AMD Radeon Token Factory | Une allocation quotidienne gratuite par clé, de taille non publiée ; la première clé exige l'échange d'un code, dont aucun moyen public d'obtention n'est trouvé ; le « 10 $ par jour » d'un annuaire ne figure pas sur la page officielle | | Un dépôt n'y change rien ; non vérifié, non pris |
| Free AI | Plan gratuit annoncé : 1 000 requêtes par mois et 30 000 jetons par jour pour tout le compte, un seul modèle propre (un Qwen), les autres étant des relais gratuits d'OpenRouter ; les pages se contredisent sur l'obtention d'une clé gratuite | | Non pris : environ 33 requêtes par jour, aucun quota propre sur les relais, clé gratuite non vérifiée |
| AnyModel | La route gratuite `am/free` exige un solde positif dont le minimum n'est pas indiqué ; revendeur qui relaie des paliers gratuits (aucun quota propre), paiement en cartes russes ou en cryptomonnaie, exploitant non vérifiable | | Non |
| Cent AI | Revendeur prépayé (dépôt minimal de 1 $) ; un modèle gratuit « jusqu'au 30 novembre » pour tous, puis un pool gratuit quotidien partagé, premier arrivé premier servi, sans allocation par compte | Crédit d'inscription unique de 30 jours | Non : aucun dépôt n'est nécessaire, le modèle gratuit étant routé sans rien déposer (ligne du groupe 1) ; le modèle gratuit « événement » tiré chaque jour, sous un identifiant qui change, n'est pas routable |
| Puter, Rewind AI, Top Tools AI | Puter : ses points d'accès compatibles OpenAI refusent les comptes gratuits ; Rewind AI : le moteur de Free AI avec 5 000 jetons par jour ; Top Tools AI : revendeur à forfait mensuel | | Non |

#### Requesty, une seconde source des modèles `:free` d'OpenRouter

Requesty est une passerelle : elle relaie chaque requête vers le fournisseur du modèle. LiteLLM n'a pas de fournisseur de ce nom, donc chaque entrée est écrite `openai/<fournisseur>/<modèle>` avec un `api_base`, comme celles d'OmniRoute : LiteLLM ne retire que le préfixe `openai/`, et le reste, barre oblique comprise, part chez Requesty comme identifiant de modèle, que sa documentation demande sous la forme `fournisseur/modèle`. Cette lecture a été vérifiée dans le code de LiteLLM, appels de fonctions (`tools`) compris ; si chaque modèle les accepte chez Requesty, aucune page lue ne le dit.

Des entrées pour les seuls modèles que le `model_list` sert déjà par OpenRouter, chacune juste derrière son jumeau OpenRouter dans les cascades où il a une place : Nemotron 3 Ultra et Nemotron 3 Nano Omni (raisonnement) dans `Auto-Pro`, Gemma 4 31B dans `Auto-Flash`, Nemotron 3.5 Lightning dans `Auto-Flash-Lite`. Que ce soient les mêmes poids des deux côtés ne repose que sur les noms. Les autres modèles gratuits de la page « Free models » ne sont pas routés : aucun n'est un modèle que le `model_list` sert déjà. Aucune entrée n'entre dans `Auto-Code` ni `Auto-Claude-Code`, et la présence d'une clé Requesty seule ne fait donc pas exister `Auto-Claude-Code`.

| Point | Ce que les pages lues disent (relues le 2026-11-22) |
| --- | --- |
| Limites | Par organisation : 200 requêtes par jour et 20 par minute pour une organisation neuve, 1 000 et 60 pour une organisation qui paie, « across all free models combined », remis à zéro chaque jour. Un quota à part de celui d'OpenRouter |
| Durée | Gratuit « for now » : un changement sera annoncé dans le journal des modifications avant d'entrer en vigueur. Un modèle payant répond 402 quand le solde est nul |
| Quota commun | Toutes les entrées puisent dans le même quota : une place Requesty n'est une seconde source que tant qu'il dure |
| Point d'accès | Le point d'accès européen est écrit en dur dans les entrées (Francfort, d'après la page « Data privacy »). Que tous les modèles gratuits y soient servis n'est **pas vérifié** ; la base américaine est un changement d'une ligne par entrée |
| Données | Les requêtes et réponses ne sont pas stockées sauf si la journalisation est activée, et Requesty n'entraîne pas de modèle dessus ; ce que le fournisseur en amont conserve dépend de lui |
| Compte | Un seul. Les conditions d'utilisation n'ont **pas** été lues par la session qui a écrit ceci (la page n'a rendu aucun texte) : rien n'est établi sur plusieurs comptes, le contournement des limites, les passerelles ou la revente |

### Choisir à la place du client : le routeur `Auto`

Un client qui ne veut pas choisir son routeur (LibreChat en laisse le choix à la personne, un agent doit le coder en dur) demande `Auto`. LiteLLM note chaque requête localement avec le classement heuristique de son `complexity_router` (longueur, présence de code, mots de raisonnement, termes techniques, quelques motifs de plusieurs étapes), en moins d'une milliseconde, sans appeler un modèle ni calculer un embedding, puis réécrit le modèle de la requête en celui du niveau obtenu. Un client qui veut un routeur précis le nomme toujours.

| Niveau | Score (bornes par défaut de LiteLLM, lues le 2026-11-23) | Routeur visé |
| --- | --- | --- |
| `SIMPLE` | moins de 0,15 | `Auto-Flash-Lite` |
| `MEDIUM` | de 0,15 à 0,35 | `Auto-Flash` |
| `COMPLEX` | de 0,35 à 0,60 | `Auto-Pro` |
| `REASONING` | plus de 0,60 | `Auto-Pro` : une seule cascade sert les deux niveaux du haut, et une copie pour le dernier serait une seconde liste à tenir au même niveau |

**Les niveaux nomment des routeurs, pas leurs têtes, et c'est ce qui garde les cascades.** LiteLLM cherche les replis sous le nom qui a été demandé après le choix, donc un niveau qui nomme `Auto-Flash` retombe sur la cascade d'`Auto-Flash`, alors qu'un niveau qui nommerait directement le modèle de tête n'aurait plus aucun repli. Mesuré le 2026-11-23, avec des fournisseurs simulés dont la tête répond 429 et dont le deuxième membre échoue lui aussi : sur chacun des quatre niveaux, en flux ou non, la requête passe au premier membre qui répond, comme quand le routeur est nommé. Même résultat avec le fichier rendu avec toutes les clés, chargé dans le routeur de LiteLLM et chaque tête en échec : le membre qui répond est le même par `Auto` et par le routeur nommé. Le niveau est décidé avant l'appel, donc un membre qui échoue ne fait pas descendre ni monter la requête de niveau.

**Ce que `Auto` ne demande pas.** Ni Redis, ni base, ni licence : le code de la voie heuristique n'a aucune barrière de licence ni d'offre payante (lu le 2026-11-23), un proxy démarré avec sa base et sans clé de licence a servi les trois niveaux (fournisseurs simulés), et un autre, sans base, a chargé le fichier rendu avec toutes les clés. Seul le réglage du classement (poids, bornes, mots-clés) est limité par la licence de LiteLLM, à un routeur modifié sans licence : aucun n'est posé ici, et `check_compose_template.py` refuse tout réglage.

**Ce qu'une clé doit savoir.** LiteLLM saute un repli que l'appelant n'a pas le droit d'appeler : une clé qui nomme seulement `Auto` (ou seulement un routeur) reçoit le 429 de la tête au lieu de la cascade (mesuré le 2026-11-23, et vrai d'un routeur nommé directement comme d'`Auto`). La clé doit donc porter aussi les membres des cascades, c'est-à-dire le groupe `LLM`. C'est pourquoi `Auto` est une **entrée** du `model_list`, dans le groupe `LLM` comme tout ce qui n'est pas un alias de tête : une clé limitée à `LLM` l'atteint et la liste, celle d'un compte LibreChat sans que `Artificial_Intelligence_LibreChat_gateway_key_models` la nomme. Elle n'est pas dans `Artificial_Intelligence_Claude_code_additional_models` : la clé de l'agent est limitée à des routeurs, et la cascade d'`Auto-Claude-Code` est tenue à des appels d'outils stricts que celle d'`Auto-Flash-Lite` ne garantit pas.

**Deux réglages par défaut sont coupés**, parce qu'ils font ce que cette passerelle ne veut pas :

- `max_tokens_from_tier_model` remplace le `max_tokens` du client par le plafond de sortie de la tête du routeur choisi (mesuré le 2026-11-23 : un appel qui en demandait 100 est arrivé chez la tête avec son plafond), si bien qu'une réponse courte demandée n'est pas respectée et que le quota de jetons de la tête sert à une longue ;
- `context_compaction` fait résumer par un modèle des niveaux une conversation qui approche la limite du modèle choisi : un appel que personne n'a demandé, et une réécriture de ce que le client a envoyé.

**L'heuristique se trompe, et c'est le prix de l'absence d'appel.** Elle lit des mots, pas la difficulté. Mesuré le 2026-11-23 : « hi » et « What is the capital of France? » vont à `SIMPLE` ; demander d'écrire en Python une fonction qui lit un CSV va à `MEDIUM` ; concevoir une classe de pool de connexions réparti avec contrôle de concurrence va à `COMPLEX` ; un « think step by step » sur un limiteur de débit réparti va à `REASONING`. Mais « Explain how a hash map handles collisions and compare chaining with open addressing », une question de fond sans mot de code ni terme technique de la liste, a un score de 0 et va à `SIMPLE`. Un client qui sait que sa question est difficile nomme `Auto-Pro`.

**Un niveau qui nomme un groupe que personne ne sert n'est pas refusé au chargement.** LiteLLM charge le fichier et fait échouer les requêtes qui tombent sur ce niveau (mesuré le 2026-11-23). L'entrée n'est donc rendue que lorsque les trois routeurs le sont, et deux contrôles tiennent le reste : `check_compose_template.py` exige `Auto` exactement quand ses trois routeurs sont servis, avec ses niveaux, ses deux réglages coupés, aucune clé, aucune cascade ni alias, et rien d'autre dans sa configuration ; `check_LiteLLM_account_isolation.py` ne la compte pas comme une entrée sans compte (elle n'appelle aucun fournisseur) et refuse un niveau qui nomme un groupe non déclaré, un autre routeur de ce genre, ou des groupes de comptes différents.

**Ce qui a été écarté.** Un classifieur par modèle (un appel de plus par requête, sur un quota gratuit), la correspondance sémantique par embeddings (un appel d'embedding par requête, sur le quota Gemini) et l'ancien routeur sémantique (déprécié par LiteLLM) : la voie heuristique coûte zéro appel, et les trois autres se rouvrent si elle se révèle trop souvent fausse.

### La transcription de la parole : le routeur `Auto-STT`

Un client qui envoie de l'audio à `/v1/audio/transcriptions` demande le modèle `Auto-STT`, qui est un alias comme `Auto-Pro` ou `Auto-Flash` : celui de la tête de sa cascade dont le fournisseur a une clé, et rien du tout quand aucun membre n'a de clé. La cascade est `whisper-large-v3-groq`, puis `whisper-large-v3-turbo-groq`, puis `gemini-3-5-transcribe`, puis `voxtral-mini-mistral` en dernier recours payant. Ses entrées portent `model_info.mode: audio_transcription`, et `check_compose_template.py` refuse une cascade `Auto-STT` qui contient un modèle d'un autre mode, une cascade de texte qui contient un modèle audio, un `Auto-STT` servi sans clé de Groq, de Gemini ni de Mistral et un alias qui n'est pas la tête de sa cascade. Aucune variable n'est ajoutée : les clés sont celles de Groq, de Gemini et de Mistral.

L'ordre n'est classé par aucun script et ne répond à aucun contrat : il est décidé à la main, par le taux d'erreur sur les mots que Groq publie sur sa page « Speech to Text » (10,3 % pour `whisper-large-v3`, 12 % pour `whisper-large-v3-turbo`, relue le 2026-11-22), le modèle payant passant après les trois gratuits, et celui de Google après ceux de Groq à cause de ce que son palier gratuit fait de l'audio (voir le groupe 1). Les deux modèles de Groq sont deux entrées pour que chacun ait son propre quota. Le code de LiteLLM a été lu pour s'assurer que le routeur applique les cascades de repli et les alias de groupe aux appels de transcription comme à ceux de chat : la route `/audio/transcriptions` appelle `atranscription`, qui passe par la même marche de repli que `aembedding` et `aspeech`, sous le nom demandé.

**Ce qui n'est pas établi.** Groq ne nomme pas le français, seulement « multilingual », et ne donne aucun taux par langue ; le tableau de limites de sa page affiche 20 requêtes par minute et 7,2K secondes d'audio par heure pour les deux modèles, sans que le plan auquel il se rapporte soit établi ; son corps de fichier est limité à 25 Mo sur l'offre gratuite. Le prix de Voxtral par minute, une éventuelle offre gratuite et la politique sur les données de l'API de Mistral n'ont pas été trouvés sur ses pages.

**Groupe 1 -- utilisés aujourd'hui.**

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Groq (`whisper-large-v3`, `whisper-large-v3-turbo`) | Palier gratuit, route compatible OpenAI, `groq/whisper-large-v3` dans LiteLLM | 25 Mo par fichier en gratuit, 100 Mo en payant, durée minimale facturée de 10 secondes ; limites par organisation. Ne conserve pas les données d'inférence par défaut, journaux jusqu'à 30 jours pour la fiabilité et les abus ; entraînement : non indiqué | Routé, têtes de la cascade, `whisper-large-v3` d'abord |
| Google Gemini (`gemini-3.5-transcribe`) | Gratuit sur le palier gratuit, `gemini/gemini-3.5-transcribe` dans LiteLLM ; clé déjà donnée | 3 requêtes par minute, 10 K jetons par minute et 25 requêtes par jour (voir « Gemini : conditions et quotas du palier gratuit »). **Hors de l'EEE, de la Suisse et du Royaume-Uni, le palier gratuit sert à améliorer les produits de Google et des relecteurs humains peuvent lire les entrées et sorties, ce qu'un enregistrement portant la voix de tiers ne supporte pas** | Routé en troisième, sur l'autorisation du mainteneur du 2026-11-22, qui accepte ce coût ; un appelant qui ne peut pas l'accepter ne donne pas de clé Gemini à une passerelle qui sert `Auto-STT` |
| Mistral (Voxtral) | Aucune pour l'API (voir le groupe 1 du registre ci-dessus) ; `mistral/voxtral-mini-latest` dans LiteLLM ; le français figure parmi les langues de la documentation | Prix par minute et politique sur les données de l'API : non trouvés | Routé en dernier, payant, comme Mistral dans les cascades de texte |

**Groupe 2 -- à ajouter.**

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Cloudflare Workers AI (`whisper-large-v3-turbo`) | 10 000 « neurons » par jour, soit environ 214 minutes d'audio par jour (46,6 neurons par minute, **calcul**, non publié tel quel) ; aucune rétention des données ni entraînement | Pas de route de transcription compatible OpenAI, et aucune chaîne `cloudflare/` de transcription dans LiteLLM : l'appel est natif | À ajouter le jour où la passerelle sait l'appeler ; **non routable aujourd'hui** |

**Groupe 3 -- écartés, avec la raison.**

| Fournisseur | Ce qui est offert | Raison de l'écart |
| --- | --- | --- |
| Azure AI Speech (palier F0) | 5 heures d'audio gratuites par mois, transcription en temps réel seulement | API native, aucune chaîne de transcription dans LiteLLM, compte Azure exigé |
| ElevenLabs Scribe | 10 000 crédits gratuits par mois à 330 crédits la minute, soit environ 30 minutes par mois (**calcul**) ; `elevenlabs/scribe_v1` dans LiteLLM | Trop étroit ; les conditions n'ont pas été lues |
| Deepgram | 200 $ de crédit une seule fois, sans carte ni échéance ; `deepgram/nova-2` dans LiteLLM ; ne stocke pas les transcriptions | Crédit unique, pas de palier durable ; le français n'est pas nommé |
| AssemblyAI, Speechmatics, Gladia | Crédits d'essai uniques (50 $, 100 $ pendant 12 mois, 50 EUR pendant un an) | Crédits uniques, aucune route dans LiteLLM |
| OpenAI (`gpt-transcribe`, `whisper-1`) | Aucune offre gratuite trouvée pour l'API ; `whisper-1` s'arrête le 2027-02-26 | Payant |
| AWS Transcribe | 60 minutes d'audio par mois pendant 12 mois à partir de la première requête (page des tarifs relue le 2026-11-24) | Essai limité dans le temps, API native, aucune chaîne de transcription dans LiteLLM |
| Soniox, Together AI, Fireworks, Hugging Face, Google Cloud Speech-to-Text | Aucun palier gratuit durable trouvé, ou non évalué (page de Fireworks introuvable, page de Google non récupérable ; Hugging Face : pas de crédit mensuel pour les comptes gratuits) | Rien d'établi ; aucun n'est un verdict |

Pages officielles lues le 2026-11-22 :

- Groq : pages « Speech to Text », « Rate limits » et « Your data » de sa documentation
- Mistral : la page de sa documentation sur la transcription audio (la liste des langues) et sa page « Pricing »
- Google Gemini API : pages « Pricing » et « Terms of service »
- LiteLLM : pages « Audio Transcription » et « Providers » de sa documentation
- Cloudflare Workers AI : sa page « Pricing » et la page de sa documentation sur les points d'accès compatibles OpenAI
- Azure AI Speech : page « Pricing » ; ElevenLabs : page « Pricing » ; Deepgram : page « Pricing »

### La synthèse vocale : le routeur `Auto-TTS`

`Auto-TTS` est un routeur comme `Auto-Pro` ou `Auto-Flash` -- un alias du premier membre de sa cascade dont la clé est donnée, avec sa cascade sous ce nom -- mais pour `/v1/audio/speech` : le client envoie le texte et un nom de voix, la réponse est un fichier audio. Il n'ajoute aucune variable : il existe dès que la clé Gemini est donnée, et n'existe pas sans elle. Il n'est ni classé ni soumis à un contrat de `.github/LiteLLM_router_contracts.yaml` (aucun classement de modèles vocaux n'a été lu ici) : l'ordre de sa cascade est décidé à la main, et `check_compose_template.py` tient le routeur aux mêmes règles que les cinq autres, plus une : un modèle vocal (`model_info.mode: audio_speech`) n'entre dans aucune cascade de texte, et un modèle de texte dans aucune cascade vocale.

**Ce qui a été lu dans le code de LiteLLM** (le 2026-11-22), parce que la documentation ne le dit pas : le routeur applique `fallbacks` et `model_group_alias` à `/audio/speech` comme au chat, et un essai contre un faux serveur Google l'a confirmé (une réponse 429 de la tête de cascade fait répondre le membre suivant). Les deux modèles Gemini sont servis par le fournisseur `gemini/` de LiteLLM, qui traduit les noms de voix d'OpenAI vers les voix de Gemini.

| Cascade `Auto-TTS` | Modèle | Pourquoi là |
| --- | --- | --- |
| 1 | `gemini-3.8-flash-tts` | Le modèle complet ; le français est listé comme pris en charge par la page « Speech » de la documentation de l'API Gemini |
| 2 | `gemini-3.8-flash-lite-tts` | Le même fournisseur, un modèle à lui : il répond quand le premier est refusé pour quota : Google compte le quota par modèle, 10 requêtes par jour chacun au palier gratuit |

Les trois modèles de préversion plus anciens ne sont pas routés : la page « Deprecations » les arrête au plus tôt le 2026-12-18.

**Ce que l'appelant reçoit.**

- Un fichier **WAV** par défaut (mono, 16 bits, un en-tête à 24 kHz écrit par LiteLLM : le débit réel de Google n'a pas été relu), ou du **PCM brut** avec `response_format: pcm`. Gemini ne produit rien d'autre : `mp3`, `opus`, `aac` ou `flac` sont refusés par LiteLLM avant tout appel, pour les deux membres à la fois. Convertir en mp3 ou en opus est l'affaire de l'appelant.
- Les noms de voix d'OpenAI `alloy`, `ash`, `ballad`, `cedar`, `coral`, `echo`, `fable`, `marin`, `onyx`, `sage`, `shimmer` et `verse` sont traduits en voix Gemini. **`nova` ne l'est pas** : LiteLLM le transmet tel quel, et ce n'est pas un nom de voix Gemini. Un nom de voix Gemini (`Kore`, `Puck`, `Sulafat`...) passe directement. La page « Speech » en liste trente, avec un descripteur de style et sans genre.
- Aucune voix masculine française n'est établie ici : ni la page de Gemini ni celle de Mistral n'en donne.

**Mistral Voxtral est servi mais n'est pas dans la cascade.** LiteLLM traduit six noms d'OpenAI vers des voix **anglaises** de Mistral et transmet les autres tels quels comme identifiants de voix Mistral, et la langue se règle par la voix, non par un paramètre : un appelant qui demande `alloy` pour du texte français serait lu par une voix anglaise. Ses voix françaises (quatre, toutes féminines : Marie, Manon, Lea, Camille) se demandent par leur propre identifiant, ce qu'une cascade partagée avec Gemini ne permet pas. L'entrée est laissée en commentaire dans `LiteLLM_config.yaml.j2`, avec cette raison.

**Les données.** Le palier gratuit de l'API Gemini n'est pas fait pour du texte sensible : hors de l'EEE, de la Suisse et du Royaume-Uni, le contenu sert à améliorer les produits de Google (voir « Gemini : conditions et quotas du palier gratuit »). Un texte qu'on ne veut pas voir réutilisé ne passe pas par `Auto-TTS` avec une clé du palier gratuit. Le quota de ces deux modèles est de 10 requêtes par jour chacun.

**Le registre des fournisseurs de synthèse vocale**, lu le 2026-11-22, dans le même ordre que celui des fournisseurs de texte. Les pages de LiteLLM listent comme fournisseurs de `/audio/speech` OpenAI, Azure OpenAI, Azure AI Speech, AWS Polly, Vertex AI, Gemini, ElevenLabs, MiniMax et Mistral : Groq, Cloudflare, Together, Deepgram, Cartesia et Edge n'y sont pas.

**Groupe 1 -- utilisés ou examinés.**

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Google Gemini API | Quota des services non payants, « free of charge with generous limits » d'après la page des tarifs ; 10 requêtes par jour et par modèle de synthèse | Format WAV ou PCM seulement ; deux voix par conversation au plus ; contenu réutilisé par Google sur le palier gratuit hors de l'EEE, de la Suisse et du Royaume-Uni | Routé, `gemini-3.8-flash-tts` puis `gemini-3.8-flash-lite-tts` |
| Mistral Voxtral | Aucune : la clé du dépôt est payante, le prix à la minute et un palier d'essai n'ont pas été trouvés | Sortie mp3, wav, pcm, flac ou opus ; la langue se règle par la voix ; quatre voix françaises, toutes féminines | Examiné, non routé (entrée commentée) : les noms de voix d'OpenAI y donnent des voix anglaises |

**Groupe 2 -- à ajouter.**

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| AWS Polly | Voix standard : 5 millions de caractères par mois sans date de fin affichée ; neuronales (1 million) et génératives (100 000) pendant les douze premiers mois seulement ; fournisseur natif de LiteLLM | Voix françaises masculines : Rémi (neuronale et générative), Mathieu (standard), Florian (générative), Liam (français canadien). Un compte AWS, donc une clé d'accès, un secret et une région : trois nouvelles variables ; la carte bancaire n'est pas indiquée | La meilleure piste vérifiée pour une voix masculine française ; pas construit ici, c'est un nouveau fournisseur |

**Groupe 3 -- écartés, avec la raison.**

| Fournisseur | Ce qui est offert | Raison de l'écart |
| --- | --- | --- |
| Groq | Orpheus, en anglais et en arabe (saoudien) ; 100 requêtes par jour et 3,6 K jetons par jour affichés pour l'anglais, plan non vérifié | Pas de français, et absent de la liste de LiteLLM pour `/audio/speech` |
| Cloudflare Workers AI | MeloTTS (`lang` à `fr` accepté) ; les modèles Aura n'ont pas le français | MeloTTS est marqué « Deprecated 11/20/2026 », donc déjà passé ; aucune route de type OpenAI ni chaîne LiteLLM |
| Cartesia | Plan gratuit de 20 000 crédits par mois (environ 20 000 caractères), français listé | Le plan gratuit n'a pas la licence d'usage commercial, la politique de confidentialité autorise l'entraînement sur le contenu avec une désactivation partielle, et les services sont « designed for users in the United States only » |
| Deepgram Aura | 200 dollars, une seule fois | Crédit unique ; pas de français indiqué |
| Together AI, OpenAI | Aucune | Payants (Kokoro 4 dollars le million de caractères, Orpheus 15 ; `tts-1` 15 dollars le million) |
| edge-tts | Client non officiel du service de lecture à voix haute de Microsoft Edge : sans clé, de nombreuses voix françaises dont des masculines | Usage non officiel d'un service de Microsoft ; son README ne dit rien des conditions, de la stabilité ni des limites |

**Groupe 4 -- pistes non vérifiées.** Aucune n'est un verdict.

| Fournisseur | Ce qui a été vu | Ce qui manque |
| --- | --- | --- |
| Azure AI Speech (palier F0) | 0,5 million de caractères neuronaux gratuits par mois | Les prix, la liste des voix françaises, et un compte Azure |
| ElevenLabs | Un résumé de la page des tarifs parle de 10 000 crédits par mois en gratuit, soit environ 10 000 caractères | Rien ne le confirme pour la synthèse, ni l'usage commercial sur le plan gratuit |

**La synthèse locale.** Piper (qui a des voix françaises masculines) ou Kokoro tournant sur le processeur du serveur est la voie saine pour une voix masculine française, sans envoyer de texte à un tiers : elle est suivie par une issue du dépôt, et n'est pas promise ici.

Pages officielles lues :

- Google Gemini API : pages « Speech », « Pricing », « Deprecations » et ses conditions d'utilisation
- Mistral : documentation du modèle Voxtral de synthèse vocale
- LiteLLM : page « Text to Speech » de sa documentation, et son code source
- AWS Polly : pages « Pricing » et des voix
- Groq : page « Text to Speech » de sa documentation
- Cloudflare Workers AI : page du modèle MeloTTS et page « Models »
- Cartesia : pages des tarifs et de confidentialité
- Deepgram, Together AI, OpenAI : pages des tarifs
- Azure AI Speech : page « Pricing »
- ElevenLabs : page des tarifs
- edge-tts : son README

### Décider et extraire : les routeurs `Auto-Decision` et `Auto-Extraction`

Deux routeurs qui ne sont pas du chat, servis dès que la clé Cloudflare est donnée, et faits pour les automatisations (n8n, par exemple) plutôt que pour une conversation. Ils ont leurs propres routes de LiteLLM, et non `/v1/chat/completions` : les nœuds « OpenAI » de n8n ne savent pas les appeler, un nœud « HTTP Request » avec la clé de la passerelle en `Authorization: Bearer` le fait.

| Routeur | Route | Ce qu'on envoie | Ce qu'on reçoit | Cascade |
| --- | --- | --- | --- | --- |
| `Auto-Decision` | `POST /v1/systemone` | un `state` (texte, objet ou liste) et des `questions` typées : `noul` (oui ou non), `choice` (une option parmi des `criteria`), `score` (un niveau sur une échelle) | une probabilité pour chaque réponse permise de chaque question | Clef (27B), puis Clef Omni |
| `Auto-Extraction` | `POST /v1/extraction` | un `state` (texte), éventuellement des images ou des PDF, et des `fields` typés : texte, date, nombre, liste, estimation dans un intervalle | chaque valeur, avec sa confiance, ou `null` quand le texte ne la donne pas | Clairic, puis Clairic Flash |

Exemple, le tri d'un message d'assistance :

```bash
curl -s "$GATEWAY/v1/systemone" -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" -d '{
  "model": "Auto-Decision",
  "state": "Le paiement échoue pour tous les clients depuis une heure.",
  "questions": {
    "urgent": {"type": "noul", "instructions": "La demande est-elle urgente ?"},
    "equipe": {"type": "choice", "criteria": {"facturation": "Paiements et remboursements", "technique": "Pannes et erreurs"}},
    "gravite": {"type": "score", "criteria": ["Aucun impact", "Mineur", "Majeur", "Critique"]}
  }
}'
```

**Un repli doit tout accepter de ce qu'accepte la tête**, pour que la bascule ne se voie pas. Clef Omni prend le texte et les images comme Clef, avec 64 000 jetons de contexte contre 65 536 : seule une requête entre les deux échouerait sur lui. Clef Flash (9B) n'a que 24 576 jetons : il reste hors de la cascade et s'appelle par son nom, `clef-flash-cloudflare`. Clairic Flash, lui, prend exactement ce que prend Clairic.

**Le son et la vidéo** : seul Clef Omni les lit (quatre extraits audio de cinq minutes, deux vidéos d'une minute au plus) ; une requête qui en porte demande `clef-omni-cloudflare` par son nom.

**Ce qu'ils coûtent** : les jetons d'entrée seulement, sur les 10 000 neurons par jour du compte Cloudflare, partagés avec ses modèles de texte. Au prix lu le 2026-11-23, cela fait au plus environ 460 000 jetons par jour pour Clef, 730 000 pour Clef Omni, 2,9 millions pour Clef Flash, 1,1 million pour Clairic et Clairic Flash (460 000 pour Clairic après le 2026-12-01, quand son prix promotionnel s'arrête).

**Ce qui n'est pas vérifié** : ces routes n'ont pas été appelées depuis une passerelle réelle. Qu'un routeur à replis s'applique à `/v1/systemone` et à `/v1/extraction` comme au chat est ce que dit la documentation de LiteLLM, lue le 2026-11-23, et les routes demandent une version récente de LiteLLM (l'image n'est pas épinglée). Clairic est en préversion, Clairic Flash en préversion de recherche.

### Les modèles de jeu de rôle : le routeur `Auto-Fiction` et le groupe `Fiction`

Aion Labs sert six modèles de texte que son catalogue public, lu le 2026-11-23, décrit comme réglés pour le jeu de rôle et la narration immersifs, avec des « thèmes adultes et sombres » traités avec nuance, et qu'il ne modère pas (`is_moderated` est faux pour les six). Ils sont donc gardés à part : un groupe d'accès à eux, `Fiction`, au lieu de `LLM`, et un routeur à eux, `Auto-Fiction`, qui ne tient qu'eux. Aucun autre routeur n'en tient un, aucun de ces modèles n'est dans une autre cascade, et `check_compose_template.py` refuse un template où l'un des deux se produirait.

| Entrée | Modèle | Famille | Contexte |
| --- | --- | --- | --- |
| `aion-3-5-aion-labs` | `aion-labs/aion-3.5` | GLM, système de plusieurs modèles | 262 144 |
| `aion-3-5-mini-aion-labs` | `aion-labs/aion-3.5-mini` | GLM | 262 144 |
| `aion-3-0-aion-labs` | `aion-labs/aion-3.0` | GLM | 131 072 |
| `aion-3-0-mini-aion-labs` | `aion-labs/aion-3.0-mini` | DeepSeek | 131 072 |
| `aion-2-0-aion-labs` | `aion-labs/aion-2.0` | variante de DeepSeek V3.2 | 131 072 |
| `aion-rp-llama-3-1-8b-aion-labs` | `aion-labs/aion-rp-llama-3.1-8b` | variante de Llama 3.1 8B | 32 768 |

La cascade de `Auto-Fiction` est dans cet ordre, le plus récent et le plus grand d'abord : aucun chiffre n'est lu pour ces modèles (le classement d'Artificial Analysis n'en publie aucun d'après le mainteneur, ce que cette session n'a pas pu vérifier faute de clé de lecture du classement), l'ordre est donc écrit à la main, et les contrats de routeur les rangent « sans enregistrement ». Le routeur n'existe que si la clé d'Aion Labs est donnée. Les entrées s'écrivent `openai/aion-labs/<modèle>` avec `api_base: https://api.aionlabs.ai/v1`, LiteLLM n'ayant pas de fournisseur de ce nom ; la clé arrive au conteneur comme `AION_LABS_API_KEY`. Aucun appel n'a été fait depuis la session qui a écrit ce qui précède, faute de clé : la forme est celle du guide de démarrage du fournisseur.

**Qui les atteint : personne par défaut.** `Fiction` et `Auto-Fiction` ne sont pas dans `Artificial_Intelligence_LibreChat_gateway_key_models`, et `check_compose_template.py` refuse un défaut qui les contiendrait. Pour les essayer :

- avec LibreChat, ajouter `Fiction` (les six modèles) ou `Auto-Fiction` (le routeur) à cette liste : elle vaut pour la clé de chaque compte LibreChat, qui les atteindra tous ;
- pour une seule clé, la créer dans `/ui` limitée au groupe `Fiction` ou au modèle `Auto-Fiction`.

**Le palier gratuit est celui du compte, pas celui d'un modèle.** La page « Rate limits » de sa documentation (lue le 2026-11-23) donne au palier gratuit 15 requêtes par minute, 20 000 jetons par minute et 20 000 jetons par jour, tous les modèles ensemble, ce qui tient en quelques requêtes avec des modèles qui raisonnent. Les clés d'API s'activent en vérifiant une carte bancaire, jamais débitée, une carte par compte gratuit. Ses conditions (du 2026-10-17) disent que l'usage gratuit « is a courtesy that we may change or withdraw at any time », et qu'un modèle ou une limite se retire avec 14 jours de préavis « where we are able to give it ». Le catalogue donne un prix à chaque modèle, et tout achat de crédit fait passer le compte au palier 1, sans limite quotidienne de jetons, où les appels sont facturés à ces prix : **n'ajouter aucun crédit au compte**, de façon que la limite quotidienne reste la fin de l'allocation.

**Le contrôle de dérive lit ce catalogue**, public et sans secret. Un modèle qu'il ne liste plus est une entrée à supprimer, comme chez les autres fournisseurs, et la pull request qui la supprime est relue par une personne, le groupe `Fiction` n'étant pas `LLM`. Un modèle nouveau n'est jamais prêt : aucun indicateur de gratuité par modèle n'existe, il est proposé dans la pull request des modèles à vérifier, avec une entrée écrite dans le groupe `Fiction`, à placer à la main dans `Auto-Fiction`.

### Les capacités sans routeur : ce qui a été lu, et pourquoi rien n'est routé

Cette section dit, pour cinq capacités qui n'ont pas de routeur, ce qui a été lu (pages officielles, relues le 2026-11-22) et pourquoi aucun routeur n'existe encore, afin qu'une prochaine session reparte de ce constat et non de zéro. Les verdicts ont été relus le 2026-11-22 sous ces règles : ceux qui ont changé le disent. Chaque verdict porte la condition qui le changerait. Même position du mainteneur que plus haut sur l'entraînement, les préversions et les dépôts (un dépôt unique jusqu'à 10 €, supposé valable à vie : ni abonnement, ni recharge, ni crédit qui expire) ; un contenu qui part chez un tiers n'est pas une raison d'écarter un fournisseur ; un fournisseur qui n'a pas pu être lu est marqué non vérifié, jamais jugé.

**Le fait qui décide plusieurs lignes : Cloudflare Workers AI.** La page « OpenAI compatibility » ne liste que les complétions de chat et les embeddings (`/v1/embeddings`) ; elle ne liste ni génération d'images, ni transcription, ni synthèse vocale. Les modèles d'image, de parole et de transcription ne s'atteignent que par l'appel natif `/ai/run/<modèle>`, pour lequel LiteLLM n'a pas de fournisseur : rien n'est donc routable par la passerelle aujourd'hui, même si le quota gratuit (10 000 « neurons » par jour) et la politique sur les données (aucune conservation, aucun entraînement sur le contenu client, page « Data usage ») sont ceux du fournisseur déjà retenu.

#### Génération d'images

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Cloudflare Workers AI | Modèles d'image (flux-1-schnell, flux-2, stable-diffusion-xl, etc.) dans les 10 000 « neurons » quotidiens | 720 requêtes par minute pour le texte vers image ; flux-1-schnell : prompt de 2048 caractères au plus, 8 pas au plus ; coût en neurons par tuile et par pas, sans total par image sur la page | À ajouter le jour où un routage existe : seule source gratuite et durable trouvée, mais inatteignable par LiteLLM (appel natif seulement) |
| OpenRouter | Aucun modèle d'image `:free` ni à prix nul dans le catalogue ; des modèles d'image payants existent (Gemini image à environ 0,039 $ l'image, modèles d'image d'OpenAI) | LiteLLM les appelle par `/images/generations` sous la forme `openrouter/<modèle>` et les traduit en complétions de chat avec modalité image (lu dans sa documentation, non essayé) | Candidat comme réserve payante, pas comme palier gratuit : le crédit de 10 $ que le registre recommande pour porter les modèles `:free` de 50 à 1 000 requêtes par jour paierait environ 250 images, mais OpenRouter se réserve le droit d'expirer un crédit inutilisé au bout d'un an (le palier de 1 000 par jour, lui, tient au total acheté). Aucun routeur d'images n'est construit |
| Google Gemini API | Les modèles d'image sont « Not available » en palier gratuit (lu dans un résumé de la page des tarifs, non vérifié mot pour mot) ; payant de 0,039 à 0,134 $ par image | Contenu du palier gratuit utilisé pour améliorer les produits hors de l'EEE, de la Suisse et du Royaume-Uni | Écarté : payant |
| Recraft | Unités prépayées (1 $ = 1 000 unités), « Purchased units don't expire » ; 0,007 $ l'image en V4.1 Flash V2, 0,035 $ en V4.1 : 10 € achètent environ 1 600 images Flash ou 330 images V4.1 | Aucune allocation gratuite d'API trouvée ; taille minimale du paquet non lue (derrière un compte) ; route LiteLLM `recraft/recraftv3` | Candidat comme réserve payante (dépôt unique, crédit qui n'expire pas), pas comme palier gratuit : à ajouter seulement si un client du stack génère des images |
| Together AI, OpenAI, xAI, fal (plateforme d'images), Replicate | Together AI : premier achat de 15 $, au-dessus du plafond ; OpenAI : 5 $ minimum, mais les crédits expirent au bout d'un an ; xAI, fal, Replicate : minimum et expiration non lus | Aucune route d'images de LiteLLM trouvée pour Together AI, xAI, fal ni Replicate | Écartés : plafond, crédit qui expire, ou aucune route |
| Black Forest Labs | Paiement à l'usage ; les conditions donnent une licence pour entraîner sur les entrées et sorties et interdisent l'accès à l'API depuis autre chose que l'application du développeur | Passerelle exclue par les conditions | Écarté |
| Stability AI | 25 crédits offerts, une seule fois (environ 8 images « Core ») | Crédit unique | Écarté |
| Hugging Face, Ideogram | Hugging Face : aucun crédit mensuel pour les comptes gratuits ; Ideogram : l'API n'inclut aucun usage, les crédits hebdomadaires sont ceux de l'application et les images du plan gratuit y sont publiques | Pas d'offre gratuite d'API | Écartés |
| Pollinations | Une route compatible OpenAI `POST /v1/images/generations` existe ; une clé est requise ; le solde « gratuit » est crédité par des quêtes ponctuelles (0,25 à 1 « pollen » chacune), aucune attribution récurrente trouvée | Conditions et politique de données illisibles (pages JavaScript) | Non retenu : aucun palier récurrent trouvé |
| Fireworks, Leonardo, OmniRoute, Nscale | Fireworks : aucun modèle d'image sur sa page des tarifs ; Leonardo : page des tarifs introuvable ; OmniRoute : documentation injoignable, offre d'image inconnue ; Nscale : fournisseur d'images de LiteLLM, mais documentation et prix derrière un code d'accès | Non vérifié | Non vérifiés |

**Ce qui changerait le verdict** : un client du stack qui génère des images, auquel cas OpenRouter (le crédit déjà recommandé) ou Recraft (un dépôt unique qui n'expire pas) sont joignables ; un fournisseur Cloudflare pour les images dans LiteLLM, ou un point d'accès `images/generations` compatible OpenAI sur Workers AI ; un modèle d'image gratuit sur OpenRouter ; ou un service de diffusion local, que le serveur sans GPU ne permet pas de façon réaliste. LiteLLM route aujourd'hui la génération d'images vers OpenAI, Azure OpenAI, Google AI Studio, Vertex AI, AWS Bedrock, Black Forest Labs, Recraft, OpenRouter, Xinference et Nscale (page « Image Generation ») : aucun n'est à la fois gratuit et durable, seuls OpenRouter et Recraft se paient d'un dépôt unique.

#### Analyse de documents et OCR

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Docling (auto-hébergé) | Licence MIT ; PDF, DOCX, PPTX, XLSX, HTML et images vers Markdown ou JSON ; exécution locale, y compris pour des données sensibles | Aucune mesure de vitesse ni de processeur trouvée : à mesurer sur la machine | À ajouter : un service Docker, pas un routeur. Rien ne quitte la machine |
| Google Gemini API | Lit les PDF comme entrée multimodale des modèles de chat déjà routés | Contenu du palier gratuit utilisé pour améliorer les produits hors de l'EEE, de la Suisse et du Royaume-Uni | Servi autrement : aucun nouveau routeur n'est nécessaire |
| Mistral OCR | 2 $ les 1 000 pages (3 $ avec annotations), aucun palier gratuit d'OCR trouvé ; le solde est prépayé, un appel à solde nul répond 402, un plafond de dépense se règle, les frais prépayés ne sont pas remboursables (page lue le 2026-11-22) | Fournisseur `mistral/mistral-ocr-latest` de LiteLLM ; minimum et expiration du solde non lus (à lire dans la console) | Utilisable comme réserve payante (10 € achètent environ 5 700 pages), pas comme palier gratuit : à décider avec un besoin d'OCR |
| Cloudflare Workers AI `toMarkdown` | « Free for most format conversions » (page datée du 2026-04-21) | Liste des formats non trouvée ; appel natif seulement | Non routable, comme ci-dessus |
| Azure AI Document Intelligence | Niveau F0 : 500 pages gratuites par mois, récurrent ; compte Azure avec une carte non prépayée et un numéro de téléphone, sans frais | Route LiteLLM `azure_ai/doc-intelligence/prebuilt-layout` | Candidat : récurrent et joignable par LiteLLM. L'ancienne raison d'écart (contenu tiers chez un fournisseur cloud) ne tient plus ; à ajouter avec un besoin d'OCR |
| LlamaParse | 10 000 crédits gratuits par mois, récurrents (1 crédit par page en mode rapide, 10 en mode agentique) | Aucun fournisseur LiteLLM ; la suppression des résultats en cache après 48 heures ne compte pas ici | Non routable : hors de la passerelle, comme Docling, qui serait un service à part |
| Reducto | 150 $ une fois, puis payant | Rétention zéro réservée aux offres Growth et Enterprise | Écarté : crédit unique |
| Cohere Parse | Clé d'essai | « Not permitted to be used for production or commercial purposes » | Écarté |
| Unstructured | 10 000 pages gratuites une seule fois, sans carte | Aucune route LiteLLM trouvée | Écarté : quota unique |
| Google Cloud Document AI | OCR : les 1 000 premières pages gratuites, période non précisée (page lue le 2026-11-22) | Aucune route LiteLLM trouvée | Non routable |

**Ce qui changerait le verdict** : la mesure de Docling sur la machine (vitesse et mémoire), qui décide s'il devient un service, et le chantier d'ingestion de documents qui en serait le client ; un palier gratuit durable de Mistral OCR avec une politique de données acceptable. Le service local reste préféré parce qu'il ne coûte rien et ne dépend de personne, non parce que le contenu serait trop sensible : le mainteneur refuse un chemin réservé aux données sensibles.

#### Traduction

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Routeurs de texte existants | Les modèles de chat déjà routés traduisent | Ceux des cascades | Servi autrement : aucun routeur de traduction n'est nécessaire |
| Azure Translator | Niveau F0 : 2 millions de caractères gratuits par mois, récurrent ; compte Azure avec une carte non prépayée et un numéro de téléphone, sans frais | Aucune route LiteLLM | Non routable |
| DeepL API Free | 500 000 caractères par mois d'après un extrait de la page d'aide (page non lue, refusée à la lecture) ; les 50 000 écrits ici avant la relecture étaient probablement faux | Aucune route LiteLLM | Non routable |
| Cloudflare Workers AI (m2m100-1.2b) | 0,342 $ par million de jetons, dans les neurons quotidiens | Appel natif seulement | Non routable |
| LibreTranslate (auto-hébergé) | Licence AGPL, moteur Argos Translate | Vitesse sur processeur non trouvée | Non vérifié |
| Google Cloud Translation | 500 000 caractères gratuits par mois (page lue le 2026-11-22) | Aucune route LiteLLM trouvée | Non routable |

**Ce qui changerait le verdict** : un besoin de volume ou de qualité que les modèles de chat ne couvrent pas, ou une route LiteLLM vérifiée pour un de ces moteurs.

#### Modération

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| OpenAI `omni-moderation-latest` | « The moderation endpoint is free to use » (guide de modération), texte et images ; route LiteLLM `/moderations` avec `openai/omni-moderation-latest` | Un compte OpenAI est nécessaire ; qu'un compte sans dépôt puisse appeler ce point d'accès n'est pas établi. Si un dépôt est exigé : 5 $ au minimum, crédits expirant au bout d'un an et non remboursables, ce qui ne répond pas à la règle du dépôt unique à vie | Candidat technique, non essayé : gratuit et joignable par LiteLLM, mais rien dans le stack ne demande de modération |
| Mistral | Page de la modération introuvable | Tout | Non vérifié |

**Ce qui changerait le verdict** : un service du stack qui exposerait des entrées d'utilisateurs non fiables ; il faudrait alors un compte OpenAI et vérifier la route dans LiteLLM.

#### Voix en temps réel

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Google Gemini Live API | Modèles `gemini-3.8-live` et `gemini-3.8-live-extended-thinking` gratuits (pages « Live API » et des tarifs) ; l'ancien `gemini-2.5-flash-native-audio-preview-12-2025` s'arrête le 2027-03-31 | Sessions audio de 15 minutes au plus sans compression, connexion d'environ 10 minutes ; entrée PCM 16 bits à 16 kHz, sortie à 24 kHz ; contenu du palier gratuit utilisé pour améliorer les produits hors de l'EEE, de la Suisse et du Royaume-Uni ; le français figure dans le tableau des langues (lu dans un résumé, non vérifié mot pour mot) | Non routé : la documentation de LiteLLM liste Google AI Studio (Gemini) pour `/realtime` et donne une configuration `mode: realtime`, avec des identifiants de modèle plus anciens que ceux de cette ligne (non essayée) ; reste qu'aucun client du stack n'ouvre de session temps réel |

**Ce qui changerait le verdict** : un client temps réel réel dans le stack et un essai de la route Gemini Live de LiteLLM avec les modèles actuels. Aucune décision sur la téléphonie n'est prise ici.

### Les modèles d'embeddings, et pourquoi il n'y a ni routeur ni repli pour eux

Six entrées du `model_list` sont des modèles d'embeddings (`model_info.mode: embedding`), appelées par leur propre nom sur `/v1/embeddings` : `gemini-embedding-2` (rendue avec la clé Gemini), `mistral-embed` (rendue avec la clé Mistral) `bge-m3-cloudflare` (rendue avec la clé et l'identifiant de compte Cloudflare), et `nemotron-3-embed-1b-free`, `nemotron-3-5-embed-1b-free` et `nemotron-3-5-embed-8b-free` (rendues avec la clé OpenRouter). Aucune n'est dans une cascade, aucune n'a d'alias : un embedding n'a pas de « routeur » comme `Auto-Flash` ou `Auto-Code`.

**Pourquoi.** Les vecteurs de deux modèles ne sont pas comparables entre eux, même à dimensions égales. Un repli d'un modèle vers un autre, ou un alias qui désignerait un modèle différent selon les clés données, ferait changer silencieusement d'espace vectoriel : les nouvelles requêtes seraient comparées à une collection remplie par l'ancien modèle, et rien n'échouerait pour le dire. LiteLLM applique bien les replis à un appel d'embeddings (lu dans son code le 2026-11-22), donc le seul moyen sûr est de n'en déclarer aucun. `check_compose_template.py` le tient : dans chaque rendu, une entrée `mode: embedding` n'est ni membre d'une cascade, ni clé d'une cascade, ni cible ou nom d'un alias.

**Une collection Qdrant est liée à un seul modèle.** Elle est créée avec la taille de vecteur de ce modèle, et ingestion comme requêtes passent par le même nom de modèle et les mêmes `dimensions`. Changer de modèle, y compris de `gemini-embedding-001` à `gemini-embedding-2` (Google dit leurs espaces « incompatible »), c'est créer une nouvelle collection et tout ré-embedder.

| Modèle | Taille du vecteur | À savoir |
| --- | --- | --- |
| `gemini-embedding-2` | 3072 par défaut ; le paramètre `dimensions` de la requête (LiteLLM l'envoie à Google comme `outputDimensionality`) accepte de 128 à 3072, Google recommande 768, 1536 ou 3072 ; les vecteurs tronqués sont renormalisés par Google | Entrée de 8 192 jetons au plus ; pas de `task_type` pour ce modèle, la consigne se met dans le texte. Le rôle n'impose aucune valeur par défaut : l'appelant choisit, une fois, et la collection est créée à cette taille |
| `bge-m3-cloudflare` | Non lue sur les deux pages de Cloudflare : créer la collection d'après la longueur du premier vecteur reçu | Contexte de 60 000 jetons, multilingue, rétention zéro. Gratuit dans l'allocation quotidienne de 10 000 neurons (environ 9,3 millions de jetons, **déduit** de la note de la page des tarifs), mais **appelé par le point d'accès compatible OpenAI**, car le fournisseur `cloudflare/` de LiteLLM n'a pas de route d'embeddings : l'entrée est `openai/@cf/baai/bge-m3`, et son `api_base` est lu en entier dans `CLOUDFLARE_EMBEDDINGS_API_BASE`, que le rôle construit depuis l'identifiant du compte. Aucun appel réel n'a été essayé |
| `nemotron-3-embed-1b-free` | Non lue sur une page : créer la collection d'après la longueur du premier vecteur reçu | Texte seul, 4 096 jetons par entrée ; gratuit, mais sans garantie de durée ni de disponibilité, et pas pour des documents privés (voir le registre) |
| `nemotron-3-5-embed-1b-free`, `nemotron-3-5-embed-8b-free` | Non lue sur une page : créer la collection d'après la longueur du premier vecteur reçu ; les espaces des trois modèles Nemotron ne sont pas à supposer compatibles | Multilingues, 32 768 jetons par entrée, texte et images de pages (l'entrée n'essaie que le texte) ; gratuits, pas pour des documents privés |
| `mistral-embed` | Fixe, **non lue sur une page** : créer la collection d'après la longueur du premier vecteur reçu | La passerelle règle `drop_params: true` : un `dimensions` envoyé à ce modèle est ignoré sans erreur et le vecteur complet revient, alors que LiteLLM seul refuse l'appel |

**À ne pas faire : plonger des documents privés par le palier gratuit de Gemini.** D'après un résumé de la page des tarifs (non relue mot pour mot), le palier gratuit emploie le contenu pour améliorer les produits de Google hors de l'EEE, de la Suisse et du Royaume-Uni (voir « Gemini : conditions et quotas du palier gratuit »), et il n'y a pas lieu d'y envoyer des informations personnelles, sensibles ou confidentielles. Le corpus que ce stack route comprend des documents juridiques de tiers : pour eux, ni cette entrée avec une clé du palier gratuit, ni aucun autre palier gratuit qui s'entraîne sur les entrées. `mistral-embed` est payant, donc hors de ce risque, au prix de 0,10 $ le million de jetons d'après la table de prix de LiteLLM. Pour des documents privés, la voie est `bge-m3-cloudflare` (voir le registre ci-dessous) : rétention zéro des données, pas d'entraînement, et un modèle multilingue.

#### Le registre des embeddings et du rerank

Même registre, même lecture que ci-dessus, pages lues le 2026-11-22. Le rerank n'a aucune entrée : aucun point d'accès gratuit, durable et sans entraînement n'est atteignable avec les clés que le rôle connaît.

**Groupe 1 -- utilisés aujourd'hui.**

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Google Gemini API | `gemini-embedding-2` : palier gratuit d'après un résumé de la page des tarifs (non relu mot pour mot), payant 0,20 $ le million de jetons d'après la table de LiteLLM ; arrêt annoncé de `gemini-embedding-001` au 2028-05-14, remplaçant `gemini-embedding-2` | Entrée de 8 192 jetons ; plus de 100 langues, sans affirmation propre au français | Routé par son nom. Contenu utilisé pour améliorer les produits au palier gratuit hors de l'EEE, de la Suisse et du Royaume-Uni : pas pour des documents privés |
| Mistral La Plateforme | Aucune : `mistral-embed` à 0,10 $ le million de jetons, `codestral-embed` à 0,15 $ | Taille du vecteur et limite d'entrée non lues sur une page | `mistral-embed` routé par son nom ; `codestral-embed` non ajouté (code seulement) |
| Cloudflare Workers AI | 10 000 « neurons » par jour sans frais, soit environ 9,3 millions de jetons `@cf/baai/bge-m3` par jour (**dérivé** de 1 075 neurons le million de jetons, page des tarifs lue le 2026-11-24) ; `@cf/baai/bge-m3` : contexte de 60 000 jetons, « Zero data retention », 0,012 $ le million de jetons | 3 000 requêtes par minute pour les embeddings ; taille du vecteur non lue sur une page | `bge-m3-cloudflare` routé par son nom, par le point d'accès compatible OpenAI (le fournisseur `cloudflare/` de LiteLLM n'a pas de route d'embeddings). « Zero data retention » et « No training » : le meilleur candidat pour des documents privés |

Pages officielles lues :

- Google Gemini API : [Embeddings](https://ai.google.dev/gemini-api/docs/embeddings), [Deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
- Mistral : page « Pricing » et page « Embeddings » de sa documentation, dont le corps ne s'affiche pas sans script
- Cloudflare Workers AI : [bge-m3](https://developers.cloudflare.com/workers-ai/models/bge-m3/) et [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/), lues le 2026-11-24
- OpenRouter : [catalogue des modèles d'embeddings](https://openrouter.ai/api/v1/embeddings/models), [page de `nvidia/nemotron-3-embed-1b:free`](https://openrouter.ai/nvidia/nemotron-3-embed-1b:free), [3.5 1B](https://openrouter.ai/nvidia/nemotron-3.5-embed-1b:free) et [3.5 8B](https://openrouter.ai/nvidia/nemotron-3.5-embed-8b:free), lues le 2026-11-24

**Groupe 2 -- à ajouter.**

| Fournisseur | Offre gratuite | Limites | Verdict |
| --- | --- | --- | --- |
| Cloudflare Workers AI (les autres modèles) | Même allocation de 10 000 « neurons » par jour, comptée avec celle de `bge-m3` ; `@cf/baai/bge-large-en-v1.5` (1024 dimensions, anglais), `@cf/google/embeddinggemma-2` (768 dimensions, options 128, 256, 512) ; le rerank (`bge-reranker-base`, 0,003 $ le million) n'a pas de route LiteLLM listée | 3 000 requêtes par minute pour les embeddings | Non ajoutés : `bge-m3` couvre le multilingue, et un second modèle d'un même fournisseur ne donne pas de second quota. Un modèle moins cher en neurons que `bge-m3` (`@cf/google/embeddinggemma-2`, 154 neurons le million de jetons, page des tarifs lue le 2026-11-24) mérite un examen avant qu'une collection ne soit remplie |

Pages officielles lues : celles de Cloudflare dans le groupe 1.

**Groupe 3 -- écartés, avec la raison.**

| Fournisseur | Ce qui est offert | Raison de l'écart |
| --- | --- | --- |
| Cohere (embed et rerank) | Clés d'essai : 1 000 appels par mois, rerank limité à 10 requêtes par minute ; le français est géré | Clés d'essai « not permitted to be used for production or commercial purposes » |
| NVIDIA build | Clé d'essai | Conditions d'essai déjà écartées plus haut |
| Hugging Face Inference Providers | Aucun crédit pour les comptes gratuits | Pas d'offre gratuite |
| OpenAI | `text-embedding-3-small` (1536) et `-large` (3072) | Aucune offre gratuite trouvée |
| Fireworks | Crédits prépayés, embeddings de 0,008 à 0,016 $ le million de jetons | Pas d'offre gratuite |

**Groupe 4 -- pistes non vérifiées.** Aucune n'est un verdict.

| Fournisseur | Ce qui a été vu | Ce qui manque |
| --- | --- | --- |
| Voyage AI | Famille voyage-4, 1024 dimensions par défaut, 32 000 jetons ; « The first 200 million tokens ... are free for every account » ; rerank-3 à 0,05 $ le million ; fournisseur `voyage/` de LiteLLM | Un compte à ouvrir, et rien ne dit que le crédit se renouvelle |
| Jina AI | Jetons gratuits pour une clé neuve, 100 requêtes par minute avec une clé gratuite | Le montant ; aucune chaîne d'embedding propre à LiteLLM, le point d'accès compatible OpenAI conviendrait |
| Together AI, Nebius | Pas de prix d'embeddings chez le premier, page des tarifs en 404 chez le second | Tout |

### Les administrateurs de `/ui`, invités et non dotés d'un mot de passe

`Artificial_Intelligence_LiteLLM_admin_users` est une **liste**, vide par défaut, de `{username, email}`. Chaque entrée devient un
compte LiteLLM au rôle `proxy_admin`, créé par le même appel `POST /user/new` que les comptes internes (`auto_create_key: false` :
un administrateur n'a pas besoin de clé pour se connecter à `/ui`, et LiteLLM en mintait une que personne ne voyait). Le compte
`Artificial_Intelligence_LiteLLM_UI_username`/`_password` reste : c'est par lui qu'un premier déploiement s'ouvre, et rien dans cette
liste ne le retire. Elle prépare le jour où il sera désactivé, ce que LiteLLM recommande puisqu'il signale ce secret partagé comme
critique, sans le faire elle-même.

**Une invitation, pas un mot de passe.** `/user/new` n'en accepte pas ; `/user/update` en pose un, soumis à la politique de LiteLLM (12
caractères au moins, majuscule, minuscule, chiffre, caractère spécial) et à changer à la première connexion : la valeur du coffre de
l'appelant serait périmée dès que la personne se serait connectée une fois. Le rôle demande donc `POST /invitation/new` pour chaque
compte **créé à ce run** et s'arrête, **une seule fois**, sur le lien complet `<Artificial_Intelligence_LiteLLM_UI_URL>/ui/onboarding?invitation_id=<id>`,
valable sept jours, un par administrateur, chacun sur sa ligne pour être cliquable : la personne l'ouvre, choisit son mot de passe, qui
sert tel quel, puis se connecte avec son courriel, et le run reprend à Entrée (Ctrl+C puis A l'abandonne), comme les autres rôles qui
attendent une action à la main. L'adresse est celle de l'appelant, pas celle du rôle : `Artificial_Intelligence_LiteLLM_UI_URL`, dont le
défaut est celle du nœud.

- **Un compte qui existe déjà** (409) n'est ni modifié ni réinvité, et son mot de passe n'est jamais réinitialisé : le rôle ne crée
  un compte qu'une fois. Un lien perdu se refait depuis *Internal Users* de `/ui`, ou par `POST /invitation/new` avec la clé maîtresse.
- **Pour changer le mot de passe d'un administrateur**, il se le change lui-même (menu du compte) ; pour repartir de zéro, on
  supprime l'utilisateur dans `/ui` puis on relance le rôle, qui le recrée et en reinvite.
- **Noms et courriels distincts** de ceux de `Artificial_Intelligence_LiteLLM_internal_users`, dont les entrées passent par le même
  appel : un 409 sur un identifiant déjà pris par l'autre liste ferait ignorer l'entrée sans un mot, donc `tasks/main.yml` refuse la
  collision (courriels comparés sans tenir compte de la casse) avant tout déploiement.
- **L'identité de la clé maîtresse existe avant la première invitation.** LiteLLM enregistre l'auteur d'une invitation comme clé
  étrangère vers sa table des utilisateurs, avec l'identité de l'appelant : `default_user_id` pour la clé maîtresse, une ligne qu'il ne
  crée que lorsque quelqu'un se connecte à `/ui` avec l'identifiant d'environnement. Quand celui-ci est coupé dès le premier
  déploiement, personne ne le fait, et l'invitation est refusée d'un 400 « User id does not exist ». Le rôle crée donc cette
  ligne (`proxy_admin`, sans clé ni courriel, comme le ferait cette connexion) juste avant d'inviter, seulement quand une invitation
  va avoir lieu, et un 409 la laisse telle quelle. C'est un contournement de ce comportement de LiteLLM, pas la cause.
- **Une invitation refusée fait échouer le run avec ce que LiteLLM a répondu** (le statut et son message, qui n'ont rien de secret),
  et non plus avec un « 400 Bad Request » sans corps. Le compte existe alors sans mot de passe et un nouveau run ne l'invite pas :
  le message dit comment l'inviter depuis *Internal Users*.
- **Avec `--check`**, ces tâches sont sautées, comme celles des comptes internes : il n'y a pas de passerelle à interroger.
- **Sans terminal** (CI, Semaphore), la pause n'affiche que « Not waiting for response to prompt », pas son texte : le run continue et le lien n'est montré nulle part. Le compte existe alors sans mot de passe, et un nouveau run ne le réinvite pas : on l'invite depuis *Internal Users* de `/ui` tant que la connexion d'environnement est active, ou par `POST /invitation/new` avec la clé maîtresse.
- **Les administrateurs n'ont pas de clé virtuelle** : l'invitation est tout ce que le rôle leur donne.


### Un compte par personne, pas une paire figée (#103)

`Artificial_Intelligence_LiteLLM_internal_users` est une **liste**, vide par défaut, jamais une variable nommée par
personne : figer des noms fait de l'ajout d'une personne une modification de structure du rôle plutôt
qu'une ligne ajoutée à une liste. `tasks/main.yml` boucle
dessus et, pour chaque `{username, email}`, crée un compte LiteLLM au rôle `internal_user` --
self-service (peut créer/voir/supprimer ses propres clés, voir sa propre consommation) et rien
d'autre : jamais les clés d'un autre compte, jamais la configuration de la passerelle. Le compte
`Artificial_Intelligence_LiteLLM_UI_username`/`_password` (admin, plus haut) n'a pas sa place dans cette liste : il a déjà
un accès complet par le mécanisme natif de LiteLLM, une entrée ici ne lui apporterait rien.

Chaque compte reçoit **une seule clé virtuelle, sans restriction de modèles** : tant que #2 n'a pas
construit l'isolation par compte, elle atteint tous les modèles de la passerelle, ceux du compte de la
passerelle compris -- le comportement que #114 a posé comme attendu pour l'intérim. `POST /user/new` est
appelé avec `auto_create_key: false`, faute de quoi LiteLLM en mintait une seconde, sans restriction,
que la tâche n'affichait jamais ; la clé vient de `POST /key/generate` et de nulle part ailleurs. Cette
clé portait avant `models: ["access_group:<username>"]`, qui n'est pas une syntaxe de LiteLLM (un
groupe d'accès se nomme nu) : elle ne donnait accès à aucun modèle, mesuré sur `v1.100.0`. `POST
/key/generate` n'est appelé **qu'une fois par compte, pour toujours** : la tâche se déclenche seulement l'exécution où
`POST /user/new` vient tout juste de créer ce compte (409 ensuite, pour toujours), jamais sur la base
du comportement propre de `/key/generate` rejoué, qui reste à vérifier contre une instance réelle (voir
« Non vérifié » plus bas). Cette clé n'est montrée qu'**une seule fois**, dans la sortie de ce rôle, le
jour où elle est réellement créée : LiteLLM ne la restitue pas une seconde fois, au même titre qu'un
jeton GitHub ou un mot de passe de registre. C'est cette clé-là, et non un compte LiteLLM partagé, que
la personne colle ensuite dans son propre compte LibreChat -- voir juste en dessous. Avec `--check`, la création des
comptes et celle des clés sont sautées : il n'y a pas de passerelle à interroger, et la seconde lisait un statut que la
première, sautée, ne rend pas (le rôle s'arrêtait alors sur `object of type 'dict' has no attribute 'status'`).

**`librechat.yaml` route désormais chaque compte LibreChat vers sa propre identité côté passerelle.**
`apiKey: "user_provided"` (au lieu d'une clé unique lue dans l'environnement du conteneur) fait que
LibreChat range une clé propre à CHAQUE compte, saisie une fois par l'engrenage à côté du nom de l'endpoint,
et la retient chiffrée pour lui seul. Avant #103, une seule clé virtuelle servait tout le conteneur : n'importe
quel compte LibreChat, humain ou non, parlait à la passerelle sous la même identité, ce qui défaisait
l'isolation par compte dès qu'un deuxième humain existait -- même avec son propre compte LiteLLM créé
par la liste ci-dessus, rien ne l'aurait fait passer par lui plutôt que par l'unique clé partagée.
`Artificial_Intelligence_LibreChat_LiteLLM_virtual_key` et son `assert` obligatoire disparaissent avec ce changement :
plus personne n'a besoin de pré-fabriquer une clé virtuelle avant que LibreChat ne tourne, ce qui
règle au passage le problème d'ordre de démarrage que ce même `assert` posait (LiteLLM devait tourner
pour émettre une clé via son propre `/key/generate`, et rien ne se déployait tant que l'`assert`
n'était pas satisfait).

**Une clé de la passerelle par compte LibreChat, faite et rangée par le rôle.** Pour un compte qui porte `gateway_key: true`
dans `Artificial_Intelligence_LibreChat_users`, plus de saisie à la main : le rôle se connecte à LibreChat **avec le mot de
passe de ce compte**, qu'il détient puisqu'il l'a créé, demande à LiteLLM une clé d'alias `librechat-<username>` limitée à
`Artificial_Intelligence_LibreChat_gateway_key_models`, puis la range par la route de LibreChat que l'engrenage appelle, `PUT /api/keys`, sous le nom de l'endpoint. La clé
n'est rangée que dans ce compte, qu'aucun autre ne partage, n'est écrite nulle part dans l'inventaire, et LibreChat la chiffre
et la stocke lui-même : le rôle ne touche pas à sa base de données. Un compte sans `gateway_key` saisit sa clé à la main, comme
avant. Elle est faite une fois : le rôle regarde d'abord, par `GET /api/keys`, si LibreChat a déjà une clé pour ce compte, et ne
fait rien dans ce cas, donc un second passage ne change rien. À chaque passage, le rôle cherche aussi à LiteLLM la clé de l'alias
`librechat-<username>` et, si sa liste de modèles n'est pas celle de la variable, la met à jour (`POST /key/update`) : une clé faite avant
cette limite, ou avant un changement de la liste, la reçoit sans être supprimée.

Ce que ça ne fait pas : **multiplier les quotas gratuits.** Ils sont comptés par les fournisseurs, sur les clés de fournisseur de la
passerelle, et partagés par toutes les clés virtuelles ; une clé par compte sépare le suivi et la révocation, et permet des
limites par clé si on en pose. Et un cas à la main : LiteLLM rend la clé une seule fois, donc si LibreChat n'a plus la clé du
compte alors que LiteLLM garde l'alias (le run s'est arrêté entre les deux appels, ou la clé a été supprimée de LibreChat), la
création est refusée et le message dit de supprimer cette clé depuis `/ui` puis de redéployer. Si LibreChat refuse la
connexion du compte (mot de passe de l'appel différent du sien, double authentification, trop de connexions), la tâche s'arrête
de même sur un message qui dit quoi vérifier.

**Redis, déployé par #71, pour l'état de cooldown partagé entre les workers de LiteLLM** ; ni #1 ni
#2 n'en avait le périmètre à l'origine. `--requirepass` est obligatoire, sans défaut, même raisonnement
que la clé d'API de Qdrant (#3) : défense en profondeur sur un service interne, sans port publié.

**Le cache de réponses, l'autre raison de #71, n'existe pas -- et c'est mesuré (#79).** Il n'avait en
fait jamais été actif : la configuration disait `enable_caching: true`, une clé que LiteLLM ne connaît
pas (la sienne est `cache: true`, et sans elle il n'y a pas de cache). Activé correctement, il
**franchit la frontière entre comptes** : sur LiteLLM 1.100.0, une requête identique envoyée avec la
clé virtuelle B a reçu la réponse mise en cache pour la clé A. La clé du cache exact contient la
liste `messages` entière (tout l'historique et le prompt système), le modèle et les paramètres, mais
rien sur l'appelant ; seuls les caches *sémantiques* y ajoutent son identité. Il ne vaut de toute façon
presque rien ici : un client de conversation renvoie un historique qui diffère à chaque tour, donc il
ne tombe presque jamais sur une requête identique. La raison est écrite dans `LiteLLM_config.yaml.j2`.

**Un modèle repéré comme vieillissant, laissé en place.** `gemini-2-5-flash` est plusieurs générations
derrière la ligne `gemini-3.x`, et #2 le signale comme tel -- mais rien ne confirme qu'il soit
réellement retiré. Il ne figure dans aucune cascade : on ne l'atteint qu'en le demandant par son
nom. Retiré ou confirmé au prochain audit de #2, pas ici.

## L'agent Claude Code (#13)

Déployé **tel quel** depuis l'image que publie `Claude-Code-Docker-container`
(`ghcr.io/dragnix-tigerblue77/claude-code-docker-container`), écrite sans tag comme les autres images
qui ne sont pas des bases de données : le déployeur la récupère à chaque exécution, sans variable ni
épinglage de notre côté. Rien n'est construit ici.

**Ce que « sans tag » veut dire pour cet agent.** Le tag `latest` de cette image suit le canal `stable` de
npm, pas son canal `latest` : la version de Claude Code qu'il porte a quelques publications de retard, voulu
par le dépôt amont. Un déploiement qui trouve une nouvelle image recrée le conteneur et met fin au
processus `claude` en cours ; l'état de la conversation est dans le volume du répertoire personnel, et
`claude --continue` la reprend. Pour revenir en arrière, écrire la version dans la ligne `image:` du
template (`...:<version>`) le temps de corriger.

**Ce que l'image apporte, et ce qu'elle n'apporte pas.** Mesuré le 2026-10-10 dans l'image publiée
(Claude Code 2.1.287 ; le tag bouge, le README du dépôt amont fait foi) : l'utilisateur non-root `node`,
`/workspace` comme répertoire de travail, l'auto-updater désactivé, `git`, `ripgrep`, `jq` et `less`. Elle ne
porte ni `gh`, ni `ansible-core` (ni `python3`, ni `pip3`), ni client `docker`, ni `build-essential`, ni
`curl`, ni `procps`, c'est-à-dire les outils du travail d'infrastructure. Les avoir dans
l'agent passe par l'image publiée elle-même, ou par une image dérivée publiée à part.

**Déployé comme les autres conteneurs, sans étape manuelle.** Le stack démarre avec l'agent : l'option
`Artificial_Intelligence_Claude_code_enabled` n'existe que pour qu'un appelant qui n'en veut
pas le retire (`false`). Deux entrées ne peuvent pas exister au premier passage, et le rôle les fournit
lui-même plutôt que de les laisser à l'appelant.

**Le dossier de travail est un volume nommé par défaut.** `Artificial_Intelligence_Claude_code_workspace_directory`
vaut `false` (« non fourni ») et `/workspace` est alors le volume
`Claude_code_workspace`, déclaré avec les autres : rien à préparer
sur l'hôte. Le `Dockerfile` amont crée `/workspace` et le donne à l'utilisateur `node` avant de passer
sous cet utilisateur, et Docker initialise un volume nommé vide depuis le contenu de l'image à ce chemin :
le dossier est donc inscriptible par `node` (lu dans le `Dockerfile`, pas mesuré avec un démon). Le
volume du répertoire personnel reste un volume à part : l'un tient la session, l'autre le travail. Une
chaîne à la place est un chemin absolu de l'hôte, monté en bind ; le rôle ne le crée pas -- il doit
exister, et être inscriptible par `node` (uid 1000 dans l'image) -- et refuse un chemin vide ou relatif,
qu'un orchestrateur lirait comme un nom de volume. Passer d'un mode à l'autre change l'endroit où l'agent
travaille : le contenu de l'un n'est pas recopié dans l'autre.

**Le rôle enregistre lui-même la clé virtuelle de l'agent dans LiteLLM.** La **valeur** de
`Artificial_Intelligence_Claude_code_virtual_key` reste un secret de l'appelant, vaulté et
interpolé dans le fichier compose comme les autres (même `$` doublé, même chaîne JSON). Une fois LiteLLM
prêt (l'attente décrite plus haut, trois minutes au plus), le rôle demande à `GET /key/info` si cette clé existe -- par
son SHA-256, ce que LiteLLM stocke, pour que le secret n'apparaisse pas dans l'URL -- puis, si elle est
inconnue (404) ou signalée supprimée, la crée par `POST /key/generate` avec cette valeur dans `key`, le
`key_alias` `claude_code` et pour liste blanche l'alias du modèle
(`Artificial_Intelligence_Claude_code_model`) suivi des routeurs de
`Artificial_Intelligence_Claude_code_additional_models` : c'est elle qui tient le conteneur à l'écart
du quota de tous les autres comptes. Les appels s'authentifient avec la clé maîtresse, que l'agent ne
détient jamais, et leurs tâches sont en `no_log`. Un second passage trouve la clé et ne change rien.

Ce que cela ne fait pas : le rôle **crée** la clé, il ne **réconcilie** pas une clé qui existe déjà -- elle
garde les modèles avec lesquels elle a été créée (la liste de `Artificial_Intelligence_Claude_code_additional_models`
comprise, #307). Et **faire tourner la clé** demande d'abord de supprimer
l'ancienne depuis `/ui` : son alias est unique, `POST /key/generate` refuserait la nouvelle tant que
l'ancienne existe, et la tâche étant en `no_log`, l'échec n'en dit pas la cause. Le conteneur peut
démarrer quelques secondes avant que sa clé existe : il n'appelle la passerelle que lorsqu'on s'en sert,
et sa politique de redémarrage (`any`) le relance s'il sort entre-temps. Le rôle saute ces tâches avec
`--check` : le stack n'y est que rendu, il n'y a pas de LiteLLM à interroger.

Les champs de la requête (`key`, `key_alias`, `models`, le préfixe `sk-` et les 16 caractères minimum, le
`404` de `/key/info` pour une clé inconnue, le SHA-256 en paramètre) sont lus dans le code de LiteLLM
v1.106.6 (`litellm/proxy/management_endpoints/key_management_endpoints.py`), pas exécutés contre une
passerelle vivante. Les valeurs refusées par LiteLLM (`disable_custom_api_keys`, un alias déjà pris) font
échouer la tâche.

**Le service démarre comme l'image le prévoit.** L'entrée de l'image publiée est `claude` seul, sans
`CMD`, et le bloc du service ne pose ni `command:`, ni `user:`, ni `working_dir:` : le conteneur lance
`claude` sans argument.

**Le répertoire personnel monté est `/home/node` en entier, jamais `~/.claude` seul.** C'est le piège
d'authentification que le dépôt amont documente sur lui-même : `~/.claude.json` vit À CÔTÉ de
`~/.claude`, pas dedans, et un volume sur `~/.claude` seul perd la moitié de la session à chaque
recréation du conteneur, sans qu'aucune erreur ne le signale. C'est ce montage qui tient la session. Rien
ne restaure `~/.claude.json` s'il manque alors que `~/.claude/backups/` survit (un fichier effacé, un
volume monté d'abord sur `~/.claude` seul) : la copie se refait à la main depuis `~/.claude/backups/`.

**Aucun montage de `docker.sock` dans cette issue.** #11 n'a pas encore conçu l'isolation qu'un agent
doit respecter avant de pouvoir atteindre le démon Docker de l'hôte, et ce conteneur attend cette
décision plutôt que de la devancer. L'image publiée ne porte d'ailleurs aucun client `docker` : rien ne
branche le socket tant que #11 n'a pas tranché.

**Le jeton GitHub est facultatif (#245).** #13 délègue l'accès aux dépôts au connecteur MCP GitHub (#23) et
l'accès aux outils à la passerelle MCP (#7) ; `Artificial_Intelligence_Claude_code_GitHub_token` n'est pas
cet accès, seulement un jeton personnel que le rôle pose dans le conteneur, en `GH_TOKEN` et `GITHUB_TOKEN`, s'il est
fourni. Ce qui les lit, c'est Claude Code lui-même, sans passer par `gh` : il s'en sert pour interroger l'API GitHub, et
son pied de page d'état de la pull request de la branche courante (réglage `prStatusFooterEnabled`, activé par défaut) en
est l'usage établi. C'est une lecture des chaînes du binaire de la 2.1.287, la version mesurée plus haut, et non une
exécution. L'image ne porte pas `gh`, le repli de Claude Code quand ces variables manquent, et git ne lit ni l'une ni
l'autre de lui-même : sans jeton, ce même code affiche « install gh for PR status » à la place du pied de page, et ses
autres appels à l'API GitHub qui se servent du jeton partent sans. Le bloc du service ne pose donc les deux variables
que si le jeton est fourni : un déploiement qui préfère ne mettre aucun jeton GitHub dans l'environnement du
conteneur -- où chaque `docker inspect` le montre -- n'en donne pas, et perd ce pied de page.
Fournie, la variable doit être une chaîne non vide : une valeur vide ou qui n'est pas une chaîne fait échouer le rôle
plutôt que d'être ignorée en silence. `false`, sa valeur par défaut, veut dire « non fourni ».

**Le modèle est un alias, jamais un nom de modèle Anthropic littéral.** `ANTHROPIC_BASE_URL` pointe sur
la passerelle interne (`litellm:4000`, #1), jamais sur l'API Anthropic, et `ANTHROPIC_MODEL` porte
l'alias `Auto-Claude-Code` que #2 résout dans LiteLLM. C'est le point de conformité de #13 : quoi que cet
alias résolve, ce ne doit jamais être un modèle Anthropic adossé à un abonnement.

**Toutes les variables de modèle de Claude Code portent ce même alias (#287).** Claude Code n'envoie pas que ses
requêtes principales : ses requêtes d'arrière-plan (titres, résumés courts) partent vers le modèle de classe Haiku, ses
sous-agents vers le leur, et les alias `sonnet` et `opus` vers d'autres encore. Or la clé de l'agent n'autorise que
l'alias et les routeurs de `Artificial_Intelligence_Claude_code_additional_models` (voir plus haut) : une requête sous
un autre nom est refusée par la passerelle. Le bloc du service pose donc `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`,
`ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL` et `CLAUDE_CODE_SUBAGENT_MODEL`, toutes sur
`Artificial_Intelligence_Claude_code_model`, sans second alias : la liste blanche de la clé ne s'élargit que par les
routeurs de `Artificial_Intelligence_Claude_code_additional_models`, et c'est elle qui tient le conteneur à l'écart du
quota des autres comptes. Le coût : les requêtes d'arrière-plan et les sous-agents
passent par le modèle principal. Les noms viennent de la documentation de Claude Code
(« Model configuration » et « Environment variables », consultées le 2026-10-31) :
`ANTHROPIC_SMALL_FAST_MODEL`, l'ancien nom de la variable Haiku, y est déclaré obsolète au profit de
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, et n'est pas posé. Ne le sont pas non plus `ANTHROPIC_DEFAULT_FABLE_MODEL` (l'alias
`fable`, que la documentation lie à une sélection explicite et au repli automatique de modèle sur un fournisseur tiers)
et `CLAUDE_CODE_AUTO_MODE_MODEL` (le classificateur du mode automatique) : ni l'un ni l'autre n'est un chemin que le
déploiement emprunte tel quel, et leur effet derrière la passerelle n'est pas mesuré. Rien de tout cela n'a été exécuté : ni LiteLLM réel, ni Claude Code
réel, donc ce que Claude Code affiche quand une requête est refusée reste non mesuré.

**Choisir son routeur depuis Claude Code (#307).** Sans rien faire, le conteneur demande `Auto-Claude-Code`. Pour un autre
routeur, on le nomme : `/model Auto-Flash` en session, ou `claude --model Auto-Flash` au lancement. Claude Code envoie alors ce
nom tel quel (mesuré avec `--model` sur la version 2.1.316 ; la saisie `/model` n'a pas été mesurée), et la passerelle
l'accepte parce que la clé de l'agent l'autorise : `Auto-Pro`, `Auto-Flash`, `Auto-Flash-Lite` et `Auto-Code` par défaut
(`Artificial_Intelligence_Claude_code_additional_models`), les autres routeurs du `model_list`, adossés aux modèles
du compte par défaut et à ceux, sans compte, d'OmniRoute, de Kilo Gateway et d'OVHcloud -- l'agent n'atteint donc le quota d'aucun
autre compte, mais ceux, anonymes et par adresse IP, de Kilo et d'OVHcloud, que `Auto-Claude-Code` ne sert pas. Un nom hors de
la liste, celui d'un modèle d'un autre compte compris, reste refusé. Les paliers du CLI (`opus`, `sonnet`, `haiku`) ne
choisissent pas de routeur : leurs variables restent sur l'alias. Un routeur dont aucun membre n'a de clé ni n'en demande n'existe pas dans la
passerelle, et le demander est refusé par elle, pas par le rôle ; LiteLLM 1.100.0 n'examine pas les noms de `models`
d'une clé sans équipe ni projet à sa création (lu dans son code), si bien qu'un routeur absent peut figurer dans la
liste sans erreur. **Un agent déjà déployé ne reçoit pas la nouvelle liste** : supprimez sa clé depuis `/ui` avant de
redéployer.

**Ce service ne dépend pas de #1 pour être mergé, seulement pour tourner.** Il se déploie et se rend
indépendamment ; c'est au démarrage du conteneur, une fois `litellm` réellement présent, que
`ANTHROPIC_BASE_URL` doit pouvoir le résoudre.

## Monter PostgreSQL d'un majeur (#168)

**Une migration, pas un changement de tag.** L'image est épinglée en dur dans le template
(`postgres:18`), et le volume est monté là où l'image de ce majeur range ses données :
`/var/lib/postgresql/data` jusqu'à 17, `/var/lib/postgresql` à partir de 18, où l'image officielle
garde chaque cluster dans un sous-répertoire à son nom (`18/docker`). Les deux se changent ensemble,
dans le même commit : laissé sur l'ancien chemin, 18 refuse de démarrer, même sur un volume vide.

Sur un volume qui porte déjà un cluster, le nouveau majeur le refuse aussi, à l'un comme à l'autre
chemin, et la politique `any` le relance en boucle : rien n'est perdu, rien ne démarre. Le passage,
vérifié de 17 à 18 sous Compose avec LiteLLM v1.100.0 -- une clé virtuelle créée avant la montée
retrouvée après, et l'ancien volume redémarrant toujours sous 17 :

```bash
# « litellm » est le défaut du rôle comme de la base : remplacer par les vôtres s'ils diffèrent.
# 1. Sous l'ancien majeur, LiteLLM arrêté pour que plus rien n'écrive (docker stop <conteneur litellm>
#    sous Compose, docker service scale <stack>_litellm=0 sous Swarm), exporter la base
docker exec <conteneur postgres> pg_dump -U litellm --format=custom --no-owner --no-privileges litellm > litellm.dump
# 2. Monter le tag de `postgres` dans le template (et le chemin du volume, si l'on franchit 18) ET
#    donner un nouveau nom à Artificial_Intelligence_PostgreSQL_data_Docker_volume_name : le nouveau
#    majeur initialise un volume vide, et l'ancien reste intact pour revenir en arrière
# 3. Redéployer avec le rôle -- LiteLLM migre une base vide --, l'arrêter de nouveau, restaurer,
#    puis le relancer (docker start, ou scale à 1)
docker exec -i <conteneur postgres> pg_restore -U litellm -d litellm --clean --if-exists --no-owner --no-privileges --exit-on-error < litellm.dump
# 4. Une fois le nouveau volume éprouvé, et seulement alors, supprimer l'ancien
docker volume rm <ancien volume PostgreSQL du stack>
```

`pg_upgrade` est l'autre voie, sur place et plus rapide sur une grosse base, mais il lui faut les
binaires des deux majeurs dans un même conteneur, ce que l'image officielle ne fournit pas ; pour une
base de cette taille, l'export est le plus simple des deux. Une tentative refusée, volume monté sur
`/var/lib/postgresql`, laisse un répertoire vide `18/docker` à la racine de l'ancien cluster : 17
redémarre dessus sans le voir.

## Ce que ce squelette ne fait pas

- **Il ne déploie plus rien de vide, mais il n'a pas été déployé.** Depuis #1, `services:` porte
  `postgres` et `litellm` **inconditionnellement**, et depuis #73, #3 et #76 `omniroute`, `qdrant` et
  `librechat`/`librechat_mongodb` les rejoignent, inconditionnellement aussi. Depuis #13,
  `claude_code` s'y ajoute aussi, inconditionnellement tant que
  `Artificial_Intelligence_Claude_code_enabled` garde sa valeur par défaut `true` (un appelant
  qui n'en veut pas le passe à `false`) ; dans tous les états, les seuls ports qui apparaissent dans la configuration résolue sont le `4000` de LiteLLM, le
  `20128` d'OmniRoute et le `3080` de LibreChat, publiés à dessein -- Qdrant n'en publie aucun. La
  case « le rôle se déploie sur la VM de test et les conteneurs démarrent » de #31 devient donc
  vérifiable sur le banc d'essai, pas avant. Les comptes LibreChat et leur promotion `ADMIN` sont
  vérifiés contre un vrai `docker compose up` (voir plus haut) ; ce qui reste à faire sur une vraie
  machine : la mesure sous charge des limites mémoire, la persistance après un `down` / `up`,
  l'idempotence sur un second passage, et, hors du périmètre de #3, la création des collections
  Qdrant une fois le modèle d'embedding choisi (#21).
- **Il ne fournit ni `.env` ni `.env.example`, et n'en fournira pas.** #31 et #32 revendiquaient tous
  deux le `.env.example` ; #1 a tranché autrement : chaque secret est une variable du rôle, interpolée
  par Ansible dans le fichier rendu (voir « Les secrets vivent dans le fichier compose » plus haut). Le
  `.gitignore` et l'intégration continue sont arrivés avec #32.
- **Il ne tranche pas la topologie réseau.** Un seul réseau interne, parce que #7 décidera la séparation
  collecteur / acteur et que c'est cette décision-là qui dira s'il en faut deux ou trois. Un squelette qui
  la préempterait ferait le contraire de son travail.

## Pourquoi tout vit sous `deploy:`

Le modèle commenté dans le template écrit les limites de ressources et la politique de redémarrage sous
`deploy:`, et jamais sous leurs équivalents de premier niveau. C'est la seule forme que **Compose et Swarm
honorent tous les deux**, et c'est ce qui permet au rôle de ne présupposer aucun orchestrateur : la cible
d'aujourd'hui est une VM en Compose, celle de demain est Swarm, et la bascule ne doit pas rouvrir ce
fichier.

Écrites autrement, les mêmes intentions se perdent en silence :

| Clé | Compose | Swarm |
|---|---|---|
| `restart: unless-stopped` | fonctionne | **ignoré** — il faut `deploy.restart_policy.condition: any` |
| `mem_limit` / `cpus` | fonctionnent | **ignorés** — remplacés par `deploy.resources.limits` |
| `depends_on` en liste | démarre les services listés d'abord, sans attendre qu'ils soient sains | accepté, **sans effet** |
| `depends_on` en forme longue (`condition:`) | attend la condition | **fichier entier refusé** — n'écrire que la liste |
| `deploy.update_config.failure_action: rollback` | sans effet | une mise à jour qui échoue **revient à l'image précédente** ; sans la clé, le service reste en pause sur la version cassée |
| `shm_size` | fonctionne | **ignoré** |
| `container_name` | fonctionne | déprécié — ne jamais s'en servir comme nom d'hôte |
| Secrets | fichier ou variable | secrets natifs de l'orchestrateur |

Sur les limites mémoire : le rôle n'en pose aucune par défaut, et seul l'appelant en demande une, en donnant une taille (`"2g"`) à la variable `*_memory_limit` du service ; `false` laisse le service sans limite, et le rôle refuse toute autre valeur qu'une taille (un nombre, `true` ou une chaîne vide seraient sinon ignorés sans un mot ou écrits comme une limite invalide). Les tailles que le rôle a portées un temps n'ont jamais été mesurées, et sans limite un conteneur qui s'emballe peut entraîner les autres par OOM : c'est un arbitrage que le rôle laisse à l'appelant, qui connaît sa machine. Posée, la limite s'écrit sous `deploy.resources.limits.memory`, la seule forme que Compose et Swarm honorent tous les deux.

Sur `restart_policy` : `condition: any`, jamais `on-failure`. Quand un conteneur devient malsain,
l'orchestrateur l'arrête **proprement** ; le processus sort avec le code 0 ; et `on-failure` ne remplace
jamais une tâche sortie proprement. Le service reste à 0 réplique, le reverse proxy ne construit plus de
route à partir des tâches en cours d'exécution, et l'URL répond un 404 nu sans que rien ne soit journalisé
nulle part. Ce n'est pas une hypothèse : c'est une panne déjà payée une fois.

Que Compose v2 honore bien `deploy.resources.limits` et `deploy.restart_policy` est l'hypothèse sur
laquelle repose ce choix. Elle est documentée par Compose, et elle **reste à confirmer sur le banc
d'essai** avec la première issue de service : rien de ce qui est ici ne démarre de conteneur, donc rien
ici ne la prouve.

## Vérifier une modification du template

Lire le diff ne suffit pas, et « Auto-merging » non plus : les conflits qui font mal ici sont sémantiques,
pas textuels. Le template se **rend** et le résultat se **parse** :

```bash
yamllint .
ansible-lint
ansible-playbook --syntax-check playbook.Artificial_Intelligence.example.yaml
python3 .github/scripts/check_compose_template.py
```

Le dernier est celui qui compte pour le template. Il le rend dans ses **deux** états -- réseau publié
renseigné et non renseigné -- parse les deux, compare les objets parsés plutôt que les fichiers, et tient
chaque bloc de service aux conventions que le modèle commenté du template documente : image sans tag ou épinglée avec sa raison,
limite mémoire quand l'appelant en pose une (aucune par défaut), `restart_policy.condition: any`, pas de `container_name`, pas de `build:` (une image se
récupère, elle ne se construit pas ici), et tout réseau ou volume référencé effectivement déclaré.

Il rend aussi `LiteLLM_config.yaml.j2` pour chaque ensemble non vide de clés fournisseurs (#296), et tient
chaque rendu aux règles de « Les clés fournisseurs » plus haut.

Il le rend aussi avec les sommes de contrôle des configurations montées renseignées (#161), que les
défauts laissent à `false` : chaque fichier doit être monté par `configs` -- jamais en bind mount dans
`volumes` --, sous une config déclarée au niveau supérieur avec son `file`, nommée d'après le contenu
sans suffixe quand rien n'est renseigné, et sans que rien d'autre ne change entre les deux états.

Il refuse aussi un nom de volume par défaut qui commence par le nom du stack, que Compose et Swarm préfixeraient une seconde fois.

L'état « désactivé » est celui que personne ne regarde, et une condition Jinja qui ne marche que quand la
fonctionnalité est active est un défaut qui part en production. C'est pour cela que les deux états sont
rendus, et que le contrôle refuse qu'activer le réseau publié change autre chose que le bloc `networks:`.

L'agent Claude Code, déployé par défaut, a trois formes que le contrôle rend chacune : son dossier de
travail en volume nommé (le défaut), en chemin d'hôte, et l'agent retiré (`enabled: false`). Il vérifie que
`/workspace` est monté par le volume nommé dans le premier cas et par le chemin dans le second, que le
volume de travail n'est déclaré que dans le premier -- un volume déclaré que rien ne monte est le reste
d'une condition qui n'a pas suivi son interrupteur --, et que la troisième ne laisse ni service ni volume
de l'agent. Sa clé virtuelle n'a pas de défaut : chaque état la reçoit, comme un appelant ; le jeton GitHub,
facultatif, n'est donné qu'à l'état qui le juge.

Avant tout rendu, il résout les valeurs par défaut qui en interpolent d'autres -- un chemin de
destination est un répertoire suivi d'un nom de fichier -- et il les résout comme Ansible (#184) : une
référence à un nom que `defaults/main.yml` ne définit pas, et qu'il ne déclare pas non plus obligatoire
par une ligne commentée `# <nom>:`, est un constat et non une chaîne vide ; un défaut qui s'interpole
lui-même aussi ; et un filtre, un test ou une fonction que seul Ansible fournit (`ternary`, `bool`,
`lookup()`…) est signalé comme tel au lieu de faire planter le contrôle. Dans chacun de ces cas, comme
pour un gabarit Jinja2 invalide, le template n'est pas rendu et le contrôle sort en erreur : le rendu
porterait une valeur qu'aucun déploiement n'écrit. Un défaut dérivé d'une variable obligatoire, lui,
est de l'Ansible ordinaire : il se résout comme le rendu écrit la variable elle-même, vide. Les valeurs que l'appelant passe au rôle, dans chacun des états rendus, sont appliquées avant cette
résolution, comme Ansible lit un défaut dérivé : le nom d'une config Docker, construit sur la somme de contrôle de son
fichier (#161), la porte donc bien.

Il fait aussi un rendu de plus (#155), avec un chemin d'hôte pour l'agent Claude Code, où portent `$`, `${`, `$$`, `/`, `@` et
`#` : toute variable que le template lit et que `defaults/main.yml` ne définit pas ou laisse vide (`""`)
-- les obligatoires, donc aussi le secret du prochain service, et les optionnelles vides comme la clé
GitHub Models -- ainsi que les valeurs libres à vrai défaut que le script énumère dans
`FREE_FORM_WITH_A_DEFAULT`. Il refuse alors toute chaîne du résultat où un `$` n'appartient pas à un
`$$`, c'est-à-dire tout ce que Compose réinterpréterait. Les emplacements qu'une autre pull request
réécrit déjà y sont exemptés un par un, avec leur numéro, et une exemption qui n'exempte plus rien fait
échouer le contrôle.

Ce n'est pas toute valeur de l'appelant : une nouvelle valeur libre dotée d'un vrai défaut, ou d'un
défaut `false`, n'est rendue avec un `$` qu'une fois ajoutée à cette liste. Rien dans un défaut ne dit si
sa grammaire admet un `$`, et `false` écrit aussi un interrupteur. L'avant-dernière ligne du contrôle
donne le nombre de valeurs effectivement rendues avec un `$` : s'il baisse, une valeur est sortie du
rendu.

Les mêmes valeurs portent aussi `"`, `'`, `\t`, `\x41`, `\\` et un emoji (#188), et le contrôle suit
chacune dans le résultat parsé : partout où elle est écrite telle quelle, elle doit arriver entière,
telle que Compose la lira. Il la reconnaît à son marqueur -- le nom de la variable, `@` et `Ab` -- et ne
suit pas un emplacement qui l'encode exprès, comme une URL de connexion, où `@` devient `%40`. Le filtre
`to_json` de ce rendu est celui d'Ansible, importé : le fichier rendu est celui qu'écrirait le module
`template`. Les variables qu'une ligne écrit encore brute, parce qu'une autre pull request réécrit cette
ligne, sont rendues sans ces caractères -- un `"` brut ferait refuser tout le rendu -- et nommées une par
une avec leur pull request ; là encore, une exemption qui n'exempte plus rien fait échouer le contrôle.

Pour l'agent Claude Code, dont le jeton GitHub est facultatif (#245), le contrôle rend l'état activé **sans** le
jeton -- le défaut --, où ni `GH_TOKEN` ni `GITHUB_TOKEN` ne doivent figurer, puis **avec**, où les deux doivent porter
la valeur passée, sans que rien d'autre ne change entre les deux. Le jeton a pour défaut `false` : il est donc dans
`FREE_FORM_WITH_A_DEFAULT`, et le rendu qui porte des `$` vérifie que les deux variables arrivent bien, avec leur `$`
doublé. Le contrôle exige aussi que ce défaut soit exactement `false` : supprimé, il ne se verrait dans aucun rendu,
puisque le contrôle y traite une variable sans valeur comme vide, alors qu'Ansible échoue sur `is string` d'une variable
non définie, pour tout appelant qui laisse le jeton de côté.

Pour l'agent Claude Code encore (#287), chaque rendu qui le porte -- l'état activé, avec le jeton, avec un dossier hôte, et
le rendu qui porte des `$` -- est tenu de poser les cinq variables de modèle sur l'alias : l'une absente, ou à une autre
valeur, fait échouer le contrôle, et dans le rendu à `$` l'alias arrive avec ses `$` doublés comme le reste. L'alias est dans
`FREE_FORM_WITH_A_DEFAULT` pour cette raison.

## Exemple d'appel

```yaml
- role: deploy_Artificial_Intelligence_Docker_stack
  vars:
    Artificial_Intelligence_Docker_stack_deployment_role_name: "your_stack_deployment_role"
    Artificial_Intelligence_server_time_zone: "{{ server_time_zone | default('Etc/UTC') }}"
```

`playbook.Artificial_Intelligence.example.yaml`, à la racine du dépôt, en donne la version complète et commentée.

## Dépendances

Aucune déclarée dans `meta/`. Le rôle en inclut une à l'exécution -- celle que l'appelant nomme -- et c'est
précisément pour qu'elle ne soit pas déclarée ici qu'elle est un paramètre.

Une collection, en revanche, l'est dans `requirements.yml` à la racine du dépôt depuis #76 :
`community.docker`, pour les deux modules qui créent les comptes LibreChat. Voir « Prérequis » plus
haut.

## Licence

Double licence, et les deux arms ne sont pas symétriques :

- **AGPL-3.0-only** pour tout le monde, sans frais et sans formalité. Le texte est dans [`LICENSE`](LICENSE) ;
- ou une **licence commerciale négociée séparément**, pour qui ne peut pas tenir les obligations de l'AGPL.

Le choix est celui du destinataire. Prendre ce travail sous l'AGPL ne demande ni permission, ni
enregistrement, ni notification à quiconque.

Trois fichiers portent le reste, et ils se renvoient l'un à l'autre :

| Fichier | Ce qu'il dit |
|---|---|
| [`LICENSE-COMMERCIAL.md`](LICENSE-COMMERCIAL.md) | Ce que couvre l'arm commercial, dans quels cas il est nécessaire — presque jamais — et comment le demander. **Ce n'est pas une licence** : c'est la description d'une offre de négocier. |
| [`NOTICE`](NOTICE) | Le titulaire, l'absence d'historique de licence, et le matériel tiers — au premier chef les images que le stack nommera, qui gardent chacune leur licence et ne deviennent pas des œuvres dérivées de ce dépôt. |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | La clause qui permet à une contribution d'être offerte sous les **deux** arms. Elle est arrivée avant la première contribution extérieure, ce qui est la seule façon qu'elle avait de les couvrir toutes. |

Chaque fichier source de ce dépôt porte un en-tête SPDX. Les templates n'en portent pas : ils sont rendus
sur les nœuds gérés, et l'en-tête finirait recopié dans le `docker-compose` déployé.

## Auteur

[tigerblue77](https://github.com/tigerblue77)
