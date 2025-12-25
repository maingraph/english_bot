"""
Netlify Function for TMA API endpoints.
This is a simplified version that works with Netlify's serverless architecture.
"""
import json
import os
import sys
from urllib.parse import urlparse, parse_qs

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
        
        # Route requests
        if path == '/.netlify/functions/tma-api' or path.endswith('/tma-api'):
            # Get the actual route from query string or path
            query = event.get('queryStringParameters', {}) or {}
            route = query.get('route', '')
            
            if not route:
                # Try to infer from path
                if 'join' in path.lower():
                    route = 'join'
                elif 'state' in path.lower():
                    route = 'state'
                elif 'answer' in path.lower():
                    route = 'answer'
                elif 'admin' in path.lower():
                    route = 'admin'
        
        # Handle routes
        if method == 'POST' and ('join' in path.lower() or route == 'join'):
            return handle_join(headers, body)
        elif method == 'GET' and ('state' in path.lower() or route == 'state'):
            return handle_state(headers)
        elif method == 'POST' and ('answer' in path.lower() or route == 'answer'):
            return handle_answer(headers, body)
        elif method == 'POST' and 'admin' in path.lower():
            return handle_admin(headers, body, path)
        else:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'ok': False, 'error': 'Not found'})
            }
            
    except Exception as e:
        import traceback
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'ok': False, 'error': str(e)})
        }


def handle_join(headers, body):
    """Handle player join."""
    # For demo, allow joining without full auth
    user_id = body.get('user_id', 123)  # Fallback for testing
    name = body.get('name', 'Player')
    
    if not _game_state['is_open']:
        return json_response({'ok': False, 'error': 'Lobby not open'}, 400)
    
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
    state = {
        'is_open': _game_state['is_open'],
        'is_running': _game_state['is_running'],
        'is_finished': _game_state['is_finished'],
        'player_count': len(_game_state['players']),
        'current_round': _game_state['current_round'],
        'total_rounds': _game_state['total_rounds'],
        'leaderboard': get_leaderboard(5),
    }
    
    if _game_state['current_question']:
        state['question'] = _game_state['current_question']
    
    return json_response(state)


def handle_answer(headers, body):
    """Handle answer submission."""
    user_id = body.get('user_id', 123)
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

