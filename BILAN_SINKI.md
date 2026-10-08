# Bilan SINKI : audit, corrections et préparation aux stores

Date : 7 octobre 2026. Branche de travail : `claude/preparation-stores` (rien n'est encore poussé sur GitHub ni déployé).
Sauvegardes : tags Git `backup-avant-claude-2026-10-07` et `backup-origin-main-2026-10-07`, plus une copie des données non versionnées dans `~/sinki-sauvegardes/`.

## 0. Les outils installés

| Outil | État constaté | Utilisation |
|---|---|---|
| Graphify | CLI installé et fonctionnel (`~/.local/bin/graphify`) | Utilisé : carte du code (885 nœuds, 36 groupes) dans `graphify-out/` (ignoré par Git) pour repérer les fonctions centrales et l'impact des modifications |
| Ponytail | Source ajoutée dans les réglages Claude, mais **le plugin n'est pas installé ni activé** : ses commandes ne sont pas disponibles dans cette session | Pas utilisé comme outil. J'ai lu sa documentation et appliqué son principe : corrections minimales, pas de réécriture |
| OmniRoute | CLI présent (v3.8.51) | Pas utilisé : il sert à router des modèles. Cette session parle directement à Claude, donc rien à router |
| Kilo Code | Extension VS Code installée (v7.8.3) | Pas utilisable d'ici : je ne pilote pas VS Code |

## 1. Ce qu'est réellement l'application

- **Technologie** : site web (PWA) en JavaScript simple (`web/app.js`, `web/index.html`) et serveur Python sans framework (`web/serve.py`). Hébergé sur Render (offre gratuite) via Docker. Données dans Supabase.
- **Pas d'application iOS ou Android** : aucun projet Xcode, Android ou Capacitor n'existe. Il faut en créer une (voir section 7).
- **Comptes** : connexion par code à 6 chiffres envoyé par mail (pas de mot de passe). Les comptes ne sont pas dans Supabase Auth : ils sont stockés dans **une seule ligne JSON** de la table `groups`.
- **Catalogue** : 2,62 millions de lignes `outings`, dont 2,43 millions actives. **2,29 millions sont des « clones nearby »**, des copies de lieux réels rattachées aux communes voisines. Il n'y a donc qu'environ 140 000 sorties distinctes.
- **Paiements** : la grille tarifaire existe dans le code, mais **aucun paiement ne peut aboutir** : il n'y a ni application native ni connexion à StoreKit ou Google Play Billing. Le serveur refuse honnêtement tout achat.
- **Code mort** : une copie React/Node (`web/src`, `api.mjs`…) n'était jamais déployée. Les « corrections » précédentes du bouton dé et du multi-catégories avaient été faites dans cette copie et n'avaient donc aucun effet. Supprimée.

## 2. Problèmes importants : cause, correction, test

Légende : ✅ corrigé et vérifié · 🟡 corrigé mais pas encore vérifié en production · 🔒 bloqué par un accès ou une configuration · ⏳ reste à faire

| # | Problème | Cause | Correction | Statut |
|---|---|---|---|---|
| 1 | **Codes de connexion jamais reçus** (inscription) | En production, Resend n'est pas configuré (`/api/health` → `resend:false`). Les codes partent donc par le mailer intégré de Supabase, qui **refuse d'écrire aux adresses hors de l'équipe Supabase** et se limite à 2 mails/heure (documentation officielle Supabase) | Erreurs Resend désormais journalisées avec leur raison. `/api/health` signale l'expéditeur de test `onboarding@resend.dev`, qui ne peut écrire qu'au propriétaire du compte Resend | 🔒 configuration à faire de ton côté (section 3) |
| 2 | « Code incorrect ou expiré » alors que le code est bon | Tous les comptes, sessions et codes sont dans une seule ligne réécrite en entier à chaque action. Deux actions simultanées : la seconde efface la première | Écriture « compare-and-swap » avec nouvel essai automatique | ✅ tests automatiques (12 inscriptions simultanées), parcours complet testé en local |
| 3 | Comptes qui « disparaissent » | Une erreur réseau vers Supabase était lue comme « aucun compte », ce qui pouvait créer un second store vide. En cas de panne, l'ancien fichier local pouvait aussi écraser la production | Une panne renvoie maintenant « service momentanément indisponible » et rien n'est écrasé | ✅ test |
| 4 | Comptes supprimés qui reviennent | Au démarrage, le cache disque était réinjecté dans la production | Import uniquement si aucun store n'existe | ✅ test |
| 5 | Suppression de compte incomplète | L'utilisateur Supabase Auth n'était pas supprimé | Il l'est maintenant (avec favoris, groupes, événements, sessions) | ✅ local · 🟡 production |
| 6 | **Code source du serveur public** | `https://sinki.onrender.com/serve.py` était téléchargeable | Seuls les fichiers du site sont servis | ✅ local (404) · 🟡 production après déploiement |
| 7 | Droits payants falsifiables | Le serveur lisait le « plan » dans des métadonnées que l'utilisateur peut modifier | Seules des données serveur comptent | ✅ |
| 8 | **« SINKI me propose » bloqué** | Quota gratuit de 6 sorties par jour (2 recherches). Ensuite, mur de paiement impossible à payer et la même carte en boucle | Ni quota ni mur tant qu'aucun achat réel n'est possible ; message clair « tout est gratuit pour l'instant » | ✅ testé dans le navigateur (8 clics = 8 sorties différentes) |
| 9 | **Photos qui ne correspondent pas** | Les photos Wikimedia étaient cherchées par nom dans le monde entier. À Lyon, les 3 premières suggestions montraient un autre cinéma, un tableau de musée et la gare | Une photo Wikimedia n'est affichée que si son nom de fichier contient 2 mots distinctifs du lieu ET un mot de son adresse (ville, rue). Sinon, pas de photo. La base n'est pas modifiée | ✅ sur un échantillon de 2 650 sorties. Conséquence : environ 9 photos Wikimedia sur 10 sont masquées. Les photos des offices de tourisme (Apidae, Tourinsoft) restent |
| 10 | Événements trompeurs | Les **30 547 événements actifs n'ont aucune date** : l'import DATAtourisme ne les a jamais enregistrées | Les événements sans date ou terminés sont exclus des suggestions ; le filtre « Événements » est masqué | ✅ vérifié via l'API (0 événement renvoyé) |
| 11 | Hôtels dans Explorer | Seules les chaînes étaient filtrées dans Explorer | Règle unique, qui garde l'Hôtel de Ville, l'Hôtel-Dieu et l'Hôtel de la Marine | ✅ test |
| 12 | Messages de groupe perdus | Même écrasement que n°2 | Même protection | ✅ test |
| 13 | Partage aux amis peu utilisable | L'invitation ne contenait qu'un code, sans lien | Lien `…/?groupe=CODE` qui ouvre le groupe directement | ✅ testé dans le navigateur |
| 14 | Groupe qui ne se met pas à jour | Pas de rafraîchissement automatique | Mise à jour toutes les 8 s quand l'écran Groupe est visible, sans effacer le message en cours | ✅ |
| 15 | Pas de signalement ni de blocage (exigé par Apple, règle 1.2) | Absent | Boutons « Signaler » (message retiré + mail au support) et « Bloquer » dans le chat | ✅ |
| 16 | Événements organisateurs perdus | Stockés sur le disque Render, effacé à chaque redémarrage. Mail de modération envoyé seulement via l'app Mail d'un Mac. « Paiement » = simple case cochée par le navigateur | Dépôt désactivé en production avec un message clair. Mail de modération via Resend | ✅ · ⏳ un vrai stockage est nécessaire pour réactiver |
| 17 | Adresse de contact injoignable | `bonjour@sinki.app` n'a aucun serveur mail (pas d'enregistrement MX) | Remplacée par `thesinkiisinki@gmail.com` dans la politique de confidentialité, la page de suppression et l'app | ✅ **à confirmer par toi** |
| 18 | Multi-catégories (activité ET shopping) | Fonctionnait déjà dans la vraie app | Vérifié | ✅ testé |

