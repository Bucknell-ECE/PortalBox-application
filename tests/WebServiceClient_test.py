import unittest
from unittest.mock import MagicMock, patch

from .context import WebServiceClient

class TestWebServiceClient(unittest.TestCase):
    @patch('WebServiceClient.requests')
    def test_log_startup_error_when_not_registered(self, mock_requests):
        url = 'http://127.0.0.1'
        mac = 'abcdef123456'

        response = MagicMock()
        response.status_code = 404

        mock_requests.post.return_value = response

        client = WebServiceClient.Client(url, mac)

        with self.assertRaises(WebServiceClient.NotRegisteredError):
            client.log_startup()

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box.php",
            params = {"mac": mac},
            data = "startup"
        )

    @patch('WebServiceClient.requests')
    def test_log_startup_error_when_out_of_service(self, mock_requests):
        url = 'http://127.0.0.1'
        mac = 'abcdef123456'

        response = MagicMock()
        response.status_code = 409

        mock_requests.post.return_value = response

        client = WebServiceClient.Client(url, mac)

        with self.assertRaises(WebServiceClient.OutOfServiceError):
            client.log_startup()

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box.php",
            params = {"mac": mac},
            data = "startup"
        )

    @patch('WebServiceClient.requests')
    def test_log_startup_success(self, mock_requests):
        url = 'http://127.0.0.1'
        mac = 'abcdef123456'

        response = MagicMock()
        response.status_code = 200

        mock_requests.post.return_value = response

        client = WebServiceClient.Client(url, mac)
        client.log_startup()

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box.php",
            params = {"mac": mac},
            data = "startup"
        )
