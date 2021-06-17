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
    "user_authority": 0,
    "card_type": "none",
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

    # def __del__(self):
    #     """
    #     free resources after run
    #     """
    #     self.box.cleanup()

    def connect_to_database(self):
        # connect to backend database
        self.db = Database(self.settings["db"])

    def connect_to_email(self):
        # be prepared to send emails
        self.emailer = Emailer(self.settings["email"])


    def get_equipment_role(self):
        # Step 2 Figure out our identity
        mac_address = format(get_mac_address(), "x")

        # determine what we are
        profile = (-1,)
        while profile[0] < 0:
            profile = self.db.get_equipment_profile(mac_address)
            if profile[0] < 0:
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
        logging.info("Discovered identity. Type: %s(%s) Timeout: %s m",
            self.equipment_type,
            self.equipment_type_id,
            self.timeout_period)
        self.db.log_started_status(self.equipment_id)


    def get_inputs(self):
        new_card_id = self.box.read_RFID_card()
        new_inputs = {
            "card_id": new_card_id,
            "user_is_authorized": self.get_user_auths(new_card_id),
            "user_authority": 0,
            "card_type": self.db.get_card_type(new_card_id),
            "button_pressed": self.box.has_button_been_pressed()
        }
        return new_inputs

    def get_user_auths(self, card_id):
        '''
        Determines whether or not the user is authorized for the equipment type
        @return a boolean of whether or not the user is authorized for the equipment
        '''
        #Check if we should always check the remote database
        ## TODO: have this actually check for the local database
        if(True):
            return self.db.is_user_authorized_for_equipment_type(uid, self.equipment_type_id)
        else:
            #Unpickle the local database and see if the equipment_type_id is in it
            user_auths = pickle.load(open(os.path.join(sys.path[0], LOCAL_DATABASE_FILE_PATH),"rb"))
            return equipment_type_id in user_auths[uid][1]

    def send_user_email(self, auth_id):
            logging.debug("Getting user email ID from DB")
            user = self.db.get_user(auth_id)
            try:
                logging.debug("Mailing user")
                self.emailer.send(user[1], "Access Card left in PortalBox", "{} it appears you left your access card in a badge box for the {} in the {}".format(user[0], self.equipment_type, self.location))
            except Exception as e:
                logging.error("{}".format(e))

    def handle_interupt(self, signum, frame):
        ''' Stop the service from a signal'''
        logging.debug("Interrupted")
        os.system("echo service_interrupt > /tmp/boxactivity")



    def shutdown(self):
        ''' Stop looping in all run states '''
        logging.info("Service Exiting")
        os.system("echo service_exit > /tmp/boxactivity")
        os.system("echo False > /tmp/running")
        if self.running:
            if self.equipment_id:
                logging.info("Logging exit-while-running to DB")
                self.db.log_shutdown_status(self.equipment_id, False)
            self.running = False
        else:
            # never made it to the run state
            logging.info("Not running, just exit")
            sys.exit()




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

    # Create Badge Box Service
    service = PortalBoxApplication(settings)

    # Add signal handler so systemd can shutdown service
    signal.signal(signal.SIGINT, service.handle_interupt)
    signal.signal(signal.SIGTERM, service.handle_interupt)

    # Create finite state machine
    fsm = fsm.Setup(service, input_data)

    # Run service
    while True:
        input_data = service.get_inputs()
        fsm(input_data)

    # Cleanup and exit
    service.box.cleanup()
