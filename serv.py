#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
S-Wing Réunion PRO - Serveur Flask
Port: 5001
AISStream + API REST + WebSocket + KPIs Calculés
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
from collections import deque
import random

# ============================================================
# CONFIGURATION
# ============================================================

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = 'swing-reunion-pro-2024'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

PORT = 5001
AIS_API_KEY = os.getenv('AIS_API_KEY', '6542112575fd3e48c752ae4bfbc7d5d56b5aba3c')
BOUNDING_BOX = [[-21.5, 54.5], [-20.5, 56.5]]

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

# Accumulateurs temps réel pour KPIs
quai_events = deque(maxlen=100)

# ============================================================
# DONNÉES DE TEST STABLES
# ============================================================

BASE_VESSELS = [
    {'id': '228339000', 'name': 'MSC Isabella', 'type': 'import', 'cargo': 7, 'flag': 'FR', 'lat': -21.08, 'lng': 55.52, 'speed': 8.5, 'course': 315, 'heading': 315, 'length': 366, 'draft': 12.5, 'destination': 'Port de La Reunion', 'eta': '2026-06-30 14:00'},
    {'id': '228339001', 'name': 'CMA CGM La Reunion', 'type': 'export', 'cargo': 7, 'flag': 'PA', 'lat': -21.15, 'lng': 55.56, 'speed': 12.3, 'course': 45, 'heading': 45, 'length': 399, 'draft': 14.2, 'destination': 'Marseille', 'eta': '2026-07-01 08:00'},
    {'id': '228339002', 'name': 'MAERSK Cardiff', 'type': 'transit', 'cargo': 7, 'flag': 'SG', 'lat': -21.10, 'lng': 55.48, 'speed': 6.2, 'course': 180, 'heading': 180, 'length': 350, 'draft': 11.8, 'destination': 'Singapour', 'eta': '2026-07-05 22:00'},
    {'id': '228339003', 'name': 'EVER Glory', 'type': 'import', 'cargo': 7, 'flag': 'CN', 'lat': -21.18, 'lng': 55.60, 'speed': 0.2, 'course': 90, 'heading': 90, 'length': 400, 'draft': 15.0, 'destination': 'Port de La Reunion', 'eta': '2026-06-29 18:00'},
    {'id': '228339004', 'name': 'HMM Rotterdam', 'type': 'export', 'cargo': 10, 'flag': 'UK', 'lat': -21.05, 'lng': 55.50, 'speed': 14.7, 'course': 270, 'heading': 270, 'length': 330, 'draft': 13.5, 'destination': 'Rotterdam', 'eta': '2026-07-03 12:00'},
    {'id': '228339005', 'name': 'COSCO Shipping', 'type': 'import', 'cargo': 7, 'flag': 'CN', 'lat': -21.12, 'lng': 55.54, 'speed': 0.1, 'course': 45, 'heading': 45, 'length': 400, 'draft': 14.8, 'destination': 'Port de La Reunion', 'eta': '2026-06-29 20:00'},
    {'id': '228339006', 'name': 'MSC World Europa', 'type': 'transit', 'cargo': 4, 'flag': 'PA', 'lat': -21.08, 'lng': 55.62, 'speed': 18.5, 'course': 90, 'heading': 90, 'length': 333, 'draft': 9.5, 'destination': 'Dubai', 'eta': '2026-07-08 06:00'},
    {'id': '228339007', 'name': 'Stena Bulk', 'type': 'export', 'cargo': 10, 'flag': 'SE', 'lat': -21.20, 'lng': 55.45, 'speed': 11.2, 'course': 135, 'heading': 135, 'length': 228, 'draft': 12.0, 'destination': 'Stockholm', 'eta': '2026-07-12 15:00'},
    {'id': '228339008', 'name': 'MOL Triumph', 'type': 'import', 'cargo': 7, 'flag': 'JP', 'lat': -21.16, 'lng': 55.58, 'speed': 0.3, 'course': 270, 'heading': 270, 'length': 400, 'draft': 16.0, 'destination': 'Port de La Reunion', 'eta': '2026-06-30 02:00'},
    {'id': '228339009', 'name': 'ONE Trust', 'type': 'transit', 'cargo': 7, 'flag': 'SG', 'lat': -21.02, 'lng': 55.42, 'speed': 9.8, 'course': 315, 'heading': 315, 'length': 366, 'draft': 13.2, 'destination': 'Colombo', 'eta': '2026-07-06 18:00'},
]

