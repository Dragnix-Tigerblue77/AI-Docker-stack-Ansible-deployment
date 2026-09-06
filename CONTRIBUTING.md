<!--
SPDX-FileCopyrightText: 2026 Tigerblue77
SPDX-License-Identifier: AGPL-3.0-only
-->

# Contribuer

## La seule chose à faire une fois par clone

```bash
git config core.hooksPath .githooks
```

Un hook git n'est pas versionné : c'est le répertoire `.githooks/` qui l'est, et la commande
ci-dessus dit à git d'aller l'y chercher. Sans elle, `.githooks/pre-commit` est un fichier inerte.

Il faut aussi que `gitleaks` soit installé — depuis
[ses releases](https://github.com/gitleaks/gitleaks/releases), à la version que la CI épingle, ou
en déposant le binaire à la racine du dépôt sous le nom `gitleaks`. Le hook accepte les deux.

**Ce hook est le seul garde-fou de ce dépôt qui refuse réellement quelque chose.** L'organisation
est sur un plan qui n'autorise ni *ruleset* ni protection de branche sur un dépôt privé
(`GET /repos/.../rulesets` répond `403 « Upgrade to GitHub Pro or make this repository public »`),
donc aucun contrôle de CI ne peut être rendu obligatoire avant fusion : la CI *constate*, elle ne
garde pas la porte. Le hook, lui, refuse le commit.

Deux propriétés à connaître plutôt qu'à découvrir :

* `git commit --no-verify` le contourne sans rien dire. C'est une propriété de git, et le
  contournement reste un geste délibéré — le workflow `gitleaks` le rattrape à la pull request.
* si `gitleaks` est absent, le hook **refuse le commit** au lieu de se taire. Un hook de sécurité
  qui se désactive tout seul chez qui ne l'a pas installé ment à la personne qui en a le plus
  besoin.

## Lancer ce que la CI lancera

Aucun de ces contrôles n'a besoin de la moindre machine du homelab.

```bash
pip install -r requirements.txt          # ansible-core, ansible-lint, yamllint, reuse, PyYAML (épinglés)

yamllint .
ansible-lint
ansible-playbook --syntax-check playbook.*.yaml

python3 .github/scripts/check_compose_template.py --selftest
python3 .github/scripts/check_compose_template.py
python3 .github/scripts/check_LiteLLM_account_isolation.py --selftest
python3 .github/scripts/check_LiteLLM_account_isolation.py
python3 .github/scripts/check_no_inventory_data.py --selftest
python3 .github/scripts/check_no_inventory_data.py

reuse lint
gitleaks dir . --no-banner --redact       # ce que le workflow "gitleaks" lance
```

`check_no_inventory_data.py` n'utilise que la bibliothèque standard.
`check_LiteLLM_account_isolation.py` lit PyYAML, et c'est la seule dépendance que ces contrôles se
paient : sa version ligne à ligne ne voyait pas un repli inter-comptes écrit en style bloc — la
forme même que produit tout sérialiseur YAML, donc `to_nice_yaml`. Un garde-fou qui dépend du style
d'écriture de ce qu'il surveille n'en est pas un.

Chacun sait se vérifier lui-même (`--selftest`) — un contrôle dont personne n'a jamais vu l'échec
est un contrôle que personne ne croit. Le premier compare ses verdicts à neuf configurations dont
huit sont délibérément fautives ; le second à seize lignes construites en mémoire.

> `gitleaks dir .` lancé **en local** sur un arbre contenant un vrai `.env` sort en 1, alors que le
> job de CI est vert : `dir` lit l'arbre de travail et ne consulte pas le `.gitignore`, tandis que
> `actions/checkout` ne matérialise que ce qui est suivi par git. Les deux comportements sont
> corrects ; ce n'est pas une régression à corriger.

## Ce que les contrôles maison refusent, et comment les satisfaire

| Contrôle | Ce qu'il refuse |
| --- | --- |
| `check_LiteLLM_account_isolation.py` | Une configuration où le quota d'une personne peut payer l'appel d'une autre : un `model_name` qui regroupe deux comptes, un repli qui traverse une frontière de compte, une entrée dont l'étiquette ne dit pas la même chose que sa clé. |
| `check_no_inventory_data.py` | Une adresse IP ou un nom de domaine écrit en dur. Ils appartiennent à l'inventaire de l'appelant : un rôle qui les porte cesse d'être réutilisable, et publie le homelab au passage. |
| `check_compose_template.py` | Arrivé avec #31, il rend le template de compose dans ses **deux** états et analyse le résultat — lire un diff n'est pas une vérification. Rien ne le lançait jusqu'ici, faute de workflow ; c'est cette PR qui le branche. |

Le second fonctionne par **liste blanche**, et c'est la seule forme possible : une liste noire
devrait énumérer les domaines interdits, donc écrire le domaine du homelab dans un fichier
versionné — exactement ce que la règle interdit. Un hôte amont légitime s'ajoute à `ALLOWED_HOSTS`
**avec sa raison**, dans le même commit que le code qui le cite.

## Conventions

* Documentation, commentaires et messages de commit **en français**. Ce dépôt diverge
  volontairement de `Homelab_Ansible_deployment` sur ce point.
* Aucun secret en clair, jamais, y compris dans un exemple.
* Aucune adresse IP ni nom d'hôte dans le code **ni dans les issues**. `gitleaks` ne lit que l'arbre
  de travail et le *secret scanning* de GitHub demanderait un plan que l'organisation n'a pas : le
  contenu des issues n'est couvert par **aucun** filet automatique, c'est une vigilance humaine.
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

### Sur le *sign-off*

L'historique n'en porte aucun et rien ne l'impose. Le grant ci-dessus est ce qu'un *Developer
Certificate of Origin* serait là pour certifier, et il s'applique qu'une ligne `Signed-off-by` soit
présente ou non. Si cela change, ce sera annoncé ici, pas appliqué en silence.

### Pourquoi cette clause arrive maintenant

Parce qu'elle ne peut parler que des contributions soumises **après** son existence. À la date où
elle est écrite, `git shortlog -sne` sur `main` ne nomme que deux auteurs : le titulaire des droits,
et l'agent qui a commité pour lui et à sa demande. **Aucune contribution extérieure n'est encore
arrivée**, donc la clause les couvre toutes — il n'y a rien derrière elle à rattraper. Écrite six
mois plus tard, elle aurait laissé un trou.
