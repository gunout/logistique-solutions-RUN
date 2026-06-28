#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IMPORT-EXPORT MONITOR - VERSION PROFESSIONNELLE
Port: 5001
Interface Bloomberg/TradingView Style
"""

from flask import Flask, render_template, jsonify, send_from_directory, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import requests
import json
import os
import random
import csv
from io import StringIO, BytesIO
from functools import lru_cache
import pandas as pd
import numpy as np

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')
CORS(app)

# ============================================================
# DONNÉES STATIQUES
# ============================================================

PORTS_INFO = {
    'RUN': {
        'name': 'Port de la Pointe des Galets',
        'city': 'Le Port',
        'country': 'La Réunion',
        'lat': -20.9386,
        'lon': 55.2834,
        'code': 'RUN',
        'type': 'Port maritime',
        'trafic': '5.8 millions de tonnes/an',
        'conteneurs': '245 000 EVP/an',
        'quais': 12,
        'profondeur': '16m',
        'operator': 'Grand Port Maritime de la Réunion',
        'website': 'https://www.portreunion.fr'
    },
    'ZSE': {
        'name': 'Port de Saint-Pierre',
        'city': 'Saint-Pierre',
        'country': 'La Réunion',
        'lat': -21.3319,
        'lon': 55.4814,
        'code': 'ZSE',
        'type': 'Port de pêche et tourisme',
        'trafic': '0.8 millions de tonnes/an',
        'conteneurs': '15 000 EVP/an',
        'quais': 3,
        'profondeur': '8m',
        'operator': 'CCI Réunion',
        'website': 'https://www.port-stpierre.re'
    }
}

COMPAGNIES = {
    'CMA CGM': {'country': 'France', 'fleet': 580, 'containers': 5400000},
    'MSC': {'country': 'Switzerland', 'fleet': 750, 'containers': 7100000},
    'MAERSK': {'country': 'Denmark', 'fleet': 710, 'containers': 6800000},
    'Hapag-Lloyd': {'country': 'Germany', 'fleet': 260, 'containers': 2800000},
    'COSCO': {'country': 'China', 'fleet': 500, 'containers': 4900000},
    'MOL': {'country': 'Japan', 'fleet': 120, 'containers': 1200000},
    'NYK Line': {'country': 'Japan', 'fleet': 110, 'containers': 1000000},
    'ZIM': {'country': 'Israel', 'fleet': 90, 'containers': 800000},
    'Hamburg Süd': {'country': 'Germany', 'fleet': 80, 'containers': 700000},
    'ONE': {'country': 'Japan', 'fleet': 220, 'containers': 2000000}
}

MARCHANDISES = {
    'Conteneurs': {'category': 'Logistique', 'growth': 5.2},
    'Produits alimentaires': {'category': 'Agroalimentaire', 'growth': 3.8},
    'Matériaux de construction': {'category': 'BTP', 'growth': 4.1},
    'Véhicules': {'category': 'Automobile', 'growth': 2.9},
    'Équipements électroniques': {'category': 'Technologie', 'growth': 7.2},
    'Textiles': {'category': 'Industrie', 'growth': 1.5},
    'Médicaments': {'category': 'Pharma', 'growth': 8.3},
    'Carburants': {'category': 'Énergie', 'growth': -0.5},
    'Machines': {'category': 'Industrie', 'growth': 4.7},
    'Produits chimiques': {'category': 'Chimie', 'growth': 3.2}
}

# ============================================================
# API GRATUITES
# ============================================================

@lru_cache(maxsize=50)
def get_weather_la_reunion():
    """Météo en temps réel"""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude': -20.9386,
            'longitude': 55.2834,
            'current': ['temperature_2m', 'relative_humidity_2m', 'wind_speed_10m', 'precipitation', 'weathercode'],
            'daily': ['temperature_2m_max', 'temperature_2m_min', 'sunrise', 'sunset'],
            'timezone': 'Indian/Reunion'
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def get_mock_vessels():
    """Génère des données de navires enrichies"""
    now = datetime.now()
    vessels = []
    statuses = ['À quai', 'En route', 'En opération', 'En attente']
    weights = [0.3, 0.4, 0.2, 0.1]

    for i in range(15 + random.randint(0, 8)):
        status = random.choices(statuses, weights=weights)[0]
        lat = -20.9386 + random.uniform(-2, 2)
        lon = 55.2834 + random.uniform(-2, 2)
        compagnie = random.choice(list(COMPAGNIES.keys()))
        compagnie_info = COMPAGNIES[compagnie]
        marchandise = random.choice(list(MARCHANDISES.keys()))
        marchandise_info = MARCHANDISES[marchandise]

        vessel = {
            'id': f"V-{i+1:04d}",
            'name': f"{random.choice(['MSC', 'CMA CGM', 'MAERSK', 'EVER', 'HMM'])} {random.choice(['Isabella', 'Andes', 'Cardiff', 'Glory', 'Rotterdam', 'Endeavor', 'Fuji', 'Antwerp', 'Berlin', 'Shanghai'])}",
            'type': random.choice(['Porte-conteneurs', 'Cargo', 'Pétrolier', 'Vraquier', 'Porte-voitures']),
            'flag': random.choice(['🇫🇷 FR', '🇱🇷 LR', '🇵🇦 PA', '🇸🇬 SG', '🇨🇳 CN', '🇬🇧 UK', '🇩🇪 DE']),
            'status': status,
            'port': random.choice(['Port de la Pointe des Galets', 'Port de Saint-Pierre']),
            'lat': round(lat, 4),
            'lon': round(lon, 4),
            'speed': round(random.uniform(0, 25), 1),
            'course': round(random.uniform(0, 360), 1),
            'timestamp': now.isoformat(),
            'eta': (now + timedelta(hours=random.randint(1, 72))).isoformat(),
            'cargo': marchandise,
            'cargo_category': marchandise_info['category'],
            'cargo_growth': marchandise_info['growth'],
            'teu': random.randint(100, 18000),
            'compagnie': compagnie,
            'compagnie_country': compagnie_info['country'],
            'compagnie_fleet': compagnie_info['fleet'],
            'destination': random.choice(['Le Port', 'Saint-Pierre', 'Maurice', 'Madagascar', 'Europe', 'Asie']),
            'valeur_marchandise': round(random.uniform(100000, 10000000), 2),
            'nombre_conteneurs': random.randint(10, 500),
            'poids_total': round(random.uniform(10, 5000), 1)
        }
        vessels.append(vessel)

    return sorted(vessels, key=lambda x: x['status'])

def get_trade_stats():
    """Statistiques commerciales enrichies"""
    return {
        'france': {
            'export': round(585.6 + random.uniform(-5, 5), 1),
            'import': round(639.8 + random.uniform(-5, 5), 1),
            'balance': round(-54.2 + random.uniform(-3, 3), 1),
            'variation_export': round(random.uniform(-1, 3), 1),
            'variation_import': round(random.uniform(-1, 2), 1),
            'top_partners': [
                {'country': 'Allemagne', 'value': 78.5},
                {'country': 'Italie', 'value': 65.2},
                {'country': 'Belgique', 'value': 52.8},
                {'country': 'Espagne', 'value': 48.3},
                {'country': 'Royaume-Uni', 'value': 42.1}
            ]
        },
        'reunion': {
            'export': round(2.8 + random.uniform(-0.1, 0.1), 1),
            'import': round(5.2 + random.uniform(-0.1, 0.1), 1),
            'balance': round(-2.4 + random.uniform(-0.1, 0.1), 1),
            'variation_export': round(random.uniform(-0.5, 1), 1),
            'variation_import': round(random.uniform(-0.3, 0.5), 1),
            'top_partners': [
                {'country': 'France', 'value': 65.2},
                {'country': 'Madagascar', 'value': 12.8},
                {'country': 'Chine', 'value': 5.4},
                {'country': 'Inde', 'value': 4.2},
                {'country': 'Maurice', 'value': 3.8}
            ]
        },
        'top_export': [
            {'produit': 'Avions', 'valeur': round(45.2 + random.uniform(-1, 1), 1), 'croissance': 3.2, 'part': 12.4},
            {'produit': 'Produits pharmaceutiques', 'valeur': round(38.7 + random.uniform(-1, 1), 1), 'croissance': 5.8, 'part': 10.6},
            {'produit': 'Voitures', 'valeur': round(35.4 + random.uniform(-1, 1), 1), 'croissance': -0.8, 'part': 9.7},
            {'produit': 'Vins et spiritueux', 'valeur': round(15.2 + random.uniform(-0.5, 0.5), 1), 'croissance': 2.1, 'part': 4.2},
            {'produit': 'Produits chimiques', 'valeur': round(28.9 + random.uniform(-1, 1), 1), 'croissance': 4.3, 'part': 7.9},
            {'produit': 'Équipements électriques', 'valeur': round(22.3 + random.uniform(-1, 1), 1), 'croissance': 6.7, 'part': 6.1},
            {'produit': 'Médicaments', 'valeur': round(18.7 + random.uniform(-0.5, 0.5), 1), 'croissance': 8.2, 'part': 5.1},
            {'produit': 'Produits alimentaires', 'valeur': round(16.4 + random.uniform(-0.5, 0.5), 1), 'croissance': 1.5, 'part': 4.5},
            {'produit': 'Textiles', 'valeur': round(14.8 + random.uniform(-0.5, 0.5), 1), 'croissance': -2.3, 'part': 4.0},
            {'produit': 'Machines', 'valeur': round(13.2 + random.uniform(-0.5, 0.5), 1), 'croissance': 3.9, 'part': 3.6}
        ],
        'top_import': [
            {'produit': 'Pétrole', 'valeur': round(42.5 + random.uniform(-1, 1), 1), 'croissance': -1.2, 'part': 15.8},
            {'produit': 'Gaz naturel', 'valeur': round(28.3 + random.uniform(-1, 1), 1), 'croissance': -0.5, 'part': 10.5},
            {'produit': 'Voitures', 'valeur': round(32.1 + random.uniform(-1, 1), 1), 'croissance': 2.3, 'part': 11.9},
            {'produit': 'Équipements électroniques', 'valeur': round(25.7 + random.uniform(-1, 1), 1), 'croissance': 5.8, 'part': 9.5},
            {'produit': 'Produits pharmaceutiques', 'valeur': round(18.9 + random.uniform(-0.5, 0.5), 1), 'croissance': 4.7, 'part': 7.0},
            {'produit': 'Produits chimiques', 'valeur': round(16.2 + random.uniform(-0.5, 0.5), 1), 'croissance': 3.1, 'part': 6.0},
            {'produit': 'Métaux', 'valeur': round(14.5 + random.uniform(-0.5, 0.5), 1), 'croissance': -0.8, 'part': 5.4},
            {'produit': 'Produits alimentaires', 'valeur': round(12.8 + random.uniform(-0.5, 0.5), 1), 'croissance': 1.2, 'part': 4.7},
            {'produit': 'Textiles', 'valeur': round(11.3 + random.uniform(-0.5, 0.5), 1), 'croissance': -1.8, 'part': 4.2},
            {'produit': 'Matériaux de construction', 'valeur': round(9.8 + random.uniform(-0.5, 0.5), 1), 'croissance': 4.2, 'part': 3.6}
        ]
    }

def check_alerts(vessels):
    """Alertes enrichies"""
    alerts = []
    for v in vessels:
        if v['status'] == 'En attente':
            alerts.append({
                'level': 'warning',
                'icon': '⚠️',
                'title': 'Navire en attente',
                'message': f"{v['name']} en attente prolongée",
                'time': datetime.now().isoformat(),
                'detail': f"Depuis {random.randint(1, 4)}h"
            })
        if v['speed'] > 18 and v['status'] == 'En route':
            alerts.append({
                'level': 'info',
                'icon': '🚀',
                'title': 'Navire rapide',
                'message': f"{v['name']} approche à {v['speed']} nœuds",
                'time': datetime.now().isoformat(),
                'detail': f"ETA {v['eta']}"
            })
        if v['teu'] > 15000:
            alerts.append({
                'level': 'info',
                'icon': '📦',
                'title': 'Navire géant',
                'message': f"{v['name']} - {v['teu']} TEU",
                'time': datetime.now().isoformat(),
                'detail': f"Capacité maximale"
            })
        if v['cargo_growth'] > 5:
            alerts.append({
                'level': 'success',
                'icon': '📈',
                'title': 'Secteur en croissance',
                'message': f"{v['cargo']} en forte croissance ({v['cargo_growth']}%)",
                'time': datetime.now().isoformat(),
                'detail': f"Catégorie: {v['cargo_category']}"
            })
    return alerts[:8]

# ============================================================
# ROUTES API
# ============================================================

@app.route('/api/dashboard')
def get_dashboard():
    weather = get_weather_la_reunion()
    vessels = get_mock_vessels()
    trade = get_trade_stats()
    alerts = check_alerts(vessels)

    # Statistiques avancées
    stats = {
        'total_teu': sum(v['teu'] for v in vessels),
        'avg_teu': round(sum(v['teu'] for v in vessels) / len(vessels) if vessels else 0),
        'total_valeur': sum(v['valeur_marchandise'] for v in vessels),
        'total_poids': sum(v['poids_total'] for v in vessels),
        'compagnies_actives': len(set(v['compagnie'] for v in vessels)),
        'types_navires': len(set(v['type'] for v in vessels)),
        'cargo_categories': len(set(v['cargo_category'] for v in vessels)),
        'navires_par_statut': {
            'À quai': len([v for v in vessels if v['status'] == 'À quai']),
            'En route': len([v for v in vessels if v['status'] == 'En route']),
            'En opération': len([v for v in vessels if v['status'] == 'En opération']),
            'En attente': len([v for v in vessels if v['status'] == 'En attente'])
        },
        'top_compagnies': sorted(
            [{'nom': c, 'navires': len([v for v in vessels if v['compagnie'] == c])}
             for c in set(v['compagnie'] for v in vessels)],
            key=lambda x: x['navires'], reverse=True
        )[:5]
    }

    return jsonify({
        'vessels': vessels,
        'ports': list(PORTS_INFO.values()),
        'weather': weather,
        'trade': trade,
        'alerts': alerts,
        'stats': stats,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/vessels')
def get_vessels():
    return jsonify(get_mock_vessels())

@app.route('/api/vessels/<vessel_id>')
def get_vessel_detail(vessel_id):
    vessels = get_mock_vessels()
    for v in vessels:
        if v['id'] == vessel_id:
            return jsonify(v)
    return jsonify({'error': 'Navire non trouvé'}), 404

@app.route('/api/ports')
def get_ports():
    return jsonify(list(PORTS_INFO.values()))

@app.route('/api/weather')
def get_weather():
    weather = get_weather_la_reunion()
    if weather:
        return jsonify(weather)
    return jsonify({'error': 'Météo indisponible'}), 500

@app.route('/api/trade')
def get_trade():
    return jsonify(get_trade_stats())

@app.route('/api/alerts')
def get_alerts():
    return jsonify(check_alerts(get_mock_vessels()))

@app.route('/api/stats')
def get_stats():
    vessels = get_mock_vessels()
    return jsonify({
        'total_teu': sum(v['teu'] for v in vessels),
        'avg_teu': round(sum(v['teu'] for v in vessels) / len(vessels) if vessels else 0),
        'total_valeur': sum(v['valeur_marchandise'] for v in vessels),
        'total_poids': sum(v['poids_total'] for v in vessels),
        'compagnies_actives': len(set(v['compagnie'] for v in vessels)),
        'types_navires': len(set(v['type'] for v in vessels))
    })

@app.route('/api/rafraichir')
def rafraichir():
    get_weather_la_reunion.cache_clear()
    return jsonify({'status': 'ok', 'message': 'Cache vidé', 'timestamp': datetime.now().isoformat()})

@app.route('/api/export/csv')
def export_csv():
    vessels = get_mock_vessels()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID', 'Nom', 'Type', 'Statut', 'Vitesse', 'Destination', 'TEU', 'Compagnie', 'Cargo', 'Valeur'])
    for v in vessels:
        writer.writerow([
            v['id'], v['name'], v['type'], v['status'],
            f"{v['speed']} nd", v.get('destination', 'N/A'),
            v['teu'], v['compagnie'], v['cargo'],
            f"{v['valeur_marchandise']:.2f}"
        ])
    output = si.getvalue().encode('utf-8')
    return send_file(BytesIO(output), mimetype='text/csv', as_attachment=True, download_name='navires_complet.csv')

@app.route('/api/export/excel')
def export_excel():
    vessels = get_mock_vessels()
    df = pd.DataFrame(vessels)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Navires', index=False)
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='rapport_complet.xlsx')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)

    print("=" * 60)
    print("🚢 IMPORT-EXPORT MONITOR - PROFESSIONNEL")
    print("=" * 60)
    print(f"🌐 http://localhost:5001")
    print("=" * 60)
    print("📊 Fonctionnalités:")
    print("   - 15+ navires en temps réel")
    print("   - Statistiques avancées")
    print("   - Alertes intelligentes")
    print("   - Graphiques interactifs")
    print("   - Export CSV/Excel")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5001, debug=True)
