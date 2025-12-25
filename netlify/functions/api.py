"""
Netlify Function wrapper for TMA API.
Handles all API routes in a single serverless function.
"""
import json
import os
import sys
from typing import Any, Dict

# Add parent directory to path so we can import duel_ladder_bot
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from duel_ladder_bot.tma_server import (
    game,
    validate_init_data,
    ADMIN_TOKEN,
    handle_join,
    handle_state,
    handle_answer,
    handle_admin_open,
    handle_admin_start,
    handle_admin_reset,
    handle_admin_next,
    check_admin,
)

# Import aiohttp web for request/response handling
from aiohttp import web


def handler(event, context):
    """Netlify Function handler."""
    try:
        # Parse request
        path = event.get('path', '')
        method = event.get('httpMethod', 'GET')
        headers = event.get('headers', {}) or {}
        body = event.get('body', '')
        
        # Parse body if present
        request_body = None
        if body:
            try:
                request_body = json.loads(body)
            except:
                pass
        
        # Create a mock request object
        class MockRequest:
            def __init__(self):
                self.method = method
                self.path = path
                self.headers = headers
                self._body = request_body
                self._json = request_body
            
            async def json(self):
                return self._json or {}
        
        mock_req = MockRequest()
        
        # Route to appropriate handler
        if path == '/api/join' and method == 'POST':
            response = await handle_join(mock_req)
        elif path == '/api/state' and method == 'GET':
            response = await handle_state(mock_req)
        elif path == '/api/answer' and method == 'POST':
            response = await handle_answer(mock_req)
        elif path == '/api/admin/open' and method == 'POST':
            response = await handle_admin_open(mock_req)
        elif path == '/api/admin/start' and method == 'POST':
            response = await handle_admin_start(mock_req)
        elif path == '/api/admin/reset' and method == 'POST':
            response = await handle_admin_reset(mock_req)
        elif path == '/api/admin/next' and method == 'POST':
            response = await handle_admin_next(mock_req)
        else:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'ok': False, 'error': 'Not found'})
            }
        
        # Convert aiohttp response to Netlify format
        if isinstance(response, web.Response):
            body_text = response.text if hasattr(response, 'text') else ''
            try:
                body_data = json.loads(body_text) if body_text else {}
            except:
                body_data = {'ok': False, 'error': 'Invalid response'}
            
            return {
                'statusCode': response.status,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(body_data)
            }
        else:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(response)
            }
            
    except Exception as e:
        import traceback
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'ok': False, 'error': str(e), 'trace': traceback.format_exc()})
        }

