"""
The finite state machine for the portal box service.

2021-05-07 KJHass

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
      logging.debug("checking if grace time has expired")
      if((datetime.now() - self.grace_start) > self.grace_delta):
          logging.debug("time passed: {}".format((datetime.now() - self.grace_start)))
          return True
      else:
          return False

class Setup(State):
    def __call__(self, input_data):
        self.next_state(IdleNoCard, input_data)

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
        except Exception as e:
            logging.error("Unable to complete setup exception raised \n\t{}".format(e))
            self.next_state(Shutdown, input_data)



class Shutdown(State):

    def __call__(self, input_data):
      self.service.box.set_equipment_power_on(False)
      self.service.box.set_display_color()# Turns off the display
      self.service.shutdown() #logging the shutdown is done in this method



class IdleNoCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] > 0):
            self.next_state(IdleUnknownCard, input_data)

    def on_enter(self, input_data):
        self.service.box.set_display_color(self.service.settings["display"]["sleep_color"])

class AccessComplete(State):
    def __call__(self, input_data):
        self.next_state(IdleNoCard, input_data)

    def on_enter(self, input_data):
        self.service.db.log_access_completion(input_data["card_id"], self.service.equipment_id)
        self.service.box.set_equipment_power_on(False)

class IdleUnknownCard(State):

    def __call__(self, input_data):
        pass


    def on_enter(self, input_data):
        if(input_data["card_type"] == CardType.SHUTDOWN_CARD):
            logging.info("Inserted a shutdown card, shutting the box down")
            self.next_state(Shutdown, input_data)

        elif(input_data["user_is_authorized"]):
            logging.info("Inserted card with id {}, is authorized for this equipment".format(input_data["card_id"]))
            self.next_state(RunningAuthUser, input_data)

        else:
            logging.info("Inserted card with id {}, is not authorized for this equipment".format(input_data["card_id"]))
            self.next_state(IdleUnauthCard, input_data)

class RunningAuthUser(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard, input_data)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout, input_data)

    def on_enter(self, input_data):
        self.timeout_start = datetime.now()
        self.proxy_id = 0
        self.training_id = 0
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display_color(self.service.settings["display"]["auth_color"])
        self.auth_user_id = input_data["card_id"]
        self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, True)


class IdleUnauthCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard, input_data)

    def on_enter(self, input_data):
        self.service.box.set_display_color(self.service.settings["display"]["unauth_color"])
        self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, False)

class RunningNoCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] > 0):
            grace_timer.cancel()
            if(input_data["card_type"] == CardType.PROXY_CARD):
                self.next_state(RunningProxyCard, input_data)
            elif(input_data["card_type"] == CardType.TRAINING_CARD):
                self.next_state(RunningTrainingCard, input_data)
            elif(input_data["card_type"] == CardType.USER_CARD):
                if(input_data["card_id"] == self.auth_user_id):
                    self.next_state(RunningAuthUser, input_data)
            else:
                self.next_state(IdleUnknownCard, input_data)

        elif(
                self.grace_expired() or
                input_data["button_pressed"]
            ):
            self.next_state(IdleNoCard, input_data)

    def on_enter(self, input_data):
        self.grace_start = datetime.now()
        self.service.box.flash_display(self.service.settings["display"]["no_card_grace_color"],self.grace_delta.total_seconds(),5)

class RunningTimeout(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard, input_data)

        if(self.timeout_expired()):
            self.next_state(IdleAuthCard, input_data)

        if(input_data["button_pressed"]):
            if(input_data["card_type"] == CardType.PROXY_CARD):
                self.next_state(RunningProxyCard, input_data)
            elif(input_data["card_type"] == CardType.TRAINING_CARD):
                self.next_state(RunningTrainingCard, input_data)
            elif(input_data["card_type"] == CardType.USER_CARD):
                if(input_data["card_id"] == self.auth_user_id):
                    self.next_state(RunningAuthUser, input_data)
            else:
                self.next_state(IdleUnknownCard, input_data)

    def on_enter(self, input_data):
        self.timeout_start = datetime.now()
        self.service.box.flash_display(self.service.settings["display"]["grace_timeout_color"],self.timeout_delta.total_seconds(),5)
        self.service.box.set_display_color(self.service.settings["display"]["grace_timeout_color"])

class IdleAuthCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard, input_data)

    def on_enter(self, input_data):
        self.service.box.set_equipment_power_on(False)
        self.service.send_user_email(input_data["card_id"])
        self.service.box.set_display_color(self.service.settings["display"]["timeout_color"])

class RunningProxyCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard, input_data)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout, input_data)

    def on_enter(self, input_data):
        self.training_id = 0
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display_color(self.service.settings["display"]["proxy_color"])
        self.proxy_id = input_data["card_id"]
        self.service.db.log_access_attempt(input_data["card_id"], self.equipment_id, True)

class RunningTrainingCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard, input_data)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout, input_data)

    def on_enter(self, input_data):
        self.proxy_id = 0
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display_color(self.service.settings["display"]["training_color"])
        self.training_id = input_data["card_id"]
        self.service.db.log_access_attempt(input_data["card_id"], self.equipment_id, True)