def get_test_vessels():
    """Retourne des données de test stables"""
    global simulation_step
    simulation_step += 1
    out = []
    for b in BASE_VESSELS:
        v = b.copy()
        if simulation_step % 30 == 0:
            if v['type'] == 'import':
                v['lat'] += random.uniform(-0.0005, 0.0005)
                v['lng'] += random.uniform(-0.0005, 0.0005)
            elif v['type'] == 'export':
                v['lat'] += random.uniform(-0.0005, 0.0005)
                v['lng'] += random.uniform(-0.0005, 0.0005)
            v['speed'] = max(0, min(25, v['speed'] + random.uniform(-0.5, 0.5)))
            v['course'] = (v['course'] + random.uniform(-2, 2)) % 360
            v['heading'] = v['course']
        v['timestamp'] = datetime.now().isoformat()
        out.append(v)
    return out

# ============================================================
# MODULE KPIs (Simplifié et robuste)
# ============================================================

def compute_kpis(vessels_list):
    total = len(vessels_list)
    if total == 0:
        return {'conteneurs': 0, 'occupation': 0.0, 'satisfaction': 0.0, 'retards': 0.0, 'efficacite': 0.0, 'rotation': 0.0, 'cout_teu': 0.0, 'co2': 0.0, 'metadata': {'navires_total': 0, 'navires_quai': 0, 'navires_mouvement': 0, 'navires_cargo': 0}}

    at_quay = [v for v in vessels_list if (v.get('speed') or 0) < 0.5]
    moving = [v for v in vessels_list if (v.get('speed') or 0) >= 0.5]

    # Détection des navires cargos (gestion des types numériques et textuels)
    cargo_vessels = []
    for v in vessels_list:
        cargo = v.get('cargo', '')
        if isinstance(cargo, (int, float)):
            cargo_val = int(cargo)
            if cargo_val in [7, 8, 9, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79]:
                cargo_vessels.append(v)
        elif isinstance(cargo, str):
            if cargo.lower() in ['cargo', 'conteneurs', '7', '8', '9']:
                cargo_vessels.append(v)

    # 1. Conteneurs estimés
    teu = 0
    for v in at_quay + cargo_vessels:
        length = v.get('length') or 0
        if length > 50:
            teu += (length / 20) * 180 * 0.75
    conteneurs = int(teu)

    # 2. Occupation quais
    occupation = round((len(at_quay) / 6) * 100, 1)

    # 3. Efficacité
    engorgement = max(0, (len(at_quay) - 6) * 5) if len(at_quay) > 6 else 0
    efficacite = round(max(60.0, min(99.5, 95.0 - engorgement)), 1)

    # 4. Rotation (basée sur les événements ou valeur par défaut)
    rotation = 3.2
    if len(quai_events) >= 4:
        # Estimation basique de rotation
        rotation = round(2.5 + random.uniform(-0.5, 0.5), 1)

    # 5. Retards
    slow = [v for v in moving if 0.5 <= (v.get('speed') or 0) < 3.0]
    retards = round(1.5 + (len(slow) / max(1, total)) * 8.0, 1)

    # 6. Coût/TEU
    cout_teu = round((85000 + (conteneurs * 42)) / max(1, conteneurs), 2) if conteneurs > 0 else 0.0

    # 7. CO2
    co2_kg = 0.0
    for v in vessels_list:
        spd = v.get('speed') or 0
        size = (v.get('length') or 100) / 100
        co2_kg += (120 + (spd * 8.5)) * size * 3.15
    co2 = round(co2_kg / 1000, 2)

    # 8. Satisfaction
    sat_pen = max(0, (retards - 2.0) * 5) + max(0, (90.0 - efficacite) * 1)
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
            'navires_mouvement': len(moving),
            'navires_cargo': len(cargo_vessels)
        }
    }

# ============================================================
# THREAD WEBSOCKET AISSTREAM
# ============================================================

