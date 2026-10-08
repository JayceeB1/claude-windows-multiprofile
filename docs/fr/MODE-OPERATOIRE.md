# Mode opératoire : Claude Desktop avec deux comptes (A et B)

Ce document dit quoi cliquer, où se trouve chaque chose, et quoi faire après une mise à jour ou
quand un compte te redemande de te connecter. Rien ici ne demande de taper une commande au quotidien.

## 1. Au quotidien : deux raccourcis

Sur le **bureau** :

| Raccourci | Compte | Icône |
| --- | --- | --- |
| **Claude (A existing)** | A, ton compte d'origine | orange |
| **Claude (B)** | B, le second compte | bleu avec un petit « B » |

- Les deux fenêtres peuvent tourner en même temps, chacune avec **son propre bouton** dans la barre des tâches.
- **Épingle une seule fois « Claude (B) »** à la barre des tâches : clic droit sur le raccourci du bureau,
  « Épingler à la barre des tâches ». Ensuite tu lances B depuis la barre des tâches, sans rien d'autre.
- N'épingle jamais le bouton d'une fenêtre déjà ouverte : Windows fabrique alors une épingle générique,
  avec l'icône d'origine. Si ça arrive, détache-la et épingle le raccourci du bureau.
- L'ancien raccourci **« Claude (B added) »** fonctionne encore, mais n'a ni l'icône bleue ni son propre bouton.
  Ne le supprime pas : l'installation de base le surveille.

Dans le dossier **« Claude multi-comptes »** du bureau :

| Raccourci | Quand l'utiliser |
| --- | --- |
| **Réparer Claude (A+B)** | Après une mise à jour de Claude, ou si quelque chose semble de travers (icône qui revient, partage cassé) |
| **Reconnecter B** | Si le compte B te demande de te connecter à nouveau |
| **Mode opératoire** | Ce document |

## 2. Où se trouve quoi

Les chemins ci-dessous sont les valeurs par défaut ; `%USERPROFILE%` désigne ton dossier utilisateur
(`C:\Users\<toi>`). Si tu as choisi d'autres dossiers à l'installation, remplace-les.

