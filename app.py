import os, json, re, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict

import bcrypt
import jwt
from flask import Flask, jsonify, request, send_file

LOG = lambda msg: print(f'[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}', flush=True)

app = Flask(__name__)

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://scaevckmodsmfmtudlgb.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNjYWV2Y2ttb2RzbWZtdHVkbGdiIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTYyODgzMCwiZXhwIjoyMDk3MjA0ODMwfQ.fX4iFhkgd2K8uVU2Y04Qe3sjwjxWRB5n0TFrG-AV9Oc')

JWT_SECRET_FILE = os.path.join(os.path.dirname(__file__), '.jwt_secret')
JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    if os.path.exists(JWT_SECRET_FILE):
        JWT_SECRET = open(JWT_SECRET_FILE).read().strip()
    else:
        JWT_SECRET = os.urandom(64).hex()
        with open(JWT_SECRET_FILE, 'w') as f:
            f.write(JWT_SECRET)
JWT_EXPIRATION  = timedelta(hours=8)
BCRYPT_ROUNDS   = 12
DEFAULT_PASSWORD = 'Estech@1904'

_login_attempts = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MIN  = 15


# ── Supabase REST API helper ──
def _sb(method, table, filters=None, data=None):
    url = f'{SUPABASE_URL}/rest/v1/{table}'
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'Accept': 'application/json',
    }
    if filters:
        # URL-encode filter values to handle special characters
        encoded = []
        for f in filters:
            if '=eq.' in f or '=neq.' in f:
                parts = f.split('=', 1)
                encoded.append(parts[0] + '=' + urllib.parse.quote(parts[1], safe=''))
            else:
                encoded.append(urllib.parse.quote(f, safe='=&'))
        url += '?' + '&'.join(encoded)
    if data is not None:
        body = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
        headers['Prefer'] = 'return=representation'
    else:
        body = None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode()
        return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        err_text = e.read().decode()[:200]
        raise RuntimeError(f'Supabase {method} /{table}: {e.code} {err_text}')

def sb_select(table, filters=None):
    return _sb('GET', table, filters)

def sb_select_one(table, filters):
    rows = _sb('GET', table, filters)
    return rows[0] if rows else None

def sb_insert(table, data):
    return _sb('POST', table, data=data)

def sb_update(table, id_col, id_val, data):
    return _sb('PATCH', table, filters=[f'{id_col}=eq.{id_val}'], data=data)

def sb_delete(table, id_col, id_val):
    return _sb('DELETE', table, filters=[f'{id_col}=eq.{id_val}'])

def sb_delete_all(table):
    return _sb('DELETE', table, filters=['id=gte.0'])

def sb_count(table):
    rows = _sb('GET', table)
    return len(rows) if rows else 0


# ── Helpers ──
HTML_PATH = os.path.join(os.path.dirname(__file__), 'Vers\u00e3o Final.html')

def err(msg, code=400):
    return jsonify({'error': msg}), code

def valid_password(pw):
    if len(pw) < 8: return False
    if not re.search(r'[A-Z]', pw): return False
    if not re.search(r'[a-z]', pw): return False
    if not re.search(r'[0-9]', pw): return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\'\/]', pw): return False
    return True

def create_token(user_id, role):
    return jwt.encode({
        'sub': str(user_id), 'role': role,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + JWT_EXPIRATION
    }, JWT_SECRET, algorithm='HS256')

