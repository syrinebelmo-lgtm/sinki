#!/bin/bash
# Relance un worker jusqu'à ce qu'aucune ville ne soit sautée (coupure réseau, serveur saturé).
# usage : pipeline/relancer.sh <journal> <commande…>
log="$1"; shift
for pass in $(seq 1 30); do
  until curl -s -m 15 -o /dev/null https://www.wikidata.org; do sleep 60; done
  "$@" >> "$log" 2>&1
  tail -400 "$log" | sed -n '/^PASSE/,$p' | grep -q "ville sautée\|villes introuvables" || break
  echo "PASSE $pass terminée, villes sautées : nouvelle passe dans 5 min" >> "$log"
  sleep 300
done
echo "FIN" >> "$log"