Tests automatiques : `python3 -m unittest discover -s tests` (27 tests OK) et `node --test tests/test_multi_select.mjs` (2 OK).

Points constatés mais non corrigés :
- ⏳ **Date, durée, moment et transport du formulaire ne sont pas utilisés par la recherche.** Seuls ville, rayon, budget, catégories et intérieur/extérieur filtrent. Il faut soit les brancher, soit les retirer du formulaire.
- ⏳ Les photos de profil sont stockées en base64 dans la ligne des comptes, qui grossit et ralentit chaque connexion. Il faut migrer les comptes vers de vraies tables (ou vers Supabase Auth) avec les photos dans Supabase Storage. C'est le prochain gros chantier conseillé.
- ⏳ 2,29 millions de clones gonflent la base, dont certains datent d'avant la limite de 20 km. Le script `supabase/01_verifier_securite.sql` affiche la taille de la base (le plan gratuit est limité à 500 Mo).
- ⏳ Catégories DATAtourisme parfois fausses : par exemple « Ciao Nonna », un restaurant classé en Shopping.
- ⏳ Les prix « à confirmer » passent tous les budgets (choix volontaire, affiché comme tel).

## 3. Comptes et emails : ce que tu dois configurer

Le code d'envoi fonctionne (testé de bout en bout en local). Ce qui bloque en production, c'est la **configuration** :