def ais_websocket_thread():
    global is_connected, message_count, last_update, use_test_data

    def on_message(ws, message):
        global message_count, last_update, use_test_data
        try:
            data = json.loads(message)
            message_count += 1
            use_test_data = False
            if data.get('MessageType') == 'PositionReport':
                meta = data.get('MetaData', {})
                pos = data.get('Message', {}).get('Position', {})
                if meta and pos:
                    mmsi = str(meta.get('MMSI', ''))
                    with vessel_lock:
                        was_at_quay = mmsi in vessels and (vessels[mmsi].get('speed') or 0) < 0.5
                        if mmsi not in vessel_history:
                            vessel_history[mmsi] = deque(maxlen=history_size)
                        vessel_history[mmsi].append(vessels[mmsi].copy() if mmsi in vessels else {})

                        new_speed = pos.get('SpeedOverGround', 0)
                        vessels[mmsi] = {
                            'id': mmsi,
                            'name': meta.get('ShipName', 'Inconnu'),
                            'type': determine_type(meta.get('ShipType', 'Cargo')),
                            'cargo': meta.get('ShipType', 'Cargo'),
                            'flag': meta.get('Flag', '--'),
                            'lat': pos.get('Latitude', 0),
                            'lng': pos.get('Longitude', 0),
                            'speed': new_speed,
                            'course': pos.get('CourseOverGround', 0),
                            'timestamp': datetime.now().isoformat(),
                            'length': meta.get('Length', 0),
                            'draft': meta.get('Draft', 0),
                            'destination': meta.get('Destination', 'Inconnu'),
                            'eta': meta.get('ETA', ''),
                            'heading': pos.get('TrueHeading', 0),
                            'history': list(vessel_history.get(mmsi, []))[-10:]
                        }
                        is_at_quay = new_speed < 0.5
                        if was_at_quay and not is_at_quay:
                            quai_events.append({'type': 'depart', 'mmsi': mmsi, 'time': datetime.now()})
                        elif not was_at_quay and is_at_quay:
                            quai_events.append({'type': 'arrivee', 'mmsi': mmsi, 'time': datetime.now()})
                        last_update = datetime.now()
                        socketio.emit('vessel_update', {'vessels': list(vessels.values()), 'stats': get_stats()})
        except Exception as e:
            print(f"Erreur message: {e}")

    def on_error(ws, error):
        print(f"Erreur WebSocket: {error}")

    def on_close(ws, close_status_code, close_msg):
        global is_connected
        is_connected = False
        print("WebSocket fermé, reconnexion dans 10s...")
        try:
            socketio.emit('ais_status', {'connected': False})
        except:
            pass
        threading.Timer(10, ais_websocket_thread).start()

    def on_open(ws):
        global is_connected
        is_connected = True
        print("✅ AISStream connecté")
        try:
            socketio.emit('ais_status', {'connected': True})
        except:
            pass
        ws.send(json.dumps({"APIKey": AIS_API_KEY, "BoundingBoxes": [BOUNDING_BOX]}))

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
        print(f"Erreur AISStream: {e}")
        is_connected = False

def determine_type(ship_type):
    t = str(ship_type).lower()
    if 'cargo' in t:
        return 'cargo'
    if 'tanker' in t:
        return 'tanker'
    if 'passenger' in t or 'passagers' in t:
        return 'passenger'
    if 'fishing' in t or 'peche' in t:
        return 'fishing'
    if 'tug' in t or 'remorqueur' in t:
        return 'tug'
    if 'military' in t or 'militaire' in t:
        return 'military'
    return 'other'

def get_stats():
    with vessel_lock:
        vl = list(vessels.values())
        return {
            'total': len(vl),
            'connected': is_connected,
            'messages': message_count,
            'last_update': last_update.isoformat() if last_update else None,
            'types': list({v.get('type', 'other') for v in vl})
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
        with vessel_lock:
            vl = list(vessels.values())
            if len(vl) == 0 and use_test_data:
                vl = get_test_vessels()
            return jsonify(compute_kpis(vl))
    except Exception as e:
        print(f"!!! ERREUR KPIs !!!\n{traceback.format_exc()}")
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/weather')
def get_weather():
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/marine",
            params={
                'latitude': -20.9386,
                'longitude': 55.2834,
                'hourly': 'wave_height,wave_direction,wave_period,swell_wave_height',
                'timezone': 'Indian/Reunion'
            },
            timeout=10
        )
        if r.status_code == 200:
            return jsonify(r.json())
    except:
        pass
    # Données de fallback
    return jsonify({
        'hourly': {
            'wave_height': [1.2, 1.3, 1.1, 1.4, 1.2, 1.5, 1.3],
            'wave_direction': [215, 220, 210, 225, 215, 230, 218],
            'wave_period': [7.5, 7.8, 7.2, 8.0, 7.5, 8.2, 7.6],
            'swell_wave_height': [0.9, 1.0, 0.8, 1.1, 0.9, 1.2, 1.0]
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
        preds = []
        for i in range(7):
            pred = traffic * (1 + (i * 0.02))
            confidence = 0.88 - (i * 0.02)
            preds.append({
                'day': i + 1,
                'prediction': max(0, pred),
                'confidence': max(0.55, confidence)
            })
        trend = ((preds[-1]['prediction'] - preds[0]['prediction']) / max(1, preds[0]['prediction']) * 100)
        return jsonify({
            'predictions': preds,
            'trend': trend,
            'peak': max(p['prediction'] for p in preds),
            'avg_confidence': sum(p['confidence'] for p in preds) / len(preds)
        })

@app.route('/api/status')
def get_status():
    return jsonify({
        'status': 'running',
        'connected': is_connected,
        'vessels': len(vessels),
        'messages': message_count,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚢 S-Wing Réunion PRO - Serveur")
    print("=" * 60)
    print(f"🌐 http://localhost:{PORT}")
    print("=" * 60)
    print("📡 Connexion AISStream...")

    threading.Thread(target=ais_websocket_thread, daemon=True).start()
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)

    try:
        socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du serveur...")
    except Exception as e:
        print(f"❌ Erreur: {e}")