def verify_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except:
        return None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return err('Token ausente ou inv\u00e1lido', 401)
        payload = verify_token(auth[7:])
        if not payload:
            return err('Token expirado ou inv\u00e1lido', 401)
        user = sb_select_one('usuario', [f'id=eq.{payload["sub"]}'])
        if not user:
            return err('Usu\u00e1rio n\u00e3o encontrado', 401)
        return f(user=user, *args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    @require_auth
    def decorated(user=None, *args, **kwargs):
        if user['role'] != 'admin':
            return err('Acesso negado', 403)
        return f(user=user, *args, **kwargs)
    return decorated

def check_rate_limit(ip):
    now = datetime.utcnow()
    _login_attempts[ip] = [t for t in _login_attempts[ip]
                          if now - t < timedelta(minutes=LOGIN_LOCKOUT_MIN)]
    if len(_login_attempts[ip]) >= MAX_LOGIN_ATTEMPTS:
        return False
    _login_attempts[ip].append(now)
    return True

def _build_tree(items, parent_id=None):
    tree = []
    for item in items:
        if item.get('parent_id') == parent_id:
            node = {'l': item['name']}
            kids = _build_tree(items, item['id'])
            if kids: node['c'] = kids
            tree.append(node)
    return tree


# ── API: Tree ──
@app.route('/api/tree', methods=['GET'])
@require_auth
def get_tree(user=None):
    items = sb_select('menu_item', ['order=sort_order.asc'])
    items.sort(key=lambda x: (0 if x['parent_id'] is None else 1, x.get('parent_id') or 0, x['sort_order']))
    tree = _build_tree(items)
    LOG(f'GET /api/tree -> {len(tree)} itens raiz retornados.')
    return jsonify(tree)

@app.route('/api/tree', methods=['POST'])
@require_admin
def save_tree(user=None):
    data = request.json
    if not isinstance(data, list):
        return err('expected array')
    try:
        sb_delete_all('menu_item')
        _flatten_and_insert(data)
        LOG(f'POST /api/tree (admin="{user["nome"]}"): menu reescrito.')
        return jsonify({'ok': True})
    except Exception as e:
        LOG(f'POST /api/tree ERRO: {e}')
        return err(str(e), 500)

def _flatten_and_insert(data, parent_id=None):
    for i, node in enumerate(data):
        row = sb_insert('menu_item', {
            'name': node['l'],
            'sort_order': i,
            'parent_id': parent_id
        })
        new_id = row[0]['id'] if row and isinstance(row, list) else None
        if 'c' in node and node['c']:
            _flatten_and_insert(node['c'], new_id)


# ── API: Users ──
@app.route('/api/users', methods=['GET'])
@require_admin
def get_users(user=None):
    users = sb_select('usuario', ['order=id.asc'])
    LOG(f'GET /api/users (admin="{user["nome"]}"): listados {len(users)} usu\u00e1rios.')
    return jsonify([{
        'id': u['id'], 'nome': u['nome'], 'email': u['email'],
        'role': u['role'],
        'ultimo_login': u['ultimo_login'] if u.get('ultimo_login') else None,
        'criado_em': u['criado_em']
    } for u in users])

@app.route('/api/users', methods=['POST'])
@require_admin
def add_user(user=None):
    data = request.json
    nome = (data.get('nome') or '').strip()
    email = (data.get('email') or '').strip()
    if not nome or not email:
        return err('nome e email s\u00e3o obrigat\u00f3rios')
    if sb_select_one('usuario', [f'nome=eq.{nome}']):
        return err('Nome de usu\u00e1rio j\u00e1 existe')
    if sb_select_one('usuario', [f'email=eq.{email}']):
        return err('Email j\u00e1 cadastrado')
    h = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
    sb_insert('usuario', {
        'nome': nome, 'email': email,
        'password_hash': h.decode(), 'role': 'user'
    })
    LOG(f'POST /api/users (admin="{user["nome"]}"): criado usu\u00e1rio "{nome}" com senha padr\u00e3o.')
    return jsonify({'ok': True, 'password': DEFAULT_PASSWORD})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@require_admin
def delete_user(uid, user=None):
    u = sb_select_one('usuario', [f'id=eq.{uid}'])
    if not u: return err('Usu\u00e1rio n\u00e3o encontrado', 404)
    if u['id'] == user['id']: return err('N\u00e3o pode excluir a si mesmo')
    nome_excluido = u['nome']
    sb_delete('usuario', 'id', uid)
    LOG(f'DELETE /api/users/{uid} (admin="{user["nome"]}"): exclu\u00eddo usu\u00e1rio "{nome_excluido}".')
    return jsonify({'ok': True})

@app.route('/api/users/<int:uid>/reset-password', methods=['POST'])
@require_admin
def reset_user_password(uid, user=None):
    u = sb_select_one('usuario', [f'id=eq.{uid}'])
    if not u: return err('Usu\u00e1rio n\u00e3o encontrado', 404)
    h = bcrypt.hashpw(DEFAULT_PASSWORD.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
    sb_update('usuario', 'id', uid, {'password_hash': h.decode()})
    LOG(f'POST /api/users/{uid}/reset-password (admin="{user["nome"]}"): senha de "{u["nome"]}" resetada.')
    return jsonify({'ok': True, 'password': DEFAULT_PASSWORD})

@app.route('/api/users/<int:uid>/role', methods=['PUT'])
@require_admin
def update_user_role(uid, user=None):
    u = sb_select_one('usuario', [f'id=eq.{uid}'])
    if not u: return err('Usu\u00e1rio n\u00e3o encontrado', 404)
    if u['id'] == user['id']:
        return err('N\u00e3o pode alterar o pr\u00f3prio cargo')
    new_role = request.json.get('role')
    if new_role not in ('admin', 'user'):
        return err('Cargo inv\u00e1lido. Use "admin" ou "user".')
    old_role = u['role']
    sb_update('usuario', 'id', uid, {'role': new_role})
    LOG(f'PUT /api/users/{uid}/role (admin="{user["nome"]}"): "{u["nome"]}" alterado de "{old_role}" para "{new_role}".')
    return jsonify({'ok': True})


# ── API: Pages ──
@app.route('/api/pages/<path:key>', methods=['GET'])
@require_auth
def get_page(key, user=None):
    p = sb_select_one('page', [f'key=eq.{key}'])
    tamanho = len(p['content']) if p else 0
    LOG(f'GET /api/pages/...{key[-40:]} -> {"encontrada" if p else "NOVA (vazia)"} ({tamanho} chars).')
    return jsonify({'content': p['content'] if p else ''})

@app.route('/api/pages/<path:key>', methods=['PUT'])
@require_auth
def save_page(key, user=None):
    content = request.json.get('content', '')
    p = sb_select_one('page', [f'key=eq.{key}'])
    if p:
        sb_update('page', 'id', p['id'], {'content': content})
        acao = 'atualizada'
    else:
        sb_insert('page', {'key': key, 'content': content})
        acao = 'criada'
    LOG(f'PUT /api/pages/...{key[-40:]} ({user["nome"]}): p\u00e1gina {acao} ({len(content)} chars).')
    return jsonify({'ok': True})


# ── API: Profile ──
@app.route('/api/auth/profile', methods=['PUT'])
@require_auth
def update_profile(user=None):
    data = request.json
    updated = []

    if 'nome' in data:
        nome = (data['nome'] or '').strip()
        if not nome:
            return err('Nome inv\u00e1lido')
        existing = sb_select_one('usuario', [f'nome=eq.{nome}', f'id=neq.{user["id"]}'])
        if existing:
            return err('Nome de usu\u00e1rio j\u00e1 existe')
        sb_update('usuario', 'id', user['id'], {'nome': nome})
        updated.append('nome')

    if 'email' in data:
        email = (data['email'] or '').strip()
        if not email or '@' not in email:
            return err('Email inv\u00e1lido')
        existing = sb_select_one('usuario', [f'email=eq.{email}', f'id=neq.{user["id"]}'])
        if existing:
            return err('Email j\u00e1 cadastrado')
        sb_update('usuario', 'id', user['id'], {'email': email})
        updated.append('email')

    if 'current_password' in data or 'new_password' in data:
        current_pw = data.get('current_password', '')
        new_pw = data.get('new_password', '')
        if not current_pw or not new_pw:
            return err('current_password e new_password s\u00e3o obrigat\u00f3rios')
        if not valid_password(new_pw):
            return err('Senha deve ter 8+ caracteres, mai\u00fascula, min\u00fascula, n\u00famero e especial')
        try:
            if not bcrypt.checkpw(current_pw.encode(), user['password_hash'].encode()):
                return err('Senha atual incorreta', 401)
        except Exception:
            return err('Senha atual incorreta', 401)
        h = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
        sb_update('usuario', 'id', user['id'], {'password_hash': h.decode()})
        updated.append('senha')

    if not updated:
        return err('Nada a alterar. Envie nome, email e/ou current_password + new_password.')

    LOG(f'PUT /api/auth/profile ({user["nome"]}): alterado(s) {", ".join(updated)}.')
    return jsonify({'ok': True, 'updated': updated})


# ── API: Auth ──
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    nome = (data.get('nome') or '').strip()
    email = (data.get('email') or '').strip()
    pw = data.get('password', '')
    if not nome or not email or not pw:
        return err('nome, email e password s\u00e3o obrigat\u00f3rios')
    if not valid_password(pw):
        return err('Senha deve ter 8+ caracteres, mai\u00fascula, min\u00fascula, n\u00famero e especial')
    if sb_select_one('usuario', [f'nome=eq.{nome}']):
        return err('Nome de usu\u00e1rio j\u00e1 existe')
    if sb_select_one('usuario', [f'email=eq.{email}']):
        return err('Email j\u00e1 cadastrado')
    h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
    row = sb_insert('usuario', {
        'nome': nome, 'email': email,
        'password_hash': h.decode(), 'role': 'user'
    })
    u = row[0]
    token = create_token(u['id'], u['role'])
    LOG(f'POST /api/auth/register: novo usu\u00e1rio "{nome}" registrado e logado automaticamente.')
    return jsonify({
        'token': token,
        'user': {'id': u['id'], 'nome': u['nome'], 'email': u['email'], 'role': u['role']}
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    ip = request.remote_addr or 'unknown'
    if not check_rate_limit(ip):
        LOG(f'POST /api/auth/login BLOQUEADO (rate limit) — IP={ip}.')
        return err('Muitas tentativas. Aguarde 15 minutos.', 429)

    data = request.json
    nome = (data.get('nome') or data.get('username') or '').strip()
    pw = data.get('password', '')

    if not nome or not pw:
        return err('nome e password s\u00e3o obrigat\u00f3rios', 401)

    user = sb_select_one('usuario', [f'nome=eq.{nome}'])
    if not user:
        LOG(f'POST /api/auth/login FALHA: usu\u00e1rio "{nome}" n\u00e3o encontrado (IP={ip}).')
        return err('Usu\u00e1rio ou senha inv\u00e1lidos', 401)

    try:
        pw_bytes = pw.encode()
        hash_bytes = user['password_hash'].encode()
        if not bcrypt.checkpw(pw_bytes, hash_bytes):
            LOG(f'POST /api/auth/login FALHA: senha incorreta para "{nome}" (IP={ip}).')
            return err('Usu\u00e1rio ou senha inv\u00e1lidos', 401)
    except Exception:
        LOG(f'POST /api/auth/login FALHA: erro ao verificar senha de "{nome}" (IP={ip}).')
        return err('Usu\u00e1rio ou senha inv\u00e1lidos', 401)

    sb_update('usuario', 'id', user['id'], {'ultimo_login': datetime.utcnow().isoformat()})

    token = create_token(user['id'], user['role'])
    LOG(f'POST /api/auth/login OK: "{nome}" logado (role={user["role"]}, IP={ip}).')
    return jsonify({
        'token': token,
        'user': {
            'id': user['id'], 'nome': user['nome'], 'email': user['email'],
            'role': user['role'],
            'ultimo_login': user.get('ultimo_login')
        }
    })

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me(user=None):
    LOG(f'GET /api/auth/me: "{user["nome"]}" verificou pr\u00f3prio perfil.')
    return jsonify({
        'id': user['id'], 'nome': user['nome'], 'email': user['email'],
        'role': user['role'],
        'ultimo_login': user.get('ultimo_login'),
        'criado_em': user['criado_em']
    })


# ── Serve HTML ──
@app.route('/')
def serve_html():
    LOG(f'GET / -> servindo frontend ({os.path.getsize(HTML_PATH)} bytes).')
    return send_file(HTML_PATH)


if __name__ != '__main__':
    pass  # gunicorn import path
else:
    port = int(os.environ.get('PORT', 5050))
    try:
        c = sb_count('menu_item')
        LOG(f'SUPABASE: {c} itens de menu, {sb_count("usuario")} usu\u00e1rios, {sb_count("page")} p\u00e1ginas.')
    except Exception as e:
        LOG(f'ERRO ao conectar no Supabase: {e}')
        sys.exit(1)
    https_status = 'SIM' if os.environ.get('HTTPS') else 'N\u00c3O'
    LOG(f'SERVIDOR INICIADO em http://0.0.0.0:{port}/ (HTTPS={https_status}).')
    app.run(host='0.0.0.0', port=port, ssl_context='adhoc' if os.environ.get('HTTPS') else None,
            debug=bool(os.environ.get('FLASK_DEBUG', '')))
