import unittest
from unittest.mock import MagicMock, patch

from .context import WebService

class TestWebService(unittest.TestCase):
    @patch("WebService.requests")
    def test_log_startup_error_when_not_registered(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"

        response = MagicMock()
        response.status_code = 404

        mock_requests.post.return_value = response

        client = WebService.Client(url, mac)

        with self.assertRaises(WebService.NotRegisteredError):
            client.log_startup()

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box.php",
            params = {"mac": mac},
            data = "startup"
        )

    @patch("WebService.requests")
    def test_log_startup_error_when_out_of_service(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"

        response = MagicMock()
        response.status_code = 409

        mock_requests.post.return_value = response

        client = WebService.Client(url, mac)

        with self.assertRaises(WebService.OutOfServiceError):
            client.log_startup()

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box.php",
            params = {"mac": mac},
            data = "startup"
        )

    @patch("WebService.requests")
    def test_log_startup_success(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"

        response = MagicMock()
        response.status_code = 200

        mock_requests.post.return_value = response

        client = WebService.Client(url, mac)
        client.log_startup()

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box.php",
            params = {"mac": mac},
            data = "startup"
        )

    @patch("WebService.requests")
    def test_begin_usage_session_error_when_not_token_garbled(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"
        card_id = "f6e5d4c3b2a100"

        response = MagicMock()
        response.status_code = 401

        mock_requests.put.return_value = response

        client = WebService.Client(url, mac)

        with self.assertRaises(WebService.NotAuthorizedError):
            client.begin_usage_session(card_id)

        mock_requests.put.assert_called_with(
            f"{url}/api/v2/box-activation.php",
            params = {"mac": mac},
            headers = {"Authorization": f"Bearer {card_id}"}
        )

    @patch("WebService.requests")
    def test_begin_usage_session_error_when_not_authorized(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"
        card_id = "f6e5d4c3b2a100"

        response = MagicMock()
        response.status_code = 403

        mock_requests.put.return_value = response

        client = WebService.Client(url, mac)

        with self.assertRaises(WebService.NotAuthorizedError):
            client.begin_usage_session(card_id)

        mock_requests.put.assert_called_with(
            f"{url}/api/v2/box-activation.php",
            params = {"mac": mac},
            headers = {"Authorization": f"Bearer {card_id}"}
        )

    @patch("WebService.requests")
    def test_begin_usage_session_success(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"
        card_id = "f6e5d4c3b2a100"

        response = MagicMock()
        response.status_code = 200

        mock_requests.put.return_value = response

        client = WebService.Client(url, mac)
        client.begin_usage_session(card_id)

        mock_requests.put.assert_called_with(
            f"{url}/api/v2/box-activation.php",
            params = {"mac": mac},
            headers = {"Authorization": f"Bearer {card_id}"}
        )

    @patch("WebService.requests")
    def test_end_usage_session_error_when_not_token_garbled(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"
        card_id = "f6e5d4c3b2a100"

        response = MagicMock()
        response.status_code = 401

        mock_requests.post.return_value = response

        client = WebService.Client(url, mac)

        with self.assertRaises(WebService.NotAuthorizedError):
            client.end_usage_session(card_id)

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box-activation.php",
            params = {"mac": mac},
            headers = {"Authorization": f"Bearer {card_id}"}
        )

    @patch("WebService.requests")
    def test_end_usage_session_error_when_not_authorized(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"
        card_id = "f6e5d4c3b2a100"

        response = MagicMock()
        response.status_code = 403

        mock_requests.post.return_value = response

        client = WebService.Client(url, mac)

        with self.assertRaises(WebService.NotAuthorizedError):
            client.end_usage_session(card_id)

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box-activation.php",
            params = {"mac": mac},
            headers = {"Authorization": f"Bearer {card_id}"}
        )

    @patch("WebService.requests")
    def test_end_usage_session_success(self, mock_requests):
        url = "http://127.0.0.1"
        mac = "abcdef123456"
        card_id = "f6e5d4c3b2a100"

        response = MagicMock()
        response.status_code = 200

        mock_requests.post.return_value = response

        client = WebService.Client(url, mac)
        client.end_usage_session(card_id)

        mock_requests.post.assert_called_with(
            f"{url}/api/v2/box-activation.php",
            params = {"mac": mac},
            headers = {"Authorization": f"Bearer {card_id}"}
        )
