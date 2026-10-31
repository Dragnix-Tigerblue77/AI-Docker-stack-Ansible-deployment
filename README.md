<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
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
mécanique appartient à l'appelant, et elle existe déjà -- `Docker/deploy_Docker_swarm_stack` et
`Docker/deploy_Docker_compose_stack` du dépôt `Homelab_Ansible_deployment` la portent, chacun pour son
orchestrateur, avec tout ce que leurs commentaires documentent de pannes déjà payées.

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
    Artificial_Intelligence_Docker_stack_deployment_role_name: "Docker/deploy_Docker_swarm_stack"
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
| `Artificial_Intelligence_Docker_compose_file_destination_directory` | `/tmp/` | Où le fichier rendu atterrit sur le nœud géré. |
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
| `Artificial_Intelligence_PostgreSQL_database` · `Artificial_Intelligence_PostgreSQL_user` | `litellm` | Base et rôle de la passerelle. |
| `Artificial_Intelligence_PostgreSQL_data_Docker_volume_name` | `Artificial_Intelligence_PostgreSQL_data` | Volume **nommé** : survivre à une recréation de conteneur est un critère d'acceptation. |
| `Artificial_Intelligence_PostgreSQL_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`1g`) limite le service à cette taille, `false` n'en pose aucune. Voir « Pourquoi tout vit sous `deploy:` ». |
| `Artificial_Intelligence_LiteLLM_config_file_name` · `..._destination_path` | `LiteLLM_config.yaml` | La configuration de routage, montée en lecture seule. #2 en remplit le `model_list`. |
| `Artificial_Intelligence_LiteLLM_config_checksum` · `Artificial_Intelligence_LibreChat_config_checksum` | `false` | **Pas des réglages.** Le SHA-1 de chaque configuration montée, tel que le run vient de l'écrire : `tasks/main.yml` le passe lui-même au rôle de déploiement, et ce paramètre l'emporte sur tout sauf une *extra var*. Le nom de la config Docker qui porte chaque fichier en est dérivé (`..._config_Docker_name`). Voir « Une configuration modifiée recrée le conteneur qui la lit » plus bas (#161). |
| `Artificial_Intelligence_LiteLLM_UI_username` | `admin` | Le compte de connexion à `/ui`, dont le port est publié -- voir plus bas. |
| `Artificial_Intelligence_LiteLLM_UI_password` | aucun | **Obligatoire.** Rendu depuis le vault de l'appelant, comme les secrets ci-dessus. |
| `Artificial_Intelligence_LiteLLM_internal_users` | `[]` | Une **liste**, jamais une paire de variables nommées (#103) : chaque `{username, email}` devient un compte `internal_user` à lui, self-service, ajouté à `access_group:<username>`. Voir « Un compte par personne, pas une paire figée » plus bas. |
| `Artificial_Intelligence_LiteLLM_admin_API_URL` | *dérivé du port de LiteLLM* | **Pas un réglage.** Où les tâches `uri` du rôle joignent l'API d'administration de LiteLLM, depuis le nœud qui les exécute. |

Et celles que #2 apporte, pour le `model_list` du compte de la passerelle (voir plus bas pourquoi les
autres comptes n'ont pas les leurs ici) :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_LiteLLM_Gemini_API_key` | aucun | **Obligatoire.** |
| `Artificial_Intelligence_LiteLLM_GitHub_API_key` | `""` | Optionnelle depuis le retrait de GitHub Models (#109, #119) : plus aucune entrée active du `model_list` ne la lit. |
| `Artificial_Intelligence_LiteLLM_Mistral_API_key` | aucun | **Obligatoire.** |
| `Artificial_Intelligence_LiteLLM_Cerebras_API_key` | `""` | Optionnelle depuis que Cerebras n'a plus de palier gratuit (#200) : ses deux entrées sont commentées, plus aucune entrée active du `model_list` ne la lit. |
| `Artificial_Intelligence_LiteLLM_Groq_API_key` | aucun | **Obligatoire.** |
| `Artificial_Intelligence_LiteLLM_OpenRouter_API_key` | aucun | **Obligatoire.** |
| `Artificial_Intelligence_LiteLLM_DeepSeek_API_key` | aucun | **Obligatoire.** Le seul fournisseur **payant** de ce fichier (#101) -- l'API directe de DeepSeek n'a pas de palier gratuit permanent, contrairement à tous les autres. |

Et celles que #71 apporte, pour Redis :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_Redis_data_Docker_volume_name` | `Artificial_Intelligence_Redis_data` | Volume nommé : `--save 60 1` sans volume derrière ne sert à rien. |
| `Artificial_Intelligence_Redis_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`256m`) limite le service à cette taille, `false` n'en pose aucune. |
| `Artificial_Intelligence_Redis_password` | aucun | **Obligatoire.** `--requirepass` serait vide sinon. |

Et celles que #73 apporte, pour OmniRoute :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_OmniRoute_data_Docker_volume_name` | `Artificial_Intelligence_OmniRoute_data` | Volume nommé pour son magasin SQLite. |
| `Artificial_Intelligence_OmniRoute_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`2g`) limite le service à cette taille, `false` n'en pose aucune. À dimensionner si l'usage dépasse le simple dernier recours. |
| `Artificial_Intelligence_OmniRoute_dashboard_password` | aucun | **Obligatoire.** Remplace le `CHANGEME` de l'image. |

Et celles que #3 apporte, pour Qdrant :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_Qdrant_data_Docker_volume_name` | `Artificial_Intelligence_Qdrant_data` | Volume nommé pour `/qdrant/storage`. |
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
| `Artificial_Intelligence_Claude_code_workspace_Docker_volume_name` | `Artificial_Intelligence_Claude_code_workspace` | Le volume nommé monté sur `/workspace` quand le dossier hôte n'est pas fourni. Déclaré seulement dans ce cas. |
| `Artificial_Intelligence_Claude_code_model` | `claude-code` | L'alias que LiteLLM résout (#2) -- jamais un nom de modèle Anthropic littéral. C'est aussi la liste blanche de la clé de l'agent, et la valeur de **toutes** les variables de modèle de Claude Code posées dans le conteneur (#287, voir « L'agent Claude Code »). |
| `Artificial_Intelligence_Claude_code_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`2g`) limite le service à cette taille, `false` n'en pose aucune. |
| `Artificial_Intelligence_Claude_code_home_Docker_volume_name` | `Artificial_Intelligence_Claude_code_home` | Le volume nommé du répertoire personnel **entier** -- voir plus bas pourquoi. |

Et celles que #76 apporte, pour LibreChat et sa base :

| Variable | Défaut | Description |
|---|---|---|
| `Artificial_Intelligence_LibreChat_creds_key` · `..._creds_IV` · `..._JWT_secret` · `..._JWT_refresh_secret` | aucun | **Obligatoires**, les quatre. Sans eux, LibreChat en génère des temporaires au premier démarrage. |
| `Artificial_Intelligence_LibreChat_allow_registration` | `false` | Fermé : le port est publié sur le LAN. Comptes créés via `create-user`. |
| `Artificial_Intelligence_LibreChat_uploads_Docker_volume_name` · `Artificial_Intelligence_MongoDB_LibreChat_data_Docker_volume_name` | dérivés | Volumes nommés pour les pièces jointes et la base. |
| `Artificial_Intelligence_LibreChat_memory_limit` · `Artificial_Intelligence_MongoDB_LibreChat_memory_limit` | `false` | Aucune limite par défaut ; une chaîne (`1g`) limite le service à cette taille, `false` n'en pose aucune. / `512m` en exemple. |
| `Artificial_Intelligence_LibreChat_users` | aucun (`[]`) | **Obligatoire.** Liste de comptes LibreChat à créer, un dictionnaire par compte : `email`, `name`, `username`, `password` (chaînes non vides) et `admin` (booléen, `false` si absent) ; `admin: true` promeut le compte `ADMIN`. Voir plus bas. |

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

**Le mot de passe du tableau de bord est obligatoire, sans défaut.** L'image démarre avec `CHANGEME` si
rien n'est fourni -- documenté en amont comme volontairement faible pour forcer un changement. Traité
comme le mot de passe `/ui` de LiteLLM (#1) : vaulté, jamais laissé à son défaut.

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
saisissant lui-même sa propre clé de la passerelle -- Ansible n'a rien à y interpoler. Repris du POC
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

Ce n'est pas théorique. `Docker/deploy_Docker_swarm_stack` et `Docker/deploy_Docker_compose_stack` du
dépôt `Homelab_Ansible_deployment` remplissent tous les deux les trois obligations ci-dessus **sans
modification** — mais tous les deux lisent aussi `APT_cache_lifetime`, qui n'a de défaut ni dans l'un ni
dans l'autre. Elle vit dans les `vars:` du `playbook.CHSONP.yaml` de ce dépôt, donc elle est en portée
quand c'est lui qui appelle, et **absente partout ailleurs**. Un appelant qui ne la déclare pas échoue au
déploiement, sur une variable non définie, à l'intérieur d'un rôle d'un autre dépôt, portant un nom qui
n'apparaît nulle part dans l'appel qu'il a écrit.

Les deux rôles rendent en plus deux faits que les issues de service voudront lire :
`Docker_stack_first_deployment`, qui dit si le stack est déployé pour la première fois sur cette machine,
et `Docker_stack_deployment_state`.

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
sur tout le LAN) est accepté tel quel, sur un LAN jugé de confiance.** Chaque compte ajoute ses propres
clés fournisseur depuis `/ui`, à la main, plutôt que de les faire
rendre depuis un vault : c'est le même modèle que les autres bases auto-hébergées de cette estate --
déployées vides, peuplées en direct, sauvegardées de temps en temps dans leur dépôt -- et `/ui` doit donc
être joignable depuis un simple navigateur du LAN, avant même qu'un reverse proxy existe pour le faire à
sa place. Le coût n'est pas nul : pas de TLS, et l'authentification `UI_USERNAME` / `UI_PASSWORD` (voir
`Artificial_Intelligence_LiteLLM_UI_password` plus haut) comme seule chose entre le LAN et le conteneur qui porte la clé
maîtresse et les clés fournisseur des deux comptes. Un reverse proxy devant `/ui` reste la suite logique,
pas une clause de style.

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

`LiteLLM_config.yaml.j2` porte désormais le `model_list` réel du compte de la passerelle -- 52 entrées actives à
travers Gemini, Mistral, Groq, OpenRouter (`:free`) et OmniRoute en dernier recours -- repris de son
propre POC fonctionnel plutôt que ré-inventé. DeepSeek (#101) s'y ajoute en accès direct, seul
fournisseur payant du fichier : placé en dernier recours dans chaque cascade où il apparaît, juste
avant OmniRoute, qui reste le seul vraiment gratuit. La liste suit la règle posée par #169
(`CLAUDE.md`, « The model list keeps only what can be called ») : un modèle retiré par son fournisseur
est supprimé, un modèle servi mais délibérément non routé reste commenté avec sa raison, un nouveau
modèle est ajouté. #169 l'a appliquée à Groq, #200 à tous les autres (recensement du 2026-09-27) :
GitHub Models, fermé par GitHub le 2026-07-30 (#109), est supprimé et non plus archivé ; Cerebras n'a
plus de palier gratuit permanent (5 $ de crédit après ajout d'un moyen de paiement, expirés au bout
de 30 jours), ses deux modèles sont donc commentés comme ceux de SambaNova, et sa clé, restée
obligatoire, n'est plus lue par aucune entrée active ; Mistral ne donne plus qu'un crédit de 10 $
par mois (« Free mode », sans carte), traité comme gratuit. Les entrées `:free` d'OpenRouter
partagent une seule limite pour tout le compte : 20 requêtes par minute et 50 par jour, 1000 une fois
10 crédits achetés.

**Un seul compte dans ce `model_list`, et c'est un choix assumé, pas un oubli.** Les autres comptes
ajoutent les leurs eux-mêmes depuis `/ui` (voir `Artificial_Intelligence_LiteLLM_UI_password` plus haut) : même
modèle que les autres bases auto-hébergées, déployées vides puis peuplées en direct. Aucune entrée ne porte de
`model_info.access_groups` : un nom de compte figé dans une étiquette d'autorisation romprait la
réutilisabilité de ce rôle pour qui l'installe, pour un gain nul tant qu'il n'y a
qu'un seul compte à isoler de personne. Par défaut, toute clé voit tous les modèles -- voir « Un compte
par personne, pas une paire figée » plus bas pour la seule clé, `internal_user`, qui restreint déjà.
#2 demande encore davantage : `rpm_limit` / `tpm_limit` par clé, la segmentation `sci-*` / `gen-*`, le
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

### Un compte par personne, pas une paire figée (#103)

`Artificial_Intelligence_LiteLLM_internal_users` est une **liste**, vide par défaut, jamais une variable nommée par
personne : figer des noms fait de l'ajout d'une personne une modification de structure du rôle plutôt
qu'une ligne ajoutée à une liste. `tasks/main.yml` boucle
dessus et, pour chaque `{username, email}`, crée un compte LiteLLM au rôle `internal_user` --
self-service (peut créer/voir/supprimer ses propres clés, voir sa propre consommation) et rien
d'autre : jamais les clés d'un autre compte, jamais la configuration de la passerelle. Le compte
`Artificial_Intelligence_LiteLLM_UI_username`/`_password` (admin, plus haut) n'a pas sa place dans cette liste : il a déjà
un accès complet par le mécanisme natif de LiteLLM, une entrée ici ne lui apporterait rien.

La clé de chaque compte est scopée à `access_group:<username>` dès sa création -- LiteLLM sait déjà
grouper des clés par cette étiquette, alors même que le `model_list` (plus haut) n'en
porte plus aucune -- et `POST /key/generate`
n'est appelé **qu'une fois par compte, pour toujours** : la tâche se déclenche seulement l'exécution où
`POST /user/new` vient tout juste de créer ce compte (409 ensuite, pour toujours), jamais sur la base
du comportement propre de `/key/generate` rejoué, qui reste à vérifier contre une instance réelle (voir
« Non vérifié » plus bas). Cette clé n'est montrée qu'**une seule fois**, dans la sortie de ce rôle, le
jour où elle est réellement créée : LiteLLM ne la restitue pas une seconde fois, au même titre qu'un
jeton GitHub ou un mot de passe de registre. C'est cette clé-là, et non un compte LiteLLM partagé, que
la personne colle ensuite dans son propre compte LibreChat -- voir juste en dessous.

**`librechat.yaml` route désormais chaque compte LibreChat vers sa propre identité côté passerelle.**
`apiKey: "user_provided"` (au lieu d'une clé unique lue dans l'environnement du conteneur) fait que
LibreChat demande sa propre clé à CHAQUE compte, la première fois qu'il utilise cet endpoint, et la
retient chiffrée pour lui seul. Avant #103, une seule clé virtuelle servait tout le conteneur : n'importe
quel compte LibreChat, humain ou non, parlait à la passerelle sous la même identité, ce qui défaisait
l'isolation par compte dès qu'un deuxième humain existait -- même avec son propre compte LiteLLM créé
par la liste ci-dessus, rien ne l'aurait fait passer par lui plutôt que par l'unique clé partagée.
`Artificial_Intelligence_LibreChat_LiteLLM_virtual_key` et son `assert` obligatoire disparaissent avec ce changement :
plus personne n'a besoin de pré-fabriquer une clé virtuelle avant que LibreChat ne tourne, ce qui
règle au passage le problème d'ordre de démarrage que ce même `assert` posait (LiteLLM devait tourner
pour émettre une clé via son propre `/key/generate`, et rien ne se déployait tant que l'`assert`
n'était pas satisfait).

**Redis, déployé par #71.** Le cache de réponses (préserve les quotas TPM des paliers gratuits) et
l'état de cooldown partagé entre les workers de LiteLLM en avaient besoin ; ni #1 ni #2 n'en avait le
périmètre à l'origine. `--requirepass` est obligatoire, sans défaut, même raisonnement que la clé
d'API de Qdrant (#3) : défense en profondeur sur un service interne, sans port publié. **Le
cloisonnement du cache entre comptes n'est pas vérifié depuis cette session** -- documenté en amont
comme limité à la clé/l'équipe/l'organisation par défaut, mais à confirmer sur le banc d'essai avant
d'y faire confiance ; #79 est ouverte pour ça, voir aussi le commentaire dans
`LiteLLM_config.yaml.j2`.

**Un modèle repéré comme vieillissant, laissé en place.** `gemini-2-5-flash` est plusieurs générations
derrière la ligne `gemini-3.x` déjà prioritaire partout où il apparaît, et #2 le signale comme tel --
mais rien ne confirme qu'il soit réellement retiré, et il ne figure qu'en dernier recours dans les
cascades. Retiré ou confirmé au prochain audit de #2, pas ici.

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
`Artificial_Intelligence_Claude_code_workspace`, déclaré avec les autres : rien à préparer
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
prêt (`/health/readiness`, jusqu'à 150 s), le rôle demande à `GET /key/info` si cette clé existe -- par
son SHA-256, ce que LiteLLM stocke, pour que le secret n'apparaisse pas dans l'URL -- puis, si elle est
inconnue (404) ou signalée supprimée, la crée par `POST /key/generate` avec cette valeur dans `key`, le
`key_alias` `claude_code` et pour seule liste blanche l'alias du modèle
(`Artificial_Intelligence_Claude_code_model`) : c'est elle qui tient le conteneur à l'écart
du quota de tous les autres comptes. Les appels s'authentifient avec la clé maîtresse, que l'agent ne
détient jamais, et leurs tâches sont en `no_log`. Un second passage trouve la clé et ne change rien.

Ce que cela ne fait pas : le rôle **crée** la clé, il ne **réconcilie** pas une clé qui existe déjà -- elle
garde les modèles avec lesquels elle a été créée. Et **faire tourner la clé** demande d'abord de supprimer
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
l'alias `claude-code` que #2 résout dans LiteLLM. C'est le point de conformité de #13 : quoi que cet
alias résolve, ce ne doit jamais être un modèle Anthropic adossé à un abonnement.

**Toutes les variables de modèle de Claude Code portent ce même alias (#287).** Claude Code n'envoie pas que ses
requêtes principales : ses requêtes d'arrière-plan (titres, résumés courts) partent vers le modèle de classe Haiku, ses
sous-agents vers le leur, et les alias `sonnet` et `opus` vers d'autres encore. Or la clé de l'agent n'autorise que l'alias
(voir plus haut), et la `model_group_alias` de LiteLLM résout les noms Claude d'origine vers d'autres groupes
(`claude-3-5-haiku` vers `flash-lite`, `claude-3-opus` vers `pro`) : une requête sous l'un de ces noms est refusée par la
passerelle. Le bloc du service pose donc `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`,
`ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL` et `CLAUDE_CODE_SUBAGENT_MODEL`, toutes sur
`Artificial_Intelligence_Claude_code_model`, sans second alias et sans élargir la liste blanche de la clé -- c'est elle
qui tient le conteneur à l'écart du quota des autres comptes. Le coût : les requêtes d'arrière-plan et les sous-agents
passent par le modèle principal. Les noms viennent de la documentation de Claude Code
(« Model configuration » et « Environment variables », consultées le 2026-10-31) :
`ANTHROPIC_SMALL_FAST_MODEL`, l'ancien nom de la variable Haiku, y est déclaré obsolète au profit de
`ANTHROPIC_DEFAULT_HAIKU_MODEL`, et n'est pas posé. Ne le sont pas non plus `ANTHROPIC_DEFAULT_FABLE_MODEL` (l'alias
`fable`, que la documentation lie à une sélection explicite et au repli automatique de modèle sur un fournisseur tiers)
et `CLAUDE_CODE_AUTO_MODE_MODEL` (le classificateur du mode automatique) : ni l'un ni l'autre n'est un chemin que le
déploiement emprunte tel quel, et leur effet derrière la passerelle n'est pas mesuré. Rien de tout cela n'a été exécuté : ni LiteLLM réel, ni Claude Code
réel, donc ce que Claude Code affiche quand une requête est refusée reste non mesuré.

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

Il le rend aussi avec les sommes de contrôle des configurations montées renseignées (#161), que les
défauts laissent à `false` : chaque fichier doit être monté par `configs` -- jamais en bind mount dans
`volumes` --, sous une config déclarée au niveau supérieur avec son `file`, nommée d'après le contenu
sans suffixe quand rien n'est renseigné, et sans que rien d'autre ne change entre les deux états.

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
    Artificial_Intelligence_Docker_stack_deployment_role_name: "Docker/deploy_Docker_swarm_stack"
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
