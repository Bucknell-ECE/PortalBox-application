import requests

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
