"""
Speckle authentication module for Blender connector.

Implements OAuth-style authentication flow with a local HTTP server,
eliminating the dependency on the desktop service.
"""

import errno
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


# Speckle Blender dedicated app constants (registered server-side)
SPECKLE_APP_ID = "sblndrdui"  # Dedicated app ID for Blender connector
SPECKLE_AUTH_PORT = 29365  # Port for local auth callback server


def get_user_agent() -> str:
    """Get User-Agent string identifying the Blender connector to prevent Cloudflare blocking."""
    try:
        from pathlib import Path

        # Get the extension directory
        addon_dir = Path(__file__).parent.parent.parent

        # Try to read version from blender_manifest.toml
        manifest_path = addon_dir / "blender_manifest.toml"
        if manifest_path.exists():
            with open(manifest_path, "r") as f:
                for line in f:
                    if line.startswith("version = "):
                        version = line.split("=")[1].strip().strip('"')
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
    """Generate a random 12-character alphanumeric challenge string."""
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(12))


class ThreadSafeAuthServer(HTTPServer):
    """Thread-safe HTTP server for Speckle authentication with locked state management."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()
        self._server_url: Optional[str] = None
        self._challenge: Optional[str] = None
        self._auth_complete: bool = False
        self._auth_success: bool = False
        self._error_message: Optional[str] = None
        self._request_count: int = 0

    @property
    def server_url(self) -> Optional[str]:
        with self._lock:
            return self._server_url

    @server_url.setter
    def server_url(self, value: str) -> None:
        with self._lock:
            self._server_url = value

    @property
    def challenge(self) -> Optional[str]:
        with self._lock:
            return self._challenge

    @challenge.setter
    def challenge(self, value: str) -> None:
        with self._lock:
            self._challenge = value

    @property
    def is_complete(self) -> bool:
        with self._lock:
            return self._auth_complete

    @property
    def is_successful(self) -> bool:
        with self._lock:
            return self._auth_success

    @property
    def error_message(self) -> Optional[str]:
        with self._lock:
            return self._error_message

    def set_auth_success(self) -> None:
        """Mark authentication as successful (sets auth_complete LAST for atomicity)."""
        with self._lock:
            self._auth_success = True
            self._error_message = None
            self._auth_complete = True  # Set LAST to prevent partial reads

    def set_auth_failure(self, error_message: str) -> None:
        """Mark authentication as failed (sets auth_complete LAST for atomicity)."""
        with self._lock:
            self._auth_success = False
            self._error_message = error_message
            self._auth_complete = True  # Set LAST to prevent partial reads

    def increment_request_count(self) -> int:
        """Increment and return request count."""
        with self._lock:
            self._request_count += 1
            return self._request_count

    @property
    def request_count(self) -> int:
        with self._lock:
            return self._request_count


class SpeckleAuthHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Speckle authentication flow with /auth/add-account and callback routes."""

    def log_message(self, format, *args):
        print(f"[Auth Server] {format % args}")

    def do_GET(self):
        self.server.increment_request_count()

        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)

        if parsed_path.path == "/auth/add-account":
            self._handle_add_account(query_params)
        elif parsed_path.path == "/":
            self._handle_callback(query_params)
        else:
            self._send_error_response(404, "Not Found")

    def _handle_add_account(self, query_params: Dict[str, list]):
        """Handle initial add-account request, generate challenge and redirect to Speckle server."""
        # Get server URL from query params
        server_url = query_params.get("serverUrl", ["https://app.speckle.systems"])[0]
        self.server.server_url = server_url.rstrip("/")

        # Generate challenge
        self.server.challenge = generate_challenge()

        # Construct redirect URL
        auth_url = f"{self.server.server_url}/authn/verify/{SPECKLE_APP_ID}/{self.server.challenge}"

        print(f"[Auth Server] Redirecting to: {auth_url}")

        # Send redirect response
        self.send_response(302)
        self.send_header("Location", auth_url)
        self.end_headers()

    def _handle_callback(self, query_params: Dict[str, list]):
        """Handle callback from Speckle server, exchange access code for tokens and save account."""
        # Get access code from query params
        access_code_list = query_params.get("access_code", [])

        if not access_code_list:
            self._redirect_to_failure("fail-no-access-code")
            return

        access_code = access_code_list[0]

        try:
            # Exchange access code for tokens
            tokens = exchange_access_code_for_tokens(
                access_code, self.server.challenge, self.server.server_url
            )

            # Get user and server info
            user_info, server_info = get_user_and_server_info(
                tokens["token"], self.server.server_url
            )

            # Save account
            save_account_to_storage(
                tokens["token"], tokens["refreshToken"], user_info, server_info
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
        self.send_response(302)
        self.send_header(
            "Location", "https://www.speckle.systems/connector-auth/success"
        )
        self.end_headers()

    def _redirect_to_failure(self, reason: str):
        self.send_response(302)
        self.send_header(
            "Location", f"https://www.speckle.systems/connector-auth/{reason}"
        )
        self.end_headers()

    def _send_error_response(self, code: int, message: str):
        self.send_response(code)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(
            f"<html><body><h1>{code} {message}</h1></body></html>".encode()
        )


def _handle_auth_error(e: AuthenticationError) -> None:
    """Re-raise AuthenticationError with user-friendly message for network errors."""
    error_str = str(e)
    if "Network error" in error_str or "URLError" in error_str:
        raise AuthenticationError(
            "Network error while authenticating. Please check your internet connection."
        ) from e
    raise


def _post_json(
    url: str,
    body: Dict[str, Any],
    auth_token: Optional[str] = None,
    error_context: str = "Request",
) -> Dict[str, Any]:
    """Make POST request with JSON body and optional Bearer token."""
    # Encode body as JSON
    data = json.dumps(body).encode("utf-8")

    # Build headers
    headers = {"Content-Type": "application/json", "User-Agent": get_user_agent()}

    # Add Authorization header if token provided
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        request = Request(url, data=data, headers=headers)
        with urlopen(request, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
            return response_data

    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else "No error details"
        raise AuthenticationError(f"{error_context} failed: {e.code} {error_body}")
    except URLError as e:
        raise AuthenticationError(f"Network error during {error_context}: {e.reason}")
    except json.JSONDecodeError as e:
        raise AuthenticationError(f"Invalid JSON response from {error_context}: {e}")


def exchange_access_code_for_tokens(
    access_code: str, challenge: str, server_url: str
) -> Dict[str, str]:
    """Exchange access code and challenge for authentication tokens."""
    if not challenge:
        raise AuthenticationError("No challenge available")

    # Prepare request body
    body = {
        "appId": SPECKLE_APP_ID,
        "appSecret": SPECKLE_APP_ID,
        "accessCode": access_code,
        "challenge": challenge,
    }

    # Make POST request
    url = f"{server_url}/auth/token"
    try:
        response_data = _post_json(url, body, error_context="token exchange")
    except AuthenticationError as e:
        _handle_auth_error(e)

    # Validate response
    if "token" not in response_data or "refreshToken" not in response_data:
        raise AuthenticationError("Invalid response from token endpoint")

    return {
        "token": response_data["token"],
        "refreshToken": response_data["refreshToken"],
    }


def get_user_and_server_info(
    token: str, server_url: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Get user and server information using GraphQL query with auth token."""
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

    body = {"query": query}

    # Make POST request
    url = f"{server_url}/graphql"
    try:
        response_data = _post_json(
            url, body, auth_token=token, error_context="user info request"
        )
    except AuthenticationError as e:
        _handle_auth_error(e)

    # Validate response
    if "data" not in response_data:
        raise AuthenticationError("Invalid GraphQL response")

    data = response_data["data"]

    if "activeUser" not in data or "serverInfo" not in data:
        raise AuthenticationError("Missing user or server info in response")

    user_info = data["activeUser"]
    server_info = data["serverInfo"]

    # Ensure server URL is set correctly
    server_info["url"] = server_url.rstrip("/")

    return user_info, server_info


def save_account_to_storage(
    token: str,
    refresh_token: str,
    user_info: Dict[str, Any],
    server_info: Dict[str, Any],
) -> None:
    """Save account to Accounts.db SQLite database for compatibility with specklepy."""
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
                "name": server_info["name"],
                "company": server_info.get("company"),
                "version": server_info.get("version"),
                "description": server_info.get("description"),
                "url": server_info["url"],
            },
            "userInfo": {
                "id": user_info["id"],
                "name": user_info["name"],
                "email": user_info["email"],
                "company": user_info.get("company"),
                "avatar": user_info.get("avatar"),
            },
        }

        # Get database path
        speckle_folder = speckle_path_provider.user_speckle_folder_path()
        db_path = os.path.join(speckle_folder, "Accounts.db")

        # Ensure the Speckle folder exists
        os.makedirs(speckle_folder, exist_ok=True)

        # Connect to database and save account
        # Use IMMEDIATE isolation level to acquire write lock immediately,
        # preventing race conditions in concurrent account additions
        conn = sqlite3.connect(db_path, isolation_level="IMMEDIATE")
        try:
            with conn:
                cursor = conn.cursor()

                # Create table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS objects (
                        hash TEXT PRIMARY KEY,
                        content TEXT
                    )
                """)

                # If setting as default, remove default flag from other accounts
                # Use batch update to make the operation more atomic
                if account_data["isDefault"]:
                    cursor.execute("SELECT hash, content FROM objects")
                    rows = cursor.fetchall()

                    # Build list of updates to execute in batch
                    updates = []
                    for existing_id, existing_content in rows:
                        try:
                            existing_account = json.loads(existing_content)
                            if existing_account.get("isDefault", False):
                                existing_account["isDefault"] = False
                                updates.append(
                                    (json.dumps(existing_account), existing_id)
                                )
                        except json.JSONDecodeError:
                            # Skip malformed accounts
                            continue

                    # Execute all updates in batch for better atomicity
                    if updates:
                        cursor.executemany(
                            "UPDATE objects SET content = ? WHERE hash = ?", updates
                        )

                # Insert or replace the account
                cursor.execute(
                    "INSERT OR REPLACE INTO objects (hash, content) VALUES (?, ?)",
                    (account_id, json.dumps(account_data)),
                )

                conn.commit()
        finally:
            conn.close()

        print(
            f"[Auth] Successfully saved account: {user_info['email']} @ {server_info['url']} (ID: {account_id})"
        )

        # Track account creation event
        try:
            from specklepy.logging import metrics

            metrics.track(metrics.HOST_APP, "connector", "account", {"action": "add"})
        except Exception as e:
            # Don't fail if metrics tracking fails
            print(f"[Auth] Failed to track metrics: {e}")

    except Exception as e:
        raise AuthenticationError(f"Failed to save account: {e}")


class AuthenticationServer:
    """Manages local HTTP server for Speckle authentication in a background thread."""

    def __init__(self, port: int = SPECKLE_AUTH_PORT):
        self.port = port
        self.server: Optional[ThreadSafeAuthServer] = None
        self.thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()

    def start(self) -> bool:
        """Start HTTP server in background thread."""
        try:
            # Create thread-safe server (state initialized in constructor)
            self.server = ThreadSafeAuthServer(
                ("127.0.0.1", self.port), SpeckleAuthHandler
            )

            # Start server in background thread
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()

            print(f"[Auth Server] Started on http://127.0.0.1:{self.port}")
            return True

        except OSError as e:
            if e.errno in (errno.EADDRINUSE, 10048):  # Address already in use
                print(f"[Auth Server] Port {self.port} is already in use.")
            else:
                print(f"[Auth Server] Failed to start server: {e}")
            return False
        except Exception as e:
            print(f"[Auth Server] Unexpected error starting server: {e}")
            return False

    def _run_server(self):
        try:
            # Set a timeout so handle_request doesn't block forever
            self.server.timeout = 0.5

            # Server should handle a maximum of 3 requests:
            # 1. /auth/add-account (redirect to Speckle)
            # 2. / callback (from Speckle with access_code)
            # 3. Maybe a favicon or other browser request
            # After that or when shutdown is signaled, stop
            max_requests = 5  # Allow a few extra for browser quirks

            while (
                not self.shutdown_event.is_set()
                and self.server.request_count < max_requests
            ):
                self.server.handle_request()

                # If auth is complete, we can stop serving
                if self.server.is_complete:
                    print("[Auth Server] Authentication complete, stopping server")
                    break

        except Exception as e:
            print(f"[Auth Server] Error in server thread: {e}")
            self.server.set_auth_failure(f"Server thread crashed: {e}")

    def shutdown(self):
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
        return self.server.is_complete if self.server else False

    def is_successful(self) -> bool:
        return self.server.is_successful if self.server else False

    def get_error_message(self) -> Optional[str]:
        return self.server.error_message if self.server else None

    def open_auth_url(self, server_url: str = "https://app.speckle.systems"):
        """Open authentication URL in browser to initiate auth flow."""
        # Trigger the add-account endpoint
        url = f"http://127.0.0.1:{self.port}/auth/add-account?serverUrl={server_url}"
        webbrowser.open(url)
        print("[Auth Server] Opening browser to initiate authentication...")
