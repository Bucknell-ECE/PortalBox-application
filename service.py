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
import pickle
from time import sleep, time, time_ns
from uuid import getnode as get_mac_address

# our code
from portalbox.PortalBox import PortalBox
from Database import Database
from Emailer import Emailer

# Definitions aka constants
DEFAULT_CONFIG_FILE_PATH = "config.ini"

LOCAL_DATABASE_FILE_PATH = "local-data.p"

RED = b'\xFF\x00\x00'
GREEN = b'\x00\xFF\x00'
YELLOW = b'\xFF\xFF\x00'
BLUE = b'\x00\x00\xFF'
ORANGE = b'\xDF\x20\x00'
PURPLE = b'\x80\x00\x80'
WHITE = b'\xFF\xFF\xFF'

AUTH_COLOR = GREEN
PROXY_COLOR = ORANGE
TRAINER_COLOR = PURPLE

class PortalBoxApplication:
    '''
    Wrap code as a class to allow for clean sharing of objects
    between states
    '''
    def __init__(self, settings):
        '''
        Setup the bare minimun, defering as much as poosible to the run method
        so signal handlers can be configured in __main__
        '''
        self.exceeded_time = False
        self.running = False
        self.equipment_id = False
        self.box = PortalBox()
        self.settings = settings
        os.system("echo portalbox_init > /tmp/boxactivity")
        os.system("echo False > /tmp/running")

        self.always_check_remote_database = True

        # Caches for recent authorized users, training cards, proxy cards
        # Card ID numbers are stored in this list
        # Newest entries are at the **end** of the list
        # To add a new id to the newest end of a list:
        #    del self.proxy_cards[0]
        #    self.proxy_cards.append(uid)
        # To move an id to the "newest" end of a list:
        #    self.training_cards.remove(uid)
        #    self.training_cards.append(uid)
        self.users = [""] * 5
        self.training_cards = [""] * 10
        self.proxy_cards = [""] * 10

    def __del__(self):
        '''
        free resources after run
        '''
        self.box.cleanup()

    def testTimes(self):
        for x in range(10000):
            self.update_local_database()
        updatelocalDBTimes = open(os.path.join(sys.path[0], "pullPickelTime.txt"), "r+")
        timeAccumulator = 0
        lineCount = 0
        for line in updatelocalDBTimes:
            timeAccumulator += int(line.strip())
            lineCount += 1
        logging.debug("Average time to pull from remote and update local is {}".format(timeAccumulator/lineCount))

        self.always_check_remote_database = False
        for x in range(10000):
            self.is_user_authorized_for_equipment_type(1,1)
        timeLog = open(os.path.join(sys.path[0], "checkFromLocalDBTimes.txt"), "r+")
        timeAccumulator = 0
        lineCount = 0
        for line in timeLog:
            timeAccumulator += int(line.strip())
            lineCount += 1
        logging.debug("Average time to check from local is {}".format((timeAccumulator/lineCount)))

        self.always_check_remote_database = True
        for x in range(10000):
            self.is_user_authorized_for_equipment_type(1,1)
        timeLog = open(os.path.join(sys.path[0], "checkFromRemoteDBTimes.txt"), "r+")
        timeAccumulator = 0
        lineCount = 0
        for line in timeLog:
            timeAccumulator += int(line.strip())
            lineCount += 1
        logging.debug("Average time to check from remote is {}".format((timeAccumulator/lineCount)))


    def run(self):
        '''
        Actually get ready to run... we defered initialization in order to
        configure signal handlers in __main__ but they should now be in place

        This corresponds to the transition from Start in FSM.odg see docs
        '''


        self.testTimes()

        os.system("echo False > /tmp/running")

        # Step 1 Do a bit of a dance to show we are running
        logging.info("Setting display color to wipe red")
        self.box.set_display_color_wipe(RED, 100)
        logging.info("Started PortalBoxApplication.run()")

        # Set 2 Figure out our identity
        mac_address = format(get_mac_address(), 'x')
        logging.info("Discovered Mac Address: %s", mac_address)

        # connect to backend database
        logging.info("Connecting to database on host %s", self.settings['db']['host'])
        try:
            logging.debug("Creating database instance")
            self.db = Database(self.settings['db'])
            logging.info("Connected to Database")
        except Exception as e:
            logging.error("{}".format(e))
            sys.exit(1)

        # be prepared to send emails
        try:
            logging.info("Creating emailer instance")
            self.emailer = Emailer(self.settings['email'])
            logging.info("Cached email settings")
        except Exception as e:
            # should be unreachable
            logging.error("{}".format(e))
            os.system("echo False > /tmp/running")
            sys.exit(1)

        # give user hint we are making progress
        logging.debug("Setting display color to wipe orange")
        self.box.set_display_color_wipe(ORANGE, 100)

        # determine what we are
        profile = (-1,)
        self.running = True
        while self.running and 0 > profile[0]:
            os.system("echo equipment_profile > /tmp/boxactivity")
            logging.info("Trying to get equipment profile")
            profile = self.db.get_equipment_profile(mac_address)
            if 0 > profile[0]:
                sleep(5)


        #Setup a view varibles from the config

        self.always_check_remote_database = settings['database_updates']['always_check_remote_database'].lower() in ("yes", "true", "1")

        # only run if we have role, which we might not if systemd asked us to
        # shutdown before we discovered a role
        if 0 < profile[0]:
            # profile:
            #   (int) equipment id
            #   (int) equipment type id
            #   (str) equipment type
            #   (int) location id
            #   (str) location
            #   (int) time limit in minutes
            self.equipment_id = profile[0]
            self.equipment_type_id = profile[1]
            self.equipment_type = profile[2]
            self.location = profile[4]
            self.timeout_period = profile[5]

            logging.info("Discovered identity. Type: %s(%s) Timeout: %s m",
                    self.equipment_type,
                    self.equipment_type_id,
                    self.timeout_period)
            self.db.log_started_status(self.equipment_id)

            logging.info("Setting display to wipe green")
            self.box.set_display_color_wipe(GREEN, 10)
            self.timeout_period *= 60 # python threading wants seconds, DB has minutes
            self.proxy_uid = -1
            self.training_mode = False
            logging.info("Intially updating local database")
            self.update_local_database()
            logging.info("Starting to wait for access card")
            self.wait_for_access_card()
        else:
            logging.info("Running ending; did not discover identity.")
            sys.exit(1)


    def wait_for_access_card(self):
        '''
        Wait for a card and if we read a card decide what to do
        '''
        logging.debug("Setting display to sleep")
        self.box.sleep_display()
        # Run... loop endlessly waiting for RFID cards
        logging.debug("Waiting for an access card")
        while self.running:
            os.system("echo wait_for_a_card > /tmp/boxactivity")

            # Update the local DataBase from the server
            self.update_local_database()

            # Scan for card
            uid = self.box.read_RFID_card()
            if -1 < uid:
                logging.debug("Detected a card")
                # we read a card... decide what to do
                card_type = self.db.get_card_type(uid)
                logging.debug("Card of type: %s was presented", card_type)
                if Database.SHUTDOWN_CARD == card_type:
                    logging.info("Shutdown Card: %s detected, triggering box shutdown", uid)
                    self.db.log_shutdown_status(self.equipment_id, uid)
                    logging.debug("Blanking display")
                    self.box.set_display_color()
                    logging.debug("Telling OS to shut down")
                    os.system("sync; shutdown -h now")
                elif Database.USER_CARD == card_type:
                    logging.info("User card %s detected, authorized?", uid)
                    if uid in self.users:
                        logging.info("Cached user %s authorized for %s",
                                uid,
                                self.equipment_type)

                        self.users.remove(uid)
                        self.users.append(uid)
                        logging.debug(str(self.users))

                        self.run_session(uid)
                    elif self.is_user_authorized_for_equipment_type(uid, self.equipment_type_id):
                        logging.info("User %s authorized for %s",
                                uid,
                                self.equipment_type)

                        del self.users[0]
                        self.users.append(uid)
                        logging.debug(str(self.users))

                        self.run_session(uid)
                    else:
                        self.wait_for_unauthorized_card_removal(uid)
                    logging.debug("Done with user card, start sleep display")
                    self.box.sleep_display()
                else:
                    logging.info("Unauthorized card %s detected", uid)
                    self.wait_for_unauthorized_card_removal(uid)
                    logging.debug("Done with unauthorized card, start sleep display")
                    self.box.sleep_display()

                self.box.sleep_display()

            sleep(0.1)


    def run_session(self, user_id):
        '''
        Allow user to use the equipment
        '''
        self.authorized_uid = user_id
        self.proxy_uid = -1
        self.training_mode = False
        self.user_is_trainer = False

        logging.debug("Setting display to green")
        self.box.set_display_color(AUTH_COLOR)
        self.box.set_buzzer(True)
        self.box.set_equipment_power_on(True)
        sleep(0.05)

        logging.info("Logging activation of %s to DB", self.equipment_type)
        self.db.log_access_attempt(user_id, self.equipment_id, True)
        self.box.set_buzzer(False)
        logging.debug("Setting display to green")
        self.box.set_display_color(AUTH_COLOR)

        logging.debug("Checking if user is a trainer or admin")
        self.user_is_trainer = self.db.is_user_trainer(user_id)

        if 0 < self.timeout_period:
            self.exceeded_time = False
            logging.debug("Starting equipment timer")
            self.activation_timeout = threading.Timer(self.timeout_period, self.timeout)
            logging.debug("Starting timeout")
            self.activation_timeout.start()
        self.wait_for_authorized_card_removal()
        if not self.exceeded_time and 0 < self.timeout_period:
            logging.debug("Canceling timeout")
            self.activation_timeout.cancel()
        self.box.set_equipment_power_on(False)
        logging.info("Logging end of %s access to DB", self.equipment_type)
        self.db.log_access_completion(user_id, self.equipment_id)
        self.authorized_uid = -1
        logging.debug("run_session() ends")

