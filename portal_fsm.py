"""
The finite state machine for the portal box service.

2021-05-07 KJHass
    -Created skeleton code for the class
2021-06-26 James Howe
    -Finished the rest of the class

Inspired by @cmcginty's answer at
https://stackoverflow.com/questions/2101961/python-state-machine-design
"""
# from standard library
from datetime import datetime, timedelta
import logging
import threading

# our code
from CardType import CardType

class State(object):
    """The parent state for all FSM states."""

    # Shared state variables that keep a little history of the cards
    # that have been presented to the box.
    auth_user_id = -1
    proxy_id = -1
    training_id = -1
    user_authority_level = 0

    # Create the FSM.
    # Create a reference to the portal box service, which includes the
    #   box itself, the database, the emailer, etc.
    # Calculate datetime objects for the grace time when a card is
    #   removed and for the equipment timeout limit
    # Create datetime objects for the beginning of a grace period or
    #   timeout, their value is not important.
    def __init__(self, portal_box_service, input_data):
        self.service = portal_box_service
        self.timeout_start = datetime.now()
        self.grace_start = datetime.now()
        self.timeout_delta = timedelta(0)
        self.grace_delta = timedelta(seconds = 2)
        self.on_enter(input_data)

    # Transition the FSM to another state, and invoke the on_enter()
    # method for the new state.
    def next_state(self, cls, input_data):
        logging.debug("State transtition : {0} -> {1}".format(self.__class__.__name__,cls.__name__))
        self.__class__ = cls
        self.on_enter(input_data)


    def on_enter(self, input_data):
        """
        A default on_enter() method, just logs which state is being entered
        """
        logging.debug("Entering state {}".format(self.__class__.__name__))


    def timeout_expired(self):
      """
      Determines whether or not the timeout period has expired
      @return a boolean which is True when the timeout period has expired
      """
      if (
            self.service.timeout_minutes > 0 and # Not infinite
            (datetime.now() - self.timeout_start) > self.timeout_delta # timed out
        ):
          return True
      else:
          return False


    def grace_expired(self):
      """
      Determines whether or not the grace period has expired
      @return a boolean which is True when the grace period has expired
      """
      if((datetime.now() - self.grace_start) > self.grace_delta):
          logging.debug("time passed: {}".format((datetime.now() - self.grace_start)))
          return True
      else:
          return False

class Setup(State):
    """
    The first state, trys to setup everything that needs to be setup and goes
        to shutdown if it can't
    """
    def __call__(self, input_data):
        pass

    def on_enter(self, input_data):
        #Do everything related to setup, if anything fails and returns an exception, then go to Shutdown
        logging.info("Starting setup")
        self.service.box.set_display_color(self.service.settings["display"]["setup_color"])
        try:
            self.service.connect_to_database()
            self.service.connect_to_email()
            self.service.get_equipment_role()
            self.timeout_delta = timedelta(minutes = self.service.timeout_minutes)
            self.grace_delta = timedelta(seconds = self.service.settings.getint("user_exp","grace_period"))
            self.next_state(IdleNoCard, input_data)
        except Exception as e:
            logging.error("Unable to complete setup exception raised: \n\t{}".format(e))
            self.next_state(Shutdown, input_data)




class Shutdown(State):
    """
    Shuts down the box
    """
    def __call__(self, input_data):
        self.service.box.set_equipment_power_on(False)
        self.service.box.set_display_color()# Turns off the display
        self.service.shutdown() #logging the shutdown is done in this method



class IdleNoCard(State):
    """
    The state that it will spend the most time in, waits for some card input
    """
    def __call__(self, input_data):
        if(input_data["card_id"] > 0):
            self.next_state(IdleUnknownCard, input_data)

    def on_enter(self, input_data):
        self.service.box.set_display_color(self.service.settings["display"]["sleep_color"])

class AccessComplete(State):
    """
    Before returning to the Idle state it logs the machine usage, and turns off
        the power to the machine
    """
    def __call__(self, input_data):
        pass

    def on_enter(self, input_data):
        logging.info("Usage complete, logging usage and turning off machine")
        self.service.db.log_access_completion(self.auth_user_id, self.service.equipment_id)
        self.service.box.set_equipment_power_on(False)
        self.proxy_id = 0
        self.training_id = 0
        self.auth_user_id = 0
        self.user_authority_level = 0
        self.next_state(IdleNoCard, input_data)

class IdleUnknownCard(State):
    """
    A card input has been read, the next state is determined by the card type
    """
    def __call__(self, input_data):
        pass


    def on_enter(self, input_data):
        if(input_data["card_type"] == CardType.SHUTDOWN_CARD):
            logging.info("Inserted a shutdown card, shutting the box down")
            self.next_state(Shutdown, input_data)

        elif(input_data["user_is_authorized"] and input_data["card_type"] == CardType.USER_CARD):
            logging.info("Inserted card with id {}, is authorized for this equipment".format(input_data["card_id"]))
            self.next_state(RunningAuthUser, input_data)

        else:
            logging.info("Inserted card with id {}, is not authorized for this equipment".format(input_data["card_id"]))
            self.next_state(IdleUnauthCard, input_data)
