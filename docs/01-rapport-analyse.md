# Étape 1 : rapport d'analyse

Sources lues (lecture seule, aucune connexion à l'imprimante) :

- `flashforge-python-api` 1.6.0 (roue PyPI).
- `ff-5mp-hass` (GhostTypes, MIT), branche `main`, version 1.6.1 du 2026-09-27.

## Constat principal : ff-5mp-hass gère déjà la Creator 5 Pro

Le plan supposait que ff-5mp-hass ne gérait que l'AD5X, la 5M et la 5M Pro. Ce n'est plus vrai :
depuis plusieurs versions, il reconnaît la Creator 5 (PID 40) et la Creator 5 Pro (PID 41). Son
`AGENTS.md` indique des tests sur une vraie Creator 5 Pro (firmware 1.9.4).

En revanche, il expose dès l'installation des commandes que nos règles interdisent avant validation :

| Plateforme | Entités de contrôle |
|---|---|
| `button` | pause, reprise, annulation, nettoyage du plateau |
| `switch` | lumière, filtration |
| `select` | mode de filtration |
| carte Lovelace + websocket | téléversement 3MF et démarrage d'impression |

Le composant `flashforge_creator5pro` reprend donc la même base (même bibliothèque, mêmes leçons
de terrain), mais **en lecture seule** : capteurs, capteurs binaires et caméra.

## Canal de chaque commande (dans la bibliothèque 1.6.0)

| Méthode | Appel réel | Canal | Remarque |
|---|---|---|---|
| `get_printer_status` | `info.get()` → `POST /detail` | HTTP 8898 | Lecture. Exige numéro de série et check code. |
| `get_temperatures` | `tcp_client.get_temp_info()` (`M105`) | **TCP 8899** | Pas de garde HTTP seul : voir ci-dessous. |
| `pause_print` | `POST /control`, `jobCtl_cmd`, `action=pause` | HTTP 8898 | |
| `resume_print` | `POST /control`, `jobCtl_cmd`, `action=continue` | HTTP 8898 | |
| `emergency_stop` | `POST /control`, `jobCtl_cmd`, `action=cancel` | HTTP 8898 | **Ce n'est pas un arrêt d'urgence** : c'est une annulation de tâche. |
| `home_all_axes` | `tcp_client.home_axes()` | TCP 8899 | Refusé d'office sur Creator 5 (`can_use_tcp` renvoie False). |
| `initialize` | `verify_connection()` : `/detail`, puis TCP si pas HTTP seul | HTTP 8898 | Sur Creator 5 / 5 Pro, la bibliothèque passe en HTTP seul d'après le PID et n'ouvre pas le port 8899. |

### Réponses aux questions ouvertes

**Le port 8899 est-il requis pour pause, reprise, arrêt ?** Non. Les trois passent par HTTP 8898
(`/control`). Ce n'est confirmé que par la lecture du code : aucun envoi n'a été fait.

**`emergency_stop`** appelle `cancel_print_job()`. Il n'existe pas de vrai arrêt d'urgence
(type `M112`) sur le canal HTTP dans cette bibliothèque. Le nom est trompeur : il ne faut pas
l'exposer comme « arrêt d'urgence » dans Home Assistant.

**Pourquoi `get_temperatures` renvoie `None` ?** La méthode appelle directement le client TCP,
sans vérifier `can_use_tcp()` comme le font les autres méthodes TCP. Sur la Creator 5 Pro, le
port 8899 refuse la connexion, la bibliothèque attrape l'erreur et renvoie `None`. C'est un oubli
dans la bibliothèque, pas un problème de l'imprimante.

**Les températures du statut sont-elles fiables ?** Elles viennent du même `POST /detail` que le
reste du statut : `print_bed`, `extruder`, `chamber` et `tool_temps` (une entrée par tête,
quatre sur la Creator 5 Pro). C'est la source qu'utilise ff-5mp-hass, testée sur matériel. La
chambre peut renvoyer `-108` quand le capteur est absent : la bibliothèque le transforme en
`None` et met `has_chamber_sensor` à False.

**« Connexion OK » affiché après un échec** : `initialize()` renvoie bien False en cas d'échec ;
c'est le script de test qui ne vérifie pas le retour. Le nouveau script
(`scripts/read_status.py`) s'arrête avec un code d'erreur.

## Point de sécurité découvert : un check code refusé ressemble à une coupure

`Info.get_detail_raw()` renvoie `None` à la fois quand l'imprimante est injoignable et quand elle
répond avec un statut HTTP différent de 200. Une intégration qui s'appuie dessus réessaie donc
un check code refusé à chaque cycle (toutes les 10 s dans ff-5mp-hass), ce qui va à l'encontre
de la règle « une tentative refusée peut bloquer l'accès ».

Le nouveau composant fait donc lui-même la requête `/detail` (même charge utile que la
bibliothèque) et distingue trois cas :

| Cas | Effet dans Home Assistant |
|---|---|
| Pas de réponse (délai, connexion refusée) | Entités indisponibles, nouvel essai au cycle suivant. |
| Réponse HTTP 401/403 ou `code` différent de 0 | **Arrêt des interrogations**, demande de réauthentification. Aucun nouvel essai automatique. |
| Réponse illisible | Entités indisponibles, message distinct « réponse illisible ». |

Le comportement réel de l'imprimante face à un mauvais code (statut HTTP, valeur de `code`) n'a
pas été observé et ne doit pas l'être par essai. Le composant traite donc **tout** code non nul
comme un refus : en cas de doute, il s'arrête.

## Entités de ff-5mp-hass et ce qui est repris

| ff-5mp-hass | Repris | Commentaire |
|---|---|---|
| état, progression, fichier, couches, durées | oui | |
| buse, plateau (actuel et cible) | oui | |
| 4 têtes T1 à T4 (actuel et cible) | oui | Spécifique Creator 5. |
| chambre (actuel et cible) | oui | Créée seulement si le capteur répond. |
| filament estimé (longueur, poids) | oui | C'est l'estimation de la tâche, pas le reste sur la bobine. |
| 4 emplacements de matériel | oui | En capteurs texte (matière, couleur en attribut). |
| ventilateurs, TVOC, vitesse, décalage Z | oui | |
| porte ouverte | oui | Seulement si `has_door_sensor`. |
| erreur, impression, pause, en ligne | oui | |
| caméra | oui | Entité MJPEG native de Home Assistant, URL du port 8080. |
| boutons, interrupteurs, sélecteur | **non** | Étape 5, après validation. |
| carte, téléversement, websocket | **non** | Hors périmètre. |
| diagnostics | **non** | Évite toute fuite de données d'identification. |

## Écarts avec la Creator 5 Pro

- **Filament restant** : le firmware ne renvoie pas la quantité restante par bobine. Les capteurs
  disponibles sont l'estimation de la tâche en cours et le cumul de toute la vie de l'imprimante.
- **Interrupteur caméra** : ff-5mp-hass ne le crée pas sur la Creator 5, car `streamCtrl_cmd` y
  répond « succès » sans rien faire (observé en firmware 1.9.4). Rien à faire de notre côté.
- **Filtration** : `/product` donne des valeurs fausses sur la Creator 5 Pro d'après ff-5mp-hass.
  Le composant ne l'interroge pas.
- **Firmware** : les observations de ff-5mp-hass portent sur le firmware 1.9.4. Notre imprimante
  est en 1.9.9.

## Mise à jour du 2026-10-17

**Le check code est-il le champ « Access code » du menu LAN ?** Avec l'imprimante en français,
le check code s'appelle « ID de l'appareil » dans le menu LAN (confirmé par l'utilisateur).
L'interface française de l'intégration reprend ce libellé.