1. **Un nom de domaine à toi.** `sinki.app` existe chez Cloudflare. Est-il à toi ? Si oui, on l'utilise. Sinon, achète-en un (environ 10 à 20 €/an).
2. **Resend** (gratuit jusqu'à 3 000 mails/mois) : ajoute le domaine, copie les enregistrements DNS (SPF/DKIM) chez Cloudflare, attends « Verified ».
3. **Render → sinki → Environment** :
   - `RESEND_API_KEY` = ta clé Resend (ne me l'envoie pas, colle-la directement dans Render) ;
   - `MAIL_FROM` = `SINKI <code@tondomaine>`.
4. Conseillé : dans **Supabase → Authentication → SMTP**, mets aussi Resend, comme secours.
5. Dans **Supabase → Authentication → Email Templates → Magic Link**, vérifie que le modèle contient `{{ .Token }}` (le code à 6 chiffres). Le modèle par défaut envoie un lien, pas un code.
6. Ensuite, on teste ensemble avec ton adresse et celle d'un ami : réception, spams, expiration (15 min), renvoi.

Je n'ai **pas** pu vérifier la réception réelle d'un mail. Je n'ai pas non plus lu les comptes de production : l'outil de sécurité a bloqué la lecture des données utilisateurs sans ton accord explicite.

## 4. Données des sorties

- Aucune donnée n'a été supprimée ni modifiée en base. Toutes les corrections sont des filtres à l'affichage, donc réversibles.
- Vérifié automatiquement : photos Wikimedia, événements sans date, hôtels.
- **Je n'ai pas vérifié chaque sortie une par une** (2,4 millions).
- Exclus des suggestions : événements sans date, hôtels, photos douteuses.
- À faire ensuite : réimporter les dates des événements DATAtourisme, puis lancer une vérification des photos Wikimedia via leurs coordonnées GPS pour récupérer les bonnes.
- Licences : les photos Wikimedia sont sous licence libre (CC-BY/CC-BY-SA), mais **l'auteur et la licence doivent être affichés** à côté de chaque photo (attribution obligatoire). DATAtourisme impose aussi la mention de la source. Ces deux points sont à vérifier dans la fiche sortie.

## 5. Abonnements : proposition simple

Constat sur la grille envisagée :
- « Plus » et « Sorties illimitées » se chevauchent (Plus inclut l'illimité, pour 2 € d'écart) : c'est confus.
- Les formules à la semaine (2,99 €/sem ≈ 13 €/mois) sont chères pour des 16-25 ans.
- **Il n'y a aucune publicité dans l'app** : vendre leur suppression (5,99 €) n'est pas possible.
- Boosts organisateurs : Apple impose ses achats intégrés pour tout service numérique consommé dans l'app. Plus simple : les vendre plus tard sur le site web, aux professionnels (Stripe), en dehors de l'app.

Proposition :
- **Gratuit** : recherche, 3 suggestions, « Sinki me propose », dé, favoris, groupes, votes, partage, dans son pays.
- **SINKI Plus**, un seul abonnement : 3,99 €/mois ou 29,99 €/an.
  - Contenu : exploration du monde entier, suggestions illimitées au-delà d'un plafond généreux (par exemple 15/jour), sorties prévues illimitées, votes à plus de 3 choix.
  - Essai gratuit de 7 jours possible.
- Pas de publicité ni de boosts au lancement.

Rien de tout cela n'est activé. Il faut l'app native et les comptes développeur avant de tester en sandbox. Côté serveur, il faudra ajouter :
- la vérification des reçus Apple et Google, et leurs notifications (renouvellement, remboursement, expiration) ;
- l'anti-doublon ;
- la restauration des achats.

RevenueCat (gratuit jusqu'à 2 500 $ de revenus mensuels) simplifie beaucoup ce travail et réduit le risque d'erreur.

## 6. Comment l'argent arrive

- **Qui encaisse** : Apple (App Store) ou Google (Play) encaisse le client, reverse la TVA dans l'UE, retient sa commission et te verse le reste.
- **Commission** :
  - Apple : 15 % si tu t'inscris au Small Business Program (moins d'1 M$/an), sinon 30 %. Abonnements : 15 % dès la 2e année.
  - Google : 15 % sur les abonnements. Depuis juin 2026 dans l'UE : 10 % + 5 % de frais de facturation pour les nouvelles installations.
- **Quand** : Apple paie environ 33 jours après la fin de chaque mois fiscal (au-dessus d'un seuil minimal). Google paie vers le 15 du mois suivant.
- **Il te faudra** :
  - un IBAN à ton nom ;
  - une pièce d'identité ;
  - les formulaires fiscaux (W-8BEN pour les États-Unis) ;
  - l'accord « Paid Apps » chez Apple et un profil de paiement chez Google ;
  - un statut de **commerçant UE (DSA)** : adresse, téléphone et email affichés publiquement sur la fiche de l'app. Une micro-entreprise (SIRET) avec une adresse de domiciliation évite d'exposer ton adresse personnelle.
  - Les comptes développeur exigent d'être **majeur·e**. Sinon, un parent doit les ouvrir.
- **À faire vérifier par un comptable ou l'URSSAF** : statut (micro-entreprise BIC ou BNC), cotisations sociales (environ 21 à 25 % du chiffre d'affaires), franchise de TVA, déclaration des revenus versés par Apple et Google (sociétés étrangères).

Coûts de fonctionnement mensuels (hypothèses) :

| Poste | Minimal | Prudent |
|---|---|---|
| Render (Starter, sans mise en veille) | 7 € | 7 € |
| Supabase (Free ou Pro) | 0 € | 25 € |
| Apple Developer (99 $/an) | 8,30 € | 8,30 € |
| Domaine | 1,30 € | 1,30 € |
| Google Play (25 $ une seule fois) | – | – |
| Resend / RevenueCat (offres gratuites) | 0 € | 0 € |
| **Total** | **≈ 17 €/mois** | **≈ 42 €/mois** |

Revenu net par abonné mensuel à 3,99 € TTC :
- 3,99 € TTC = 3,33 € HT (TVA 20 %) ;
- moins 15 % de commission → 2,83 € ;
- moins environ 22 % de cotisations → **≈ 2,20 € par mois**.

Seuil de rentabilité :

| Scénario | Coûts à couvrir | Abonnés payants nécessaires | Utilisateurs actifs nécessaires (si 2 à 5 % s'abonnent) |
|---|---|---|---|
| Minimal | 17 € | ≈ 8 | ≈ 160 à 400 |
| Prudent | 42 € | ≈ 19 | ≈ 380 à 950 |

Exemple : 100 abonnés ≈ 220 €/mois avant coûts, soit ≈ 180 € nets dans le scénario prudent. Ce sont des hypothèses, pas des promesses.

## 7. Préparer l'App Store et Google Play

Ce qui manque techniquement :
- **Applications natives** : je conseille Capacitor, qui emballe l'app web existante. Il faudra :
  - rendre l'adresse de l'API configurable ;
  - ajouter l'autorisation d'accès (CORS) pour l'app ;
  - utiliser la géolocalisation native avec un texte d'explication ;
  - brancher les achats via StoreKit et Play Billing ;
  - ajouter les liens universels pour `?groupe=` ;
  - ajouter des icônes et un écran de démarrage.

  Attention à la règle Apple 4.2 : une app qui n'est qu'un site web emballé est refusée. Il faut des fonctions « natives » (position, partage natif, notifications…).
- Sur ce Mac : **Xcode n'est pas installé** (gratuit, App Store, environ 15 Go). Android Studio et Java non plus. Espace libre : 40 Go.

Exigences officielles vérifiées :

| Exigence | Où en est SINKI |
|---|---|
| Apple : suppression du compte dans l'app (5.1.1) | ✅ présente |
| Google : page web de suppression (déclarée dans le formulaire « Sécurité des données ») | ✅ `/delete` |
| Politique de confidentialité accessible | ✅ `/privacy` (relire et compléter) |
| Contenu généré par les utilisateurs : filtrer, signaler, bloquer, contact (Apple 1.2) | ✅ signaler et bloquer · ⏳ filtre de mots grossiers |
| Compte de démonstration pour la revue Apple (2.1) | ⏳ problème : la connexion se fait par code mail. Il faudra une adresse de démo dont tu transmets le code, ou un code fixe réservé à cette adresse |
| Achats intégrés obligatoires pour les abonnements (3.1.1 / 3.1.2) | ⏳ |
| Géolocalisation : jamais obligatoire, texte d'explication (5.1.1 / 5.1.2) | ✅ facultative · ⏳ texte natif |
| Pas de suivi publicitaire, donc pas de fenêtre ATT nécessaire | ✅ |
| Google, nouveau compte personnel : test fermé avec **12 testeurs pendant 14 jours** avant publication | ⏳ prévoir 12 amis |

Liste à préparer pour la soumission :
- comptes Apple Developer (99 $/an) et Google Play (25 $) ;
- builds signés ;
- captures d'écran (iPhone 6,9" et 6,5", Android) ;
- icône 1024×1024 ;
- descriptions FR/EN ;
- mots-clés ;
- catégorie Voyage ou Style de vie ;
- classification d'âge ;
- URL de la politique de confidentialité ;
- formulaires « App Privacy » (Apple) et « Sécurité des données » (Google) ;
- produits d'abonnement créés dans App Store Connect et la Play Console ;
- compte de démo ;
- coordonnées de commerçant DSA.

Aucune acceptation n'est garantie. Je ne publierai rien sans ton accord.

## 8. Actions pour toi

1. **Me dire si je peux pousser la branche sur GitHub et ouvrir une Pull Request.** Le déploiement Render suivra la fusion.
2. Confirmer l'adresse de contact `thesinkiisinki@gmail.com` et me dire si `sinki.app` t'appartient.
3. Configurer le mail (section 3), puis faire un test réel avec moi.
4. Exécuter `supabase/01_verifier_securite.sql` dans Supabase (lecture seule) et m'envoyer le résultat, sans clé. Puis `02_activer_rls.sql` si des tables apparaissent.
5. Si tu veux les apps : installer Xcode, et me dire si tu acceptes que j'ajoute Capacitor au projet (téléchargement de paquets npm).
6. Décider de la formule d'abonnement (section 5) et vérifier ton statut (âge, micro-entreprise).
7. M'autoriser, si tu veux, à lire les comptes de production (sans les afficher) pour vérifier la taille du store et les doublons.

Lancer l'app en local, en mode test sans toucher la production :

```
SINKI_AUTH_STORE=file SINKI_MAIL_DEV=console SINKI_DATA_DIR=/tmp/sinki-test PORT=5180 python3 web/serve.py
```
