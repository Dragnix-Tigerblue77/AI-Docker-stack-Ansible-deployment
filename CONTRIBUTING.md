<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

# Contribuer

## Les deux choses à faire une fois par clone

```bash
git config core.hooksPath .githooks
mkdir -p ~/.ansible/roles && ln -sfn "$(pwd)" ~/.ansible/roles/deploy_Artificial_Intelligence_Docker_stack
```

Un hook git n'est pas versionné : c'est le répertoire `.githooks/` qui l'est, et la première commande
ci-dessus dit à git d'aller l'y chercher. Sans elle, `.githooks/pre-commit` est un fichier inerte.

La seconde existe parce que ce dépôt **est** le rôle -- `tasks/`, `defaults/` et le reste vivent à sa
propre racine plutôt que sous un `roles/<nom>/` à lui, précisément ce qui permet à un appelant de
l'installer par Galaxy ou par un submodule et d'avoir le checkout lui-même résolu comme
`deploy_Artificial_Intelligence_Docker_stack`. Le revers : rien dans le checkout ne porte plus ce nom pour la recherche de
rôles d'Ansible, et `playbook.Artificial_Intelligence.example.yaml` appelle pourtant le rôle par ce nom nu. `~/.ansible/
roles` est l'un des emplacements qu'Ansible cherche par défaut, donc le symlink suffit, sans toucher à
`ansible.cfg`. Il est à refaire si le clone change d'emplacement -- `ln -sfn` ne s'en offusque pas, il
remplace simplement l'ancienne cible.

Il faut aussi que `gitleaks` soit installé — depuis
[ses releases](https://github.com/gitleaks/gitleaks/releases), à la version que la CI épingle, ou
en déposant le binaire à la racine du dépôt sous le nom `gitleaks`. Le hook accepte les deux.

**Ce hook est le seul garde-fou de ce dépôt qui refuse réellement quelque chose.** L'organisation
est sur un plan qui n'autorise ni *ruleset* ni protection de branche sur un dépôt privé
(`GET /repos/.../rulesets` répond `403 « Upgrade to GitHub Pro or make this repository public »`),
donc aucun contrôle de CI ne peut être rendu obligatoire avant fusion : la CI *constate*, elle ne
garde pas la porte. Le hook, lui, refuse le commit.

La seule fusion que la CI décide, c'est celle des mises à jour de Dependabot :
`.github/workflows/dependabot-auto-merge.yml` fusionne une mise à jour mineure ou corrective une
fois que chaque contrôle nommé dans `.github/rulesets/main.json` est vert sur elle — tous les jobs
de `ansible-ci.yml`, de `gitleaks.yml` et de `sign-off.yml`, par leur `name:`. Renommer ou ajouter
un job, c'est donc modifier ce fichier dans la même pull request ; `check_required_checks.py` échoue
tant que ce n'est pas fait. Ajouter un job laisse aussi chaque pull request de Dependabot déjà ouverte
attendre un contrôle qu'elle n'a jamais lancé, et rien ne la réveille : `@dependabot rebase` sur
chacune relance tous les workflows.

Cette fusion-là ne lance d'elle-même aucun workflow sur `main` : GitHub n'en démarre aucun pour un
push fait avec `GITHUB_TOKEN`. Le workflow relance donc lui-même `Ansible CI` et `gitleaks` sur
`main` juste après avoir fusionné (#180) : ce sont les runs d'événement `workflow_dispatch` qu'on
voit alors sur `main` dans l'onglet Actions. Ces deux workflows gardent pour cela leur déclencheur
`workflow_dispatch:`, qui permet aussi de les lancer à la main, sur n'importe quelle branche.
`sign-off` n'en a pas, et n'est pas relancé : il lit les commits d'une pull request, et une exécution
lancée à la main n'a pas de pull request, donc pas d'intervalle à lire.

Deux propriétés à connaître plutôt qu'à découvrir :

* `git commit --no-verify` le contourne sans rien dire. C'est une propriété de git, et le
  contournement reste un geste délibéré — le workflow `gitleaks` le rattrape à la pull request.
* si `gitleaks` est absent, le hook **refuse le commit** au lieu de se taire. Un hook de sécurité
  qui se désactive tout seul chez qui ne l'a pas installé ment à la personne qui en a le plus
  besoin.

## Lancer ce que la CI lancera

Aucun de ces contrôles n'a besoin de la moindre machine du homelab.

```bash
pip install -r requirements.txt          # ansible-core, ansible-lint, yamllint, reuse, PyYAML, Jinja2 (épinglés)
ansible-galaxy collection install -r requirements.yml   # community.docker, depuis #76

