"""Tests de la redaction de secrets (F-105, P8-bis — directive « Redact » mattpocock).

Valide `graph_orchestrator/redaction.py` (deterministe, 0 LLM) et son
branchement dans `feedback_utils.truncate_output` (point de passage unique du
feedback vers le LLM : Tester→Judge, Judge→Coder, bash_command).

Deux volets :
- REDACTION : API keys (sk-/ghp-/AKIA/xox/JWT), en-têtes Bearer, identifiants
  d'URL, affectations nommées (password/api_key/client_secret...), blocs PEM
  privés → <REDACTED>.
- ANTI-CORRUPTION (fail-open) : du code (a.b, f(), $VAR, %VAR%) n'est JAMAIS
  redacté — priorité à la lisibilité du code montré au Judge ; idempotence ;
  opt-out REDACTION_ENABLED.
"""
from unittest.mock import patch

from graph_orchestrator.feedback_utils import truncate_output
from graph_orchestrator.redaction import REDACTED, redact_secrets


# ==========================================
# Tokens avec préfixe réservé
# ==========================================
def test_redacts_openai_style_key():
    out = redact_secrets("Erreur API 401: clé sk-abc123def456ghi789jkl012 invalide")
    assert "sk-abc123def456ghi789jkl012" not in out
    assert REDACTED in out


def test_redacts_github_pat():
    token = "ghp_" + "a1B2c3D4e5" * 4  # 40 chars
    out = redact_secrets(f"git push failed for {token}")
    assert token not in out


def test_redacts_aws_access_key():
    out = redact_secrets("config AWS: AKIAIOSFODNN7EXAMPLE et region eu-west-1")
    assert "AKIAIOSFODNN7EXAMPLE" not in out


def test_redacts_slack_token():
    out = redact_secrets("xoxb-1234567890-abcdef en sortie console")
    assert "xoxb-1234567890-abcdef" not in out


def test_redacts_jwt():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c"
    out = redact_secrets(f"Authorization header reçu : {jwt}")
    assert "eyJhbGciOiJIUzI1" not in out


def test_no_short_random_string_redacted():
    """Un identifiant court sans préfixe réservé n'est pas touché (anti-bruit)."""
    text = "variable abcd1234 non secrète"
    assert redact_secrets(text) == text


# ==========================================
# En-têtes d'autorisation / URLs
# ==========================================
def test_redacts_bearer_header():
    out = redact_secrets("curl -H 'Authorization: Bearer abcdef1234567890abcdef' https://x")
    assert "abcdef1234567890abcdef" not in out
    assert REDACTED in out


def test_redacts_url_credentials_keeps_user():
    out = redact_secrets("GET https://deploy:SuperSecret99@example.com/api → 200")
    assert "SuperSecret99" not in out
    assert "deploy:" in out  # l'utilisateur est conservé (diagnostic)
    assert "example.com" in out


# ==========================================
# Affectations nommées
# ==========================================
def test_redacts_password_assignment_shell():
    out = redact_secrets("PGPASSWORD=monsupermotdepasse psql -c 'select 1'")
    assert "monsupermotdepasse" not in out
    assert "PGPASSWORD=" in out


def test_redacts_password_yaml_with_quotes():
    out = redact_secrets('database:\n  password: "chaise-bleue-42"')
    assert "chaise-bleue-42" not in out
    assert "password" in out  # le nom reste visible


def test_redacts_api_key_and_client_secret():
    out = redact_secrets("api_key: 8f14e45fceea167a5a36dedd4bea2543\nclient_secret=verysecretvalue123")
    assert "8f14e45fceea167a5a36dedd4bea2543" not in out
    assert "verysecretvalue123" not in out


def test_redacts_access_token_assignment():
    out = redact_secrets("access_token = abcdef123456789abcdef456 retourné par OAuth")
    assert "abcdef123456789abcdef456" not in out


