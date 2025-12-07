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
import subprocess
import shutil
import re
from pathlib import Path
from urllib.parse import urlparse

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from grok_x_search import run_grok_search, run_grok_report_insights, parse_handles, parse_date

# Project management
PROJECTS_DIR = Path(__file__).parent / 'data' / 'projects'
DEFAULT_PROJECT = 'default'


def get_projects():
    """List all available projects."""
    projects = []

    # Default project (uses root data files)
    default_connections = Path(__file__).parent / 'data' / 'connections.json'
    if default_connections.exists():
        projects.append({
            'name': DEFAULT_PROJECT,
            'display_name': 'NYC Urbanist Ideas (Default)',
            'is_default': True,
            'has_clusters': (Path(__file__).parent / 'data' / 'enhanced_clusters.json').exists()
        })

    # Custom projects
    if PROJECTS_DIR.exists():
        for project_dir in sorted(PROJECTS_DIR.iterdir()):
            if project_dir.is_dir():
                connections_file = project_dir / 'connections.json'
                if connections_file.exists():
                    projects.append({
                        'name': project_dir.name,
                        'display_name': project_dir.name.replace('_', ' ').title(),
                        'is_default': False,
                        'has_clusters': (project_dir / 'enhanced_clusters.json').exists()
                    })

    return projects


def get_project_path(project_name):
    """Get the data directory for a project."""
    if project_name == DEFAULT_PROJECT:
        return Path(__file__).parent / 'data'
    return PROJECTS_DIR / project_name


def create_project(name):
    """Create a new empty project."""
    # Sanitize name
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower().strip())
    if not safe_name:
        raise ValueError("Invalid project name")

    project_dir = PROJECTS_DIR / safe_name
    if project_dir.exists():
        raise ValueError(f"Project '{safe_name}' already exists")

    project_dir.mkdir(parents=True, exist_ok=True)

    # Create empty connections file
    empty_data = {'nodes': [], 'edges': []}
    with open(project_dir / 'connections.json', 'w') as f:
        json.dump(empty_data, f, indent=2)

    return safe_name


def rename_project(old_name, new_name):
    """Rename a project."""
    if old_name == DEFAULT_PROJECT:
        raise ValueError("Cannot rename the default project")

    # Sanitize new name
    safe_new_name = re.sub(r'[^a-zA-Z0-9_-]', '_', new_name.lower().strip())
    if not safe_new_name:
        raise ValueError("Invalid project name")

    old_dir = PROJECTS_DIR / old_name
    new_dir = PROJECTS_DIR / safe_new_name

    if not old_dir.exists():
        raise ValueError(f"Project '{old_name}' not found")

    if new_dir.exists() and old_dir != new_dir:
        raise ValueError(f"Project '{safe_new_name}' already exists")

    if old_dir != new_dir:
        old_dir.rename(new_dir)

    return safe_new_name


def delete_project(name):
    """Delete a project."""
    if name == DEFAULT_PROJECT:
        raise ValueError("Cannot delete the default project")

    project_dir = PROJECTS_DIR / name

    if not project_dir.exists():
        raise ValueError(f"Project '{name}' not found")

    # Remove directory and all contents
    shutil.rmtree(project_dir)

    return True


def add_nodes_to_project(project_name, rows, source='unknown'):
    """Add nodes from Grok search results or CSV import to a project.

    Args:
        project_name: The project to add nodes to
        rows: List of row dicts with node data
        source: Source of the nodes ('grok_search', 'csv_import', etc.)
    """
    project_path = get_project_path(project_name)
    connections_file = project_path / 'connections.json'

    if not connections_file.exists():
        raise ValueError(f"Project '{project_name}' not found")

    with open(connections_file, 'r') as f:
        data = json.load(f)

    # Find max existing ID
    max_id = max([n.get('id', 0) for n in data['nodes']], default=0)

    # Add new nodes with provisional status
    new_nodes = []
    for row in rows:
        max_id += 1
        node = {
            'id': max_id,
            'username': (row.get('Username') or row.get('username', '')).replace('@', ''),
            'summary': row.get('Summary/Quote') or row.get('summary', ''),
            'date': row.get('Date') or row.get('date', ''),
            'link': row.get('Link') or row.get('link', ''),
            'status': 'provisional',
            'source': source
        }
        new_nodes.append(node)
        data['nodes'].append(node)

    # Save updated data
    with open(connections_file, 'w') as f:
        json.dump(data, f, indent=2)

    return {'added': len(new_nodes), 'total': len(data['nodes']), 'new_node_ids': [n['id'] for n in new_nodes]}


