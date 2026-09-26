"""Static guardrails for the local-only Windows Buzz offer package."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_buzz_setup_keeps_secrets_local_and_port_loopback():
    script = (ROOT / 'scripts/optional/Setup-BuzzLocal.ps1').read_text()
    assert '127.0.0.1:3000:3000' in script
    assert 'BUZZ_ALLOW_ALL_USERS=false' in script
    assert 'BUZZ_REQUIRE_MENTION=true' in script
    assert 'BUZZ_PRIVATE_KEY=$agentSecret' in script
    assert 'Write-Host "Agent PUBLIC hex key' in script
    assert 'Write-Host $agentSecret' not in script
    assert 'if (Test-Path $composeEnv)' in script
    assert 'Set-Acl -Path $path' in script


def test_buzz_guide_example_is_private_and_enabled():
    guide = (ROOT / 'scripts/optional/README-BuzzLocal.md').read_text()
    example = guide.split('```yaml\n', 1)[1].split('\n```', 1)[0]
    buzz = yaml.safe_load(example)['gateway']['platforms']['buzz']
    assert buzz['enabled'] is True
    assert buzz['extra']['allow_all_users'] is False
    assert buzz['extra']['require_mention'] is True
