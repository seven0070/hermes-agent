"""Local classifier cannot grant actions and defaults to the primary model."""
from pathlib import Path
from unittest.mock import patch
from agent.decision_swarm import classify, choose_tier, train

ROOT = Path(__file__).resolve().parents[2] / 'agent/decision_swarm'

def test_seed_models_available_without_network():
    assert classify('Hello there', ROOT / 'models')['intent']['label'] == 'conversation'


def test_fallback_paths():
    cfg = {'enabled': True, 'fast_model': 'gpt-5.4-mini', 'model_dir': str(ROOT / 'models'), 'threshold': .85}
    assert choose_tier('Hello there', cfg) == 'fast'
    for text in ('Book a restaurant for tonight', 'Send the invoice to Sam', 'https://example.com', '/model x'):
        assert choose_tier(text, cfg) == 'primary'
    assert choose_tier('Hello there', cfg, explicit_model=True) == 'primary'
    assert choose_tier('Hello there', {'enabled': False, 'fast_model': 'x'}) == 'primary'
    with patch('agent.decision_swarm.classify', return_value=None):
        assert choose_tier('Hello there', cfg) == 'primary'


def test_gateway_routes_only_with_opt_in():
    from gateway.run import GatewayRunner
    runner = object.__new__(GatewayRunner)
    runner.config = {'decision_swarm': {'enabled': True, 'fast_model': 'gpt-5.4-mini', 'fast_provider': 'openrouter', 'threshold': .85}}
    runner._service_tier = None
    runtime = {'provider': 'openrouter', 'api_key': 'secret', 'base_url': 'https://openrouter.ai/api/v1'}
    with patch('gateway.run._load_gateway_config', return_value=runner.config):
        route = runner._resolve_turn_agent_config('Hello there', 'gpt-5.4', runtime)
        explicit_route = runner._resolve_turn_agent_config('Hello there', 'gpt-5.4', runtime, explicit_model=True)
        action_route = runner._resolve_turn_agent_config('Send a message', 'gpt-5.4', runtime)
    assert route['model'] == 'gpt-5.4-mini'
    assert route['runtime']['api_key'] == 'secret'
    assert explicit_route['model'] == 'gpt-5.4'
    assert action_route['model'] == 'gpt-5.4'


def test_training_from_reviewed_data(tmp_path):
    train(ROOT / 'seed.tsv', tmp_path)
    assert classify('Hello there', tmp_path)['tier']['label'] == 'fast'
