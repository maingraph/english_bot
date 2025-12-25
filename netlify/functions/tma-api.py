"""
Netlify Function for TMA API endpoints.
This is a simplified version that works with Netlify's serverless architecture.
"""
import json
import os
import sys
import hashlib
import hmac
import urllib.parse

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

# Import our modules
from duel_ladder_bot.config import ADMIN_TOKEN, BOT_TOKEN, TASK_TYPES
from duel_ladder_bot.runtime import db

# In-memory game state (resets on cold start - fine for classroom demo)
_game_state = {
    'is_open': False,
    'is_running': False,
    'is_finished': False,
    'players': {},
    'current_round': 0,
    'total_rounds': 10,
    'round_seconds': 12,
    'current_question': None,
    'round_start_time': 0,
    'answers': {},
    'task_type': 'SYNONYM',
    'round_results': [],
}

def handler(event, context):
    """Netlify Function handler - routes to appropriate endpoint."""
    try:
        path = event.get('path', '')
        method = event.get('httpMethod', 'GET')
        headers = event.get('headers', {}) or {}
        body_str = event.get('body', '')
        
        # Parse body
        body = {}
        if body_str:
            try:
                body = json.loads(body_str)
            except:
                pass
        
        # Extract route from path
        # Path will be like: /.netlify/functions/tma-api/join or /api/join
        route = ''
        if '/join' in path or path.endswith('/join'):
            route = 'join'
        elif '/state' in path or path.endswith('/state'):
            route = 'state'
        elif '/answer' in path or path.endswith('/answer'):
            route = 'answer'
        elif '/admin' in path:
            route = 'admin'
        
        # Also check query params as fallback
        if not route:
            query = event.get('queryStringParameters', {}) or {}
            route = query.get('route', '')
        
        # Handle routes
        if method == 'POST' and route == 'join':
            return handle_join(headers, body)
        elif method == 'GET' and route == 'state':
            return handle_state(headers)
        elif method == 'POST' and route == 'answer':
            return handle_answer(headers, body)
        elif method == 'POST' and route == 'admin':
            return handle_admin(headers, body, path)
        else:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'ok': False, 'error': f'Not found. Path: {path}, Route: {route}, Method: {method}'})
            }
            
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        # Log to console (visible in Netlify logs)
        print(f"Function error: {str(e)}")
        print(f"Traceback: {error_trace}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'ok': False, 'error': str(e), 'trace': error_trace})
        }


def validate_init_data(init_data: str):
    """Validate Telegram WebApp initData and extract user info."""
    if not BOT_TOKEN or not init_data:
        return None
    
    try:
        parsed = urllib.parse.parse_qs(init_data)
        data_check_string_parts = []
        received_hash = None
        
        for key in sorted(parsed.keys()):
            if key == "hash":
                received_hash = parsed[key][0]
            else:
                data_check_string_parts.append(f"{key}={parsed[key][0]}")
        
        if not received_hash:
            return None
        
        data_check_string = "\n".join(data_check_string_parts)
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if computed_hash != received_hash:
            return None
        
        # Extract user
        if "user" in parsed:
            user_data = json.loads(parsed["user"][0])
            return user_data
        return None
        
    except Exception as e:
        return None


def handle_join(headers, body):
    """Handle player join."""
    # Get Telegram init data from headers
    init_data = headers.get('x-telegram-init-data', '') or headers.get('X-Telegram-Init-Data', '')
    user = validate_init_data(init_data)
    
    if not user:
        # For testing, allow fallback
        user_id = body.get('user_id', 123)
        name = body.get('name', 'Player')
    else:
        user_id = user.get('id')
        name = user.get('first_name', 'Player')
        if user.get('last_name'):
            name += ' ' + user.get('last_name')
    
    if not _game_state['is_open']:
        return json_response({'ok': False, 'error': 'Lobby not open. Admin needs to open the lobby first.'}, 400)
    
    if user_id not in _game_state['players']:
        _game_state['players'][user_id] = {
            'name': name,
            'score': 0,
            'correct': 0,
            'wrong': 0,
        }
    
    return json_response({'ok': True})


