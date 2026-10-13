# Guide de ma version de Signal Matin

Ce dépôt est un fork de [sosoj92/signal-matin](https://github.com/sosoj92/signal-matin).
Ma version vit sur la branche `perso`, qui est la branche par défaut du fork. Elle
ajoute une édition « une feuille » : un journal A4 recto verso, généré chaque matin.

Ce guide explique comment le journal fonctionne, comment l'installer sur une
nouvelle machine, et comment récupérer les mises à jour de l'auteur d'origine sans
perdre mes modifications.

## Ce que produit le journal

Une seule feuille, deux pages.

**Recto**

- la date en titre ;
- à gauche : la météo, mon Google Agenda du jour, les marchés ;
- à droite : le gros titre, un article développé (« À retenir »), deux blocs côte à
  côte (« À lire aussi » et « Bourse & crypto »), puis un article de veille ;
- en bas : mot français, vocabulaire tech, calcul mental et citation du jour.

**Verso**

- la suite des articles sur trois colonnes : actualité, culture et sciences, veille
  IA et dev ;
- en bas : les mots croisés du jour et la météo à 5 jours.

Rien n'est jamais coupé : un article qui ne tient pas dans la page est laissé de
côté en entier, et il n'y a jamais de troisième page.

## Comment ça fonctionne

```text
config.yaml  ->  connecteurs  ->  édition (JSON)  ->  mise en page HTML/CSS  ->  PDF A4
```

1. **Les connecteurs** (`src/signal_matin/connectors/`) lisent les sources :
   flux RSS, météo Open-Meteo, Google Agenda, cours de marché Yahoo Finance,
   citation du jour (flux RSS de Dicocitations).
   Aucune clé d'API n'est nécessaire, sauf l'accès Google Agenda.
2. **Le texte des articles** : les flux ne donnent qu'une à trois phrases. Le
   journal va donc lire le début de l'article sur le site du média quand celui-ci
   le permet. Le Monde le refuse ; ses articles gardent le résumé du flux.
3. **Le choix des articles** (`src/signal_matin/selection.py`) :
   - *doublons* : deux articles de flux différents qui racontent le même fait ne
     sont imprimés qu'une fois, dans leur version la plus fournie, y compris d'une
     rubrique à l'autre (actualité, culture, veille, bourse) ;
   - *importance* : un sujet traité par plusieurs médias le même jour monte en une ;
   - *mémoire de la veille* : ce qui a été imprimé la veille passe en dernier, et le
     gros titre change de sujet d'un jour à l'autre quand un autre candidat existe.
     Cette mémoire est relue dans le fichier de la veille, dans `output/data/` :
     supprimer ce dossier la remet à zéro.

   Les articles sont comparés par leurs mots, sans comprendre le texte : c'est une
   estimation, pas un jugement éditorial.
4. **La mise en page** (`src/signal_matin/renderer.py` et `web/signal_matin.css`)
   compose les deux pages, puis Chromium en fait un PDF.

Une source en panne ne bloque rien : sa rubrique disparaît et le reste est généré.

### Où régler quoi

| Je veux changer… | Fichier | Endroit |
|---|---|---|
| Les médias d'actualité, culture, sciences | `config.yaml` | `news.feeds` |
| Les sources de veille IA et dev | `config.yaml` | `tech.feeds` (catégorie `IA` = veille IA) |
| Les valeurs de marché | `config.yaml` | `markets.groups` (codes Yahoo Finance) |
| Les actualités bourse et crypto | `config.yaml` | `markets.feeds` |
| La ville de la météo | `config.yaml` | `weather` |
| La citation du jour | `config.yaml` | `personal.quote_feed` (flux RSS) ; `personal.quotes` sert de secours |
| L'envoi sur Telegram | `config.yaml` et `.env` | `telegram.enabled` ; jeton et identifiant du chat dans `.env` |
| L'agenda Google lu | `config.yaml` | `calendar.google.calendar_id` |
| Le nombre d'articles par zone | `src/signal_matin/selection.py` | constantes `SHEET_…` en haut du fichier |
| La sévérité de la chasse aux doublons | `src/signal_matin/selection.py` | `SIMILARITY_STRONG` et `SIMILARITY_WEAK` (plus bas = plus de regroupements) |
| Les tailles, polices, espacements | `web/signal_matin.css` | bloc « Edition une feuille » |

Le fichier `web/signal_matin.css` a un jumeau, `src/signal_matin/assets/signal_matin.css` :
les deux doivent rester identiques.

### Fichiers qui ne sont pas dans Git

Le projet exclut volontairement ces fichiers du dépôt :

| Fichier | Contenu | Sur une nouvelle machine |
|---|---|---|
| `config.yaml` | Mes réglages | À recréer depuis `config.perso.yaml` |
| `credentials.json` | Accès Google (client OAuth) | À recopier à la main, ou à retélécharger depuis Google Cloud |
| `token.json` | Autorisation Google | Recréé par `signal-matin auth-google` |
| `.env` | Jeton du bot Telegram et identifiant du chat | À recréer depuis `.env.example` |
| `output/` | Journaux générés | Recréé à chaque génération |

`config.perso.yaml` est la copie versionnée de mes réglages. Après une modification
de `config.yaml` que je veux garder, je la recopie : `cp config.yaml config.perso.yaml`.

## Installer sur une nouvelle machine

### 1. Récupérer le dépôt

```bash
git clone https://github.com/webromain/signal-matin.git
cd signal-matin
git remote add upstream https://github.com/sosoj92/signal-matin.git
cp config.perso.yaml config.yaml
```

Le clone arrive directement sur `perso`, puisque c'est la branche par défaut.
La ligne `git remote add upstream` sert aux mises à jour (voir plus bas).

Recopier ensuite `credentials.json` dans le dossier, depuis l'ancienne machine.

### 2a. Lancer avec Docker (le plus simple)

Il suffit d'avoir Docker installé.

```bash
touch token.json                      # la toute première fois seulement
docker compose build                  # plusieurs minutes la première fois
docker compose run --rm signal-matin  # génère l'édition du jour
```

Le PDF arrive dans `output/pdf/`.

- Après une modification du code : relancer `docker compose build` (quelques secondes).
- Après une modification de `config.yaml` : rien à faire, il est relu à chaque lancement.
- Le conteneur ne peut ni imprimer, ni ouvrir un navigateur. La connexion Google
  (étape 3) et l'aperçu se font donc avec l'installation Python ci-dessous.

### 2b. Lancer avec Python

Il faut Python 3.11 ou plus récent. Sous Ubuntu, la commande est `python3`, et il
faut le paquet des environnements virtuels :

```bash
sudo apt install python3-venv
python3 scripts/setup.py --skip-preview
.venv/bin/python -m pip install -e ".[google,dev]"
```

Puis, dans chaque nouveau terminal :

```bash
source .venv/bin/activate
signal-matin preview --live     # ouvre le journal dans le navigateur
signal-matin generate --live    # crée le PDF dans output/pdf/
pytest                          # lance les tests
```

Le format « une feuille » est le format par défaut (`mode: sheet` dans `config.yaml`).
Les formats d'origine restent disponibles avec `--mode compact`, `standard` ou `extended`.

### 3. Connecter Google Agenda

À faire une fois par machine, avec l'installation Python :

```bash
source .venv/bin/activate
signal-matin auth-google
```

Le navigateur s'ouvre : choisir le compte, cliquer sur « Continuer » à
l'avertissement « application non validée », accepter l'accès en lecture seule.
Le fichier `token.json` est alors créé.

Si l'agenda disparaît du journal au bout d'une semaine, c'est que l'accès Google
est resté en mode « test », qui expire après 7 jours. Soit relancer
`signal-matin auth-google`, soit publier l'application dans Google Cloud Console
(Google Auth Platform → Audience → Publier l'application).

### 4. Générer chaque matin et imprimer

Ajouter une ligne avec `crontab -e`. Exemple à 7 h 30, avec Docker :

```
30 7 * * * cd /chemin/vers/signal-matin && docker compose run --rm signal-matin
```

Sur un serveur Debian, utiliser plutôt le fichier prêt à l'emploi
`deploy/signal-matin.cron` : ses premières lignes expliquent quoi adapter (dossier
et utilisateur) et comment l'installer dans `/etc/cron.d/`. Le résultat de chaque
matin est consigné dans `output/cron.log`.

Pour imprimer en recto verso depuis la machine :

```bash
lp -o sides=two-sided-long-edge output/pdf/AAAA-MM-JJ-signal-matin.pdf
```

### 5. Recevoir le journal sur Telegram

Quand `telegram.enabled` vaut `true` dans `config.yaml`, chaque `generate` envoie le
PDF dans une conversation Telegram. La tâche du matin n'a donc pas à changer.

1. Dans Telegram, écrire à `@BotFather`, envoyer `/newbot` et noter le jeton donné.
2. Envoyer un message quelconque au nouveau bot.
3. Ouvrir `https://api.telegram.org/bot<JETON>/getUpdates` : l'identifiant du chat
   est le nombre affiché dans `"chat":{"id":…}`.
4. Créer le fichier `.env` à la racine (il n'est pas dans Git) :

```
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

Si l'envoi échoue, le PDF reste dans `output/pdf/` et la raison est écrite dans
`output/cron.log`.

Avec Docker, `compose.yaml` transmet ces deux variables au conteneur : le fichier
`.env` doit donc se trouver dans le dossier d'où `docker compose` est lancé.

## Récupérer les mises à jour de l'auteur

### Le principe

| Nom | Ce que c'est |
|---|---|
| `upstream` | Le dépôt de l'auteur, `sosoj92/signal-matin`. En lecture seule pour moi. |
| `origin` | Mon fork, `webromain/signal-matin`. |
| `perso` | Ma branche, la branche par défaut du fork. Tout mon travail est dessus. |
| `main` | Une copie de la version de l'auteur. Je n'y travaille jamais. |

Mes modifications sont des commits sur `perso`. Une mise à jour consiste à
**fusionner** la version de l'auteur dans `perso`. Git conserve les deux
historiques : il n'écrase jamais mon travail en silence.

### La procédure

```bash
# 0. Partir d'un état propre : tout doit être committé
git switch perso
git status

# 1. Poser un repère pour pouvoir revenir en arrière
git tag avant-maj

# 2. Récupérer et fusionner la version de l'auteur
git fetch upstream
git merge upstream/main

# 3. Vérifier que tout marche encore
pytest
signal-matin preview --live

# 4. Publier
git push
```

Pour voir ce qui va arriver avant de fusionner : `git log --oneline perso..upstream/main`.

Pour mettre aussi à jour ma copie `main` (facultatif) : bouton **Sync fork** sur
GitHub, en ayant sélectionné la branche `main`.

### S'il y a un conflit

Un conflit survient quand l'auteur et moi avons modifié les mêmes lignes. Git
s'arrête et liste les fichiers concernés ; rien n'est perdu.

1. `git status` montre les fichiers « modifiés des deux côtés ».
2. Dans chaque fichier, choisir entre les deux versions, délimitées par
   `<<<<<<<`, `=======` et `>>>>>>>`, puis supprimer ces marqueurs.
3. `git add <fichier>` pour chaque fichier résolu, puis `git commit`.

Pour abandonner la fusion en cours et revenir comme avant : `git merge --abort`.
Pour annuler une fusion déjà terminée : `git reset --hard avant-maj`.

Les conflits sont les plus probables dans `src/signal_matin/renderer.py`,
`src/signal_matin/pipeline.py`, `src/signal_matin/models.py` et les deux feuilles
de style, où mon code est inséré au milieu de celui de l'auteur. Les fichiers
entièrement à moi ne peuvent pas en avoir : `selection.py`, `connectors/markets.py`,
`connectors/article.py`, `connectors/quote.py`, `telegram.py`, `Dockerfile`, `compose.yaml`, `config.perso.yaml` et ce guide.

### À ne pas faire

- **Ne pas travailler sur `main`** : elle doit rester identique à la version de l'auteur.
- **Ne pas cliquer sur « Sync fork » quand `perso` est sélectionnée** sans regarder :
  GitHub tente alors la fusion en ligne, sans que je puisse tester le résultat.
  Mieux vaut suivre la procédure ci-dessus.
- **Ne pas cliquer sur « Compare & pull request »** : ce bouton propose d'envoyer mes
  modifications à l'auteur, ce qui n'a rien à voir avec une mise à jour.

## Ce que ma version change par rapport à l'original

- un format `sheet` (une feuille recto verso), avec sa propre mise en page ;
- les cours de marché (`connectors/markets.py`) ;
- la lecture du début des articles sur le site des médias (`connectors/article.py`) ;
- le choix des articles : doublons entre flux, importance, mémoire de la veille
  (`selection.py`) ;
- la météo à 5 jours ;
- une citation du jour lue dans un flux RSS (`connectors/quote.py`), avec une liste
  de secours dans `personal.quotes` ;
- l'envoi du PDF sur Telegram après chaque génération (`telegram.py`) ;
- un format par défaut réglable dans `config.yaml` (`mode:`) ;
- les fichiers Docker.

Les formats d'origine (`compact`, `standard`, `extended`) ne sont pas modifiés.