| Élément | Emplacement |
| --- | --- |
| Raccourcis | `%USERPROFILE%\Desktop\` et `%USERPROFILE%\Desktop\Claude multi-comptes\` |
| Lanceur d'origine (ne pas modifier) | `%USERPROFILE%\ClaudeProfiles\bin\` |
| Bouton et icône de B | `%USERPROFILE%\ClaudeProfiles\identity\` (fichier `identity.json` = ce qui a été installé) |
| Journal du partage de config | `%USERPROFILE%\ClaudeProfiles\shared-config\` (journal et sauvegardes) |
| Dernière version vue en bon état | `%USERPROFILE%\ClaudeProfiles\repair-state.json` |
| Données du Desktop A (connexion) | `%APPDATA%\Claude\` |
| Données du Desktop B (connexion) | `%APPDATA%\Claude-B\` |
| Config Claude Code de A | `%USERPROFILE%\.claude\` |
| Config Claude Code de B | `%USERPROFILE%\.claude-b\` |
| Les outils (ce dépôt) | le dossier où tu as cloné le dépôt (appelé « le dépôt » plus bas) |
| L'application Claude | gérée par Windows, `C:\Program Files\WindowsApps\Claude_<version>_…` : on ne s'en occupe pas |

Les deux **connexions** sont dans les dossiers `Roaming\Claude` et `Roaming\Claude-B`. C'est ce qui garde
tes deux comptes ouverts d'un jour à l'autre.

## 3. Ce que A et B partagent, et ce qu'ils ne partagent pas

**Partagé en direct** (ce que fait l'un se voit chez l'autre) : tes skills, agents, plugins, mods,
les **projets avec leur mémoire**, ton `CLAUDE.md` global, tes réglages (`settings.json`) et la configuration
des serveurs MCP du Desktop. Tes dossiers de projets sont de toute façon les mêmes sur le disque.
La **liste des sessions Claude Code** (la barre latérale « Récents » de l'onglet Code, avec ses projets) est tenue à
jour par copie, pas par un lien : l'application refuse d'enregistrer une session dans un dossier lié, et un profil lié
perd donc ce qu'il démarre. `scripts/SessionRecordSync.py` (lancé aussi par le raccourci « Réparer ») copie les fiches de
chaque profil vers l'autre : une session démarrée dans A se retrouve dans B après réouverture de B, et inversement, et se
reprend depuis l'un ou l'autre compte (par exemple quand un compte a atteint sa limite). Ouvre la même session dans une
seule fenêtre à la fois. Les **Projets** (bêta) de l'application sont propres à chaque compte et ne sont pas copiés : une
session rangée dans un Projet que l'autre compte n'a pas s'y affiche comme une session de dossier ordinaire.

**Les mods d'interface de Claude Code** (panneaux, bandeau au-dessus du prompt, ligne d'état, commandes) sont
partagés par deux mécanismes déjà en place : leurs dossiers (`mods`, `dev-mods`) sont liés, et la liste des
mods à charger (`CLAUDE_CODE_PLUGIN_DIRS`, dans le bloc `env` de `settings.json`) est lue par B à travers le
même `settings.json` (par exemple un dossier de mod déclaré dans cette liste, ou un mod placé dans
`%USERPROFILE%\.claude\mods`). Un mod ajouté
dans A, déclaré dans cette liste, se retrouve donc chez B au démarrage de sa prochaine session ; un plugin
installé par le système de plugins (`enabledPlugins`) suit le même chemin. Ce qui reste propre à chaque session :
la question « Activer le rechargement à chaud pour cette session ? », posée à chaque fois, et les mods de
développement en cours (un dossier par session dans `dev-mods`). Pour vérifier dans B, ouvre une session Code
et regarde si le panneau ou le bandeau du mod apparaît ; sinon tape `/reload-plugins`.

**Copié une fois** : la liste de tes serveurs MCP de niveau utilisateur (lue dans `%USERPROFILE%\.claude.json`,
copiée dans `%USERPROFILE%\.claude-b\.claude.json`). Si tu en ajoutes
un dans A plus tard, lance « Réparer » ; si B en a déjà une liste différente, la réparation la laisse en
l'état et te le signale (voir le dépannage).

**Jamais partagé, par sécurité** : la connexion, les jetons, les identifiants, l'identité du compte, les
cookies, et les **conversations du chat claude.ai** de chaque compte (elles sont stockées sur les serveurs
d'Anthropic, rattachées à ton compte, et rien ne peut les fusionner). Seules les sessions **Claude Code locales**
sont partagées. Les tâches planifiées du Code sont dans le même dossier que les sessions : elles sont donc
communes aux deux comptes (il n'y en a aucune aujourd'hui ; si tu en crées, évite d'ouvrir A et B en même temps
au moment prévu).

## 4. Après une mise à jour de Claude

**Ce qui se passe.** Windows installe la nouvelle version de l'application dans un nouveau dossier. Rien dans
ces outils ne contient le chemin de l'application : tout la retrouve tout seul à chaque lancement. Tes
connexions sont dans `AppData`, que la mise à jour ne touche pas. La plupart du temps, tu n'as donc **rien à faire**.

**À faire après chaque mise à jour, en 30 secondes :**

1. Ferme les deux fenêtres Claude (les fenêtres déjà ouvertes gardent l'ancienne version).
2. Double-clique sur **« Réparer Claude (A+B) »** dans le dossier du bureau.
3. Lis les lignes. Tout doit afficher **OK** (ou **RÉPARÉ**, ce qui est bon aussi). Appuie sur Entrée pour fermer.
4. Relance A et B avec leurs raccourcis.

**Ce que la réparation vérifie, et corrige toute seule quand c'est possible :**

| Contrôle | Correction automatique |
| --- | --- |
| Version de Claude, mise à jour détectée | information seulement |
| Une session enregistrée pour A et pour B | non : tu utiliseras « Reconnecter B » |
| Raccourci, icône et bouton séparé de B | oui, réinstallés à l'identique |
| Routeur de connexion dans le registre réel | oui |
| Liens de partage de la config | oui (B doit être fermée) ; un fichier remplacé par une copie est sauvegardé puis relié |
| Reçu d'installation de base (utile seulement pour retirer ou restaurer B de façon native) | oui, B fermée : l'identité du dossier de B est ré-enregistrée (journal, validation, retour arrière si elle échoue) |
| Quelle application reçoit les liens `claude://` | non : se règle dans Windows |