yamllint .
ansible-lint
ansible-playbook --syntax-check playbook.*.yaml

python3 .github/scripts/check_compose_template.py --selftest
python3 .github/scripts/check_compose_template.py
python3 .github/scripts/check_LiteLLM_account_isolation.py --selftest
python3 .github/scripts/check_LiteLLM_account_isolation.py
python3 .github/scripts/check_LiteLLM_model_drift.py --selftest
python3 .github/scripts/check_LiteLLM_model_drift.py       # hors ligne ; « --online » lit les catalogues des fournisseurs (clés requises, jamais lancé par la CI d'une pull request)
python3 .github/scripts/check_no_inventory_data.py --selftest
python3 .github/scripts/check_no_inventory_data.py
python3 .github/scripts/check_sign_off.py --selftest
python3 .github/scripts/check_sign_off.py origin/main HEAD   # l'intervalle d'une pull request, comme son job le lit : sort en 1 tant que la branche n'a aucun commit
python3 .github/scripts/check_required_checks.py --selftest
python3 .github/scripts/check_required_checks.py

reuse lint
gitleaks dir . --no-banner --redact       # ce que le workflow "gitleaks" lance

# Les deux jobs « role run » : le playbook d'exemple EXÉCUTÉ, pas seulement lu -- il faut Docker,
# « pip install docker » et, pour l'agent Claude Code allumé, « .github/role_run/stand_in_gateway.py »
# qui écoute. Voici celui où l'agent est allumé ; l'autre ajoute
# « -e @.github/role_run/vars.claude_code_agent_off.yml ».
ANSIBLE_ROLES_PATH=.github/role_run/roles:~/.ansible/roles ansible-playbook \
  -i .github/role_run/inventory.ini -e @.github/role_run/vars.yml playbook.Artificial_Intelligence.example.yaml