def test_redacts_env_var_prefixed_name():
    """PGPASSWORD / OS_PASSWORD : le nom-secret est un SUFFIXE d'identifiant plus
    long — le nom complet est conservé, la valeur redactée."""
    out = redact_secrets("OS_PASSWORD=azure-diamond-42 psql -h db")
    assert "azure-diamond-42" not in out
    assert "OS_PASSWORD" in out


# ==========================================
# Clés privées PEM
# ==========================================
_PRIVATE_BLOCK = (
    "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA7kFn\n-----END RSA PRIVATE KEY-----"
)


def test_redacts_private_key_block_entirely():
    out = redact_secrets(f"certificat rejeté :\n{_PRIVATE_BLOCK}\nfin")
    assert "MIIEpAIBAAKCAQEA7kFn" not in out
    assert "BEGIN RSA PRIVATE KEY" not in out  # tout le bloc est remplacé


def test_keeps_public_key_block():
    """Un bloc PUBLIC (certificat) n'est pas un secret → intact."""
    pub = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkq\n-----END PUBLIC KEY-----"
    assert redact_secrets(pub) == pub


# ==========================================
# Anti-corruption : du code n'est JAMAIS redacté (fail-open)
# ==========================================
def test_keeps_env_var_references():
    """Directive mattpocock : les loops de repro tournent sur des env vars —
    les RÉFÉRENCES ($VAR, %VAR%) ne sont pas des secrets."""
    text = "PGPASSWORD=$DB_PASSWORD psql -h db\npassword: %APP_PW%"
    assert redact_secrets(text) == text


def test_keeps_code_like_values():
    """Valeurs avec accès attribut / appel / index / interpolation : du code."""
    samples = [
        "password: request.body.password",
        "const token = get_token();",
        "api_key: config.keys[0]",
        "password: `${user}_pw`",
        "secret: os.environ['SECRET']",
    ]
    for text in samples:
        assert redact_secrets(text) == text, text


def test_keeps_short_values():
    """< 8 caractères : trop court pour un secret réel, souvent un placeholder."""
    assert redact_secrets("pwd=abc123 status=ok") == "pwd=abc123 status=ok"


def test_not_matching_tokenizer():
    """'tokenizer' contient 'token' mais n'est pas une affectation de secret."""
    text = "tokenizer: AutoTokenizer.from_pretrained(model)"
    assert redact_secrets(text) == text


def test_idempotent():
    """Redacter 2 fois = redacter 1 fois (le placeholder n'est pas re-touché)."""
    once = redact_secrets("password=hunter2hunter2 & Bearer abcdef1234567890abcd")
    assert redact_secrets(once) == once


def test_empty_and_none():
    assert redact_secrets("") == ""
    assert redact_secrets(None) == ""


# ==========================================
# Branchement truncate_output (point unique vers le LLM)
# ==========================================
def test_truncate_output_redacts_short_text():
    """Le chemin court (early return sans troncature) redact aussi — un secret
    dans une sortie courte doit être masqué exactement comme dans une longue."""
    out = truncate_output("clé sk-abc123def456ghi789jkl012 rejetée", max_chars=500)
    assert "sk-abc123def456ghi789jkl012" not in out


def test_truncate_output_redacts_long_text():
    long_text = ("ligne de log normale\n" * 40) + "Authorization: Bearer abcdef1234567890abcdef\n"
    out = truncate_output(long_text, head_lines=5, tail_lines=5, max_chars=2000)
    assert "abcdef1234567890abcdef" not in out


def test_truncate_output_opt_out():
    """REDACTION_ENABLED=false → comportement historique (aucune redaction)."""
    with patch("graph_orchestrator.feedback_utils.settings") as mock_settings:
        mock_settings.redaction_enabled = False
        out = truncate_output("clé sk-abc123def456ghi789jkl012", max_chars=500)
    assert "sk-abc123def456ghi789jkl012" in out


def test_truncate_output_empty_untouched():
    assert truncate_output(None) == ""
