#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
S-Wing Réunion PRO - Serveur Flask
Port: 5001
AISStream + API REST + KPIs Enrichis par données Temps Réel (APIs gratuites)
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
quai_events = deque(maxlen=100)

# Cache pour les API externes (éviter de les spammer)
external_data_cache = {'data': {}, 'last_fetch': 0}

# ============================================================
# DONNÉES DE TEST STABLES
# ============================================================

BASE_VESSELS = [
    {'id': '228339000', 'name': 'MSC Isabella', 'type': 'import', 'cargo': 'Cargo', 'flag': 'FR', 'lat': -21.08, 'lng': 55.52, 'speed': 8.5, 'course': 315, 'length': 366, 'draft': 12.5, 'destination': 'Port de La Reunion'},
    {'id': '228339001', 'name': 'CMA CGM La Reunion', 'type': 'export', 'cargo': 'Cargo', 'flag': 'PA', 'lat': -21.15, 'lng': 55.56, 'speed': 12.3, 'course': 45, 'length': 399, 'draft': 14.2, 'destination': 'Marseille'},
    {'id': '228339002', 'name': 'MAERSK Cardiff', 'type': 'transit', 'cargo': 'Cargo', 'flag': 'SG', 'lat': -21.10, 'lng': 55.48, 'speed': 6.2, 'course': 180, 'length': 350, 'draft': 11.8, 'destination': 'Singapour'},
    {'id': '228339003', 'name': 'EVER Glory', 'type': 'import', 'cargo': 'Cargo', 'flag': 'CN', 'lat': -21.18, 'lng': 55.60, 'speed': 0.2, 'course': 90, 'length': 400, 'draft': 15.0, 'destination': 'Port de La Reunion'},
    {'id': '228339004', 'name': 'HMM Rotterdam', 'type': 'export', 'cargo': 'Tanker', 'flag': 'UK', 'lat': -21.05, 'lng': 55.50, 'speed': 14.7, 'course': 270, 'length': 330, 'draft': 13.5, 'destination': 'Rotterdam'},
]

def get_test_vessels():
    global simulation_step
    simulation_step += 1
    out = []
    for b in BASE_VESSELS:
        v = b.copy()
        if simulation_step % 30 == 0:
            if v['type'] == 'import': v['lat'] += 0.0003; v['lng'] += 0.0002
            elif v['type'] == 'export': v['lat'] -= 0.0003; v['lng'] -= 0.0002
            v['speed'] = max(0, min(20, v['speed'] + random.uniform(-0.3, 0.3)))
            v['course'] = (v['course'] + random.uniform(-1, 1)) % 360
        v['timestamp'] = datetime.now().isoformat()
        out.append(v)
    return out

# ============================================================
# APPELS API EXTERNES GRATUITES (Sans clé)
# ============================================================

def get_live_context():
    """
    Récupère les conditions physiques et économiques en temps réel
    pour influencer dynamiquement les KPIs du port.
    """
    global external_data_cache

    # Ne pas appeler les API plus d'une fois toutes les 10 minutes
    if time.time() - external_data_cache['last_fetch'] < 600 and external_data_cache['data']:
        return external_data_cache['data']

    context = {
        'wind_speed_kts': 0, 'wave_height_m': 0, 'swell_m': 0,
        'is_night': False, 'eur_usd': 1.08 # Fallback réaliste
    }

    # 1. MÉTÉO AVANCÉE (Open-Meteo) - Vent + Houle
    try:
        r = requests.get("https://api.open-meteo.com/v1/marine", params={
            'latitude': -21.115, 'longitude': 55.536,
            'current': 'wind_speed_10m,wave_height,swell_wave_height',
            'timezone': 'Indian/Reunion'
        }, timeout=5)
        if r.status_code == 200:
            c = r.json().get('current', {})
            # Conversion m/s en noeuds (x 1.943)
            context['wind_speed_kts'] = (c.get('wind_speed_10m', 0) or 0) * 1.943
            context['wave_height_m'] = c.get('wave_height', 0) or 0
            context['swell_m'] = c.get('swell_wave_height', 0) or 0
    except Exception as e:
        print(f"Erreur API Meteo avancée: {e}")

    # 2. JOUR / NUIT (Sunrise-Sunset API)
    try:
        r = requests.get("https://api.sunrise-sunset.org/json", params={
            'lat': -21.115, 'lng': 55.536, 'formatted': 0
        }, timeout=5)
        if r.status_code == 200:
            results = r.json().get('results', {})
            now = datetime.utcnow()
            sunrise = datetime.fromisoformat(results.get('sunrise', '').replace('Z', '+00:00')).replace(tzinfo=None)
            sunset = datetime.fromisoformat(results.get('sunset', '').replace('Z', '+00:00')).replace(tzinfo=None)
            # Conversion approximative heure Réunion (UTC+4)
            reunion_now = now.hour + 4
            sunrise_h = sunrise.hour + 4
            sunset_h = sunset.hour + 4
            context['is_night'] = not (sunrise_h <= reunion_now <= sunset_h)
    except Exception as e:
        print(f"Erreur API Jour/Nuit: {e}")

    # 3. TAUX DE CHANGE EUR/USD (Frankfurter API - 100% gratuit)
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=EUR&to=USD", timeout=5)
        if r.status_code == 200:
            context['eur_usd'] = r.json().get('rates', {}).get('USD', 1.08)
    except Exception as e:
        print(f"Erreur API Change: {e}")

    external_data_cache['data'] = context
    external_data_cache['last_fetch'] = time.time()
    return context

