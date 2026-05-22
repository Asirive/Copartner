import os
import unittest
from unittest.mock import MagicMock, patch
from core.gemini_client import GeminiClient

class TestGeminiClient(unittest.TestCase):
    """
    Unit tests for the GeminiClient class using mock client interfaces.
    """
    @patch('core.gemini_client.genai.Client')
    def test_client_init_success(self, mock_client_class):
        # Should initialize correctly when given an API key
        client = GeminiClient(api_key="mock-key-123")
        self.assertEqual(client.api_key, "mock-key-123")
        mock_client_class.assert_called_once_with(api_key="mock-key-123")

    @patch.dict(os.environ, {}, clear=True)
    def test_client_init_missing_key(self):
        # Should raise ValueError when key is completely missing
        with self.assertRaises(ValueError):
            GeminiClient(api_key=None)

    @patch('core.gemini_client.genai.Client')
    def test_generate_content(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_response = MagicMock()
        mock_response.text = "Mocked Response Text"
        mock_instance.models.generate_content.return_value = mock_response

        client = GeminiClient(api_key="mock-key")
        result = client.generate_content("test query", use_pro=False)

        self.assertEqual(result, "Mocked Response Text")
        mock_instance.models.generate_content.assert_called_once()

    @patch('core.gemini_client.genai.Client')
    def test_get_embeddings(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        
        # Mocking list of embeddings with lists of values
        mock_embedding_obj = MagicMock()
        mock_embedding_obj.values = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.embeddings = [mock_embedding_obj]
        mock_instance.models.embed_content.return_value = mock_response

        client = GeminiClient(api_key="mock-key")
        result = client.get_embeddings("test query")

        self.assertEqual(result, [[0.1, 0.2, 0.3]])
        mock_instance.models.embed_content.assert_called_once()

    @patch('core.gemini_client.genai.Client')
    def test_count_tokens(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_response = MagicMock()
        mock_response.total_tokens = 42
        mock_instance.models.count_tokens.return_value = mock_response

        client = GeminiClient(api_key="mock-key")
        result = client.count_tokens("test query", use_pro=True)

        self.assertEqual(result, 42)
        mock_instance.models.count_tokens.assert_called_once()

if __name__ == '__main__':
    unittest.main()
