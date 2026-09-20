# 🌊 S-Wing Réunion PRO

> **Centre de commandement portuaire temps réel** — Suivi AIS, KPIs enrichis et prédictions IA pour le Port de La Réunion (97420).

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![AISStream](https://img.shields.io/badge/AISStream-WebSocket-0055A4)](https://aisstream.io/)
[![Leaflet](https://img.shields.io/badge/Leaflet-1.9.4-199900?logo=leaflet&logoColor=white)](https://leafletjs.com/)
[![Chart.js](https://img.shields.io/badge/Chart.js-4.4-FF6384?logo=chartdotjs&logoColor=white)](https://www.chartjs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](#-licence)

---

## 📖 Présentation

**S-Wing Réunion PRO** est un tableau de bord maritime qui agrège en temps réel les signaux AIS des navires transitant dans la zone du Port de La Réunion (océan Indien). Il combine :

- 🛰️ **Flux AIS live** via WebSocket (AISStream.io)
- 📊 **8 KPIs portuaires** calculés côté serveur (conteneurs, occupation, satisfaction, retards, efficacité, rotation, coût/TEU, CO₂)
- 🗺️ **Cartographie interactive** avec géofencing des quais (détection arrivée/départ)
- 🤖 **Prédictions de trafic à J+7** avec indice de confiance
- 🌦️ **Contexte météo maritime** (houle, swell, vent) et statut jour/nuit
- 💱 **Taux de change EUR/USD** en direct

Interface **bleu-blanc-rouge**, sobre et professionnelle, adaptée à un usage institutionnel ou portuaire.

---

## ✨ Fonctionnalités

| Module | Description |
|--------|-------------|
| **Carte AIS** | Rendu Leaflet temps réel, marqueurs différenciés (à quai / lent / en route), popups détaillés |
| **Géofencing** | Détection automatique des arrivées et départs du périmètre physique des quais |
| **KPIs enrichis** | 8 indicateurs métier calculés à partir du trafic réel, de la météo et du contexte économique |
| **Analytique** | Distribution par type de navire et par tranche de vitesse (Chart.js) |
| **IA prédictive** | Modèle simple de projection de trafic J+1 à J+7 avec intervalle de confiance |
| **Registre flotte** | Tableau complet : MMSI, nom, type, destination, longueur, tirant, position, cap, ETA |
| **Alertes dynamiques** | Bandeau d'alertes contextuel (saturation quais, houle, statut AIS) |
| **Journal système** | Console de logs live (réception AIS, erreurs, mises à jour KPIs) |
| **Mode dégradé** | Bascule automatique sur données de test si le flux AIS est indisponible |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────┐
│  Navigateur (http://localhost:5001)          │
│  ┌────────────────────────────────────────┐  │
│  │  docs/index.html                       │  │
│  │  HTML + CSS + JS (tout-en-un)          │  │
│  │  Leaflet · Chart.js · Font Awesome     │  │
│  └────────────────────────────────────────┘  │
└────────────────────┬─────────────────────────┘
                     │ fetch /api/*
                     ▼
┌──────────────────────────────────────────────┐
│  server.py — Flask (port 5001)               │
│  ├─ Thread WebSocket AISStream               │
│  ├─ Endpoints REST (/api/vessels, /api/kpis) │
│  ├─ Calcul KPIs + Géofencing                 │
│  └─ Cache contexte externe (10 min)          │
└────────────────────┬─────────────────────────┘
                     │ WebSocket + HTTP
                     ▼
┌──────────────────────────────────────────────┐
│  Sources externes (gratuites)                │
│  • AISStream.io        (flux AIS WebSocket)  │
│  • Open-Meteo Marine   (houle, swell, vent)  │
│  • Sunrise-Sunset.org  (jour / nuit)         │
│  • Frankfurter.app     (EUR → USD)           │
└──────────────────────────────────────────────┘
```

---

## 🚀 Installation

### Prérequis

- **Python** 3.9 ou supérieur
- **pip** à jour
- Une **clé API AISStream** gratuite : [aisstream.io](https://aisstream.io/)

### 1. Cloner le dépôt

```bash
git clone https://github.com/<votre-username>/swing-reunion.git
cd swing-reunion
```

### 2. Créer et activer l'environnement virtuel

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (cmd)
venv\Scripts\activate.bat
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer la clé API

Créez un fichier `.env` à la racine :

```bash
AIS_API_KEY=votre_cle_aisstream_ici
```

> ⚠️ **Le fichier `.env` ne doit JAMAIS être commité.** Il est déjà listé dans `.gitignore`.

### 5. Lancer le serveur

```bash
python server.py
```

### 6. Ouvrir l'interface

Rendez-vous sur :

```
http://localhost:5001
```

---

## 📁 Structure du projet

```
swing-reunion/
├── .env                    # Clé API (secret — non versionné)
├── .env.example            # Modèle de configuration
├── .gitignore              # Exclusions Git
├── server.py               # Backend Flask + WebSocket AIS
├── requirements.txt        # Dépendances Python
├── README.md               # Ce fichier
└── docs/
    └── index.html          # Interface tout-en-un (HTML+CSS+JS)
```

---

## 🔌 API REST

Toutes les routes sont servies par Flask sur `http://localhost:5001`.

| Méthode | Endpoint | Description | Exemple de réponse |
|---------|----------|-------------|-------------------|
| `GET` | `/` | Interface HTML | Page complète |
| `GET` | `/api/vessels` | Liste des navires détectés | `[{ id, name, lat, lng, speed, ... }]` |
| `GET` | `/api/vessels/<id>` | Détail d'un navire par MMSI | `{ id, name, ... }` |
| `GET` | `/api/stats` | Statistiques de connexion AIS | `{ total, connected, messages, last_update }` |
| `GET` | `/api/kpis` | 8 KPIs portuaires calculés | `{ conteneurs, occupation, co2, ... }` |
| `GET` | `/api/weather` | Météo maritime actuelle | `{ hourly: { wave_height, ... } }` |
| `GET` | `/api/predictions` | Projection trafic J+7 | `{ predictions: [...], trend, peak }` |

### Exemple : récupérer les KPIs

```bash
curl http://localhost:5001/api/kpis | jq
```

```json
{
  "conteneurs": 12450,
  "occupation": 66.7,
  "satisfaction": 92.4,
  "retards": 2.1,
  "efficacite": 95.0,
  "rotation": 3.2,
  "cout_teu": 187.45,
  "co2": 9.87,
  "metadata": {
    "navires_total": 12,
    "navires_quai": 4,
    "navires_mouillage": 2,
    "navires_mouvement": 6,
    "navires_cargo": 7,
    "sources": "Vent:12.3kts, Houle:1.4m, Nuit:False, EUR/USD:1.087"
  }
}
```

---

## ⚙️ Configuration

### Variables d'environnement

| Variable | Obligatoire | Description | Défaut |
|----------|-------------|-------------|--------|
| `AIS_API_KEY` | ✅ | Clé API AISStream.io | — |

### Paramètres dans `server.py`

| Constante | Valeur par défaut | Description |
|-----------|-------------------|-------------|
| `PORT` | `5001` | Port du serveur Flask |
| `BOUNDING_BOX` | `[[-21.5, 54.5], [-20.5, 56.5]]` | Zone géographique surveillée (Réunion) |
| `QUAI_POLYGON` | Coordonnées polygonales | Périmètre physique des quais (géofencing) |
| `history_size` | `100` | Nombre de positions conservées par navire |
| `external_data_cache` | `600 s` | Durée du cache des APIs externes |

### Modifier la zone surveillée

Éditez `BOUNDING_BOX` dans `server.py` :

```python
BOUNDING_BOX = [[lat_min, lng_min], [lat_max, lng_max]]
```

Le format attendu par AISStream est `[[[lat_min, lng_min], [lat_max, lng_max]]]` (double tableau), mais le code encapsule déjà correctement la valeur.

---

## 🧭 Utilisation

### Interface — 5 onglets

1. **CARTE & AIS** — Visualisation temps réel des navires, météo maritime, radar de proximité
2. **ANALYTIQUE** — Graphiques de répartition (types, vitesses) + journal système
3. **PRÉDICTIONS IA** — Projection de trafic J+7 et actions suggérées
4. **OPÉRATIONS** — Registre complet de la flotte sous forme de tableau triable
5. **RAPPORTS & EXPORT** — Configuration système (exports réservés à une V2)

### Codes couleur des marqueurs

| Couleur | Signification |
|---------|---------------|
| 🔵 **Bleu** | Navire en route (vitesse > 5 nœuds) |
| 🟡 **Ambre** | Navire lent (0,5 à 5 nœuds) |
| 🔴 **Rouge** | Navire à quai (vitesse < 0,5 nœud) |

### KPIs affichés

| KPI | Unité | Interprétation |
|-----|-------|----------------|
| Conteneurs | TEU | Volume total traité estimé |
| Occupation quais | % | Taux d'occupation des 6 postes à quai |
| Satisfaction | % | Indice client dérivé des retards et de l'efficacité |
| Retards | heures | Retard moyen pondéré |
| Efficacité | % | Performance opérationnelle globale |
| Rotation | jours | Temps moyen d'un cycle navire |
| Coût / TEU | € | Coût unitaire par conteneur |
| CO₂ | tonnes | Émissions estimées de la flotte |

---

## 🛠️ Dépannage

### Le serveur refuse de démarrer

```
RuntimeError: ❌ AIS_API_KEY manquante.
```

**Cause** : le fichier `.env` est absent ou la variable n'est pas définie.
**Solution** : créez `.env` à la racine avec `AIS_API_KEY=votre_cle`.

### `AIS OFFLINE` en orange dans l'interface

**Cause** : AISStream n'est pas joignable ou la clé est invalide.
**Solution** : vérifiez votre clé sur [aisstream.io](https://aisstream.io/), puis regardez les logs du serveur Flask. La reconnexion se fait automatiquement toutes les 10 secondes.

### `CONNEXION PERDUE` en rouge

**Cause** : le serveur Flask n'est pas lancé ou le port 5001 est déjà utilisé.
**Solution** :

```bash
# Vérifier le port
lsof -i :5001                  # Linux / macOS
netstat -ano | findstr :5001   # Windows

# Puis relancer
python server.py
```

### Aucun navire ne s'affiche

**Cause** : la zone BoundingBox ne contient aucun navire actuellement, ou le flux AIS est vide.
**Solution** : le mode test prend le relais automatiquement (`use_test_data = True`) avec 5 navires factices. Vérifiez que `BASE_VESSELS` est bien présent dans `server.py`.

### Erreur `ModuleNotFoundError: No module named 'dotenv'`

**Cause** : `python-dotenv` n'est pas installé.
**Solution** : `pip install python-dotenv`.

---

## 🧪 Tests manuels

```bash
# Statut du serveur
curl http://localhost:5001/api/stats

# Liste des navires
curl http://localhost:5001/api/vessels | jq '.[0]'

# KPIs calculés
curl http://localhost:5001/api/kpis | jq '.metadata'

# Prédictions
curl http://localhost:5001/api/predictions | jq '.trend'
```

---

## 🗺️ Feuille de route

- [x] Flux AIS temps réel via WebSocket
- [x] Géofencing physique des quais
- [x] 8 KPIs calculés côté serveur
- [x] Prédictions IA J+7
- [x] Interface bleu-blanc-rouge responsive
- [ ] Export CSV / Excel / PDF (backend V2)
- [ ] Persistance historique en base (SQLite / PostgreSQL)
- [ ] Authentification multi-utilisateurs
- [ ] Déploiement public (Render + GitHub Pages)

---

## 🔒 Sécurité

- **La clé API AISStream est stockée dans `.env`**, jamais dans le code source.
- **Le fichier `.env` est exclu du versionnement** via `.gitignore`.
- **Aucune donnée sensible n'est transmise au navigateur** : le frontend ne connaît que les endpoints `/api/*`.
- **Pour un déploiement public** : hébergez `server.py` sur Render/Railway/Fly.io et gardez `index.html` sur GitHub Pages, en pointant `const API` vers l'URL du backend.

> ⚠️ **Si votre clé a été exposée publiquement** (commit, screenshot, partage), révoquez-la immédiatement sur [aisstream.io](https://aisstream.io/) et générez-en une nouvelle.

---

## 🤝 Contribution

Les contributions sont bienvenues. Pour proposer une amélioration :

1. Forkez le dépôt
2. Créez une branche (`git checkout -b feature/ma-fonctionnalite`)
3. Commitez vos changements (`git commit -m 'Ajout de ma fonctionnalité'`)
4. Poussez la branche (`git push origin feature/ma-fonctionnalite`)
5. Ouvrez une Pull Request

---

## 📄 Licence

Ce projet est distribué sous licence **MIT**. Voir le fichier `LICENSE` pour plus de détails.

---

## 🙏 Remerciements

- [AISStream.io](https://aisstream.io/) — flux AIS mondial gratuit
- [Open-Meteo](https://open-meteo.com/) — données météo marines
- [Sunrise-Sunset.org](https://sunrise-sunset.org/) — calculs jour/nuit
- [Frankfurter.app](https://www.frankfurter.app/) — taux de change
- [Leaflet](https://leafletjs.com/) — cartographie interactive
- [Chart.js](https://www.chartjs.org/) — visualisation de données
- [Font Awesome](https://fontawesome.com/) — iconographie

---

## 📞 Contact

Pour toute question, suggestion ou signalement de bug, ouvrez une **issue** sur le dépôt GitHub.

---

<div align="center">

**S-Wing Réunion PRO** · v2.1 · Le Port 97420 · Océan Indien

_Fait avec ❤️ pour la communauté maritime réunionnaise._

</div>
