"""Verify a Google Sign-In ID token (issued to our web client) using Google's tokeninfo endpoint."""
import httpx

from ..config import get_settings

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(Exception):
    pass


def verify_google_token(credential: str) -> dict:
    """Returns {email, name, sub}. Raises GoogleAuthError for anything that is not a valid token for this app."""
    client_id = get_settings().google_client_id
    if not client_id:
        raise GoogleAuthError("Google sign-in is not configured on this server.")
    try:
        r = httpx.get(TOKENINFO_URL, params={"id_token": credential}, timeout=8)
    except httpx.HTTPError as e:
        raise GoogleAuthError("Could not reach Google to verify your sign-in. Please try again.") from e
    if r.status_code != 200:
        raise GoogleAuthError("Google sign-in could not be verified. Please try again.")
    d = r.json()
    if d.get("aud") != client_id:  # token minted for a different app
        raise GoogleAuthError("This Google token was not issued for this application.")
    if d.get("iss") not in ISSUERS:
        raise GoogleAuthError("Unexpected token issuer.")
    if str(d.get("email_verified")).lower() != "true" or not d.get("email"):
        raise GoogleAuthError("Your Google email address is not verified.")
    return {"email": d["email"], "name": d.get("name") or "", "sub": d.get("sub", "")}