def handle_state(headers):
    """Return current game state."""
    # Get user ID from Telegram init data
    user_id = None
    init_data = headers.get('x-telegram-init-data', '') or headers.get('X-Telegram-Init-Data', '')
    if init_data:
        user = validate_init_data(init_data)
        if user:
            user_id = user.get('id')
    
    state = {
        'is_open': _game_state['is_open'],
        'is_running': _game_state['is_running'],
        'is_finished': _game_state['is_finished'],
        'player_count': len(_game_state['players']),
        'current_round': _game_state['current_round'],
        'total_rounds': _game_state['total_rounds'],
        'leaderboard': get_leaderboard(5),
    }
    
    # Add user-specific data if authenticated
    if user_id and user_id in _game_state['players']:
        player = _game_state['players'][user_id]
        state['my_rank'] = get_player_rank(user_id)
        state['my_score'] = player['score']
        state['my_correct'] = player['correct']
        state['already_answered'] = user_id in _game_state['answers']
    
    if _game_state['current_question']:
        state['question'] = _game_state['current_question']
    
    return json_response(state)


def get_player_rank(user_id):
    """Get player's current rank."""
    sorted_players = sorted(
        _game_state['players'].items(),
        key=lambda x: x[1]['score'],
        reverse=True
    )
    for i, (uid, _) in enumerate(sorted_players):
        if uid == user_id:
            return i + 1
    return None


def handle_answer(headers, body):
    """Handle answer submission."""
    # Get user ID from Telegram init data
    init_data = headers.get('x-telegram-init-data', '') or headers.get('X-Telegram-Init-Data', '')
    user = validate_init_data(init_data)
    
    if not user:
        return json_response({'ok': False, 'error': 'Invalid auth'}, 401)
    
    user_id = user.get('id')
    choice = body.get('choice', -1)
    
    if user_id not in _game_state['players']:
        return json_response({'ok': False, 'error': 'Not joined'}, 400)
    
    if user_id in _game_state['answers']:
        return json_response({'ok': False, 'error': 'Already answered'}, 400)
    
    _game_state['answers'][user_id] = {'choice': choice, 'time': 0}
    return json_response({'ok': True})


def handle_admin(headers, body, path):
    """Handle admin actions."""
    admin_token = headers.get('x-admin-token', '') or headers.get('X-Admin-Token', '')
    if admin_token != ADMIN_TOKEN:
        return json_response({'ok': False, 'error': 'Unauthorized'}, 403)
    
    if 'open' in path.lower():
        _game_state['is_open'] = True
        _game_state['is_running'] = False
        _game_state['is_finished'] = False
        _game_state['players'] = {}
        _game_state['current_round'] = 0
        return json_response({'ok': True})
    elif 'start' in path.lower():
        if len(_game_state['players']) < 1:
            return json_response({'ok': False, 'error': 'Need at least 1 player'}, 400)
        _game_state['is_open'] = False
        _game_state['is_running'] = True
        _game_state['current_round'] = 1
        # Generate first question
        q = db.build_question('SYNONYM', k_options=4)
        if q:
            _game_state['current_question'] = q
        return json_response({'ok': True})
    elif 'reset' in path.lower():
        _game_state['is_open'] = False
        _game_state['is_running'] = False
        _game_state['is_finished'] = False
        _game_state['players'] = {}
        _game_state['current_round'] = 0
        _game_state['current_question'] = None
        _game_state['answers'] = {}
        return json_response({'ok': True})
    
    return json_response({'ok': False, 'error': 'Unknown action'}, 400)


def get_leaderboard(limit=5):
    """Get top players."""
    players = sorted(
        _game_state['players'].items(),
        key=lambda x: x[1]['score'],
        reverse=True
    )[:limit]
    
    return [
        {
            'user_id': uid,
            'name': p['name'],
            'score': p['score'],
            'rank': i + 1,
        }
        for i, (uid, p) in enumerate(players)
    ]


def json_response(data, status=200):
    """Create JSON response."""
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type, X-Admin-Token, X-Telegram-Init-Data',
        },
        'body': json.dumps(data)
    }

