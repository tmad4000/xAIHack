#!/usr/bin/env python3
"""
City Ideas Graph Visualization Server
A simple server to host the interactive graph visualization.

Usage:
    python server.py
"""

import http.server
import socketserver
import os
import socket
import json
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from grok_x_search import run_grok_search, parse_handles, parse_date

# Random port range to avoid conflicts
START_PORT = 7847
END_PORT = 7899

def find_available_port(start=START_PORT, end=END_PORT):
    """Find an available port in the specified range."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
    raise RuntimeError(f"No available port found in range {start}-{end}")


class CityIdeasHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler for serving the visualization."""

    def __init__(self, *args, **kwargs):
        # Set the directory to serve from
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def do_GET(self):
        """Handle GET requests with custom routing."""
        parsed = urlparse(self.path)

        # Route / to visualization/index.html
        if parsed.path == '/' or parsed.path == '':
            self.path = '/visualization/index.html'

        # Serve data files from /data/
        elif parsed.path.startswith('/data/'):
            # Already correct path
            pass

        # API endpoint for cluster summary
        elif parsed.path == '/api/clusters':
            self.send_cluster_summary()
            return

        return super().do_GET()

    def do_POST(self):
        """Handle POST requests for API endpoints."""
        parsed = urlparse(self.path)

        if parsed.path == '/api/grok-search':
            self.handle_grok_search()
            return

        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'Not found'}).encode())

    def send_cluster_summary(self):
        """Generate and send cluster summary as JSON."""
        try:
            # Load the connections data
            data_path = Path(__file__).parent / 'data' / 'connections.json'
            with open(data_path, 'r') as f:
                data = json.load(f)

            # Simple clustering summary
            summary = {
                'total_nodes': len(data['nodes']),
                'total_edges': len(data['edges']),
                'nodes': data['nodes'],
                'edges': data['edges']
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(summary).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def handle_grok_search(self):
        """Proxy a Grok x_search query from the browser."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
        except (ValueError, TypeError):
            content_length = 0

        raw_body = self.rfile.read(content_length) if content_length else b''

        try:
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}
        except json.JSONDecodeError:
            self._send_json(400, {'error': 'Invalid JSON payload'})
            return

        location = (payload.get('prompt') or payload.get('location') or '').strip()
        if not location:
            self._send_json(400, {'error': 'Prompt/location is required'})
            return

        count = payload.get('count', 10)
        try:
            count = max(1, min(int(count), 25))
        except (TypeError, ValueError):
            count = 10

        allowed_input = payload.get('allowed_handles')
        excluded_input = payload.get('excluded_handles')
        allowed_handles = self._normalize_handles(allowed_input)
        excluded_handles = self._normalize_handles(excluded_input)

        from_date = self._parse_date_value(payload.get('from_date'))
        to_date = self._parse_date_value(payload.get('to_date'))
        model = (payload.get('model') or 'grok-4-1-fast').strip() or 'grok-4-1-fast'

        try:
            result = run_grok_search(
                location,
                count=count,
                allowed_handles=allowed_handles,
                excluded_handles=excluded_handles,
                from_date=from_date,
                to_date=to_date,
                model=model,
            )
        except ValueError as exc:
            self._send_json(400, {'error': str(exc)})
            return
        except SystemExit as exc:
            self._send_json(500, {'error': str(exc)})
            return
        except Exception as exc:
            self._send_json(500, {'error': f'Grok search failed: {exc}'})
            return

        self._send_json(200, result)

    def log_message(self, format, *args):
        """Custom log format."""
        print(f"[{self.log_date_time_string()}] {args[0]}")

    def end_headers(self):
        """Add CORS headers."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def _parse_date_value(self, value):
        if not value:
            return None
        try:
            return parse_date(value) if isinstance(value, str) else None
        except ValueError:
            return None

    def _normalize_handles(self, handles_value):
        if not handles_value:
            return None
        if isinstance(handles_value, str):
            handles = parse_handles(handles_value)
        elif isinstance(handles_value, list):
            handles = parse_handles(",".join(str(h) for h in handles_value))
        else:
            handles = None
        return handles

    def _send_json(self, status_code, payload):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))


def main():
    port = find_available_port()

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   🏙️  City Ideas Graph Visualization                             ║
║                                                                  ║
║   xAI Hackathon Demo                                             ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║   Server running at: http://localhost:{port:<5}                    ║
║                                                                  ║
║   Features:                                                      ║
║   • Force-directed graph of urban improvement ideas              ║
║   • AI-powered clustering by topic and similarity                ║
║   • Interactive exploration with zoom/pan/search                 ║
║   • Consolidated actionable suggestions view                     ║
║   • Export to markdown report                                    ║
║                                                                  ║
║   Press Ctrl+C to stop the server                                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
""")

    # Open browser automatically (disabled for background running)
    url = f"http://localhost:{port}"
    # Only open browser if running interactively
    import sys
    if sys.stdout.isatty():
        print(f"Opening browser to {url}...")
        webbrowser.open(url)
    else:
        print(f"Visit: {url}")

    # Start server
    with socketserver.TCPServer(("", port), CityIdeasHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped. Goodbye!")


if __name__ == "__main__":
    main()
