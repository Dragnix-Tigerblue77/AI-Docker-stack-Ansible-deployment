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
pip install -r requirements.txt          # ansible-core, ansible-lint, yamllint (épinglés)

yamllint .
ansible-lint
ansible-playbook --syntax-check playbook.*.yaml

python3 .github/scripts/check_compose_template.py
python3 .github/scripts/check_LiteLLM_account_isolation.py --selftest
python3 .github/scripts/check_LiteLLM_account_isolation.py
python3 .github/scripts/check_no_inventory_data.py --selftest
python3 .github/scripts/check_no_inventory_data.py

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
* En-tête SPDX sur chaque fichier. `reuse lint` n'est pas encore en CI, donc ces en-têtes ne sont
  vérifiés par personne pour l'instant — et cela dérive : `Dell_iDRAC_fan_controller_Docker` pose
  des en-têtes sans contrôle, et 12 de ses fichiers en sont dépourvus.

## Licence

Le dépôt est en **double licence** : AGPL-3.0-only pour tout le monde, ou une licence commerciale
négociée séparément — voir la section « Licence » du [`README`](README.md).

> ⚠️ **La clause de licence des contributions n'est pas encore écrite.** Elle relève de #35, et elle
> demande l'accord explicite de chaque titulaire de droits ; ce fichier ne peut pas la poser à leur
> place.
>
> Ce paragraphe a d'abord affirmé que toute contribution était « distribuée sous AGPL-3.0-only ».
> C'était faux, et faux dans le sens coûteux : une contribution reçue sous une clause AGPL seule
> **ne peut plus être incluse dans l'arm commercial** sans retourner demander l'accord de son
> auteur, contribution par contribution. C'est précisément ce que #35 cherche à éviter, et ce qui
> n'est pas réparable à peu de frais après coup.
>
> En attendant #35, une contribution extérieure arrive donc sous AGPL seule **par défaut**, et pas
> parce qu'un fichier l'a décidé.
