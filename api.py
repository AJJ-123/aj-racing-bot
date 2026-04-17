"""
AJ Racing IQ — Cloud Sync API
Runs alongside the morning bot on Railway.
Stores all app data so nothing is lost if you clear your browser.
"""

import os, json, logging
from flask import Flask, request, jsonify
from flask_cors import CORS

log = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)  # Allow the HTML app to connect from any browser

# Simple file-based storage on Railway's persistent disk
# Railway gives each service a /data volume
DATA_DIR = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/tmp/aj_data')
os.makedirs(DATA_DIR, exist_ok=True)

API_TOKEN = os.environ.get('API_TOKEN', 'aj_racing_secret')

def check_auth():
    token = (request.headers.get('X-Token') or 
             request.headers.get('x-rp-token') or 
             request.args.get('token'))
    return token == API_TOKEN

def data_path(key):
    # Sanitise key for filesystem
    safe = key.replace('/', '_').replace(':', '_').replace('\\', '_')
    return os.path.join(DATA_DIR, f"{safe}.json")

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'ok': True, 'service': 'AJ Racing IQ API'})

@app.route('/data/<path:key>', methods=['GET'])
def get_data(key):
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    path = data_path(key)
    if not os.path.exists(path):
        return jsonify({'value': None}), 200
    try:
        with open(path, 'r') as f:
            value = json.load(f)
        return jsonify({'value': value}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/data/<path:key>', methods=['POST', 'PUT'])
def set_data(key):
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        body = request.get_json(force=True)
        value = body.get('value') if isinstance(body, dict) else body
        with open(data_path(key), 'w') as f:
            json.dump(value, f)
        return jsonify({'ok': True, 'key': key}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/data/<path:key>', methods=['DELETE'])
def del_data(key):
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    path = data_path(key)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'ok': True}), 200

@app.route('/keys', methods=['GET'])
def list_keys():
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    keys = [f.replace('.json', '').replace('_', ':') 
            for f in os.listdir(DATA_DIR) if f.endswith('.json')]
    return jsonify({'keys': keys}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    log.info(f"Starting API on port {port}")
    app.run(host='0.0.0.0', port=port)
