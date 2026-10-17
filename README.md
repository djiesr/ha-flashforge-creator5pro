# FlashForge Creator 5 Pro pour Home Assistant

> **English:** native Home Assistant integration for the FlashForge Creator 5 Pro, over the
> printer's local HTTP API (LAN mode). Sensors, Material Station slots, MJPEG camera, and
> chamber light, optional pause / resume / cancel buttons (cancel requires arming). No print start.
> Install through HACS as a custom repository (category *Integration*). Not affiliated with
> FlashForge.

Intégration native (`custom_components/flashforge_creator5pro`) qui interroge directement
l'imprimante en HTTP sur le port 8898. Pas de MQTT, pas de passerelle, pas de port 8899.

Trois commandes, chacune désactivée par défaut : **annuler l'impression** (protégée par un
armement), **pause** et **reprise**. Le démarrage d'une impression n'est volontairement pas
proposé. Voir [Commandes](#commandes).

Basée sur [ff-5mp-hass](https://github.com/GhostTypes/ff-5mp-hass) (GhostTypes, licence MIT) et
sur la bibliothèque `flashforge-python-api` 1.6.0. Le rapport d'analyse explique les choix :
[docs/01-rapport-analyse.md](docs/01-rapport-analyse.md).

## Installation manuelle sur HAOS

1. Copiez le dossier `custom_components/flashforge_creator5pro/` dans
   `/config/custom_components/flashforge_creator5pro/`, avec le module Samba ou SSH.
   Ne copiez que ce dossier, pas `tests/` ni `scripts/`.
2. Redémarrez Home Assistant. Au premier démarrage, Home Assistant installe
   `flashforge-python-api==1.6.0`.
3. Allez dans **Paramètres → Appareils et services → Ajouter une intégration** et cherchez
   « FlashForge Creator 5 Pro ».
4. Saisissez l'adresse IP (`192.168.1.50`), puis le numéro de série et le check code
   relevés dans le menu LAN de l'imprimante. Avec l'imprimante en français, le check code s'y
   appelle **« ID de l'appareil »** ; l'intégration utilise ce même libellé en français.

Chaque validation du formulaire envoie **une seule** requête. Si l'imprimante refuse, le
formulaire l'indique et rien n'est réessayé. Relevez à nouveau les valeurs dans le menu LAN
avant de soumettre une deuxième fois : ne devinez pas.

Une installation de ff-5mp-hass sur la même instance n'entre pas en conflit (domaine
différent), mais les deux interrogeraient l'imprimante.

## Installation par HACS

1. Dans HACS : **⋮ → Dépôts personnalisés**.
2. Dépôt : `https://github.com/djiesr/ha-flashforge-creator5pro`, catégorie **Intégration**.
3. Cherchez « FlashForge Creator 5 Pro », installez, puis redémarrez Home Assistant.
4. Ajoutez l'intégration comme décrit ci-dessus (étapes 3 et 4).

### Icône

L'icône est fournie dans `custom_components/flashforge_creator5pro/brand/` (`icon.png`,
`icon@2x.png`, et leurs versions `dark_` pour le thème sombre). Home Assistant 2026.3 ou plus
récent l'affiche sans passer par le dépôt `home-assistant/brands`. C'est un dessin original :
le logo FlashForge n'est pas utilisé. HACS peut afficher une icône générique dans sa liste tant
que l'intégration n'est pas installée.

## Options

<img width="334" height="1111" alt="image" src="https://github.com/user-attachments/assets/771e13af-1790-4ff1-8ecc-205f4c1244bd" />

**Paramètres → Appareils et services → FlashForge Creator 5 Pro → Configurer** :

| Option | Défaut | Plage |
|---|---|---|
| Intervalle d'interrogation | 15 s | 10 à 120 s |
| URL du flux caméra | `http://<IP>:8080/?action=stream` | toute URL http(s) |
| Activer le bouton d'annulation | désactivé | oui / non |
| Activer les boutons pause et reprise | désactivé | oui / non |
| Afficher l'éclairage intérieur | activé | oui / non |