# ============================================================
# MODULE KPIs ENRICHI PAR LES DONNÉES TEMPS RÉEL
# ============================================================

def compute_kpis(vessels_list, context):
    total = len(vessels_list)
    if total == 0:
        return {'conteneurs': 0, 'occupation': 0.0, 'satisfaction': 0.0, 'retards': 0.0, 'efficacite': 0.0, 'rotation': 0.0, 'cout_teu': 0.0, 'co2': 0.0, 'metadata': {'navires_total': 0, 'navires_quai': 0, 'navires_mouvement': 0, 'navires_cargo': 0, 'sources': 'N/A'}}

    at_quay = [v for v in vessels_list if (v.get('speed') or 0) < 0.5]
    moving = [v for v in vessels_list if (v.get('speed') or 0) >= 0.5]
    cargo_vessels = [v for v in vessels_list if str(v.get('cargo', '')).lower() in ['cargo', 'conteneurs']]

    # Extraction du contexte temps réel
    wind = context.get('wind_speed_kts', 0)
    waves = context.get('wave_height_m', 0)
    is_night = context.get('is_night', False)
    eur_usd = context.get('eur_usd', 1.08)

    # --- 1. CONTENEURS (Basé sur la physique des navires présents) ---
    teu = 0
    for v in at_quay + cargo_vessels:
        length = v.get('length') or 0
        if length > 50:
            teu += (length / 20) * 180 * 0.75
    conteneurs = int(teu)

    # --- 2. OCCUPATION QUAIS (AIS pur) ---
    occupation = round((len(at_quay) / 6) * 100, 1)

    # --- 3. RETARDS (Influencé par le vent, la houle et la congestion) ---
    # Si vent > 20 kts ou houle > 2m, les opérations de manutention ralentissent
    meteo_penalty = 0
    if wind > 20: meteo_penalty += (wind - 20) * 0.2 # +0.2h de retard par noeud au-dessus de 20
    if waves > 2.0: meteo_penalty += (waves - 2.0) * 1.5 # +1.5h par mètre au-dessus de 2m

    congestion_ratio = len([v for v in moving if 0.5 <= (v.get('speed') or 0) < 3.0]) / total
    retards = round(1.5 + (congestion_ratio * 8.0) + meteo_penalty, 1)

    # --- 4. EFFICACITÉ (Influencée par la météo et le jour/nuit) ---
    engorgement = max(0, (len(at_quay) - 6) * 5) if len(at_quay) > 6 else 0
    meteo_eff_penalty = 0
    if wind > 25: meteo_eff_penalty += 5 # Chute d'efficacité si vent fort
    if is_night: meteo_eff_penalty += 3 # Ops nocturnes plus lentes

    efficacite = round(max(60.0, min(99.5, 95.0 - engorgement - meteo_eff_penalty)), 1)

    # --- 5. ROTATION ---
    rotation = 3.2
    if len(quai_events) >= 4:
        arrivals = {e['mmsi']: e['time'] for e in quai_events if e['type'] == 'arrivee'}
        departs = {e['mmsi']: e['time'] for e in quai_events if e['type'] == 'depart'}
        rots = [(departs[m] - arrivals[m]).total_seconds() / 3600 for m in arrivals if m in departs and (departs[m] - arrivals[m]).total_seconds() > 0]
        if rots: rotation = round(sum(rots) / len(rots) / 24, 1)

    # --- 6. COÛT / TEU (Influencé par le taux de change EUR/USD en temps réel) ---
    # Le coût de base est estimé en USD, converti en EUR avec le taux live
    base_cost_usd = 150.00
    variable_cost_usd = 42.00
    cout_teu = round(((base_cost_usd + variable_cost_usd) / eur_usd), 2) if conteneurs == 0 else round(((85000 / conteneurs) + variable_cost_usd) / eur_usd, 2)

    # --- 7. CO2 (Basé sur la physique : taille + vitesse + vent de face) ---
    co2_kg = 0.0
    for v in vessels_list:
        spd = v.get('speed') or 0
        size = (v.get('length') or 100) / 100
        # Si le navire fait face au vent, il consomme plus
        wind_factor = 1.0 + (wind * 0.01)
        co2_kg += (120 + (spd * 8.5)) * size * 3.15 * wind_factor
    co2 = round(co2_kg / 1000, 2)

    # --- 8. SATISFACTION (Dérivée des retards, de l'efficacité et de la météo) ---
    sat_pen = max(0, (retards - 2.0) * 5) + max(0, (90.0 - efficacite) * 1)
    if waves > 2.5: sat_pen += 3 # Météo défavorable frustre les clients
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
            'navires_cargo': len(cargo_vessels),
            'sources': f"Vent:{wind:.1f}kts, Houle:{waves:.1f}m, Nuit:{is_night}, EUR/USD:{eur_usd:.3f}"
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
                        if mmsi not in vessel_history: vessel_history[mmsi] = deque(maxlen=history_size)
                        vessel_history[mmsi].append(vessels[mmsi].copy() if mmsi in vessels else {})
                        new_speed = pos.get('SpeedOverGround', 0)
                        vessels[mmsi] = {
                            'id': mmsi, 'name': meta.get('ShipName', 'Inconnu'),
                            'type': determine_type(meta.get('ShipType', 'Cargo')),
                            'cargo': meta.get('ShipType', 'Cargo'), 'flag': meta.get('Flag', '--'),
                            'lat': pos.get('Latitude', 0), 'lng': pos.get('Longitude', 0),
                            'speed': new_speed, 'course': pos.get('CourseOverGround', 0),
                            'timestamp': datetime.now().isoformat(),
                            'length': meta.get('Length', 0), 'draft': meta.get('Draft', 0),
                            'destination': meta.get('Destination', 'Inconnu'),
                            'eta': meta.get('ETA', ''), 'heading': pos.get('TrueHeading', 0),
                            'history': list(vessel_history.get(mmsi, []))[-10:]
                        }
                        is_at_quay = new_speed < 0.5
                        if was_at_quay and not is_at_quay: quai_events.append({'type': 'depart', 'mmsi': mmsi, 'time': datetime.now()})
                        elif not was_at_quay and is_at_quay: quai_events.append({'type': 'arrivee', 'mmsi': mmsi, 'time': datetime.now()})
                        last_update = datetime.now()
                        socketio.emit('vessel_update', {'vessels': list(vessels.values()), 'stats': get_stats()})
        except Exception as e: print(f"Erreur message: {e}")

    def on_error(ws, error): print(f"Erreur WebSocket: {error}")
    def on_close(ws, close_status_code, close_msg):
        global is_connected
        is_connected = False
        print("WebSocket fermé, reconnexion dans 10s...")
        try: socketio.emit('ais_status', {'connected': False})
        except: pass
        threading.Timer(10, ais_websocket_thread).start()

    def on_open(ws):
        global is_connected
        is_connected = True
        print("AISStream connecté")
        try: socketio.emit('ais_status', {'connected': True})
        except: pass
        ws.send(json.dumps({"APIKey": AIS_API_KEY, "BoundingBoxes": [BOUNDING_BOX]}))

    try:
        ws = websocket.WebSocketApp("wss://stream.aisstream.io/v0/stream", on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
        ws.run_forever()
    except Exception as e:
        print(f"Erreur AISStream: {e}")
        is_connected = False

def determine_type(ship_type):
    t = str(ship_type).lower()
    if 'cargo' in t: return 'cargo'
    if 'tanker' in t: return 'tanker'
    if 'passenger' in t: return 'passenger'
    if 'fishing' in t: return 'fishing'
    if 'tug' in t: return 'tug'
    return 'other'

def get_stats():
    with vessel_lock:
        vl = list(vessels.values())
        return {'total': len(vl), 'connected': is_connected, 'messages': message_count, 'last_update': last_update.isoformat() if last_update else None, 'types': list({v.get('type', 'other') for v in vl})}

# ============================================================
# ROUTES API
# ============================================================

@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/vessels')
def get_vessels():
    with vessel_lock:
        if len(vessels) == 0 and use_test_data: return jsonify(get_test_vessels())
        return jsonify(list(vessels.values()))

@app.route('/api/vessels/<vessel_id>')
def get_vessel(vessel_id):
    with vessel_lock: return jsonify(vessels.get(vessel_id, {}))

@app.route('/api/stats')
def get_stats_api(): return jsonify(get_stats())

@app.route('/api/kpis')
def get_kpis():
    try:
        # 1. Récupérer le contexte temps réel (Météo, Change, Jour/Nuit)
        live_ctx = get_live_context()

        # 2. Récupérer les navires
        with vessel_lock:
            vl = list(vessels.values())
            if len(vl) == 0 and use_test_data:
                vl = get_test_vessels()

        # 3. Calculer les KPIs en injectant le contexte live
        return jsonify(compute_kpis(vl, live_ctx))
    except Exception as e:
        print(f"!!! ERREUR KPIs !!!\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/weather')
def get_weather():
    try:
        # On retourne le cache de la météo qu'on a déjà récupéré pour les KPIs
        ctx = get_live_context()
        h = ctx.get('wave_height_m', 1.2)
        p = 7.5 # Période par défaut
        d = 215
        s = ctx.get('swell_m', 0.9)
        return jsonify({'hourly': {'wave_height': [h], 'wave_direction': [d], 'wave_period': [p], 'swell_wave_height': [s]}})
    except: pass
    return jsonify({'hourly': {'wave_height': [1.2], 'wave_direction': [215], 'wave_period': [7.5], 'swell_wave_height': [0.9]}})

@app.route('/api/predictions')
def get_predictions():
    with vessel_lock:
        vl = list(vessels.values())
        if len(vl) == 0: vl = get_test_vessels()
        if len(vl) < 3: return jsonify({'error': 'Données insuffisantes'}), 200
        traffic = len(vl)
        preds = [{'day': i+1, 'prediction': max(0, traffic * (1 + (i * 0.02))), 'confidence': max(0.55, 0.88 - (i * 0.02))} for i in range(7)]
        trend = ((preds[-1]['prediction'] - preds[0]['prediction']) / preds[0]['prediction'] * 100) if preds[0]['prediction'] > 0 else 0
        return jsonify({'predictions': preds, 'trend': trend, 'peak': max(p['prediction'] for p in preds), 'avg_confidence': sum(p['confidence'] for p in preds) / len(preds)})

@app.route('/static/<path:filename>')
def static_files(filename): return send_from_directory('static', filename)

# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("S-Wing Reunion PRO - Serveur")
    print("Enrichissement KPIs : Meteo + Change EUR/USD + Jour/Nuit")
    print("=" * 60)
    print(f"Web: http://localhost:{PORT}")
    print("=" * 60)

    # Pré-charger la météo au démarrage
    print("Récupération des conditions temps réel (APIs gratuites)...")
    get_live_context()
    print("Contexte initialisé.")

    threading.Thread(target=ais_websocket_thread, daemon=True).start()
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)

    try:
        socketio.run(app, host='0.0.0.0', port=PORT, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\nArret du serveur...")
