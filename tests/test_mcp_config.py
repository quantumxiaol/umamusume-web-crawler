import sys
from unittest.mock import patch
from umamusume_web_crawler.mcp.server import main

def test_mcp_server_load_dotenv():
    # Mock load_dotenv to verify it's called
    with patch("umamusume_web_crawler.mcp.server.load_dotenv") as mock_load_dotenv:
        # Mock sys.argv to simulate running the command without args (default mode)
        with patch.object(sys, "argv", ["umamusume-mcp"]):
             # Mock mcp.run to prevent actual execution
             with patch("umamusume_web_crawler.mcp.server.mcp.run") as mock_run:
                 main()
                 mock_load_dotenv.assert_called_once()
                 mock_run.assert_called_once()