```

`check_no_inventory_data.py` et `check_sign_off.py` n'utilisent que la bibliothèque standard.
`check_LiteLLM_account_isolation.py` lit PyYAML, et c'est la seule dépendance de ce contrôle et de
`check_required_checks.py` (qui la lit aussi, puisqu'elle était déjà payée) : sa version ligne à
ligne ne voyait pas un repli inter-comptes écrit en style bloc — la forme même que produit tout
sérialiseur YAML, donc `to_nice_yaml`. Un garde-fou qui dépend du style d'écriture de ce qu'il
surveille n'en est pas un. `check_LiteLLM_model_drift.py` lit aussi PyYAML et y ajoute Jinja2 : il
rend le modèle de configuration avec Jinja2 seul, donc sans les filtres propres à Ansible, au lieu
de deviner ce que ses balises en feraient.

Chacun sait se vérifier lui-même (`--selftest`) — un contrôle dont personne n'a jamais vu l'échec
est un contrôle que personne ne croit. Le premier compare ses verdicts à neuf configurations dont
huit sont délibérément fautives ; le second à seize lignes construites en mémoire ; celui du
sign-off construit de vrais dépôts git jetables dans un répertoire temporaire, et y rejoue aussi le
hook de démarrage de session.

> `gitleaks dir .` lancé **en local** sur un arbre contenant un vrai `.env` sort en 1, alors que le
> job de CI est vert : `dir` lit l'arbre de travail et ne consulte pas le `.gitignore`, tandis que
> `actions/checkout` ne matérialise que ce qui est suivi par git. Les deux comportements sont
> corrects ; ce n'est pas une régression à corriger.

## Ce que les contrôles maison refusent, et comment les satisfaire

| Contrôle | Ce qu'il refuse |
| --- | --- |
| `check_LiteLLM_account_isolation.py` | Une configuration où le quota d'une personne peut payer l'appel d'une autre : un `model_name` qui regroupe deux comptes, un repli qui traverse une frontière de compte, une entrée dont l'étiquette ne dit pas la même chose que sa clé. |
| `check_LiteLLM_model_drift.py` | Une liste de modèles qui ne se tient plus : une cascade ou un alias qui nomme une entrée absente ou commentée, un `model_name` en double, une entrée commentée qui ne donne pas sa raison, une ligne `drift-ignore:` mal formée, ou un modèle qui ne se rend plus. Il lit le modèle rendu avec toutes les clés de fournisseur données, par Jinja2 seul : un filtre que seul Ansible fournit lui est refusé. La moitié en ligne, qui compare la liste aux catalogues des fournisseurs, tourne chaque semaine dans `LiteLLM_model_drift.yml` et jamais sur une pull request. |
| `check_no_inventory_data.py` | Une adresse IP ou un nom de domaine écrit en dur. Ils appartiennent à l'inventaire de l'appelant : un rôle qui les porte cesse d'être réutilisable, et publie le homelab au passage. Aussi un nom de personne dans l'interface du rôle (variable, variable d'environnement, service, volume, nom de tâche, lignes des tableaux de variables du README) : le rôle sert à des tiers, on nomme ce que la chose est, pas pour qui elle a été écrite. |
| `check_required_checks.py` | Une liste de contrôles requis, `.github/rulesets/main.json`, qui ne correspond plus aux workflows : un contexte qu'aucun job ne rapporte (chaque mise à jour de Dependabot attendrait alors un humain sans que rien ne paraisse cassé), ou un job de `ansible-ci.yml`, de `gitleaks.yml` ou de `sign-off.yml` absent de la liste (une mise à jour rouge sur ce seul job fusionnerait quand même). Il refuse aussi un fichier qui ne vise plus la branche par défaut. |
| `check_sign_off.py` | Une pull request dont un commit n'a pas de `Signed-off-by` exploitable : absent, cité au milieu du message plutôt qu'en trailer, sans adresse, ou qui ne nomme que l'agent. Voir *Signer son travail* plus bas. |
| `check_compose_template.py` | Arrivé avec #31, il rend le template de compose dans ses **deux** états et analyse le résultat — lire un diff n'est pas une vérification. Rien ne le lançait jusqu'ici, faute de workflow ; c'est cette PR qui le branche. |

Le second fonctionne par **liste blanche**, et c'est la seule forme possible : une liste noire
devrait énumérer les domaines interdits, donc écrire le domaine du homelab dans un fichier
versionné — exactement ce que la règle interdit. Un hôte amont légitime s'ajoute à `ALLOWED_HOSTS`
**avec sa raison**, dans le même commit que le code qui le cite.

## Conventions

* **En français :** les issues, les pull requests, `README.md`, `CONTRIBUTING.md` et les modèles
  d'issue. **En anglais :** les messages de commit, le code, les commentaires, les noms de tâches
  Ansible, les messages d'erreur, `NOTICE` et `LICENSE-COMMERCIAL.md`. La règle : ce qu'un tiers lit
  dans le code ou dans la sortie d'un run reste en anglais. La section *Language* de `CLAUDE.md`
  en donne la raison.
* Aucun secret en clair, jamais, y compris dans un exemple.
* Aucune adresse IP ni nom d'hôte dans le code **ni dans les issues**. `gitleaks` ne lit que l'arbre
  de travail et le *secret scanning* de GitHub demanderait un plan que l'organisation n'a pas : le
  contenu des issues n'est couvert par **aucun** filet automatique, c'est une vigilance humaine.
* Chaque commit d'une pull request porte un `Signed-off-by` : voir *Signer son travail* plus bas.
* Les pull requests ne sont **jamais ouvertes en draft**. Ce qui n'est pas vérifié se dit dans le
  corps de la pull request.
* En-tête SPDX sur chaque fichier, **vérifié par `reuse lint` en CI** (#52) — à une exception près :
  un fichier racine nommé `LICENSE*` n'est pas contrôlé du tout, `reuse` le lisant comme un texte de
  licence. Mesuré : un `LICENSE-COMMERCIAL.md` passe à l'identique avec ou sans en-tête. Les deux familles qui
  n'en portent pas — les templates de rôle, rendus sur le nœud géré, et le JSON, qui n'a pas de
  syntaxe de commentaire — sont déclarées dans `REUSE.toml`, chacune avec sa raison.
  `LICENSE` est un **lien symbolique** vers `LICENSES/AGPL-3.0-only.txt` : le fichier que `reuse`
  exige et celui dont GitHub tire le badge de licence sont ainsi les mêmes octets, pas deux copies
  libres de diverger.

## La licence de vos contributions

Le dépôt est en **double licence** : [AGPL-3.0-only](LICENSE) pour tout le monde, ou une
[licence commerciale](LICENSE-COMMERCIAL.md) négociée séparément avec le titulaire des droits.

Une double licence ne tient que si **chaque ligne de l'arbre peut être offerte sous les deux arms**.
Une seule contribution arrivée sous l'AGPL seule rendrait l'arm commercial impossible à accorder
honnêtement à partir de là — et ça ne se répare pas à peu de frais : il faut retrouver son auteur et
lui demander son accord, contribution par contribution.

Donc, **en soumettant une contribution à ce dépôt, vous acceptez que** :

1. votre contribution soit **licenciée au public sous la GNU Affero General Public License,
   version 3** (`AGPL-3.0-only`), aux mêmes termes que le reste du projet ; et
2. vous accordiez à **Tigerblue77** ([@tigerblue77](https://github.com/tigerblue77)) une licence
   perpétuelle, mondiale, non exclusive, gratuite et irrévocable de reproduire, préparer des œuvres
   dérivées de, afficher publiquement, sous-licencier et distribuer votre contribution **sous
   d'autres termes également, y compris des termes commerciaux propriétaires** ; et
3. vous ayez le droit d'accorder les deux — le travail est le vôtre, ou vous êtes autorisé à le
   soumettre (politique de propriété intellectuelle de votre employeur comprise).

### Ce que ce n'est pas

- **Ce n'est pas une cession de droits d'auteur.** Vous gardez l'intégralité du droit d'auteur sur ce
  que vous avez écrit. Vous pouvez relicencier, réutiliser ou vendre votre propre contribution
  ailleurs, exactement comme vous le pouviez avant.
- **Ce n'est pas exclusif.** Le point 2 donne au titulaire une licence *à côté* de la vôtre, pas *à
  la place* de la vôtre.
- **Ça ne met pas votre travail derrière un péage.** Tout ce que vous contribuez reste disponible
  sous l'AGPL, et le reste : une licence accordée sur une copie ne peut pas être retirée à qui la
  détient. Le point 2 permet seulement au titulaire d'offrir *en plus* le même code à une partie qui
  paie pour des termes que l'AGPL ne peut pas lui donner.

### Si vous contribuez régulièrement

Ce dépôt est partagé, et le point 2 est écrit pour un pair autant que pour un contributeur de
passage. Concrètement, pour quelqu'un qui commite ici toutes les semaines : vous restez titulaire de
tout ce que vous écrivez, vous pouvez le reprendre ailleurs sans rien demander à personne, et la
seule chose que vous accordez est le droit d'en faire **aussi** un autre usage — celui que l'AGPL
seule interdirait.

Le `NOTICE` est l'endroit où cela se voit : la ligne de copyright y devient collective à la première
contribution extérieure, et qui préfère y être nommé plutôt que couvert par elle le dit dans sa pull
request. Ni l'un ni l'autre n'est une condition pour contribuer.

### Si le point 2 ne vous convient pas

Dites-le dans votre pull request plutôt que de vous taire. Une contribution peut être fusionnée sans
le point 2 — il suffit de le signaler avant la fusion — et la partie de l'arbre qu'elle couvre est
alors inscrite dans le [`NOTICE`](NOTICE), parce qu'un licencié commercial n'a aucun autre moyen
d'apprendre où l'arm commercial ne va pas. Une contribution qui ne peut pas être doublement
licenciée vaut mieux repérée en relecture qu'après la fusion.

### Pourquoi cette clause arrive maintenant

Parce qu'elle ne peut parler que des contributions soumises **après** son existence. À la date où
elle est écrite, `git shortlog -sne` sur `main` ne nomme que deux auteurs : le titulaire des droits,
et l'agent qui a commité pour lui et à sa demande. **Aucune contribution extérieure n'est encore
arrivée**, donc la clause les couvre toutes — il n'y a rien derrière elle à rattraper. Écrite six
mois plus tard, elle aurait laissé un trou.

## Signer son travail — le *Developer Certificate of Origin*

Chaque commit d'une pull request porte une ligne `Signed-off-by`. L'ajouter, c'est votre attestation du
[Developer Certificate of Origin 1.1](https://developercertificate.org/), dont seul le texte anglais
fait foi :

> By making a contribution to this project, I certify that:
>
> (a) The contribution was created in whole or in part by me and I have the right to submit it under the open source license indicated in the file; or
>
> (b) The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate open source license and I have the right under that license to submit that work with modifications, whether created in whole or in part by me, under the same open source license (unless I am permitted to submit under a different license), as indicated in the file; or
>
> (c) The contribution was provided directly to me by some other person who certified (a), (b) or (c) and I have not modified it.
>
> (d) I understand and agree that this project and the contribution are public and that a record of the contribution (including all personal information I submit with it, including my sign-off) is maintained indefinitely and may be redistributed consistent with this project or the open source license(s) involved.

Le sign-off atteste le DCO, et lui seul : le droit de soumettre la contribution sous la licence
libre « indiquée dans le fichier », ici l'AGPL-3.0-only. Il ne dit rien de l'arm commercial, qui
repose sur le grant de la section précédente (points 1 à 3), donné en soumettant la contribution,
qu'une ligne `Signed-off-by` soit présente ou non. Le sign-off ne le remplace pas et n'en change pas
les termes ; il y ajoute une trace, commit par commit, de l'engagement de l'auteur sur son droit de
soumettre ce qu'il soumet, un droit que le point 3 du grant suppose lui aussi, mais pour les deux
licences.

Signez avec l'option `-s`, sous votre vrai nom et avec une adresse joignable :

```bash
git commit -s -m "Say what the change does"
```

qui ajoute :

```
Signed-off-by: Random J Developer <random@example.invalid>
```

Oublié sur le dernier commit ? `git commit --amend -s`. Sur plusieurs ? `git rebase --signoff <base>`, puis
`git push --force-with-lease`.

Le job **sign-off** (`.github/workflows/sign-off.yml`) lit les commits de chaque pull request et
passe au rouge sur celle où l'un d'eux n'a pas de sign-off exploitable. Comme tous les contrôles de
ce dépôt, il informe la relecture et n'empêche aucune fusion de la main du mainteneur : le hook
ci-dessus ne lit pas les sign-offs, la relecture est donc la seule barrière, et seules les mises à
jour de Dependabot attendent ce job. Les règles exactes, et pourquoi elles sont ce qu'elles sont,
sont dans la docstring de `.github/scripts/check_sign_off.py` ; ce qu'il faut en savoir :

* il lit un *trailer* au sens de git, de la forme `Signed-off-by: Nom <adresse>` : une ligne citée au
  milieu d'un message n'en est pas un, et une ligne vide ou sans adresse ne certifie personne ;
* les commits de fusion sont ignorés : git les écrit lui-même, ils n'apportent rien à attester, et ce
  qu'ils amènent a été signé là où cela a été écrit ;
* il ne regarde que les commits de la pull request. L'historique d'avant la règle n'en porte pour ainsi
  dire pas, les commits de Dependabot mis à part, et n'est pas réécrit : signer une branche publiée
  après coup demanderait de la réécrire ;
* Dependabot signe lui-même ses commits, donc ses mises à jour n'ont besoin d'aucune exception ;
* un commit fait dans l'éditeur web de GitHub n'en porte un que si le dépôt le demande, ce qui est
  un réglage (« Require contributors to sign off on web-based commits ») et non un fichier ; un
  commit écrit par un outil d'API de fichiers (`push_files`, `create_or_update_file`) n'en porte un
  que si l'appel l'a écrit dans son message, et c'est pourquoi une session commite par git et par
  l'alias, pas par l'API.

### Contributions écrites par un agent

Une partie de ce qui est ici est écrite par un agent de code, sur instruction du mainteneur. Le DCO
ne plie pas pour cela : un commit écrit par un outil a autant besoin qu'un autre d'une attestation
faite par quelqu'un qui puisse la faire.

Un agent est un outil. Un outil ne certifie rien, et un `Signed-off-by` qui en nommerait un serait un
trailer qui satisfait un contrôle en ne nommant personne qui puisse faire l'attestation ci-dessus. Mais
c'est aussi lui qui a écrit le code, et un commit a la place de dire les deux. Pour ces commits :

* **l'auteur est l'agent** (`Claude <noreply@anthropic.com>`). `git log`, `git blame`, `git shortlog` et
  le graphe des contributeurs de GitHub lisent ce champ : c'est le seul endroit où consigner qui a écrit
  le travail compte. Y mettre le mainteneur dirait qu'il a tapé ce qu'un outil a écrit ;
* **le `Signed-off-by` est celui du mainteneur** (`Tigerblue77 <37409593+tigerblue77@users.noreply.github.com>`),
  parce que l'attestation est la sienne. Elle ne peut pas venir de `git commit -s`, qui dérive le
  trailer de l'identité configurée — celle qui doit rester l'agent. Elle est donc passée explicitement
  par l'alias `git signoff` que `.claude/hooks/session-start.sh` pose au début de chaque session Claude
  Code on the web sur la copie du mainteneur : une règle qu'il faut se rappeler à chaque fois est une
  règle qu'on oublie. Une session locale commite sous le nom de la personne au clavier, qui signe avec
  `-s` comme n'importe qui ;
* **l'attestation est l'acte du mainteneur : relire, puis fusionner.** Le trailer l'énonce, la
  relecture le rend vrai. Une pull request fusionnée sans être lue porte un sign-off qui ne veut
  rien dire, et aucun workflow ne sait faire la différence. Le contrôle lit la forme du trailer et,
  sur un commit dont l'agent est l'auteur, à quelle adresse il est : il signale un sign-off qui ne
  nomme que l'agent, et un commit de l'agent signé par quelqu'un d'autre que le mainteneur. Que la
  personne derrière l'adresse ait réellement relu quoi que ce soit, il ne peut pas le voir, et ne le
  verra jamais.

Le trailer `Co-Authored-By` que l'agent ajoute à ses commits reste en place : le contrôle n'en tient aucun
compte.

Si vous êtes un contributeur et non le mainteneur, presque rien de tout cela ne vous concerne :
signez votre propre travail, sous votre nom. Une seule règle vaut pour tous : un commit dont
l'auteur porte l'adresse de l'agent (`noreply@anthropic.com`) ne passe le contrôle qu'avec le
sign-off du mainteneur. Le hook connaît la différence : il ne pose l'identité de l'agent que là où
`origin` est un dépôt de l'organisation qui héberge celui-ci, et le dit sur un fork.
