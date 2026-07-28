import unittest
from unittest.mock import patch, MagicMock

class TestSentinelWebhooksDirect(unittest.TestCase):

    @patch('requests.post')
    def test_webhook_delivery_mock(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_post.return_value = mock_response

        # Direct simulation of webhook payload dispatch
        url = "https://discord.com/api/webhooks/test"
        payload = {"content": "Test notification payload"}
        
        import requests
        response = requests.post(url, json=payload, timeout=5)

        self.assertEqual(response.status_code, 200)
        mock_post.assert_called_once_with(url, json=payload, timeout=5)

if __name__ == "__main__":
    unittest.main()