class RunningUnknownCard(State):
    """
    A Card has been read from the no card grace period
    """
    def __call__(self, input_data):

        #Proxy card, AND not coming from training mode
        if(
            input_data["card_type"] == CardType.PROXY_CARD and
            self.training_id <= 0
          ):
            self.next_state(RunningProxyCard, input_data)
        elif(input_data["card_id"] == self.auth_user_id):
            self.next_state(RunningAuthUser, input_data)

        #User card, AND
        #The box was intially authrized by a trainer AND
        #Not coming from proxy mode AND
        #Not coming from training mode, OR the card is the same one that was being trained AND
        #An unathorized user
        elif(
            input_data["card_type"] == CardType.USER_CARD and
            self.user_authority_level >= 2 and
            self.proxy_id <= 0 and
            (self.training_id <= 0 or self.training_id == input_data["card_id"]) and
            self.service.get_user_auths(input_data["card_id"])
            ):
            self.next_state(RunningTrainingCard, input_data)
        else:
            self.next_state(IdleUnknownCard, input_data)

class RunningAuthUser(State):
    """
    An authorized user has put their card in, the machine will function
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard, input_data)

        if(self.timeout_expired()):
            self.next_state(RunningTimeout, input_data)

    def on_enter(self, input_data):
        logging.info("Authorized card in box, turning machine on and logging access")
        self.timeout_start = datetime.now()
        self.proxy_id = 0
        self.training_id = 0
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display_color(self.service.settings["display"]["auth_color"])
        self.service.box.beep_once()
        self.auth_user_id = input_data["card_id"]
        self.user_authority_level = input_data["user_authority_level"]
        self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, True)



class IdleUnauthCard(State):
    """
    An unauthorized card has been put into the machine, turn off machine
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard, input_data)

    def on_enter(self, input_data):
        self.service.box.set_equipment_power_on(False)
        self.service.box.set_display_color(self.service.settings["display"]["unauth_color"])
        self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, False)

class RunningNoCard(State):
    """
    An authorized card has been removed, waits for a new card until the grace
        period expires, or a button is pressed
    """
    def __call__(self, input_data):
        #Card detected
        if(input_data["card_id"] > 0):
            self.service.box.stop_flashing()
            self.service.box.stop_beeping()
            self.next_state(RunningUnknownCard, input_data)
        if(self.grace_expired() or input_data["button_pressed"]):
            self.service.box.stop_flashing()
            self.service.box.stop_beeping()
            self.next_state(AccessComplete, input_data)

    def on_enter(self, input_data):
        logging.info("Grace period started")
        self.grace_start = datetime.now()
        self.service.box.flash_display(self.service.settings["display"]["no_card_grace_color"],self.grace_delta.seconds,self.grace_delta.seconds*2)
        self.service.box.start_beeping()

class RunningTimeout(State):
    """
    The machine has timed out, has a grace period before going to the next state
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.service.box.stop_flashing()
            self.service.box.stop_beeping()
            self.next_state(AccessComplete, input_data)

        if(self.grace_expired()):
            self.service.box.stop_flashing()
            self.service.box.stop_beeping()
            self.next_state(IdleAuthCard, input_data)

        if(input_data["button_pressed"]):
            self.service.box.stop_flashing()
            self.service.box.stop_beeping()
            self.next_state(RunningUnknownCard, input_data)

    def on_enter(self, input_data):
        logging.info("Machine timout, grace period started")
        self.grace_start = datetime.now()
        self.service.box.flash_display(self.service.settings["display"]["grace_timeout_color"],1.0)
        self.service.box.start_beeping(1.0)

class IdleAuthCard(State):
    """
    The timout grace period is expired and the user is sent and email that
        their card is still in the machine, waits until the card is removed
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(AccessComplete, input_data)

    def on_enter(self, input_data):
        self.service.box.set_equipment_power_on(False)
        self.service.send_user_email(input_data["card_id"])
        self.service.box.set_display_color(self.service.settings["display"]["timeout_color"])

class RunningProxyCard(State):
    """
    Runs the machine in the proxy mode
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard, input_data)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout, input_data)

    def on_enter(self, input_data):
        self.training_id = 0
        self.proxy_id = input_data["card_id"]
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display_color(self.service.settings["display"]["proxy_color"])
        self.service.box.beep_once()
        self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, True)

class RunningTrainingCard(State):
    """
    runs the machine in the training mode
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard, input_data)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout, input_data)

    def on_enter(self, input_data):
        self.proxy_id = 0
        self.training_id = input_data["card_id"]
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display_color(self.service.settings["display"]["training_color"])
        self.service.box.beep_once()
        self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, True)
