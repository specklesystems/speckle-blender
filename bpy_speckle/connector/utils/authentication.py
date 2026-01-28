"""
Speckle authentication module for Blender connector.

Implements OAuth-style authentication flow with a local HTTP server,
eliminating the dependency on the desktop service.
"""

import json
import secrets
import string
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


def get_user_agent() -> str:
    """
    Get User-Agent string for HTTP requests.
    
    Returns a User-Agent that identifies the Blender connector as a legitimate
    application to prevent Cloudflare from blocking requests with error 1010.
    
    Returns:
        str: User-Agent string in format "Speckle-Blender-Connector/version (Python/x.y)"
    """
    try:
        from pathlib import Path
        
        # Get the extension directory
        addon_dir = Path(__file__).parent.parent.parent
        
        # Try to read version from blender_manifest.toml
        manifest_path = addon_dir / "blender_manifest.toml"
        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                for line in f:
                    if line.startswith('version = '):
                        version = line.split('=')[1].strip().strip('"')
                        break
                else:
                    version = "3.0.0"
        else:
            version = "3.0.0"
    except Exception:
        # Fallback if we can't determine version
        version = "3.0.0"
    
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    return f"Speckle-Blender-Connector/{version} (Python/{python_version})"


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


def generate_challenge() -> str:
    """
    Generate a random 12-character alphanumeric challenge string.
    
    Returns:
        str: Random 12-character challenge string
    """
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(12))