## Entités

Toutes les valeurs viennent d'une seule requête `POST /detail`.

| Entité | Remarque |
|---|---|
| État | prête, impression, pause, chauffe, erreur, etc. |
| Progression, fichier en cours, couche actuelle, nombre de couches | |
| Durée écoulée, durée restante | |
| Fin estimée | Seulement pendant l'impression (le firmware fige l'estimation en pause). |
| Température et consigne : buse active, plateau | |
| Température et consigne : T1 à T4 | Consignes désactivées par défaut. |
| Température et consigne : chambre | Créées seulement si le capteur répond. |
| Filament consommé (tâche), en longueur et en poids | Estimation de la tâche en cours. |
| Emplacement actif, emplacements 1 à 4 | Matière, ou « vide ». Couleur en attribut. |
| Ventilateurs, TVOC, filament total (vie) | |
| Code d'erreur, firmware, stockage libre | Diagnostic. |
| Impression en cours, en pause, problème, porte | Capteurs binaires. « Problème » couvre aussi une pause avec code d'erreur (bourrage). |
| Caméra | Flux MJPEG du port 8080. |
| Éclairage intérieur | Entité lumière (allumé / éteint). Commande `lightControl_cmd` sur `/control`. L'état se met à jour à l'interrogation suivante. |

### Coupure et refus

| Situation | Comportement |
|---|---|
| Imprimante éteinte, réseau coupé, délai dépassé | Entités indisponibles, nouvel essai à chaque intervalle, retour automatique. |
| Réponse illisible | Entités indisponibles, message distinct dans le journal. |
| Check code ou numéro de série refusé | **Les interrogations s'arrêtent.** Home Assistant affiche une demande de réauthentification. Aucun nouvel essai automatique. |

## Commandes

### Annuler l'impression (ce n'est pas un arrêt d'urgence)

La Creator 5 Pro n'offre **aucun arrêt d'urgence** sur le réseau local. La méthode
`emergency_stop()` de la bibliothèque envoie en réalité « annuler la tâche » : c'est le même ordre
que le bouton Annuler de l'écran, et le firmware décide comment il arrête les moteurs et le
chauffage. Pour un vrai arrêt d'urgence, utilisez le bouton de l'imprimante ou coupez son
alimentation.

Activation : **Configurer → Activer le bouton d'annulation**. Deux entités apparaissent :

| Entité | Rôle |
|---|---|
| Interrupteur « Armer l'annulation » | Confirmation. Reste activé 30 secondes, puis se désactive seul. Toujours désactivé après un redémarrage. |
| Bouton « Annuler l'impression » | Envoie l'annulation, en une seule requête : `POST /control`, `jobCtl_cmd`, `action=cancel`, HTTP 8898. |

Un appui sur le bouton :

| Situation | Effet |
|---|---|
| Interrupteur d'armement désactivé | Erreur affichée, **rien n'est envoyé**. |
| Aucune tâche (prête, terminée, annulée, erreur) | Erreur affichée, **rien n'est envoyé**. L'armement est consommé. |
| Tâche en cours (impression, pause, chauffe, calibrage) | Une requête. L'armement est consommé. |
| L'imprimante ne répond pas | Erreur « l'annulation a pu être reçue ou non ». **Aucun nouvel essai** : vérifiez l'imprimante. |
| L'imprimante refuse | Erreur affichée avec le code reçu. |

Pour un tableau de bord, mettez les deux entités côte à côte. Vous pouvez aussi ajouter
`confirmation: true` dans l'action d'appui de la carte du bouton.

### Pause et reprise

Activation : **Configurer → Activer les boutons pause et reprise**. Pas d'armement.

| Bouton | Envoyé seulement si | Requête |
|---|---|---|
| Mettre en pause | l'imprimante imprime | `jobCtl_cmd`, `action=pause` |
| Reprendre l'impression | l'imprimante est en pause | `jobCtl_cmd`, `action=continue` |

