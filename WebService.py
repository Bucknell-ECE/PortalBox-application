import requests

class NotAuthorizedError(Exception):
    """
    Exception to raise when the web service reports the user represented by a card
    is not permitted to activate the equipment
    """

    pass

class NotRegisteredError(Exception):
    """
    Exception to raise when the web service reports a failure because the
    portalbox making the request is not registered with the service
    """

    pass

class OutOfServiceError(Exception):
    """
    Exception to raise when the web service reports a failure because the
    portalbox making the request is marked out of service
    """

    pass

class Client:
    """
    An interface to the web service responsible for coordinating portalboxes.
    """

    def __init__(self, url: str, mac: str) -> None:
        """
        Parameters
        ----------
        url : str
            The base url; protocol, host name, and optionally port; of the website
        mac : str
            The MAC of the portalbox the code is running on
        """

        self.url = url
        self.mac = mac

    def log_startup(self) -> None:
        """Inform service that the portalbox is now online

        Raises
        ------
        NotRegisteredError
            if the portalbox has not been registered with the web service
        OutOfServiceError
            if the portalbox is marked "Out of Service" in the web service
        """

        url = f"{self.url}/api/v2/box.php"
        params = {"mac": self.mac}
        response = requests.post(url, params = params, data = "startup")

        if response.status_code == 404:
            raise NotRegisteredError()

        if response.status_code == 409:
            raise OutOfServiceError()

    def begin_usage_session(self, card_id: str):
        """Request that the service begin a usage session for the user associated with the card

        Raises
        ------
        NotAuthorizedError
            if the user represented by the card can not use the attached equipment
        """

        url = f"{self.url}/api/v2/box-activation.php"
        params = {"mac": self.mac}
        headers = request_headers = {'Authorization': f'Bearer {card_id}'}
        response = requests.put(url, params = params, headers = headers)

        if response.status_code in (401, 403):
            raise NotAuthorizedError()

    def end_usage_session(self, card_id: str):
        """Tell the backend that the equipment session has ended

        Raises
        ------
        NotAuthorizedError
            if the card was invalid for ending the usage session
        """

        url = f"{self.url}/api/v2/box-activation.php"
        params = {"mac": self.mac}
        headers = request_headers = {'Authorization': f'Bearer {card_id}'}
        response = requests.post(url, params = params, headers = headers)

        if response.status_code in (401, 403):
            raise NotAuthorizedError()