class ThreadSafeAuthServer(HTTPServer):
    """
    Thread-safe HTTP server for Speckle authentication.
    
    Stores authentication state as instance variables protected by a lock
    to prevent race conditions between the server thread and main thread.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()
        self._server_url: Optional[str] = None
        self._challenge: Optional[str] = None
        self._auth_complete: bool = False
        self._auth_success: bool = False
        self._error_message: Optional[str] = None
        self._request_count: int = 0
    
    def get_server_url(self) -> Optional[str]:
        """Get server URL (thread-safe)."""
        with self._lock:
            return self._server_url
    
    def set_server_url(self, url: str) -> None:
        """Set server URL (thread-safe)."""
        with self._lock:
            self._server_url = url
    
    def get_challenge(self) -> Optional[str]:
        """Get challenge string (thread-safe)."""
        with self._lock:
            return self._challenge
    
    def set_challenge(self, challenge: str) -> None:
        """Set challenge string (thread-safe)."""
        with self._lock:
            self._challenge = challenge
    
    def is_auth_complete(self) -> bool:
        """Check if authentication is complete (thread-safe)."""
        with self._lock:
            return self._auth_complete
    
    def is_auth_successful(self) -> bool:
        """Check if authentication was successful (thread-safe)."""
        with self._lock:
            return self._auth_success
    
    def get_error_message(self) -> Optional[str]:
        """Get error message if authentication failed (thread-safe)."""
        with self._lock:
            return self._error_message
    
    def set_auth_success(self) -> None:
        """
        Mark authentication as successful (thread-safe).
        Sets auth_complete LAST to ensure atomic state update.
        """
        with self._lock:
            self._auth_success = True
            self._error_message = None
            self._auth_complete = True  # Set LAST to prevent partial reads
    
    def set_auth_failure(self, error_message: str) -> None:
        """
        Mark authentication as failed (thread-safe).
        Sets auth_complete LAST to ensure atomic state update.
        """
        with self._lock:
            self._auth_success = False
            self._error_message = error_message
            self._auth_complete = True  # Set LAST to prevent partial reads
    
    def increment_request_count(self) -> int:
        """Increment and return request count (thread-safe)."""
        with self._lock:
            self._request_count += 1
            return self._request_count
    
    def get_request_count(self) -> int:
        """Get current request count (thread-safe)."""
        with self._lock:
            return self._request_count


class SpeckleAuthHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for Speckle authentication flow.
    Handles two routes:
    - /auth/add-account?serverUrl=... : Initiates auth flow
    - / with ?access_code=... : Handles callback from Speckle
    
    Note: All state is stored on the ThreadSafeAuthServer instance (self.server)
    instead of class variables to ensure thread safety.
    """
    
    def log_message(self, format, *args):
        """Override to suppress default logging."""
        print(f"[Auth Server] {format % args}")
    
    def do_GET(self):
        """Handle GET requests."""
        self.server.increment_request_count()
        
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        if parsed_path.path == '/auth/add-account':
            self._handle_add_account(query_params)
        elif parsed_path.path == '/':
            self._handle_callback(query_params)
        else:
            self._send_error_response(404, "Not Found")
    
    def _handle_add_account(self, query_params: Dict[str, list]):
        """
        Handle the initial add-account request.
        Generates challenge and redirects to Speckle server.
        """
        # Get server URL from query params
        server_url = query_params.get('serverUrl', ['https://app.speckle.systems'])[0]
        self.server.set_server_url(server_url.rstrip('/'))
        
        # Generate challenge
        self.server.set_challenge(generate_challenge())
        
        # Construct redirect URL
        auth_url = f"{self.server.get_server_url()}/authn/verify/sdas/{self.server.get_challenge()}"
        
        print(f"[Auth Server] Redirecting to: {auth_url}")
        
        # Send redirect response
        self.send_response(302)
        self.send_header('Location', auth_url)
        self.end_headers()
    
    def _handle_callback(self, query_params: Dict[str, list]):
        """
        Handle the callback from Speckle server with access code.
        Exchanges code for tokens and saves account.
        """
        # Get access code from query params
        access_code_list = query_params.get('access_code', [])
        
        if not access_code_list:
            self._redirect_to_failure("fail-no-access-code")
            return
        
        access_code = access_code_list[0]
        
        try:
            # Exchange access code for tokens
            tokens = exchange_access_code_for_tokens(
                access_code,
                self.server.get_challenge(),
                self.server.get_server_url()
            )
            
            # Get user and server info
            user_info, server_info = get_user_and_server_info(
                tokens['token'],
                self.server.get_server_url()
            )
            
            # Save account
            save_account_to_storage(
                tokens['token'],
                tokens['refreshToken'],
                user_info,
                server_info
            )
            
            # Mark as successful (sets auth_complete LAST atomically)
            self.server.set_auth_success()
            
            # Redirect to success page
            self._redirect_to_success()
            
        except Exception as e:
            print(f"[Auth Server] Error during authentication: {e}")
            # Mark as failed (sets auth_complete LAST atomically)
            self.server.set_auth_failure(str(e))
            self._redirect_to_failure("fail")
    
    def _redirect_to_success(self):
        """Redirect browser to success page."""
        self.send_response(302)
        self.send_header('Location', 'https://www.speckle.systems/connector-auth/success')
        self.end_headers()
    
    def _redirect_to_failure(self, reason: str):
        """Redirect browser to failure page."""
        self.send_response(302)
        self.send_header('Location', f'https://www.speckle.systems/connector-auth/{reason}')
        self.end_headers()
    
    def _send_error_response(self, code: int, message: str):
        """Send an error response."""
        self.send_response(code)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(f"<html><body><h1>{code} {message}</h1></body></html>".encode())


def exchange_access_code_for_tokens(
    access_code: str,
    challenge: str,
    server_url: str
) -> Dict[str, str]:
    """
    Exchange access code and challenge for tokens.
    
    Args:
        access_code: The access code from Speckle callback
        challenge: The original challenge string
        server_url: The Speckle server URL
    
    Returns:
        Dict containing 'token' and 'refreshToken'
    
    Raises:
        AuthenticationError: If token exchange fails
    """
    if not challenge:
        raise AuthenticationError("No challenge available")
    
    # Prepare request body
    body = {
        'appId': 'sdas',
        'appSecret': 'sdas',
        'accessCode': access_code,
        'challenge': challenge
    }
    
    # Prepare request
    url = f"{server_url}/auth/token"
    data = json.dumps(body).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': get_user_agent()
    }
    
    try:
        request = Request(url, data=data, headers=headers)
        with urlopen(request, timeout=30) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            
            if 'token' not in response_data or 'refreshToken' not in response_data:
                raise AuthenticationError("Invalid response from token endpoint")
            
            return {
                'token': response_data['token'],
                'refreshToken': response_data['refreshToken']
            }
    
    except HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else "No error details"
        raise AuthenticationError(f"Failed to get token from {server_url}: {e.code} {error_body}")
    except URLError as e:
        raise AuthenticationError(f"Network error during token exchange: {e.reason}")
    except json.JSONDecodeError as e:
        raise AuthenticationError(f"Invalid JSON response from server: {e}")


