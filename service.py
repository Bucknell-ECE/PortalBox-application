#!python3

"""
2021-04-05 Version   KJHass
  - Defer database accesses until after user-visible action if possible
  - Use caches of recently used user, proxy, and training cards

2021-03-29 Version   KJHass
  - A training card is only accepted after a valid user card has been
    accepted. The box is purple while using a training card.

2021-03-18 Version   KJHass
  - Two files are periodically written in /tmp to feed a watchdog timer
    and to keep a record of the last event in case of application crash
  - Many logging statements were added to aid debugging
  - A pulsing blue display is used for sleep instead of constant blue
  - The display is updated repeatedly in case a power glitch alters some
    of the LEDs
  - The beeper is activated for a short time when the equipment is being
    turned on, as a redundant indicator to the green display

2021-06-26 Version James Howe
  - Moved most functionality into portal_fsm.py and cleaned up most functions
  - Moved all color defintions into config
"""


# from the standard library
import configparser
import logging
import os
import signal
import sys
import threading
from time import sleep, time
from uuid import getnode as get_mac_address
import socket

# our code
import portal_fsm as fsm
from portalbox.PortalBox import PortalBox
from Database import Database
from Emailer import Emailer
from CardType import CardType

# Definitions aka constants
DEFAULT_CONFIG_FILE_PATH = "config.ini"

input_data = {
    "card_id": 0,
    "user_is_authorized": False,
    "card_type": "none",
    "user_authority_level":0,
    "button_pressed": False,
}