Une mise à jour peut remplacer le fichier `claude_desktop_config.json` de B par une copie ordinaire : le
partage de ce seul fichier est alors rompu sans message. « Réparer » le détecte et le remet, après avoir
mis l'ancien de côté dans `ClaudeProfiles\shared-config\backups`.

La réparation **ne se déclenche pas toute seule** : tu la lances d'un double-clic. Rien n'est programmé en
tâche de fond. Si tu veux qu'elle se lance à l'ouverture de ta session Windows, c'est possible, mais ça se
décide à part.

## 5. Si un compte te redemande de te connecter

Cela peut arriver après une mise à jour, une longue absence ou un changement de mot de passe. Les outils ne
peuvent pas l'empêcher, mais ils guident la reconnexion. La cause d'une déconnexion vient de Claude, pas de ce
dispositif : une connexion refaite proprement la règle.

### Compte A

1. Vérifie que les liens `claude://` vont bien à **Claude** (c'est l'état normal : « Réparer » l'affiche).
2. Ouvre **Claude (A existing)**, clique sur la connexion, termine dans le navigateur.

### Compte B : double-clique sur « Reconnecter B »

Le script fait tout, sauf un clic que Windows réserve à toi.

1. Dans le navigateur, **ouvre une fenêtre privée** et connecte-toi à claude.ai avec le compte B. Ferme les
   autres onglets de connexion Claude.
2. **Étape 1** : Paramètres s'ouvre. Cherche « claude », clique sur « CLAUDE », choisis **Claude Login Router**
   puis « Définir par défaut ». Le script attend ce choix.
3. **Étape 2** : B s'ouvre. Clique sur la connexion, **vérifie dans le navigateur que c'est bien le compte B**,
   autorise. Tu as 5 minutes. Le script constate que la connexion de B a changé.
4. **Étape 3** : dans la même fenêtre Paramètres, remets **Claude** (« CLAUDE », « Claude », « Définir par défaut »).
   Le script constate le retour à la normale.

À savoir :
- Fais **une seule connexion à la fois**, et ferme les anciens onglets de connexion avant de recommencer.
- Si c'est la fenêtre **A** qui réagit à la place de B, arrête-toi, ne relance rien et reviens vers l'assistant.
- Si tu oublies l'étape 3, le routeur reste par défaut et une future connexion de A serait refusée par
  sécurité : « Réparer » te l'indique (« routeur actif »).

## 6. Tout remettre en route (nouvelle machine, ou installation à refaire)

Prérequis : Claude Desktop installé depuis le Microsoft Store et connecté une fois au compte A ; Python 3.12+ ; le Mode
développeur de Windows activé ; ta propre icône `.ico` pour B (aucune n'est fournie).

À faire depuis un PowerShell ouvert **depuis le menu Démarrer** (pas depuis Codex ni depuis Claude Desktop : ces programmes
redirigent leurs écritures, et les outils le refusent), dans le dossier du dépôt, **toutes les fenêtres Claude fermées**.

**Un seul point d'entrée, en trois passages :**

```powershell
# 1. Écrit un modèle de spécification (chemins détectés, valeurs à remplacer) ; jamais écrasé.
.\scripts\Install-ClaudeMultiAccount.ps1 -WriteSpecTemplate
#    Remplace chaque REPLACE_WITH dans %USERPROFILE%\ClaudeProfiles\setup\claude.workspace.local.json.
#    Les quatre drapeaux « evidence » sont tes propres confirmations : mets-les à true seulement après vérification.
#    Mets protocol.consent à true pour autoriser le routeur de connexion (nécessaire pour connecter B).

# 2. Aperçu : rien n'est écrit ; chaque étape dit ce qu'elle ferait ou ce qui manque.
.\scripts\Install-ClaudeMultiAccount.ps1 -Spec "$env:USERPROFILE\ClaudeProfiles\setup\claude.workspace.local.json" -IconPath C:\chemin\claude-b.ico

# 3. Installation. Elle enregistre la capsule d'approbation, indique où elle est et attend que tu tapes INSTALL.
.\scripts\Install-ClaudeMultiAccount.ps1 -Spec "$env:USERPROFILE\ClaudeProfiles\setup\claude.workspace.local.json" -IconPath C:\chemin\claude-b.ico -ApproveProtocol -Apply
```

Les étapes s'enchaînent dans cet ordre, chacune rejouable sans risque après un échec : contrôles, installation de base
(lanceur, routeur de connexion, reçu), bouton et icône de B, raccourcis « Claude multi-comptes », liens de partage, puis
contrôle en lecture seule. À la fin : épingle **« Claude (B) »** à la barre des tâches, puis double-clique sur
**« Reconnecter B »** pour connecter le compte B (section 5).

**Pas à pas à la place**, si tu préfères lancer chaque partie toi-même (tout est en aperçu d'abord ; `-Apply` pour écrire) :

1. Le lanceur de base et le routeur : voir `README.md`, `docs/reference/SHARED-WORKSPACE.md` et `docs/PROTOCOL-ROUTING.md`.
2. Icône et bouton séparé de B :
   ```powershell
   .\scripts\Install-ClaudeIdentity.ps1 -Name B -ProfileDir "$env:APPDATA\Claude-B" -ConfigDir "$env:USERPROFILE\.claude-b" -IconPath C:\chemin\claude-b.ico -Apply
   ```
3. Raccourcis d'outils (dossier « Claude multi-comptes ») :
   ```powershell
   .\scripts\Install-ClaudeTools.ps1 -Apply
   ```
4. Partage de la config, avec B fermée (aperçu, puis application) :
   ```powershell
   python -B scripts\Link-SharedConfig.py
   python -B scripts\Link-SharedConfig.py --apply --approved --replace-files
   ```
   Ou plus simplement : double-clic sur « Réparer Claude (A+B) », qui fait la même chose.

## 7. Revenir en arrière

Chaque étape se défait sans toucher à tes connexions ni à tes projets :

```powershell
python -B scripts\Link-SharedConfig.py --rollback --approved                 # B fermée : retire les liens, restaure l'état d'avant
.\scripts\Install-ClaudeIdentity.ps1 -Name B -Remove -Apply                   # retire le raccourci et le bouton séparé de B
.\scripts\Install-ClaudeTools.ps1 -Remove -Apply                              # retire le dossier « Claude multi-comptes »
```

Retirer un lien ne supprime jamais ce vers quoi il pointe : les fichiers de A restent intacts.

## 8. Dépannage

| Symptôme | Cause probable | Que faire |
| --- | --- | --- |
| Les deux fenêtres sont sous un seul bouton, icône orange | B a été lancée sans passer par « Claude (B) » | Ferme B, relance-la avec « Claude (B) » |
| L'icône d'origine revient sur le bouton de B | Épingle générique créée depuis un bouton ouvert | Détache-la, épingle le **raccourci** du bureau |
| « Réparer » affiche **BLOQUÉ** pour le partage | B est ouverte | Ferme B, relance « Réparer » |
| « Réparer » affiche « lancé depuis Codex ou Claude Desktop » | Les outils refusent de tourner dans ces programmes | Utilise le raccourci du bureau |
| « TARGET_MCP_SERVERS_DIFFER… » pour les serveurs MCP | B a déjà une liste différente de celle de A | `python -B scripts\Link-SharedConfig.py --apply --approved --replace-mcp` (B fermée) |
| « Routeur de connexion : absent du registre » | Routeur à réenregistrer | « Réparer » le refait |
| Le routeur n'apparaît pas dans Paramètres | Registre à réenregistrer | « Réparer », puis rouvre Paramètres |
| B n'est pas connectée | Session absente ou expirée | « Reconnecter B » |
| « Reçu d'installation : à réconcilier » | Le reçu de l'installation de base garde l'ancien emplacement du dossier de B | « Réparer », B fermée : c'est corrigé et la ligne passe à OK |
| Une fenêtre est restée sur l'ancienne version | Fenêtre ouverte avant la mise à jour | Ferme-la et relance-la |

## 9. Règles d'or

- Un compte par fenêtre : lance A avec le raccourci de A, B avec celui de B.
- Lance les outils depuis un raccourci du bureau ou un PowerShell ouvert depuis le menu Démarrer.
- Ne modifie pas `ClaudeProfiles\bin` ni `claude_desktop_config.json` de B à la main : ce sont des liens.
- Avant de toucher au partage ou aux liens, ferme B.
- Une connexion à la fois, et vérifie toujours le compte affiché dans le navigateur avant d'autoriser.
