#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
S-Wing Réunion PRO - Serveur Flask
Port: 5001
AISStream + API REST + KPIs Enrichis + Périmètre Quais Physique
"""

from flask import Flask, render_template, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime
import json
import os
import threading
import traceback
import websocket
import requests
import time
import math
from collections import deque
import random
from dotenv import load_dotenv

# ============================================================
# CHARGEMENT DES VARIABLES D'ENVIRONNEMENT
# ============================================================

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

app = Flask(__name__, static_folder='static', template_folder='docs')
app.config['SECRET_KEY'] = 'swing-reunion-pro-2024'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

PORT = 5001
AIS_API_KEY = os.getenv('AIS_API_KEY')

if not AIS_API_KEY:
    raise RuntimeError(
        "❌ AIS_API_KEY manquante.\n"
        "Créez un fichier .env à la racine du projet avec :\n"
        "    AIS_API_KEY=votre_cle_aisstream\n"
        "Voir .env.example pour un modèle."
    )

# ⚠️ ZONE ÉLARGIE TEMPORAIREMENT POUR DIAGNOSTIC
# Une fois le flux confirmé, réduire à [[-22.5, 53.5], [-19.5, 57.5]]
BOUNDING_BOX = [[-40.0, 20.0], [10.0, 100.0]]  # Océan Indien large

DEBUG_AIS = os.getenv('DEBUG_AIS', '1') == '1'

# ============================================================
# STOCKAGE DES DONNÉES
# ============================================================

vessels = {}
vessel_history = {}
message_count = 0
is_connected = False
last_update = None
vessel_lock = threading.Lock()
history_size = 100
simulation_step = 0
use_test_data = True
quai_events = deque(maxlen=100)

# Cache pour les API externes
external_data_cache = {'data': {}, 'last_fetch': 0}

# ============================================================
# PÉRIMÈTRE PHYSIQUE DES QUAIS (Géofencing)
# ============================================================

QUAI_POLYGON = [
    [-21.106, 55.530], [-21.107, 55.545],
    [-21.118, 55.547], [-21.119, 55.535],
    [-21.114, 55.528], [-21.106, 55.530]
]

MOUILLAGE_POLYGON = [
    [-21.095, 55.520], [-21.095, 55.550],
    [-21.105, 55.550], [-21.105, 55.520],
    [-21.095, 55.520]
]

def point_in_polygon(lat, lng, polygon):
    """Algorithme de ray-casting"""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > lng) != (yj > lng)) and (lat < (xj - xi) * (lng - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

# ============================================================
# DONNÉES DE TEST STABLES
# ============================================================

BASE_VESSELS = [
    {'id': '228339000', 'name': 'MSC Isabella', 'type': 'import', 'cargo': 'Cargo', 'flag': 'FR', 'lat': -21.08, 'lng': 55.52, 'speed': 8.5, 'course': 315, 'length': 366, 'draft': 12.5, 'destination': 'Port de La Reunion'},
    {'id': '228339001', 'name': 'CMA CGM La Reunion', 'type': 'export', 'cargo': 'Cargo', 'flag': 'PA', 'lat': -21.15, 'lng': 55.56, 'speed': 12.3, 'course': 45, 'length': 399, 'draft': 14.2, 'destination': 'Marseille'},
    {'id': '228339002', 'name': 'MAERSK Cardiff', 'type': 'transit', 'cargo': 'Cargo', 'flag': 'SG', 'lat': -21.10, 'lng': 55.48, 'speed': 6.2, 'course': 180, 'length': 350, 'draft': 11.8, 'destination': 'Singapour'},
    {'id': '228339003', 'name': 'EVER Glory', 'type': 'import', 'cargo': 'Cargo', 'flag': 'CN', 'lat': -21.112, 'lng': 55.538, 'speed': 0.2, 'course': 90, 'length': 400, 'draft': 15.0, 'destination': 'Port de La Reunion'},
    {'id': '228339004', 'name': 'HMM Rotterdam', 'type': 'export', 'cargo': 'Tanker', 'flag': 'UK', 'lat': -21.05, 'lng': 55.50, 'speed': 14.7, 'course': 270, 'length': 330, 'draft': 13.5, 'destination': 'Rotterdam'},
]

def get_test_vessels():
    global simulation_step
    simulation_step += 1
    out = []
    for b in BASE_VESSELS:
        v = b.copy()
        if simulation_step % 30 == 0:
            if v['type'] == 'import':
                v['lat'] += 0.0003
                v['lng'] += 0.0002
            elif v['type'] == 'export':
                v['lat'] -= 0.0003
                v['lng'] -= 0.0002
            v['speed'] = max(0, min(20, v['speed'] + random.uniform(-0.3, 0.3)))
            v['course'] = (v['course'] + random.uniform(-1, 1)) % 360
        v['timestamp'] = datetime.now().isoformat()
        out.append(v)
    return out

# ============================================================
# APPELS API EXTERNES GRATUITES
# ============================================================

def get_live_context():
    global external_data_cache
    if time.time() - external_data_cache['last_fetch'] < 600 and external_data_cache['data']:
        return external_data_cache['data']

    context = {'wind_speed_kts': 0, 'wave_height_m': 0, 'swell_m': 0, 'is_night': False, 'eur_usd': 1.08}

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/marine",
            params={
                'latitude': -21.115, 'longitude': 55.536,
                'current': 'wind_speed_10m,wave_height,swell_wave_height',
                'timezone': 'Indian/Reunion'
            },
            timeout=5
        )
        if r.status_code == 200:
            c = r.json().get('current', {})
            context['wind_speed_kts'] = (c.get('wind_speed_10m', 0) or 0) * 1.943
            context['wave_height_m'] = c.get('wave_height', 0) or 0
            context['swell_m'] = c.get('swell_wave_height', 0) or 0
    except Exception as e:
        print(f"Erreur Meteo: {e}")

    try:
        r = requests.get(
            "https://api.sunrise-sunset.org/json",
            params={'lat': -21.115, 'lng': 55.536, 'formatted': 0},
            timeout=5
        )
        if r.status_code == 200:
            results = r.json().get('results', {})
            now = datetime.utcnow()
            sunrise = datetime.fromisoformat(results.get('sunrise', '').replace('Z', '+00:00')).replace(tzinfo=None)
            sunset = datetime.fromisoformat(results.get('sunset', '').replace('Z', '+00:00')).replace(tzinfo=None)
            reunion_now = now.hour + 4
            context['is_night'] = not (sunrise.hour + 4 <= reunion_now <= sunset.hour + 4)
    except Exception as e:
        print(f"Erreur Sunrise/Sunset: {e}")

    try:
        r = requests.get("https://api.frankfurter.app/latest?from=EUR&to=USD", timeout=5)
        if r.status_code == 200:
            context['eur_usd'] = r.json().get('rates', {}).get('USD', 1.08)
    except Exception as e:
        print(f"Erreur FX: {e}")

    external_data_cache['data'] = context
    external_data_cache['last_fetch'] = time.time()
    return context

# ============================================================
# MODULE KPIs
# ============================================================

def is_cargo_vessel(v):
    """Détecte si un navire est de type cargo (texte OU code AIS numérique)."""
    cargo_raw = v.get('cargo', '')
    cargo_str = str(cargo_raw).lower()

    if cargo_str in ['cargo', 'conteneurs', 'container', 'containers']:
        return True

    try:
        code = int(cargo_raw)
        if 70 <= code <= 79:
            return True
    except (ValueError, TypeError):
        pass

    return False


def compute_kpis(vessels_list, context):
    total = len(vessels_list)
    if total == 0:
        return {
            'conteneurs': 0, 'occupation': 0.0, 'satisfaction': 0.0,
            'retards': 0.0, 'efficacite': 0.0, 'rotation': 0.0,
            'cout_teu': 0.0, 'co2': 0.0,
            'metadata': {
                'navires_total': 0, 'navires_quai': 0,
                'navires_mouvement': 0, 'navires_cargo': 0,
                'sources': 'N/A'
            }
        }

    at_quay = []
    at_mouillage = []
    moving = []
    cargo_vessels = []

    for v in vessels_list:
        lat, lng, spd = v.get('lat', 0), v.get('lng', 0), v.get('speed') or 0

        if is_cargo_vessel(v):
            cargo_vessels.append(v)

        if spd < 0.5:
            if point_in_polygon(lat, lng, QUAI_POLYGON):
                at_quay.append(v)
            else:
                at_mouillage.append(v)
        else:
            moving.append(v)

    wind = context.get('wind_speed_kts', 0)
    waves = context.get('wave_height_m', 0)
    is_night = context.get('is_night', False)
    eur_usd = context.get('eur_usd', 1.08)

    teu = 0
    for v in at_quay + cargo_vessels:
        length = v.get('length') or 0
        if length > 50:
            teu += (length / 20) * 180 * 0.75
    conteneurs = int(teu)

    occupation = round((len(at_quay) / 6) * 100, 1)

    meteo_penalty = 0
    if wind > 20:
        meteo_penalty += (wind - 20) * 0.2
    if waves > 2.0:
        meteo_penalty += (waves - 2.0) * 1.5
    congestion_penalty = (len(at_mouillage) * 1.5)
    retards = round(1.5 + congestion_penalty + meteo_penalty, 1)

    engorgement = max(0, (len(at_quay) - 6) * 5) if len(at_quay) > 6 else 0
    meteo_eff_penalty = 0
    if wind > 25:
        meteo_eff_penalty += 5
    if is_night:
        meteo_eff_penalty += 3
    efficacite = round(max(60.0, min(99.5, 95.0 - engorgement - meteo_eff_penalty)), 1)

    rotation = 3.2
    if len(quai_events) >= 4:
        arrivals = {e['mmsi']: e['time'] for e in quai_events if e['type'] == 'arrivee'}
        departs = {e['mmsi']: e['time'] for e in quai_events if e['type'] == 'depart'}
        rots = [
            (departs[m] - arrivals[m]).total_seconds() / 3600
            for m in arrivals
            if m in departs and (departs[m] - arrivals[m]).total_seconds() > 0
        ]
        if rots:
            rotation = round(sum(rots) / len(rots) / 24, 1)

    base_cost_usd = 150.00
    variable_cost_usd = 42.00
    cout_teu = round(((base_cost_usd + variable_cost_usd) / eur_usd), 2) if conteneurs == 0 \
        else round(((85000 / conteneurs) + variable_cost_usd) / eur_usd, 2)

    co2_kg = 0.0
    for v in vessels_list:
        spd = v.get('speed') or 0
        size = (v.get('length') or 100) / 100
        wind_factor = 1.0 + (wind * 0.01)
        co2_kg += (120 + (spd * 8.5)) * size * 3.15 * wind_factor
    co2 = round(co2_kg / 1000, 2)

    sat_pen = max(0, (retards - 2.0) * 5) + max(0, (90.0 - efficacite) * 1)
    if waves > 2.5:
        sat_pen += 3
    satisfaction = round(max(65.0, min(99.5, 98.0 - sat_pen)), 1)

    return {
        'conteneurs': conteneurs,
        'occupation': occupation,
        'efficacite': efficacite,
        'rotation': rotation,
        'retards': retards,
        'cout_teu': cout_teu,
        'co2': co2,
        'satisfaction': satisfaction,
        'metadata': {
            'navires_total': total,
            'navires_quai': len(at_quay),
            'navires_mouillage': len(at_mouillage),
            'navires_mouvement': len(moving),
            'navires_cargo': len(cargo_vessels),
            'sources': f"Vent:{wind:.1f}kts, Houle:{waves:.1f}m, Nuit:{is_night}, EUR/USD:{eur_usd:.3f}"
        }
    }

# ============================================================
# THREAD WEBSOCKET AISSTREAM
# ============================================================

def ais_websocket_thread():
    global is_connected, message_count, last_update, use_test_data

    print("🔌 Ouverture de la connexion WebSocket AISStream...")

    def on_message(ws, message):
        global message_count, last_update, use_test_data
        try:
            data = json.loads(message)
            message_count += 1

            msg_type = data.get('MessageType')

            if DEBUG_AIS and message_count <= 30:
                msg_keys = list(data.get('Message', {}).keys())
                print(f"[AIS #{message_count}] Type: {msg_type} | Keys: {msg_keys}")

            if msg_type != 'PositionReport':
                return

            meta = data.get('MetaData', {})
            pos = data.get('Message', {}).get('PositionReport', {})

            if not meta or not pos:
                return

            mmsi = str(meta.get('MMSI', ''))
            if not mmsi:
                return

            # ✅ Désactive le mode test SEULEMENT après validation du navire
            use_test_data = False

            new_speed = pos.get('Sog', pos.get('SpeedOverGround', 0)) or 0
            new_lat = pos.get('Latitude', 0) or 0
            new_lng = pos.get('Longitude', 0) or 0
            new_course = pos.get('Cog', pos.get('CourseOverGround', 0)) or 0
            new_heading = pos.get('TrueHeading', 0) or 0

            if new_lat == 0 and new_lng == 0:
                return

            ship_type = meta.get('ShipType', None)

            with vessel_lock:
                was_at_quai = mmsi in vessels and point_in_polygon(
                    vessels[mmsi].get('lat', 0),
                    vessels[mmsi].get('lng', 0),
                    QUAI_POLYGON
                )

                if mmsi not in vessel_history:
                    vessel_history[mmsi] = deque(maxlen=history_size)
                vessel_history[mmsi].append(vessels[mmsi].copy() if mmsi in vessels else {})

                vessels[mmsi] = {
                    'id': mmsi,
                    'name': (meta.get('ShipName', '') or 'Inconnu').strip(),
                    'type': determine_type(ship_type),
                    'cargo': ship_type if ship_type is not None else 0,
                    'flag': meta.get('Flag', '--'),
                    'lat': new_lat,
                    'lng': new_lng,
                    'speed': new_speed,
                    'course': new_course,
                    'timestamp': datetime.now().isoformat(),
                    'length': meta.get('Length', 0),
                    'draft': meta.get('Draft', 0),
                    'destination': meta.get('Destination', 'Inconnu'),
                    'eta': meta.get('ETA', ''),
                    'heading': new_heading,
                    'history': list(vessel_history.get(mmsi, []))[-10:]
                }

                is_at_quai = new_speed < 0.5 and point_in_polygon(new_lat, new_lng, QUAI_POLYGON)

                if was_at_quai and not is_at_quai:
                    quai_events.append({'type': 'depart', 'mmsi': mmsi, 'time': datetime.now()})
                    print(f"⚡ DÉPART QUAI : {meta.get('ShipName', mmsi)}")
                elif not was_at_quai and is_at_quai:
                    quai_events.append({'type': 'arrivee', 'mmsi': mmsi, 'time': datetime.now()})
                    print(f"📦 ARRIVÉE QUAI : {meta.get('ShipName', mmsi)}")

                last_update = datetime.now()

                try:
                    socketio.emit('vessel_update', {
                        'vessels': list(vessels.values()),
                        'stats': get_stats()
                    })
                except Exception:
                    pass

        except Exception as e:
            print(f"Erreur message: {e}")
            if DEBUG_AIS:
                traceback.print_exc()

    def on_error(ws, error):
        print(f"❌ Erreur WebSocket: {error}")

    def on_close(ws, close_status_code, close_msg):
        global is_connected
        is_connected = False
        print(f"⚠️ WebSocket fermé (code {close_status_code}, raison: {close_msg}) — reconnexion dans 10s...")
        try:
            socketio.emit('ais_status', {'connected': False})
        except Exception:
            pass
        threading.Timer(10, ais_websocket_thread).start()

    def on_open(ws):
        global is_connected
        is_connected = True
        print("✅ AISStream connecté — envoi de la souscription...")
        try:
            socketio.emit('ais_status', {'connected': True})
        except Exception:
            pass

        subscription = {
            "APIKey": AIS_API_KEY,
            "BoundingBoxes": [
                [BOUNDING_BOX[0], BOUNDING_BOX[1]]
            ],
            "FilterMessageTypes": ["PositionReport"]
        }
        ws.send(json.dumps(subscription))
        print(f"📡 BoundingBox envoyé : [[{BOUNDING_BOX[0]}, {BOUNDING_BOX[1]}]]")

    try:
        ws = websocket.WebSocketApp(
            "wss://stream.aisstream.io/v0/stream",
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        ws.run_forever()
    except Exception as e:
        print(f"❌ Erreur AISStream: {e}")
        traceback.print_exc()
        is_connected = False


def determine_type(ship_type):
    if ship_type is None:
        return 'other'
    t = str(ship_type).lower()
    if 'cargo' in t:
        return 'cargo'
    if 'tanker' in t:
        return 'tanker'
    if 'passenger' in t:
        return 'passenger'
    if 'fishing' in t:
        return 'fishing'
    if 'tug' in t:
        return 'tug'

    try:
        code = int(ship_type)
        if 70 <= code <= 79:
            return 'cargo'
        if 80 <= code <= 89:
            return 'tanker'
        if 60 <= code <= 69:
            return 'passenger'
        if 30 <= code <= 39:
            return 'fishing'
        if 50 <= code <= 59:
            return 'tug'
    except (ValueError, TypeError):
        pass

    return 'other'


def get_stats():
    with vessel_lock:
        vl = list(vessels.values())
        return {
            'total': len(vl),
            'connected': is_connected,
            'messages': message_count,
            'last_update': last_update.isoformat() if last_update else None,
            'types': list({v.get('type', 'other') for v in vl}),
            'use_test_data': use_test_data
        }

# ============================================================
# ROUTES API
# ============================================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/vessels')
def get_vessels():
    with vessel_lock:
        if len(vessels) == 0 and use_test_data:
            return jsonify(get_test_vessels())
        return jsonify(list(vessels.values()))


@app.route('/api/vessels/<vessel_id>')
def get_vessel(vessel_id):
    with vessel_lock:
        return jsonify(vessels.get(vessel_id, {}))


@app.route('/api/stats')
def get_stats_api():
    return jsonify(get_stats())


@app.route('/api/kpis')
def get_kpis():
    try:
        live_ctx = get_live_context()
        with vessel_lock:
            vl = list(vessels.values())
            if len(vl) == 0 and use_test_data:
                vl = get_test_vessels()
            return jsonify(compute_kpis(vl, live_ctx))
    except Exception as e:
        print(f"!!! ERREUR KPIs !!!\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/weather')
def get_weather():
    try:
        ctx = get_live_context()
        return jsonify({
            'hourly': {
                'wave_height': [ctx.get('wave_height_m', 1.2)],
                'wave_direction': [215],
                'wave_period': [7.5],
                'swell_wave_height': [ctx.get('swell_m', 0.9)]
            }
        })
    except Exception:
        pass
    return jsonify({
        'hourly': {
            'wave_height': [1.2],
            'wave_direction': [215],
            'wave_period': [7.5],
            'swell_wave_height': [0.9]
        }
    })


@app.route('/api/predictions')
def get_predictions():
    with vessel_lock:
        vl = list(vessels.values())
        if len(vl) == 0:
            vl = get_test_vessels()
        if len(vl) < 3:
            return jsonify({'error': 'Données insuffisantes'}), 200
        traffic = len(vl)
        preds = [
            {
                'day': i + 1,
                'prediction': max(0, traffic * (1 + (i * 0.02))),
                'confidence': max(0.55, 0.88 - (i * 0.02))
            }
            for i in range(7)
        ]
        trend = ((preds[-1]['prediction'] - preds[0]['prediction']) / preds[0]['prediction'] * 100) \
            if preds[0]['prediction'] > 0 else 0
        return jsonify({
            'predictions': preds,
            'trend': trend,
            'peak': max(p['prediction'] for p in preds),
            'avg_confidence': sum(p['confidence'] for p in preds) / len(preds)
        })


@app.route('/api/debug/ais')
def debug_ais():
    """Endpoint de diagnostic : état du flux AIS."""
    return jsonify({
        'connected': is_connected,
        'messages_received': message_count,
        'vessels_count': len(vessels),
        'use_test_data': use_test_data,
        'last_update': last_update.isoformat() if last_update else None,
        'bounding_box': BOUNDING_BOX,
        'sample_vessel': next(iter(vessels.values()), None)
    })


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("S-Wing Reunion PRO - Serveur")
    print("Géofencing actif sur le périmètre des quais")
    print("=" * 60)
    print(f"Web: http://localhost:{PORT}")
    print(f"API Key AISStream chargée : {'oui' if AIS_API_KEY else 'NON'}")
    print(f"Debug AIS : {'activé' if DEBUG_AIS else 'désactivé'}")
    print(f"BoundingBox : {BOUNDING_BOX}")
    print("=" * 60)

    # ✅ ÉTAPE 1 : Lancement du WebSocket AIS EN PREMIER (non bloquant)
    print("Démarrage du thread AISStream...")
    threading.Thread(target=ais_websocket_thread, daemon=True).start()

    # ✅ ÉTAPE 2 : Contexte météo chargé en arrière-plan (non bloquant)
    def load_context_bg():
        try:
            get_live_context()
            print("✅ Contexte météo initialisé.")
        except Exception as e:
            print(f"⚠️ Contexte météo indisponible : {e}")

    threading.Thread(target=load_context_bg, daemon=True).start()

    os.makedirs('docs', exist_ok=True)
    os.makedirs('static', exist_ok=True)

    try:
        socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\nArret du serveur...")
