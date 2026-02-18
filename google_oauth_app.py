# Copyright (c) 2024-2025 Suyash Vishwas Jadhav. All rights reserved.
# Project: EduEval - AI-Powered Automated Grading System
# Lead Developer & Architect: Suyash Vishwas Jadhav
# Module Contributor: VEDANT GOSAVI (Google OAuth Infrastructure)

import os
import json
import requests
from flask import Flask, redirect, request, session, url_for, jsonify
from oauthlib.oauth2 import WebApplicationClient

# Local development only: allow OAuth over HTTP
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Google OAuth Configuration (using values from your existing app.py)
GOOGLE_CLIENT_ID = os.environ.get(
    "GOOGLE_OAUTH_CLIENT_ID",
    "YOUR_GOOGLE_CLIENT_ID",
)
GOOGLE_CLIENT_SECRET = os.environ.get(
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "YOUR_GOOGLE_CLIENT_SECRET",
)
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()


app = Flask(__name__)
app.secret_key = os.environ.get("APP_SECRET_KEY", "dev-secret-change-me")
client = WebApplicationClient(GOOGLE_CLIENT_ID)


@app.route("/")
def index():
    return (
        "<h3>Google OAuth Demo</h3>"
        "<p><a href='/google-login'>Continue with Google</a></p>"
        "<p>After login, you will see your basic profile details.</p>"
    )


@app.route("/google-login")
def google_login():
    cfg = get_google_provider_cfg()
    authorization_endpoint = cfg["authorization_endpoint"]

    # This MUST match an authorized redirect URI in Google Cloud Console
    redirect_uri = "http://localhost:5000/auth/google/callback"

    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=redirect_uri,
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)


@app.route("/auth/google/callback")
def google_callback():
    code = request.args.get("code")
    if not code:
        return "Missing authorization code", 400

    cfg = get_google_provider_cfg()
    token_endpoint = cfg["token_endpoint"]

    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code,
    )

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return "Google OAuth is not configured (missing client credentials)", 500

    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    # Raise an error if token request failed
    try:
        token_response.raise_for_status()
    except Exception as e:
        return f"Token request failed: {e} - {token_response.text}", 502

    client.parse_request_body_response(json.dumps(token_response.json()))

    # Fetch user info
    userinfo_endpoint = cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    try:
        userinfo_response.raise_for_status()
    except Exception as e:
        return f"Failed to fetch userinfo: {e} - {userinfo_response.text}", 502

    userinfo = userinfo_response.json()
    if not userinfo.get("email_verified"):
        return "Email not verified by Google", 400

    # Minimal session example
    session["google_sub"] = userinfo.get("sub")
    session["email"] = userinfo.get("email")
    session["name"] = userinfo.get("given_name") or userinfo.get("name")

    return jsonify(
        {
            "message": "Login successful",
            "email": session["email"],
            "name": session.get("name"),
            "sub": session.get("google_sub"),
        }
    )


if __name__ == "__main__":
    # Run: python google_oauth_app.py
    # Then open: http://localhost:5000/
    app.run(host="0.0.0.0", port=5000, debug=True)


