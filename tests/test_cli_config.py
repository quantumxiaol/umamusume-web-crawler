import sys
from unittest.mock import patch, MagicMock, AsyncMock
from umamusume_web_crawler.config import config
from umamusume_web_crawler.cli import main

def test_cli_google_api_key_override():
    test_key = "TEST_API_KEY_123"
    test_cse = "TEST_CSE_ID_456"
    
    # Store original config values to restore later
    original_api_key = config.google_api_key
    original_cse_id = config.google_cse_id
    
    try:
        # Mock sys.argv
        with patch.object(sys, "argv", ["umamusume-crawler", "--url", "http://example.com", "--google-api-key", test_key, "--google-cse-id", test_cse]):
            # Mock _run to prevent actual execution, using AsyncMock because it's awaited
            with patch("umamusume_web_crawler.cli._run", new_callable=AsyncMock) as mock_run:
                # Mock load_dotenv to avoid side effects from local .env files during this specific test
                with patch("umamusume_web_crawler.cli.load_dotenv"):
                    main()
                    
                    assert config.google_api_key == test_key
                    assert config.google_cse_id == test_cse
                    mock_run.assert_called_once()
    finally:
        # Restore configuration
        config.google_api_key = original_api_key
        config.google_cse_id = original_cse_id
