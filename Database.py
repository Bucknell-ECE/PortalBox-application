#!python3

"""
  2021-04-04 Version   KJHass
    - Get "requires_training" and "requires_payment" just once rather than
      every time a card is checked

"""

# from standard library
import logging
import requests
import time

# our code
from CardType import CardType

class Database:
    '''
    A high level interface to the backend database
    '''

    def __init__(self, settings):
        '''
        Create a connection to the database specified

        @param (dict)settings - a dictionary describing the database to connect to
        '''

        # insure a minimum configuration
        if (not 'website' in settings or not 'api' in settings or
                not 'bearer_token' in settings):
            raise ValueError("Database configuration must at a minimum include the 'website', 'api', and 'bearer_token' keys")

        self.api_url= f"{settings['website']}/api/{settings['api']}"
        self.api_header = {"Authorization" : f"Bearer {settings['bearer_token']}"}

        self.request_session = requests.Session()
        self.request_session.headers.update(self.api_header)


    def __del__(self):
        '''
        Closes the encapsulated database connection
        '''
        if self._connection:
            self._connection.close()


    def _reconnect(self):
        '''
        Reestablish a connection to the database. Useful if the connection
        timed out
        '''
        logging.debug("Attempting to reconnect to database")

        self._connection = self._connect()

        logging.debug("Reconnected to database")

        return self._connection


    def _connect(self):
        '''
        Establish a connection to the database
        '''
        logging.debug("Attempting to connect to database")

        logging.debug("Connection Settings: {}".format(str(self.connection_settings)))
        connection = mysql.connector.connect(**self.connection_settings)

        logging.debug("Connected to database")

        return connection


    def is_registered(self, mac_address):
        '''
        Determine if the portal box identified by the MAC address has been
        registered with the database

        @param (string)mac_address - the mac_address of the portal box to
             check registration status of
        '''
        logging.debug(f"Checking if portal box with Mac Address {mac_address} is registered")

        params = {
                "mode" : "check_reg",
                "mac_adr" : mac_address
                }

        response = self.request_session.get(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")
        
        if(response.status_code != 200):
            # If we don't get a success status code, then return -1
            logging.error(f"API error")
            return -1

        else:
            response_details = response.json()
            return int(response_details)


    def register(self, mac_address):
        '''
        Register the portal box identified by the MAC address with the database
        as an out of service device
        '''

        params = {
                "mode" : "register",
                "mac_adr" : mac_address
                }

        response = self.request_session.put(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")

        if(response.status_code != 200):
            # If we don't get a success status code, then return -1
            logging.error(f"API error")
            return False

        else:
            return True 


    def get_equipment_profile(self, mac_address):
        '''
        Discover the equipment profile assigned to the Portal Box in the database

        @return a tuple consisting of: (int)equipment id,
        (int)equipment type id, (str)equipment type, (int)location id,
        (str)location, (int)time limit in minutes, (int) allow proxy
        '''
        logging.debug("Querying database for equipment profile")

        profile = (-1, -1, None, -1, None, -1, -1)

        params = {
                "mode" : "get_profile",
                "mac_adr" : mac_address
                }

        response = self.request_session.get(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")

        if(response.status_code == 200):
            response_details = response.json()[0]
            profile = (
                    int(response_details["id"]),
                    int(response_details["type_id"]),
                    response_details["name"][0],
                    int(response_details["location_id"]),
                    response_details["name"][1],
                    int(response_details["timeout"]),
                    int(response_details["allow_proxy"])
                    )
            self.requires_training = int(response_details["requires_training"])
            self.requires_payment  = int(response_details["charge_policy"])
        else:
            raise Exception('Error checking if portalbox is registered')

        return profile


    def log_started_status(self, equipment_id):
        '''
        Logs that this portal box has started up

        @param equipment_id: The ID assigned to the portal box
        '''
        logging.debug("Logging with the database that this portalbox has started up")


        params = {
                "mode" : "log_started_status",
                "equipment_id" :equipment_id
                }


        response = self.request_session.post(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")
        
        if(response.status_code != 200):
            #If we don't get a success status code, then return and unauthorized user 
            logging.error(f"API error")


    def log_shutdown_status(self, equipment_id, card_id):
        '''
        Logs that this portal box is shutting down

        @param equipment_id: The ID assigned to the portal box
        @param card_id: The ID read from the card presented by the user use
            or a falsy value if shutdown is not related to a card
        '''
        logging.debug("Logging with the database that this box has shutdown")

        params = {
                "mode" : "log_shutdown_status",
                "equipment_id" : equipment_id,
                "card_id" : card_id
                }


        response = self.request_session.post(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")

        if(response.status_code != 200):
            # If we don't get a success status code, then return and unauthorized user 
            logging.error(f"API error")


    def log_access_attempt(self, card_id, equipment_id, successful):
        '''
        Logs start time for user using a resource.

        @param card_id: The ID read from the card presented by the user
        @param equipment_id: The ID assigned to the portal box
        @param successful: If login was successful (user is authorized)
        '''
        
        logging.debug("Logging with database an access attempt")

        params = {
                "mode" : "log_access_attempt",
                "equipment_id" : equipment_id,
                "card_id" : card_id,
                "successful" : int(successful)
                }


        response = self.request_session.post(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")
        logging.debug(f"Took {response.elapsed.total_seconds()}")
        if(response.status_code != 200):
            #If we don't get a success status code, then return and unauthorized user 
            logging.error(f"API error")


    def log_access_completion(self, card_id, equipment_id):
        '''
        Logs end time for user using a resource.

        @param card_id: The ID read from the card presented by the user
        @param equipment_id: The ID assigned to the portal box
        '''
        
        logging.debug("Logging with database an access completion")

        params = {
                "mode" : "log_access_completion",
                "equipment_id" : equipment_id,
                "card_id" : card_id
                }


        response = self.request_session.post(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")
        logging.debug(f"Took {response.elapsed.total_seconds()}")
        if(response.status_code != 200):
            #If we don't get a success status code, then return and unauthorized user 
            logging.error(f"API error")


    def get_card_details(self, card_id, equipment_type_id):
        '''
        This function gets the persistent details about a card from the database, only connecting to it once
        These are returned in a dictionary 
        Returns: {
            "user_is_authorized": true/false //Whether or not the user is authorized for this equipment
            "card_type": CardType //The type of card
            "user_authority_level": int //Returns if the user is a normal user, trainer, or admin
            }
        '''
        logging.debug("Starting to get user details for card with ID %d", card_id)
        params = {
                "mode" : "get_card_details",
                "card_id" : card_id,
                "equipment_id" : equipment_type_id
                }


        response = self.request_session.get(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")
        logging.debug(f"Took {response.elapsed.total_seconds()}")

        if(response.status_code != 200):
            #If we don't get a success status code, then return and unauthorized user 
            logging.error(f"API error")
            details = {
                    "user_is_authorized": False,
                    "card_type" : CardType(-1),
                    "user_authority_level": 0
                    }
        else:
            response_details = response.json()[0]

            if response_details["user_role"] == None:
                response_details["user_role"] = 0

            if response_details["card_type"] == None:
                response_details["card_type"] = -1
            details = {
                    "user_is_authorized": self.is_user_authorized_for_equipment_type(response_details),
                    "card_type" : CardType(int(response_details["card_type"])),
                    "user_authority_level": int(response_details["user_role"])
                    }
        return details


    def is_user_authorized_for_equipment_type(self, card_details):
        '''
        Check if card holder identified by card_id is authorized for the
        equipment type identified by equipment_type_id
        '''
        is_authorized = False

        balance = float(card_details["user_balance"])
        user_auth = int(card_details["user_auth"])
        if card_details["user_active"] == None:
            return False
        if int(card_details["user_active"]) != 1:
            return False
            

        if self.requires_training and self.requires_payment:
            if balance > 0.0 and user_auth:
                is_authorized = True
            else:
                is_authorized = False
        elif self.requires_training and not self.requires_payment:
            if user_auth:
                is_authorized = True
            else:
                is_authorized = False
        elif not self.requires_training and self.requires_payment:
            if balance > 0.0:
                is_authorized = True
            else: 
                is_authorized = False
        else:
            is_authorized = True

        return is_authorized


    def get_user(self, card_id):
        '''
        Get details for the user identified by (card) id

        @return, a tuple of name and email
        '''
        user = (None, None)
        
        logging.debug(f"Getting user information from card ID: {id}")

        params = {
                "mode" : "get_user",
                "card_id" : card_id
                }


        response = self.request_session.get(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")
        
        if(response.status_code != 200):
            #If we don't get a succses status code, then return and unouthorized user 
            logging.error(f"API error")
        else:
            response_details = response.json()[0]
            user = (
                    response_details["name"],
                    response_details["email"]
                    )

        return user


    def get_equipment_name(self, equipment_id):
        '''
        Gets the name of the equipment given the equipment id 

        @return, a string of the name 
        '''

        logging.debug("Getting the equipment name")

        params = {
                "mode" : "get_equipment_name",
                "equipment_id" : equipment_id
                }


        response = self.request_session.get(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")
        
        if(response.status_code != 200):
            #If we don't get a success status code, then return and unauthorized user
            logging.error(f"API error")
            return "Unknown"
        else:
            response_details = response.json()[0]
            return response_details["name"]


    def record_ip(self, equipment_id, ip):
        '''
        Gets the name of the equipment given the equipment id 

        @return, a string of the name 
        '''

        logging.debug("Getting the equipment name")

        params = {
                "mode" : "record_ip",
                "equipment_id" : equipment_id,
                "ip_address" : ip
                }


        response = self.request_session.post(self.api_url, params = params)

        logging.debug(f"Got response from server\nstatus: {response.status_code}\nbody: {response.text}")
        
        if(response.status_code != 200):
            #If we don't get a succses status code, then return and unouthorized user 
            logging.error(f"API error")
            return "Unknown"