def commit_nodes(project_name, node_ids=None):
    """Commit provisional nodes (make them permanent).

    Args:
        project_name: The project name
        node_ids: List of node IDs to commit, or None to commit all provisional
    """
    project_path = get_project_path(project_name)
    connections_file = project_path / 'connections.json'

    if not connections_file.exists():
        raise ValueError(f"Project '{project_name}' not found")

    with open(connections_file, 'r') as f:
        data = json.load(f)

    committed_count = 0
    for node in data['nodes']:
        if node.get('status') == 'provisional':
            if node_ids is None or node['id'] in node_ids:
                node['status'] = 'committed'
                committed_count += 1

    with open(connections_file, 'w') as f:
        json.dump(data, f, indent=2)

    return {'committed': committed_count}


def discard_nodes(project_name, node_ids=None):
    """Discard provisional nodes (remove them).

    Args:
        project_name: The project name
        node_ids: List of node IDs to discard, or None to discard all provisional
    """
    project_path = get_project_path(project_name)
    connections_file = project_path / 'connections.json'

    if not connections_file.exists():
        raise ValueError(f"Project '{project_name}' not found")

    with open(connections_file, 'r') as f:
        data = json.load(f)

    # Find nodes to remove
    if node_ids is None:
        ids_to_remove = {n['id'] for n in data['nodes'] if n.get('status') == 'provisional'}
    else:
        ids_to_remove = {n['id'] for n in data['nodes']
                         if n.get('status') == 'provisional' and n['id'] in node_ids}

    # Remove nodes
    original_count = len(data['nodes'])
    data['nodes'] = [n for n in data['nodes'] if n['id'] not in ids_to_remove]

    # Remove edges involving discarded nodes
    data['edges'] = [e for e in data['edges']
                     if e.get('source_id') not in ids_to_remove
                     and e.get('target_id') not in ids_to_remove]

    with open(connections_file, 'w') as f:
        json.dump(data, f, indent=2)

    return {'discarded': original_count - len(data['nodes'])}


