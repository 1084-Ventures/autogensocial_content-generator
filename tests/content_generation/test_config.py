import pytest
from unittest.mock import patch, MagicMock
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import ResourceNotFoundError
from blueprints.config import Config

@pytest.fixture
def mock_key_vault():
    """Create a mock Key Vault client."""
    with patch('azure.keyvault.secrets.SecretClient') as mock_kv:
        mock_client = MagicMock()
        mock_kv.return_value = mock_client
        yield mock_client

@pytest.fixture
def config(mock_key_vault):
    """Create a Config instance with mocked Key Vault."""
    with patch('os.getenv') as mock_getenv:
        mock_getenv.side_effect = {
            'KEY_VAULT_URL': 'https://dummy.vault.azure.net',
            'COSMOS_DB_CONNECTION_STRING': 'dummy_connection',
            'COSMOS_DB_NAME': 'dummy_db',
            'COSMOS_DB_CONTAINER_BRAND': 'brands',
            'COSMOS_DB_CONTAINER_TEMPLATE': 'templates',
            'COSMOS_DB_CONTAINER_POSTS': 'posts',
            'OPENAI_API_KEY': 'dummy_key'
        }.get
        config = Config()
        config._initialized = False  # Reset for testing
        config.__init__()
        return config

def test_config_singleton():
    """Test that Config is a singleton."""
    config1 = Config()
    config2 = Config()
    assert config1 is config2

def test_config_key_vault_initialization(mock_key_vault):
    """Test Config initialization with Key Vault."""
    with patch('os.getenv', return_value='https://dummy.vault.azure.net'):
        config = Config()
        assert config._secret_client is not None

def test_config_fallback_to_env_vars(config):
    """Test fallback to environment variables when Key Vault is not available."""
    assert config.cosmos_connection_string == 'dummy_connection'
    assert config.cosmos_db_name == 'dummy_db'
    assert config.cosmos_container_brand == 'brands'
    assert config.openai_api_key == 'dummy_key'

def test_config_key_vault_secrets(config, mock_key_vault):
    """Test retrieving secrets from Key Vault."""
    mock_secret = MagicMock()
    mock_secret.value = 'vault_secret'
    mock_key_vault.get_secret.return_value = mock_secret
    
    # Override environment variable with Key Vault secret
    config._secret_client = mock_key_vault
    assert config.cosmos_connection_string == 'vault_secret'
    mock_key_vault.get_secret.assert_called_with('COSMOS-CONNECTION-STRING')

def test_config_key_vault_error_handling(config, mock_key_vault):
    """Test handling Key Vault errors gracefully."""
    mock_key_vault.get_secret.side_effect = ResourceNotFoundError('Secret not found')
    
    # Should fall back to environment variable
    config._secret_client = mock_key_vault
    assert config.cosmos_connection_string == 'dummy_connection'