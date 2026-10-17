# Rapport de test

Date : 2026-10-16. Composant `flashforge_creator5pro` 0.1.0, bibliothèque
`flashforge-python-api` 1.6.0.

## Fait (sans imprimante)

| Test | Environnement | Résultat |
|---|---|---|
| `tests/` : 30 tests (lecture, refus HTTP 401/403, code non nul, délai dépassé, connexion refusée, HTTP 500, réponse non JSON, tableau JSON, `detail` absent, type invalide, Content-Type mal orthographié, autres modèles refusés, températures, chambre absente (-108), emplacements, porte, problème en pause) | Windows, Python 3.13 | 30 réussis |
| `tests_ha/` : 9 tests dans Home Assistant 2026.10.1 (création de l'entrée, erreurs du formulaire avec une seule requête, entités en lecture seule uniquement, aucun secret dans les états, indisponible puis rétabli, refus qui arrête les interrogations et ouvre la réauthentification, refus au démarrage sans nouvel essai, réauthentification) | Windows, Python 3.14, modules factices `fcntl` et `resource` | 9 réussis |
| `scripts/read_status.py` contre une fausse imprimante locale | Windows | Lecture : code 0. Refus : code 3 avec consigne d'arrêt. |
| Lint (`ruff`, règles E, F, W, B) | | Aucun problème |

Les tests `tests_ha/` ont tourné sous Windows avec deux contournements propres au banc de test
(WSL indisponible sur ce poste) : des modules `fcntl` et `resource` factices, et la levée du
blocage des sockets de `pytest-socket`, nécessaire à la boucle asyncio de Windows. L'imprimante
y est toujours simulée.

## À faire sur le matériel

Elles demandent le numéro de série et le check code.

| # | Vérification | Résultat |
|---|---|---|
| 1 | `scripts/read_status.py` sur une machine du réseau local : code de sortie 0, valeurs cohérentes avec l'écran de l'imprimante | à faire |
| 2 | Même script avec `--camera`, imprimante au repos : le flux répond-il hors impression ? | à faire |
| 3 | Noter les champs `estimatedRightLen`/`estimatedLeftLen` pendant une impression (calcul possible du filament restant de la tâche) | à faire |
| 4 | Installation sur HAOS, ajout de l'intégration | **OK** (2026-10-16) |
| 5 | États, températures T1 à T4, plateau, chambre, progression, emplacements | **OK au repos** (Ready, T1-T4 26-28 °C, plateau et chambre 25 °C, emplacements PLA/PLA/vide/vide, porte fermée). Stockage libre affiché à 0,01 Go : unité corrigée en 0.1.1 (la valeur est en Go). Reste à vérifier pendant une impression. |
| 6 | Caméra visible dans Home Assistant | **OK**, flux affiché imprimante au repos (2026-10-16) |
| 7a | Passage en mode cloud pendant une impression | Toutes les entités indisponibles. L'imprimante a **répondu par un refus** : interrogations arrêtées, réauthentification demandée au retour en LAN (comportement prévu). À relever : la ligne du journal (code et message du refus) et si le check code a changé. |
| 7 | Imprimante éteinte puis rallumée : indisponible puis rétablie sans redémarrer Home Assistant | à faire |
| 8 | Journaux Home Assistant : rechercher le numéro de série et le check code, aucune occurrence attendue | à faire |
| 9 | Annuler l'impression : protocole ci-dessous | à faire |
| 10 | Pause, reprise : protocole ci-dessous | à faire |
| 11 | Éclairage intérieur : allumer, éteindre, état cohérent avec l'imprimante | à faire |

Pour l'étape 8, depuis le terminal SSH de HAOS :

```bash
ha core logs | grep -c -F "$FF_SERIAL"; ha core logs | grep -c -F "$FF_CHECK_CODE"
```

Les deux nombres doivent être 0. Le fichier `/config/.storage/core.config_entries` contient
forcément les valeurs, comme pour toute intégration qui stocke des identifiants : il ne doit pas
être partagé.

## Protocole d'essai de l'annulation (0.2.0)

Tests automatiques ajoutés : requête exacte envoyée sur `/control`, un seul envoi même en cas de
délai dépassé, refus d'envoyer sans armement, après expiration de l'armement ou sans tâche en
cours (40 tests sans Home Assistant, 13 dans Home Assistant : tous réussis).

Sur l'imprimante, en restant à côté :

1. Activez l'option, puis appuyez sur le bouton **sans armer** : un message d'erreur doit
   apparaître, et l'imprimante ne doit rien faire.
2. Imprimante au repos, armez puis appuyez : message « Aucune tâche à annuler », l'imprimante ne
   doit rien faire.
3. Lancez une petite impression d'essai. Pendant les premières couches, armez, puis appuyez.
   Notez : délai avant l'arrêt, comportement des moteurs et de la tête, chauffage de la buse, du
   plateau et de la chambre, état affiché ensuite par l'imprimante et par Home Assistant.
4. Recommencez une fois pendant la chauffe initiale.
5. Vérifiez dans le journal la ligne « The printer accepted the cancel job command », sans
   numéro de série ni check code.

## Protocole d'essai de la pause et de la reprise (0.3.0)

Tests automatiques : requêtes exactes (`pause`, `continue`), boutons refusés hors de l'état
attendu sans rien envoyer (48 tests sans Home Assistant, 14 dans Home Assistant : tous réussis).

1. Imprimante au repos : « Mettre en pause » et « Reprendre » affichent une erreur, rien ne se
   passe.
2. Pendant une petite impression : « Mettre en pause ». Notez le délai, la position de la tête
   et le chauffage pendant la pause, et l'état affiché (« En pause »).
3. « Reprendre » : l'impression repart-elle correctement à la même couche ?
4. Pendant la pause, « Mettre en pause » doit afficher une erreur sans rien envoyer.