def get_user_and_server_info(
    token: str,
    server_url: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Get user and server information using the auth token.
    
    Args:
        token: Bearer token
        server_url: The Speckle server URL
    
    Returns:
        Tuple of (user_info, server_info) dictionaries
    
    Raises:
        AuthenticationError: If GraphQL query fails
    """
    # Prepare GraphQL query
    query = """
    query {
        activeUser {
            id
            name
            email
            company
            avatar
        }
        serverInfo {
            name
            company
            adminContact
            description
            version
        }
    }
    """
    
    body = {'query': query}
    
    # Prepare request
    url = f"{server_url}/graphql"
    data = json.dumps(body).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'User-Agent': get_user_agent()
    }
    
    try:
        request = Request(url, data=data, headers=headers)
        with urlopen(request, timeout=30) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            
            if 'data' not in response_data:
                raise AuthenticationError("Invalid GraphQL response")
            
            data = response_data['data']
            
            if 'activeUser' not in data or 'serverInfo' not in data:
                raise AuthenticationError("Missing user or server info in response")
            
            user_info = data['activeUser']
            server_info = data['serverInfo']
            
            # Ensure server URL is set correctly
            server_info['url'] = server_url.rstrip('/')
            
            return user_info, server_info
    
    except HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else "No error details"
        raise AuthenticationError(f"Failed to get user info: {e.code} {error_body}")
    except URLError as e:
        raise AuthenticationError(f"Network error during user info request: {e.reason}")
    except json.JSONDecodeError as e:
        raise AuthenticationError(f"Invalid JSON response from GraphQL: {e}")


def save_account_to_storage(
    token: str,
    refresh_token: str,
    user_info: Dict[str, Any],
    server_info: Dict[str, Any]
) -> None:
    """
    Save account to the shared Speckle storage.
    
    Saves account directly to the Accounts.db SQLite database to ensure
    compatibility with specklepy and other Speckle connectors.
    
    Args:
        token: Bearer token
        refresh_token: Refresh token
        user_info: User information dictionary
        server_info: Server information dictionary
    
    Raises:
        AuthenticationError: If account save fails
    """
    try:
        import sqlite3
        import hashlib
        import os
        from specklepy.core.api.credentials import speckle_path_provider
        
        # Generate account ID (hash of email + server URL)
        account_id_string = f"{user_info['email']}-{server_info['url']}"
        account_id = hashlib.md5(account_id_string.encode()).hexdigest().upper()
        
        # Construct account object matching the expected format
        account_data = {
            "id": account_id,
            "token": token,
            "refreshToken": refresh_token,
            "isDefault": True,
            "isOnline": True,
            "serverInfo": {
                "name": server_info['name'],
                "company": server_info.get('company'),
                "version": server_info.get('version'),
                "description": server_info.get('description'),
                "url": server_info['url']
            },
            "userInfo": {
                "id": user_info['id'],
                "name": user_info['name'],
                "email": user_info['email'],
                "company": user_info.get('company'),
                "avatar": user_info.get('avatar')
            }
        }
        
        # Get database path
        speckle_folder = speckle_path_provider.user_speckle_folder_path()
        db_path = os.path.join(speckle_folder, 'Accounts.db')
        
        # Ensure the Speckle folder exists
        os.makedirs(speckle_folder, exist_ok=True)
        
        # Connect to database and save account
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS objects (
                    hash TEXT PRIMARY KEY,
                    content TEXT
                )
            ''')
            
            # If setting as default, remove default flag from other accounts
            if account_data['isDefault']:
                cursor.execute('SELECT hash, content FROM objects')
                for row in cursor.fetchall():
                    existing_id, existing_content = row
                    try:
                        existing_account = json.loads(existing_content)
                        if existing_account.get('isDefault', False):
                            existing_account['isDefault'] = False
                            cursor.execute(
                                'UPDATE objects SET content = ? WHERE hash = ?',
                                (json.dumps(existing_account), existing_id)
                            )
                    except json.JSONDecodeError:
                        # Skip malformed accounts
                        continue
            
            # Insert or replace the account
            cursor.execute(
                'INSERT OR REPLACE INTO objects (hash, content) VALUES (?, ?)',
                (account_id, json.dumps(account_data))
            )
            
            conn.commit()
        
        print(f"[Auth] Successfully saved account: {user_info['email']} @ {server_info['url']} (ID: {account_id})")
        
        # Track account creation event
        try:
            from specklepy.logging import metrics
            metrics.track(
                metrics.HOST_APP,
                "connector",
                "account",
                {"action": "add"}
            )
        except Exception as e:
            # Don't fail if metrics tracking fails
            print(f"[Auth] Failed to track metrics: {e}")
    
    except Exception as e:
        raise AuthenticationError(f"Failed to save account: {e}")


class AuthenticationServer:
    """
    Manages the local HTTP server for Speckle authentication.
    
    Runs the server in a background thread and provides methods to
    check status and shutdown.
    """
    
    def __init__(self, port: int = 29364):
        """
        Initialize the authentication server.
        
        Args:
            port: Port to run the server on (default: 29364)
        """
        self.port = port
        self.server: Optional[ThreadSafeAuthServer] = None
        self.thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()
    
    def start(self) -> bool:
        """
        Start the HTTP server in a background thread.
        
        Returns:
            bool: True if server started successfully, False otherwise
        """
        try:
            # Create thread-safe server (state initialized in constructor)
            self.server = ThreadSafeAuthServer(('127.0.0.1', self.port), SpeckleAuthHandler)
            
            # Start server in background thread
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()
            
            print(f"[Auth Server] Started on http://127.0.0.1:{self.port}")
            return True
        
        except OSError as e:
            if e.errno == 98 or e.errno == 10048:  # Address already in use
                print(f"[Auth Server] Port {self.port} is already in use. Is desktop service running?")
            else:
                print(f"[Auth Server] Failed to start server: {e}")
            return False
        except Exception as e:
            print(f"[Auth Server] Unexpected error starting server: {e}")
            return False
    
    def _run_server(self):
        """Run the server (called in background thread)."""
        try:
            # Set a timeout so handle_request doesn't block forever
            self.server.timeout = 0.5
            
            # Server should handle a maximum of 3 requests:
            # 1. /auth/add-account (redirect to Speckle)
            # 2. / callback (from Speckle with access_code)
            # 3. Maybe a favicon or other browser request
            # After that or when shutdown is signaled, stop
            max_requests = 5  # Allow a few extra for browser quirks
            
            while not self.shutdown_event.is_set() and self.server.get_request_count() < max_requests:
                self.server.handle_request()
                
                # If auth is complete, we can stop serving
                if self.server.is_auth_complete():
                    print("[Auth Server] Authentication complete, stopping server")
                    break
                    
        except Exception as e:
            print(f"[Auth Server] Error in server thread: {e}")
            self.server.set_auth_failure(f"Server thread crashed: {e}")
    
    def shutdown(self):
        """Shutdown the server and cleanup."""
        if self.server:
            self.shutdown_event.set()
            try:
                # Give the server thread a moment to see the shutdown event
                if self.thread and self.thread.is_alive():
                    self.thread.join(timeout=2.0)
                
                self.server.server_close()
            except Exception as e:
                print(f"[Auth Server] Error during shutdown: {e}")
            
            self.server = None
            self.thread = None
            print("[Auth Server] Shutdown complete")
    
    def is_complete(self) -> bool:
        """Check if authentication is complete."""
        return self.server.is_auth_complete() if self.server else False
    
    def is_successful(self) -> bool:
        """Check if authentication was successful."""
        return self.server.is_auth_successful() if self.server else False
    
    def get_error_message(self) -> Optional[str]:
        """Get error message if authentication failed."""
        return self.server.get_error_message() if self.server else None
    
    def open_auth_url(self, server_url: str = "https://app.speckle.systems"):
        """
        Open the authentication URL in the default browser.
        
        Args:
            server_url: Speckle server URL (default: https://app.speckle.systems)
        """
        # Trigger the add-account endpoint
        url = f"http://127.0.0.1:{self.port}/auth/add-account?serverUrl={server_url}"
        webbrowser.open(url)
        print("[Auth Server] Opening browser to initiate authentication...")