Dans tous les autres états, une erreur s'affiche et rien n'est envoyé. Comme pour l'annulation :
un seul envoi, aucun nouvel essai automatique.

### En cas d'erreur ou de problème

Rien n'est annulé automatiquement. Un bourrage, par exemple, met l'impression en pause avec un
code d'erreur ; une annulation automatique perdrait une impression qu'on aurait pu reprendre.
L'annulation reste une décision humaine. Pour être prévenu, une automatisation sur le capteur
« Problème » suffit :

```yaml
alias: Creator 5 Pro - problème
triggers:
  - trigger: state
    entity_id: binary_sensor.creator_5_pro_probleme
    to: "on"
actions:
  - action: notify.notify
    data:
      title: Creator 5 Pro
      message: >-
        Problème détecté (code {{ states('sensor.creator_5_pro_code_d_erreur') }}).
        Vérifiez la caméra, puis reprenez ou annulez.
```

Adaptez les noms d'entités à ceux de votre installation.

### Non proposé

Démarrer une impression : sur la Creator 5 Pro, il faut associer chaque outil à un emplacement
de matériel, et personne ne vérifie à distance que le plateau est libre.

## Limites connues

- **Mode cloud** : l'imprimante ne sert plus son API locale ; toutes les entités sont
  indisponibles (observé le 2026-10-16). Restez en mode LAN pour le suivi dans Home Assistant. Si
  une réauthentification est demandée au retour en LAN, relevez à nouveau le check code dans le
  menu LAN : il peut avoir changé.
- **Filament restant sur la bobine** : le firmware ne le renvoie pas. Seule l'estimation de la
  tâche en cours est disponible.
- **`get_temperatures()`** de la bibliothèque renvoie toujours `None` sur cette imprimante : il
  passe par le port 8899, qui est fermé. L'intégration ne l'utilise pas.
- **Réponse en cas de mauvais check code** : jamais observée. Par sécurité, tout code de réponse
  non nul est traité comme un refus et arrête les interrogations.
- **Caméra** : on ne peut pas l'allumer ni l'éteindre depuis Home Assistant. Le flux est actif
  imprimante au repos (vérifié).
- Les comportements décrits par ff-5mp-hass ont été observés en firmware 1.9.4 ; l'imprimante est
  en 1.9.9.

## Test de lecture manuel

Le script n'envoie que `POST /detail`, plus une lecture du flux caméra avec `--camera`.
Les secrets viennent des variables d'environnement et n'apparaissent jamais à l'écran.

```bash
FF_HOST=192.168.1.50 FF_SERIAL=... FF_CHECK_CODE=... python3 scripts/read_status.py --camera
```

Il faut un Python 3.11 ou plus récent avec `flashforge-python-api==1.6.0` installé.
Pour ne pas laisser les valeurs dans l'historique du shell, chargez-les depuis un fichier
protégé (`chmod 600`) hors du dépôt, avec `set -a; . ~/.ff-env; set +a`.

Codes de sortie : `0` lecture réussie, `2` variables manquantes, `3` **refus : arrêtez et
vérifiez le menu LAN**, `4` injoignable, `5` réponse illisible, `6` pas une Creator 5 Pro,
`7` caméra en échec.

## Tests automatiques

```bash
uv venv .venv
uv pip install -p .venv -r requirements-test.txt
.venv/Scripts/python -m pytest tests
```

Les tests de `tests/` n'ont pas besoin de Home Assistant : ils couvrent le parsing, la
détection du modèle et les erreurs (refus, délai, réponse invalide) contre un faux serveur
local.

Les tests de `tests_ha/` chargent l'intégration dans Home Assistant (imprimante simulée). Ils
s'exécutent sous Linux avec `requirements-test-ha.txt` (Python 3.14) :

```bash
python -m pytest tests_ha
```

Sous Windows, il faut en plus des modules factices `fcntl` et `resource` dans le `PYTHONPATH`
(voir [docs/02-rapport-test.md](docs/02-rapport-test.md)).