##TODO RENAME THIS
    def is_user_authorized_for_equipment_type(self, uid, equipment_type_id):
        '''
        Determines whether or not the user is authorized for the equipment type

        @return a boolean of whether or not the user is authorized for the equipment
        '''
        start_time = time_ns()
        #Check if we should always check the remote database
        if(self.always_check_remote_database):
            x = self.db.is_user_authorized_for_equipment_type(uid, equipment_type_id)
            timeLog = open(os.path.join(sys.path[0], "checkFromRemoteDBTimes.txt"), "a+")
            timeLog.write("{} \n".format(time_ns()-start_time))
            return x

        else:
            #Unpickle the local database and see if the equipment_type_id is in it
            user_auths = pickle.load(open(os.path.join(sys.path[0], LOCAL_DATABASE_FILE_PATH),"rb"))
            x = equipment_type_id in user_auths[uid][1]
            timeLog = open(os.path.join(sys.path[0], "checkFromLocalDBTimes.txt"), "a+")
            timeLog.write("{} \n".format(time_ns()-start_time))
            return x

    def update_local_database(self):
        '''
        Updates the local data base from the sql server
        the format of the local database is a dictionary where the keys are the card IDs
        and the value is a list consisting of
        (int)user_id,
        (list of ints)equipment_type's they are authorized to use
        # TODO: Change this so it includes all the information that the box needs, like email
        '''

        logging.debug("Getting Database from the server")
        start_time = time_ns();
        user_info = self.db.get_user_auth();

        user_dict = {}
        for x in user_info:
            card_id = x[0]
            user_id = x[1]
            equipment_type = x[2]
            if card_id not in user_dict.keys():
                user_dict[card_id] = [user_id, [equipment_type]]
            else:
                user_dict[card_id][1].append(equipment_type)

        local_database_file = open(os.path.join(sys.path[0], LOCAL_DATABASE_FILE_PATH), "wb")
        pickle.dump(user_dict,local_database_file)
        timeLog = open(os.path.join(sys.path[0], "pullPickelTime.txt"), "a+")
        timeLog.write("{} \n".format(time_ns()-start_time))

        logging.debug("Finished getting database from Server")



    def timeout(self):
        '''
        Called by timer thread when usage time is exceeeded
        '''
        logging.info("Timer timed out")
        self.exceeded_time = True


    def wait_for_unauthorized_card_removal(self, uid):
        '''
        Wait for card to be removed
        '''
        logging.info("Card %s NOT authorized for %s", uid, self.equipment_type)
        self.db.log_access_attempt(uid, self.equipment_id, False)

        # We need a grace_counter because consecutive card reads fail
        grace_count = 0

        #loop endlessly waiting for shutdown or card to be removed
        logging.debug("Looping until not running or card removed")
        while self.running and grace_count < 2:
            os.system("echo wait_unauth_remove > /tmp/boxactivity")
            # Scan for card
            uid = self.box.read_RFID_card()
            if -1 < uid:
                # we did read a card
                grace_count = 0
            else:
                # we did not read a card
                grace_count += 1

            self.box.flash_display(RED, 100, 1, RED)
        logging.debug("wait_for_unauthorized_card_removal() ends")


    def wait_for_authorized_card_removal(self):
        '''
        Wait for card to be removed
        '''
        self.card_present = True
        self.proxy_uid = -1
        # We have to have a grace_counter because consecutive card reads currently fail
        grace_count = 0

        if self.training_mode:
            color_now = TRAINER_COLOR
        else:
            color_now = AUTH_COLOR

        #loop endlessly waiting for shutdown or card to be removed
        logging.debug("Waiting for card removal or timeout")
        while self.running and self.card_present:
            os.system("echo wait_auth_remove_timeout > /tmp/boxactivity")
            # check for timeout
            if self.exceeded_time:
                logging.debug("Time exceeded, wait for timeout grace")
                self.wait_for_timeout_grace_period_to_expire()
                logging.debug("Timeout grace period expired")
                if self.card_present:
                    # User pressed the button return to running
                    logging.debug("Button pressed, restart timeout")
                    self.exceeded_time = False
                    if self.card_present:
                            grace_count = 0
                            if self.proxy_uid > -1:
                                color_now = PROXY_COLOR
                            elif self.training_mode:
                                color_now = TRAINER_COLOR
                            else:
                                color_now = AUTH_COLOR
                    self.activation_timeout = threading.Timer(self.timeout_period, self.timeout)
                    self.activation_timeout.start()
                else:
                    logging.debug("Card removed")
                    break

            # Scan for card
            uid = self.box.read_RFID_card()
            if -1 < uid and (uid == self.authorized_uid or uid == self.proxy_uid):
                # we read an authorized card
                grace_count = 0
            else:
                # we did not read a card or we read the wrong card
                grace_count += 1

                if grace_count > 2:
                    self.wait_for_user_card_return()
                    if self.card_present:
                        grace_count = 0

            if -1 < self.proxy_uid:
                color_now = PROXY_COLOR
            elif self.training_mode:
                color_now = TRAINER_COLOR
            else:
                color_now = AUTH_COLOR

            self.box.set_display_color(color_now)
            sleep(0.1)

        self.box.set_display_color(color_now)
        logging.debug("Finished waiting for card removal or timeout")


    def wait_for_user_card_return(self):
        '''
        Wait for a time for card to return before shutting down, button press
        shuts down immediately.

        We accomplish this using the card_present flag. By setting the flag
        to False immeditely we just return and the outer loop in
        wait_for_authorized_card_removal will also end. If we get the
        authorized card back we can toggle the flag back and return which will
        cause the outer loop to continue
        '''
        logging.info("User card removed")
        self.card_present = False
        self.proxy_uid = -1

        logging.debug("Setting display to yellow")
        self.box.set_display_color(YELLOW)

        grace_count = 0
        self.box.has_button_been_pressed() # clear pending events

        logging.debug("Waiting for card to return")

        previous_uid = -1

        while self.running and grace_count < 16:
            os.system("echo wait_auth_card_return > /tmp/boxactivity")
            # Check for button press
            if self.box.has_button_been_pressed():
                logging.debug("Button pressed")
                break

            # Scan for card
            uid = self.box.read_RFID_card()
            if uid > -1 and uid != previous_uid:
                # we read a card
                previous_uid = uid
                if uid == self.authorized_uid:
                    # card returned
                    self.card_present = True
                    logging.debug("Authorized card returned")
                    break
                elif not self.training_mode: # trainers may not use proxy cards
                    if uid in self.proxy_cards:
                        self.card_present = True
                        self.proxy_uid = uid
                        self.user_is_trainer = False
                        self.proxy_cards.remove(uid)
                        self.proxy_cards.append(uid)
                        logging.info("Authorized user -> cached proxy card")
                        break

                    elif uid in self.training_cards:
                        if self.proxy_uid > -1:
                            logging.info("Training disallowed with proxy")
                        elif not self.user_is_trainer:
                            logging.info("User is not a trainer")
                        else:
                            logging.info("Cached training card %s authorized",
                                          uid)
                            self.db.log_access_attempt(uid, self.equipment_id, True)
                            self.card_present = True
                            self.training_mode = True
                            self.user_is_trainer = False
                            self.authorized_uid = uid
                            self.training_cards.remove(uid)
                            self.training_cards.append(uid)
                            break

                    else:
                        logging.debug("Checking database for card type")
                        card_type = self.db.get_card_type(uid)
                        if Database.PROXY_CARD == card_type:
                            self.card_present = True
                            self.proxy_uid = uid
                            self.user_is_trainer = False
                            del self.proxy_cards[0]
                            self.proxy_cards.append(uid)
                            logging.debug("Authorized user -> proxy card")
                            break

                        if Database.TRAINING_CARD == card_type:
                            logging.info("Training card %s detected, authorized?", uid)
                            if self.proxy_uid > -1:
                                logging.info("Training card disallowed with proxy")
                            elif not self.user_is_trainer:
                                logging.info("User is not a trainer")
                            elif self.db.is_training_card_for_equipment_type(uid, self.equipment_type_id):
                                logging.info("Training card %s authorized",
                                              uid)
                                self.db.log_access_attempt(uid, self.equipment_id, True)
                                self.card_present = True
                                self.training_mode = True
                                self.user_is_trainer = False
                                del self.training_cards[0]
                                self.training_cards.append(uid)
                                self.authorized_uid = uid
                                break
                            else:
                                logging.info("Training card %s NOT authorized for %s",
                                          uid, self.equipment_type)

            grace_count += 1
            self.box.set_buzzer(True)
            self.box.flash_display(YELLOW, 100, 1, YELLOW)
            self.box.set_buzzer(False)

        if self.running and not self.card_present:
            logging.info("Grace period following card removal expired; shutting down equipment")
        logging.debug("wait_for_user_card_return() ends")


    def wait_for_timeout_grace_period_to_expire(self):
        """
        Four posibilities:
        1) user presses button with card in to renew session
        2) user removes card and presses button to end session
        3) user removes card but does not press button to end session
        4) user forgot their card
        """
        logging.info("Equipment usage timeout")
        grace_count = 0
        self.box.has_button_been_pressed() # clear pending events
        logging.debug("Setting display to orange")
        self.box.set_display_color(ORANGE)
        logging.debug("Starting grace period")
        while self.running and grace_count < 600:
            os.system("echo grace_timeout > /tmp/boxactivity")
            #check for button press
            if self.box.has_button_been_pressed():
                logging.info("Button was pressed, extending time out period")
                uid = self.box.read_RFID_card()
                uid2 = self.box.read_RFID_card() #try twice since reader fails consecutive reads
                if -1 < uid or -1 < uid2:
                    # Card is still present session renewed
                    logging.debug("Card still present, renew session")
                    return
                else:
                    # Card removed end session
                    logging.debug("Card removed, end session")
                    self.card_present = False
                    return
            else:
                grace_count += 1

            if 1 > (grace_count % 2):
                logging.debug("Starting to flash display orange")
                self.box.flash_display(ORANGE, 100, 1, ORANGE)

            if 1 > (grace_count % 20):
                self.box.set_buzzer(True)
            else:
                self.box.set_buzzer(False)

            sleep(0.1)

        logging.debug("Grace period expired")
        # grace period expired
        # stop the buzzer
        self.box.set_buzzer(False)

        # shutdown now, do not wait for email or card removal
        self.box.set_equipment_power_on(False)

        # was forgotten card?
        logging.debug("Checking for forgotten card")
        uid = self.box.read_RFID_card()
        uid2 = self.box.read_RFID_card() #try twice since reader fails consecutive reads
        if -1 < uid or -1 < uid2:
            # Card is still present
            logging.info("User card left in portal box. Sending user email.")
            logging.debug("Setting display to wipe blue")
            self.box.set_display_color_wipe(BLUE, 50)
            logging.debug("Getting user email ID from DB")
            user = self.db.get_user(self.authorized_uid)
            try:
                logging.debug("Mailing user")
                self.emailer.send(user[1], "Access Card left in PortalBox", "{} it appears you left your access card in a badge box for the {} in the {}".format(user[0], self.equipment_type, self.location))
            except Exception as e:
                logging.error("{}".format(e))

            logging.debug("Setting display to red")
            self.box.set_display_color(RED)
            while self.running and self.card_present:
                os.system("echo user_left_card > /tmp/boxactivity")
            # wait for card to be removed... we need to make sure we don't have consecutive read failure
                uid = self.box.read_RFID_card()
                uid2 = self.box.read_RFID_card() #try twice since reader fails consecutive reads
                if 0 > uid and 0 > uid2:
                    self.card_present = False
            logging.debug("Stopped running or card removed")
        else:
            # Card removed end session
            logging.debug("Card removed, session ends")
            self.card_present = False

        logging.debug("wait_for_timeout_grace_period_to_expire() ends")


    def exit(self):
        ''' Stop looping in all run states '''
        logging.info("Service Exiting")
        os.system("echo service_exit > /tmp/boxactivity")
        os.system("echo False > /tmp/running")
        self.box.set_equipment_power_on(False)
        if self.running:
            if self.equipment_id:
                logging.debug("Logging exit-while-running to DB")
                self.db.log_shutdown_status(self.equipment_id, False)
            self.running = False
        else:
            # never made it to the run state
            logging.debug("Not running, just exit")
            sys.exit()


    def handle_interupt(self, signum, frame):
        ''' Stop the service from a signal'''
        logging.debug("Interrupted")
        os.system("echo service_interrupt > /tmp/boxactivity")
        self.exit()


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

    # Create Badge Box Service
    logging.debug("Creating PortalBoxApplication")
    service = PortalBoxApplication(settings)

    # Add signal handler so systemd can shutdown service
    signal.signal(signal.SIGINT, service.handle_interupt)
    signal.signal(signal.SIGTERM, service.handle_interupt)

    # Run service
    logging.debug("Running PortalBoxApplication")
    service.run()
    logging.debug("PortalBoxApplication ends")

    # Cleanup and exit
    os.system("echo False > /tmp/running")
    service.box.cleanup()
    logging.debug("Shutting down logger")
    logging.shutdown()