def run_clustering(project_name):
    """Run the clustering pipeline for a project."""
    project_path = get_project_path(project_name)
    connections_file = project_path / 'connections.json'

    if not connections_file.exists():
        raise ValueError(f"Project '{project_name}' not found")

    # Read project metadata to get context
    with open(connections_file, 'r') as f:
        data = json.load(f)
    project_context = data.get('metadata', {}).get('context', 'civic')

    # Run find_related_items.py to generate edges
    script_dir = Path(__file__).parent
    env = os.environ.copy()

    # Set the data path for the scripts (required even for default project)
    env['CITYVOICE_DATA_PATH'] = str(project_path)

    # Set the context for prompts
    env['CITYVOICE_CONTEXT'] = project_context

    # Run edge generation
    result = subprocess.run(
        ['python', str(script_dir / 'find_related_items.py')],
        cwd=str(script_dir),
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        message = stderr or stdout or "Unknown error"
        raise RuntimeError(f"Edge generation failed: {message}")

    # Run cluster enhancement
    result = subprocess.run(
        ['python', str(script_dir / 'enhance_clusters.py')],
        cwd=str(script_dir),
        env=env,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        message = stderr or stdout or "Unknown error"
        raise RuntimeError(f"Clustering failed: {message}")

    return {'status': 'completed'}

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

        # API: List projects
        elif parsed.path == '/api/projects':
            self._send_json(200, {'projects': get_projects()})
            return

        # API: Get project data
        elif parsed.path.startswith('/api/projects/') and parsed.path.count('/') == 3:
            project_name = parsed.path.split('/')[-1]
            self.handle_get_project(project_name)
            return

        # API: Get project context
        elif parsed.path.endswith('/context') and parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 5:  # ['', 'api', 'projects', 'name', 'context']
                project_name = parts[3]
                self.handle_get_context(project_name)
                return

        return super().do_GET()

    def do_POST(self):
        """Handle POST requests for API endpoints."""
        parsed = urlparse(self.path)

        if parsed.path == '/api/grok-search':
            self.handle_grok_search()
            return

        # API: Generate Grok insights for consolidated report
        if parsed.path.endswith('/report') and parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 5:  # ['', 'api', 'projects', 'name', 'report']
                project_name = parts[3]
                self.handle_project_report(project_name)
                return

        # API: Create project
        if parsed.path == '/api/projects':
            self.handle_create_project()
            return

        # API: Add nodes to project
        if parsed.path.endswith('/nodes') and parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 5:  # ['', 'api', 'projects', 'name', 'nodes']
                project_name = parts[3]
                self.handle_add_nodes(project_name)
                return

        # API: Run clustering
        if parsed.path.endswith('/cluster') and parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 5:  # ['', 'api', 'projects', 'name', 'cluster']
                project_name = parts[3]
                self.handle_run_clustering(project_name)
                return

        # API: Commit provisional nodes
        if parsed.path.endswith('/commit') and parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 5:  # ['', 'api', 'projects', 'name', 'commit']
                project_name = parts[3]
                self.handle_commit_nodes(project_name)
                return

        # API: Discard provisional nodes
        if parsed.path.endswith('/discard') and parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 5:  # ['', 'api', 'projects', 'name', 'discard']
                project_name = parts[3]
                self.handle_discard_nodes(project_name)
                return

        # API: Rename project
        if parsed.path.endswith('/rename') and parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 5:  # ['', 'api', 'projects', 'name', 'rename']
                project_name = parts[3]
                self.handle_rename_project(project_name)
                return

        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'Not found'}).encode())

    def do_DELETE(self):
        """Handle DELETE requests for API endpoints."""
        parsed = urlparse(self.path)

        # API: Delete project
        if parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 4:  # ['', 'api', 'projects', 'name']
                project_name = parts[3]
                self.handle_delete_project(project_name)
                return

        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'Not found'}).encode())

    def do_PUT(self):
        """Handle PUT requests for API endpoints."""
        parsed = urlparse(self.path)

        # API: Set project context
        if parsed.path.endswith('/context') and parsed.path.startswith('/api/projects/'):
            parts = parsed.path.split('/')
            if len(parts) == 5:  # ['', 'api', 'projects', 'name', 'context']
                project_name = parts[3]
                self.handle_set_context(project_name)
                return

        self.send_response(404)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'Not found'}).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

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

    def handle_project_report(self, project_name: str):
        """Generate Grok insights for the consolidated report."""
        project_path = get_project_path(project_name)
        connections_file = project_path / 'connections.json'
        if not connections_file.exists():
            self._send_json(404, {'error': f"Project '{project_name}' not found"})
            return

        try:
            with open(connections_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as exc:
            self._send_json(500, {'error': f'Failed to load project data: {exc}'})
            return

        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        context = data.get('metadata', {}).get('context', 'civic')

        try:
            insights = run_grok_report_insights(nodes, edges, context=context)
        except Exception as exc:
            self._send_json(500, {'error': str(exc)})
            return

        self._send_json(200, {'insights': insights, 'context': context})

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

    def handle_get_project(self, project_name):
        """Get project data (connections and clusters)."""
        try:
            project_path = get_project_path(project_name)
            connections_file = project_path / 'connections.json'
            clusters_file = project_path / 'enhanced_clusters.json'

            if not connections_file.exists():
                self._send_json(404, {'error': f"Project '{project_name}' not found"})
                return

            with open(connections_file, 'r') as f:
                connections = json.load(f)

            clusters = None
            if clusters_file.exists():
                with open(clusters_file, 'r') as f:
                    clusters = json.load(f)

            self._send_json(200, {
                'name': project_name,
                'connections': connections,
                'clusters': clusters
            })

        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_create_project(self):
        """Create a new project."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length) if content_length else b''
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}

            name = payload.get('name', '').strip()
            if not name:
                self._send_json(400, {'error': 'Project name is required'})
                return

            safe_name = create_project(name)
            self._send_json(201, {'name': safe_name, 'message': f"Project '{safe_name}' created"})

        except ValueError as e:
            self._send_json(400, {'error': str(e)})
        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_rename_project(self, project_name):
        """Rename a project."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length) if content_length else b''
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}

            new_name = payload.get('newName', '').strip()
            if not new_name:
                self._send_json(400, {'error': 'New name is required'})
                return

            safe_new_name = rename_project(project_name, new_name)
            self._send_json(200, {'newName': safe_new_name, 'message': f"Project renamed to '{safe_new_name}'"})

        except ValueError as e:
            self._send_json(400, {'error': str(e)})
        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_delete_project(self, project_name):
        """Delete a project."""
        try:
            delete_project(project_name)
            self._send_json(200, {'message': f"Project '{project_name}' deleted"})

        except ValueError as e:
            self._send_json(400, {'error': str(e)})
        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_get_context(self, project_name):
        """Get project context type."""
        try:
            project_path = get_project_path(project_name)
            connections_file = project_path / 'connections.json'

            if not connections_file.exists():
                self._send_json(404, {'error': f"Project '{project_name}' not found"})
                return

            with open(connections_file, 'r') as f:
                data = json.load(f)

            context = data.get('metadata', {}).get('context', 'civic')
            available_contexts = ['civic', 'startup', 'product', 'general']

            self._send_json(200, {
                'context': context,
                'available': available_contexts
            })

        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_set_context(self, project_name):
        """Set project context type."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length) if content_length else b''
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}

            new_context = payload.get('context', '').strip().lower()
            valid_contexts = ['civic', 'startup', 'product', 'general']

            if new_context not in valid_contexts:
                self._send_json(400, {
                    'error': f"Invalid context. Must be one of: {', '.join(valid_contexts)}"
                })
                return

            project_path = get_project_path(project_name)
            connections_file = project_path / 'connections.json'

            if not connections_file.exists():
                self._send_json(404, {'error': f"Project '{project_name}' not found"})
                return

            with open(connections_file, 'r') as f:
                data = json.load(f)

            # Ensure metadata exists
            if 'metadata' not in data:
                data['metadata'] = {}

            data['metadata']['context'] = new_context

            with open(connections_file, 'w') as f:
                json.dump(data, f, indent=2)

            self._send_json(200, {
                'context': new_context,
                'message': f"Project context set to '{new_context}'"
            })

        except ValueError as e:
            self._send_json(400, {'error': str(e)})
        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_add_nodes(self, project_name):
        """Add nodes to a project from Grok search results or CSV import."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length) if content_length else b''
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}

            rows = payload.get('rows', [])
            if not rows:
                self._send_json(400, {'error': 'No rows to add'})
                return

            source = payload.get('source', 'unknown')
            result = add_nodes_to_project(project_name, rows, source=source)
            self._send_json(200, result)

        except ValueError as e:
            self._send_json(400, {'error': str(e)})
        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_commit_nodes(self, project_name):
        """Commit provisional nodes to the project."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length) if content_length else b''
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}

            node_ids = payload.get('node_ids')  # None means commit all
            result = commit_nodes(project_name, node_ids)
            self._send_json(200, result)

        except ValueError as e:
            self._send_json(400, {'error': str(e)})
        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_discard_nodes(self, project_name):
        """Discard provisional nodes from the project."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length) if content_length else b''
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}

            node_ids = payload.get('node_ids')  # None means discard all
            result = discard_nodes(project_name, node_ids)
            self._send_json(200, result)

        except ValueError as e:
            self._send_json(400, {'error': str(e)})
        except Exception as e:
            self._send_json(500, {'error': str(e)})

    def handle_run_clustering(self, project_name):
        """Run clustering pipeline for a project."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length) if content_length else b''
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}

            context_override = (payload.get('context') or '').strip().lower()
            if context_override:
                valid_contexts = ['civic', 'startup', 'product', 'general']
                if context_override not in valid_contexts:
                    self._send_json(400, {
                        'error': f"Invalid context. Must be one of: {', '.join(valid_contexts)}"
                    })
                    return

                project_path = get_project_path(project_name)
                connections_file = project_path / 'connections.json'
                if not connections_file.exists():
                    self._send_json(404, {'error': f"Project '{project_name}' not found"})
                    return

                with open(connections_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if 'metadata' not in data:
                    data['metadata'] = {}
                data['metadata']['context'] = context_override

                with open(connections_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)

            result = run_clustering(project_name)
            self._send_json(200, result)
        except ValueError as e:
            self._send_json(400, {'error': str(e)})
        except RuntimeError as e:
            self._send_json(500, {'error': str(e)})
        except Exception as e:
            self._send_json(500, {'error': f'Clustering failed: {e}'})

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

    # Start server with SO_REUSEADDR to allow quick restart
    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("", port), CityIdeasHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nServer stopped. Goodbye!")


if __name__ == "__main__":
    main()