class PortalBoxApplication():
    """
    wrap code as a class to allow for clean sharing of objects
    between states
    """

    def __init__(self, settings):
        """
        Setup the bare minimun, defering as much as poosible to the run method
        so signal handlers can be configured in __main__
        """
        self.equipment_id = -1
        self.box = PortalBox(settings)
        self.settings = settings
        self.running = False
        self.card_id = 0

    def __del__(self):
        """
        free resources after run
        """
        self.box.cleanup()

    def connect_to_database(self):
        '''
        Connects to the database
        '''
        # connect to backend database
        logging.info("Attempting to connect to database")

        try:
            self.db = Database(self.settings["db"])
        except Exception as e:
            logging.error("Unable to connect to database exeception raised \n\t {}".format(e))
            raise e

        logging.info("Successfully connected to database")

    def connect_to_email(self):
        # be prepared to send emails
        logging.info("Attempting to connect to email")
        try:
            self.emailer = Emailer(self.settings["email"])
        except Exception as e:
            logging.error("Unable to connect to email exeception raised \n\t {}".format(e))
            raise e
        logging.info("Successfully connected to email")

    def getmac(self, interface):
        """From Julio SChurt on https://stackoverflow.com/questions/159137/getting-mac-address"""
        try:
            mac = open('/sys/class/net/'+interface+'/address').readline()
        except:
            mac = "00:00:00:00:00:00"

        return mac[0:17]

    def record_ip(self):
        """
        This gets the IP address for the box and then records it in the database
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        self.db.record_ip(self.equipment_id, ip_address)



    def get_equipment_role(self):
        """
        Gets the equipments role from the database with the given mac address
        """
        # Determine what we are
        profile = (-1,)
        while profile[0] < 0:
          try:
              # Step 1 Figure out our identity
              logging.debug("Attempting to get mac address")
              mac_address = self.getmac("wlan0").replace(":","")
              ##format(, "x")
              #mac_address = format(get_mac_address(), "x")
              logging.debug("Successfully got mac address: {}".format(mac_address))

              profile = self.db.get_equipment_profile(mac_address)
          except Exception as e:
            logging.debug(f"{e}")
            logging.debug("Didn't get profile, trying again in 5 seconds")
            sleep(5)

        # only run if we have role, which we might not if systemd asked us to
        # shutdown before we discovered a role
        if profile[0] < 0:
            raise RuntimeError("Cannot start, no role has been assigned")
        else:
            self.equipment_id = profile[0]
            self.equipment_type_id = profile[1]
            self.equipment_type = profile[2]
            self.location = profile[4]
            self.timeout_minutes = profile[5]
            self.allow_proxy = profile[6]
        
        logging.info("Discovered identity. Type: %s(%s) Timeout: %s m Allows Proxy: %d",
            self.equipment_type,
            self.equipment_type_id,
            self.timeout_minutes,
            self.allow_proxy)
        self.db.log_started_status(self.equipment_id)


    def get_inputs(self, old_input_data):
        """
        Gets new inputs for the FSM and returns the dictionary

        @returns a dictionary of the form
                "card_id": (int)The card ID which was read,
                "user_is_authorized": (boolean) Whether or not the user is authorized,
                    for the current machine
                "card_type": (CardType enum) the type of card,
                "user_authority_level": (int) The authority of the user, 1 for normal user, 2 for trainer, 3 for admin
                "button_pressed": (boolean) whether or not the button has been
                    pressed since the last time it was checked
        """

        #Check for a card and get its ID
        card_id = self.box.read_RFID_card()

        #If a card is present, and old_input_data showed either no card present, or a different card present
        if(card_id > 0 and card_id != old_input_data["card_id"]):
            logging.info("Card with ID: %d read, Getting info from DB", card_id)
            while True:
                try:
                    details = self.db.get_card_details(card_id, self.equipment_type_id)
                    break
                except Exception as e:
                    logging.info(f"Exception: {e}\n trying again")
            new_input_data = {
                "card_id": card_id,
                "user_is_authorized": details["user_is_authorized"],              
                "card_type": details["card_type"],
                "user_authority_level": details["user_authority_level"],
                "button_pressed": self.box.has_button_been_pressed()
            }

            #Log the card reading with the card type and ID
            logging.info("Card of type: %s with ID: %d was read",
                new_input_data["card_type"],
                new_input_data["card_id"])

        #If no card is present, just update the button
        elif(card_id <= 0):
            new_input_data = {
                "card_id": -1,
                "user_is_authorized": False,
                "card_type": CardType.INVALID_CARD,
                "user_authority_level": 0,
                "button_pressed": self.box.has_button_been_pressed()
            }
        #Else just use the old data and update the button
        #ie, if there is a card, but its the same as before
        else:
            new_input_data = old_input_data
            new_input_data["button_pressed"] = self.box.has_button_been_pressed()

        return new_input_data

    def get_user_auths(self, card_id):
        '''
        Determines whether or not the user is authorized for the equipment type
        @return a boolean of whether or not the user is authorized for the equipment
        '''
        #Check if we should always check the remote database
        ## TODO: have this actually check for the local database
        if(True):
            return self.db.is_user_authorized_for_equipment_type(card_id, self.equipment_type_id)


    def send_user_email(self, auth_id):
        '''
        Sends the user an email when they have left their card in the machine
            past the timeout
        '''
        logging.debug("Getting user email ID from DB")
        user = self.db.get_user(auth_id)
        try:
            logging.debug("Mailing user")
            self.emailer.send(user[1], "Access Card left in PortalBox", "{} it appears you left your access card in a portal box for the {} named {} in the {}".format(
                user[0],
                self.equipment_type,
                self.db.get_equipment_name(self.equipment_id),
                self.location))
        except Exception as e:
            logging.error("{}".format(e))

    def send_user_email_proxy(self, auth_id):
        '''
        Sends the user an email when they have left a proxy card in the machine
            past the timeout
        '''
        logging.debug("Getting user email ID from DB")
        user = self.db.get_user(auth_id)
        try:
            logging.debug("Mailing user")
            self.emailer.send(user[1], "Proxy Card left in PortalBox", "{} it appears you left a proxy card in a portal box for the {} named {} in the {}".format(
                user[0],
                self.equipment_type,
                self.db.get_equipment_name(self.equipment_id),
                self.location))
        except Exception as e:
            logging.error("{}".format(e))

    def send_user_email_training(self, trainer_id, trainee_id):
        '''
        Sends the user and the trainer an email when they have left a training card in the machine
            past the timeout
        '''
        logging.debug("Getting user email ID from DB")
        trainer = self.db.get_user(trainer_id)
        trainee = self.db.get_user(trainee_id)
        recipients = [trainer[1], trainee[1]]
        try:
            logging.debug("Mailing user")
            self.emailer.send(recipients, "Training Card left in PortalBox", 
                f"{trainee[0]}(trained by {trainer[0]}) it appears you left your card in a portal box for the {self.equipment_type} named {self.db.get_equipment_name(self.equipment_id)} in the {self.location}"
                )
        except Exception as e:
            logging.error("{}".format(e))

    def handle_interupt(self, signum, frame):
        '''
        Stop the service from a signal
        '''
        logging.debug("Interrupted")
        os.system("echo service_interrupt > /tmp/boxactivity")
        self.shutdown()



    def shutdown(self, card_id = 1):
        '''
        Stops the program
        '''
        logging.info("Service Exiting")
        self.box.cleanup()
        os.system("echo service_exit > /tmp/boxactivity")
        os.system("echo False > /tmp/running")

        if self.equipment_id:
            logging.info("Logging exit-while-running to DB")
            self.db.log_shutdown_status(self.equipment_id,card_id)
        self.running = False





# Here is the main entry point.
if __name__ == "__main__":
    config_file_path = DEFAULT_CONFIG_FILE_PATH

    # Look at Command Line for Overrides
    if 1 < len(sys.argv):
        if os.path.isfile(sys.argv[1]):
            # override default config file
            config_file_path = sys.argv[1]
        # else print help message?

    # Read our Configuration
    settings = configparser.ConfigParser()
    settings.read(config_file_path)



    # Setup logging
    if settings.has_option('logging', 'level'):
        if 'critical' == settings['logging']['level']:
            logging.basicConfig(level=logging.CRITICAL)
        elif 'error' == settings['logging']['level']:
            logging.basicConfig(level=logging.ERROR)
        elif 'warning' == settings['logging']['level']:
            logging.basicConfig(level=logging.WARNING)
        elif 'info' == settings['logging']['level']:
            logging.basicConfig(level=logging.INFO)
        elif 'debug' == settings['logging']['level']:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.ERROR)

    # Create Portal Box Service
    logging.debug("Creating PortalBoxApplication")
    service = PortalBoxApplication(settings)

    # Add signal handler so systemd can shutdown service
    signal.signal(signal.SIGINT, service.handle_interupt)
    signal.signal(signal.SIGTERM, service.handle_interupt)


    # Create finite state machine
    fsm = fsm.Setup(service, input_data)


    # Run service
    logging.debug("Running the FSM")
    service.running = True
    while service.running:
        input_data = service.get_inputs(input_data)
        fsm(input_data)
        #If the FSM is in the Shutdown state, then stop running the while loop
        if(fsm.__class__ == "Shutdown"):
            break
    logging.debug("FSM ends")

    # Cleanup and exit
    os.system("echo False > /tmp/running")
    #service.box.cleanup() ##TODO: Why is this commented out? 
    logging.info("Shutting down logger")
    logging.shutdown()

    sys.exit()


##TODO add a default config somehwere
