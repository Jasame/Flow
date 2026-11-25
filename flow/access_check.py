"""The xmc.hk console's sign-in token (Cloudflare Access): who is asking, proven, not just said.

The console sits behind Cloudflare Access. Access adds two headers to every request it lets through: the email it
signed in (Cf-Access-Authenticated-User-Email) and a token it signed (Cf-Access-Jwt-Assertion, a JWT, RS256). With
FLOW_ACCESS_AUD (the Access application's AUD tag) and FLOW_ACCESS_TEAM (the team's domain, e.g.
<team>.cloudflareaccess.com) set, flow_admin.py takes the operator's email from a token that verifies here and refuses
the request otherwise: a header alone, from anywhere that reaches the console without Access, proves nothing. Without
the two settings, nothing changes (the header is read as before), so the switch is a configuration step on the server.

Checked: RS256 signature against the team's public keys (https://<team>/cdn-cgi/access/certs, kept an hour, fetched
again for a key not seen yet at most once a minute), aud contains FLOW_ACCESS_AUD, iss is the team, exp/nbf with a
minute of leeway, and an email claim. Standard library only (RSA PKCS#1 v1.5 verification is a modular power).
"""
import base64, hashlib, json, os, threading, time, urllib.request

LEEWAY = 60
KEYS_TTL, REFETCH_GAP = 3600, 60
SHA256_INFO = bytes.fromhex('3031300d060960864801650304020105000420')  # DigestInfo prefix for SHA-256 (RFC 8017)
_cache = {'keys': {}, 'at': 0.0, 'tried': 0.0}
_lock = threading.Lock()


def settings():
    """(aud, team) when the check is on, else None."""
    aud, team = os.getenv('FLOW_ACCESS_AUD', '').strip(), os.getenv('FLOW_ACCESS_TEAM', '').strip().rstrip('/')
    if not aud or not team:
        return None
    return aud, team.replace('https://', '')


def _b64(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def _int(s):
    return int.from_bytes(_b64(s), 'big')


def fetch_keys(team):
    """{kid: (n, e)} from the team's certs address."""
    with urllib.request.urlopen(f'https://{team}/cdn-cgi/access/certs', timeout=10) as r:
        doc = json.loads(r.read())
    return {k['kid']: (_int(k['n']), _int(k['e'])) for k in doc.get('keys', []) if k.get('kty') == 'RSA' and k.get('kid')}


def _key(team, kid, now, fetch):
    with _lock:
        fresh = now - _cache['at'] < KEYS_TTL
        if kid in _cache['keys'] and fresh:
            return _cache['keys'][kid]
        if not fresh or now - _cache['tried'] > REFETCH_GAP:  # an unknown kid: the team rotated its keys
            _cache['tried'] = now
            try:
                _cache['keys'], _cache['at'] = fetch(team), now
            except Exception:
                pass  # keep what there is; the request fails below if its key is not among them
        return _cache['keys'].get(kid)


def _rsa_ok(n, e, signed, sig):
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return False
    em = pow(int.from_bytes(sig, 'big'), e, n).to_bytes(k, 'big')
    t = SHA256_INFO + hashlib.sha256(signed).digest()
    expected = b'\x00\x01' + b'\xff' * (k - len(t) - 3) + b'\x00' + t
    return len(expected) == k and em == expected


def verify(token, aud, team, now=None, fetch=None):
    """The token's email when it is valid for this application, else None."""
    now, fetch = now or time.time(), fetch or fetch_keys
    try:
        h64, p64, s64 = str(token or '').split('.')
        header, claims = json.loads(_b64(h64)), json.loads(_b64(p64))
        if header.get('alg') != 'RS256':
            return None
        key = _key(team, header.get('kid'), now, fetch)
        if not key or not _rsa_ok(key[0], key[1], f'{h64}.{p64}'.encode(), _b64(s64)):
            return None
        auds = claims.get('aud') if isinstance(claims.get('aud'), list) else [claims.get('aud')]
        if aud not in auds or claims.get('iss') != f'https://{team}':
            return None
        if float(claims.get('exp', 0)) < now - LEEWAY or float(claims.get('nbf', 0)) > now + LEEWAY:
            return None
        email = str(claims.get('email') or '').strip().lower()
        return email[:200] or None
    except Exception:
        return None
