#!python3

"""
  2021-04-04 Version   KJHass
    - Get "requires_training" and "requires_payment" just once rather than
      every time a card is checked

"""

# from standard library
import logging

# third party libraries
import mysql.connector

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
        self.use_persistent_connection = True
        self._connection = None

        # insure a minimum configuration
        if (not 'user' in settings or not 'password' in settings or
                not 'host' in settings or not 'database' in settings):
            raise ValueError("Database configuration must at a minimum include the 'user', 'password', 'host' and 'database' keys")

        # build new settings object to filter out keys we don't want going to mysql.connector
        self.connection_settings = {
            'user': settings['user'],
            'password': settings['password'],
            'host': settings['host'],
            'database': settings['database'],
        }

        # Add in the optional keys
        if 'port' in settings:
            self.connection_settings['port'] = settings['port']

        if 'use_persistent_connection' in settings:
            if settings['use_persistent_connection'].lower() in ("no", "false", "0"):
                self.use_persistent_connection = False

        logging.debug("DB Connection Settings: %s", self.connection_settings)

        if self.use_persistent_connection:
            self._connection = mysql.connector.connect(**self.connection_settings)
            if self._connection:
                logging.debug("Initialized persistent DB connection")
            else:
                logging.error("Failed to initialize persistent connection")


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
        registered = False
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            # Send query
            query = ("SELECT count(id) FROM equipment WHERE mac_address = %s")
            cursor = connection.cursor()
            cursor.execute(query, (mac_address,))

            # Interpret result
            (registered,) = cursor.fetchone()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))

        return registered


    def register(self, mac_address):
        '''
        Register the portal box identified by the MAC address with the database
        as an out of service device
        '''
        success = False
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            # Send query
            query = ("INSERT INTO equipment (name, type_id, mac_address, location_id) VALUES ('New Portal Box', 1, %s, 1)")
            cursor = connection.cursor()
            cursor.execute(query, (mac_address,))

            if 1 == cursor.rowcount:
                success = True

            connection.commit()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))

        return success


    def get_equipment_profile(self, mac_address):
        '''
        Discover the equipment profile assigned to the Portal Box in the database

        @return a tuple consisting of: (int)equipment id,
        (int)equipment type id, (str)equipment type, (int)location id,
        (str)location, (int)time limit in minutes
        '''
        logging.debug("Querying database for equipment profile")

        profile = (-1, -1, None, -1, None, -1)
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            # Query MySQL for RID by sending MAC Address
            query = ("SELECT e.id, e.type_id, t.name, e.location_id, l.name, e.timeout "
                "FROM equipment AS e "
                "INNER JOIN equipment_types AS t ON e.type_id = t.id "
                "INNER JOIN locations AS l ON e.location_id =  l.id "
                "WHERE e.mac_address = %s")
            cursor = connection.cursor(buffered = True) # we want rowcount to be available
            cursor.execute(query, (mac_address,))

            if 0 < cursor.rowcount:
                # Interpret result
                profile = cursor.fetchone()
                logging.debug("Fetched equipment profile")
            else:
                logging.debug("Failed to fetch equipment profile")

            query = ("SELECT requires_training, charge_policy_id > 2 FROM equipment_types WHERE id = %s")
            cursor = connection.cursor()
            cursor.execute(query, (profile[1],))
            (self.requires_training,self.requires_payment) = cursor.fetchone()

            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))

        return profile


    def log_started_status(self, equipment_id):
        '''
        Logs that this portal box has started up

        @param equipment_id: The ID assigned to the portal box
        '''
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            query = ("INSERT INTO log(event_type_id, equipment_id) "
                "(SELECT id, %s FROM event_types "
                "WHERE name = 'Startup Complete')")
            cursor = connection.cursor()
            cursor.execute(query, (equipment_id,))

            # No check for success?
            connection.commit()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))


    def log_shutdown_status(self, equipment_id, card_id):
        '''
        Logs that this portal box is shutting down

        @param equipment_id: The ID assigned to the portal box
        @param card_id: The ID read from the card presented by the user use
            or a falsy value if shutdown is not related to a card
        '''
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            if card_id:
                query = ("INSERT INTO log(event_type_id, equipment_id, card_id) "
                    "(SELECT id, %s, %s FROM event_types "
                    "WHERE name = 'Planned Shutdown')")
                cursor = connection.cursor()
                cursor.execute(query, (equipment_id, card_id))
            else:
                query = ("INSERT INTO log(event_type_id, equipment_id) "
                    "(SELECT id, %s FROM event_types "
                    "WHERE name = 'Planned Shutdown')")
                cursor = connection.cursor()
                cursor.execute(query, (equipment_id,))

            # No check for success?
            connection.commit()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))


    def log_access_attempt(self, card_id, equipment_id, successful):
        '''
        Logs start time for user using a resource.

        @param card_id: The ID read from the card presented by the user
        @param equipment_id: The ID assigned to the portal box
        @param successful: If login was successful (user is authorized)
        '''
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            query = ("CALL log_access_attempt(%s, %s, %s)")
            cursor = connection.cursor()
            cursor.execute(query, (successful, card_id, equipment_id))

            # No check for success?
            connection.commit()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))


    def log_access_completion(self, card_id, equipment_id):
        '''
        Logs end time for user using a resource.

        @param card_id: The ID read from the card presented by the user
        @param equipment_id: The ID assigned to the portal box
        @param successful: If login was successful (user is authorized)
        '''
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            query = ("CALL log_access_completion(%s, %s)")
            cursor = connection.cursor()

            cursor.execute(query, (card_id, equipment_id))
            connection.commit()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))


    def is_user_authorized_for_equipment_type(self, card_id, equipment_type_id):
        '''
        Check if card holder identified by card_id is authorized for the
        equipment type identified by equipment_type_id
        '''
        is_authorized = False
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            cursor = connection.cursor()
            if self.requires_training and self.requires_payment:
                # check balance
                query = ("SELECT get_user_balance_for_card(%s)")
                cursor.execute(query, (card_id,))
                (balance,) = cursor.fetchone()
                if 0.0 < balance:
                    # balance okay check authorization
                    query = ("SELECT count(u.id) FROM users_x_cards AS u "
                    "INNER JOIN authorizations AS a ON a.user_id= u.user_id "
                    "WHERE u.card_id = %s AND a.equipment_type_id = %s")
                    cursor.execute(query, (card_id, equipment_type_id))
                    (count,) = cursor.fetchone()
                    if 0 < count:
                        is_authorized = True
            elif self.requires_training and not self.requires_payment:
                query = ("SELECT count(u.id) FROM users_x_cards AS u "
                "INNER JOIN authorizations AS a ON a.user_id= u.user_id "
                "WHERE u.card_id = %s AND a.equipment_type_id = %s")
                cursor.execute(query, (card_id, equipment_type_id))
                (count,) = cursor.fetchone()
                if 0 < count:
                    is_authorized = True
            elif not self.requires_training and self.requires_payment:
                # check balance
                query = ("SELECT get_user_balance_for_card(%s)")
                cursor.execute(query, (card_id,))
                (balance,) = cursor.fetchone()
                if 0.0 < balance:
                    is_authorized = True
            else:
                # we don't require payment or training, user is implicitly authorized
                is_authorized = True

            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))

        return is_authorized

    def get_card_type(self, id):
        '''
        Get the type of the card identified by id

        @returns a CardType enum:
            with -1 for card not found, 1 for shutdown card,
            2 for proxy card, 3 for training card, and 4 for user card
        '''
        type_id = -1
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            query = ("SELECT type_id FROM cards WHERE id = %s")

            cursor = connection.cursor(buffered = True) # we want rowcount to be available
            cursor.execute(query, (id,))

            if 0 < cursor.rowcount:
                (type_id,) = cursor.fetchone()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))

        return CardType(type_id)


    def is_training_card_for_equipment_type(self, id, type_id):
        '''
        Determine if the training card identified by id is valid as a
        training card for equipment of type specified by type_id
        '''
        valid = False
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            # Send query
            query = ("SELECT count(id) FROM equipment_type_x_cards "
                "WHERE card_id = %s AND equipment_type_id = %s")
            cursor = connection.cursor()
            cursor.execute(query, (id,type_id))

            # Interpret result
            (valid,) = cursor.fetchone()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))

        return valid


    def get_user(self, id):
        '''
        Get details for the user identified by (card) id

        @return, a tuple of name and email
        '''
        user = (None, None)
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            query = ("SELECT u.name, u.email FROM users_x_cards AS c "
                "JOIN users AS u ON u.id = c.user_id WHERE c.card_id = %s")

            cursor = connection.cursor()
            cursor.execute(query, (id,))

            user = cursor.fetchone()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))

        return user

    def is_user_trainer(self, id):
        '''
        Determine whether a particular user is a trainer or admin

        Get the management_portal_access_level from the database. This is
        an integer. A value of 1 is a normal user, 2 is a trainer, and 3
        is an admin.

        @return, True or False
        '''
        connection = self._connection

        try:
            if self.use_persistent_connection:
                if not connection.is_connected():
                    connection = self._reconnect()
            else:
                connection = self._connect()

            query = ("SELECT u.management_portal_access_level_id FROM users_x_cards AS c "
                "JOIN users AS u ON u.id = c.user_id WHERE c.card_id = %s")

            cursor = connection.cursor()
            cursor.execute(query, (id,))

            access_level = cursor.fetchone()
            cursor.close()
            if not self.use_persistent_connection:
                connection.close()
        except mysql.connector.Error as err:
            logging.error("{}".format(err))

        return access_level > 1
