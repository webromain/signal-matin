#!/usr/bin/env bash
# Hook « Stop » : lancé par Claude Code à la fin de chaque réponse de Claude (voir .claude/settings.json).
# Chaque règle est une fonction regle_* qui ajoute éventuellement une consigne à $consignes.
# S'il y a au moins une consigne, Claude reçoit le tout en un seul message et doit la traiter avant de rendre la main.
#
# Ajouter une règle : écrire une fonction regle_xxx, puis l'appeler dans la liste « Règles actives » en bas.
# Les repères de date sont les fichiers vides de .claude/state/. Ils font partie du modèle et
# peuvent être suivis par Git : seule leur date change, jamais leur contenu.
# Aucun outil à installer : le script n'utilise que bash, git et les commandes de base.
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Déjà relancé par ce hook dans ce tour : on laisse finir (évite une boucle).
if grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  exit 0
fi

etat=.claude/state
mkdir -p "$etat"
consignes=""

# CLAUDE.md est facultatif : chaque consigne se suffit à elle-même. S'il existe et contient
# la section demandée, la consigne y renvoie en plus pour les règles propres au projet.
voir_claude_md() { # $1 = titre de la section
  [ -f CLAUDE.md ] && grep -qiE "^#+ +$1" CLAUDE.md || return 0
  echo " Suis en plus les règles de la section « $1 » de CLAUDE.md."
}

json_texte() { # échappe un texte pour le placer entre guillemets dans du JSON
  local s=$1
  s=${s//\\/\\\\}; s=${s//\"/\\\"}
  s=${s//$'\n'/\\n}; s=${s//$'\r'/\\r}; s=${s//$'\t'/\\t}
  printf '%s' "$s"
}

newest() { # plus récente date de modification (secondes) parmi les fichiers donnés
  local max=0 t
  for f in "$@"; do
    [ -f "$f" ] || continue
    t=$(stat -c %Y "$f"); [ "$t" -gt "$max" ] && max=$t
  done
  echo "$max"
}

# Fichiers modifiés ou nouveaux depuis le dernier commit (le .env est ignoré par Git, donc jamais listé).
mapfile -t changed < <(git status --porcelain --untracked-files=all | sed -E 's/^.. //; s/.* -> //')
code=(); docs=()
for f in "${changed[@]}"; do
  case "$f" in
    docs/*|README.md|CLAUDE.md) docs+=("$f") ;;
    src/*|pom.xml|.env.example) code+=("$f") ;;
  esac
done
code_time=0; [ "${#code[@]}" -gt 0 ] && code_time=$(newest "${code[@]}")

# --- Règle « doc » : le code a changé après la dernière mise à jour de la doc
regle_doc() {
  local repere=$etat/docs.stamp
  [ "$code_time" -gt "$(newest "${docs[@]}" "$repere")" ] || return 0
  touch "$repere"
  consignes+="Du code ou de la configuration a changé depuis la dernière mise à jour de la documentation :
$(printf '%s\n' "${code[@]}")
Mets à jour ce qui est devenu faux ou incomplet dans la documentation (docs/, README.md et les autres guides du dépôt). Si rien n’est à documenter (étape pas encore validée, simple essai), ne modifie rien.$(voir_claude_md Documentation)
"
}

# --- Règle « commit » : proposer un message de commit, sans jamais commiter
regle_commit() {
  local repere=$etat/commit.stamp
  [ "$code_time" -gt "$(newest "$repere")" ] || return 0
  touch "$repere"
  consignes+="Il y a des modifications non commitées. Si elles forment un ensemble qui compile et fonctionne, termine ta réponse par un message de commit en une seule ligne, dans le style des commits précédents (git log), couvrant toutes les modifications depuis le dernier commit (git status / git diff HEAD). Ne commite jamais toi-même. Si le travail est encore en cours ou ne compile pas, ne propose rien.$(voir_claude_md Commits)
"
}

# --- Règles actives
regle_doc
regle_commit

# Les repères manquants sont recréés après coup : créés avant, ils masqueraient la première consigne.
for repere in docs.stamp commit.stamp; do
  [ -f "$etat/$repere" ] || : > "$etat/$repere"
done

[ -z "$consignes" ] && exit 0
printf '{"decision": "block", "reason": "%s"}\n' "$(json_texte "$consignes")"
exit 0
