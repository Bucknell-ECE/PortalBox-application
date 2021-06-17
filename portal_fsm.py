"""
The finite state machine for the portal box service.

2021-05-07 KJHass

Inspired by @cmcginty's answer at
https://stackoverflow.com/questions/2101961/python-state-machine-design
"""
# from standard library
from datetime import datetime, timedelta
import logging

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
    def next_state(self, cls):
        logging.debug("State transtition : {0} -> {1}".format(self.__class__.__name__,cls.__name__))
        self.__class__ = cls
        self.on_enter()


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
      if((datetime.now() - self.timeout_start) > self.grace_delta):
        return True
      else:
        return False

class Setup(State):
    def __call__(self, input_data):
        self.next_state(IdleNoCard)

    def on_enter(self, input_data):
        #Do everything related to setup, if anything fails and returns an exception, then go to Shutdown
        try:
            self.service.box.wipe_display(self.service.settings["setup_color"])
            self.service.connect_to_database()
            self.service.connect_to_email()
            self.service.get_equipment_role()
            self.timeout_delta = datetime.timeDelta(minutes = self.service.timeout_minutes)
            self.grace_delta = datetime.timeDelta(seconds = self.service.settings["grace_period"])
        except Exception as e:
            logging.error("{}".format(e))
            self.next_state(Shutdown)



class Shutdown(State):

    def __call__(self, input_data):
      self.service.box.set_equipment_power_on(False)
      self.service.box.set_display_color()# Turns off the display
      self.service.shutdown() #logging the shutdown is done in this method



class IdleNoCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] > 0):
            self.next_state(IdleUnknownCard)

    def on_enter(self, input_data):
        self.service.box.pulse_display(self.service.settings["sleep_color"])

class AccessComplete(State):
    def __call__(self, input_data):
        self.next_state(IdleNoCard)

    def on_enter(self, input_data):
        self.service.db.log_access_completion(input_data["card_id"], self.service.equipment_id)
        self.service.box.set_equipment_power_on(False)

class IdleUnknownCard(State):

    def __call__(self, input_data):
        if(input_data["card_type"] == CardType.SHUTDOWN_CARD):
            self.next_state(Shutdown)

        elif(input_data["user_is_authorized"]):
            self.next_state(RunningAuthUser)

        else:
            self.next_state(IdleUnauthCard)


    def on_enter(self, input_data):
        pass

class RunningAuthUser(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout)

    def on_enter(self, input_data):
        self.timeout_start = datetime.now()
        self.proxy_id = 0
        self.training_id = 0
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display(self.service.settings["auth_color"])
        self.auth_user_id = input_data["card_id"]
        self.service.db.log_access_attempt(input_data["card_id"], self.equipment_id, True)


class IdleUnauthCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard)

    def on_enter(self, input_data):
        self.service.box.flash_display(self.service.settings["unauth_color"])
        self.service.db.log_access_attempt(input_data["card_id"], self.equipment_id, False)

class RunningNoCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] > 0):
            if(input_data["card_type"] == CardType.PROXY_CARD):
                self.next_state(RunningProxyCard)
            elif(input_data["card_type"] == CardType.TRAINING_CARD):
                self.next_state(RunningTrainingCard)
            elif(input_data["card_type"] == CardType.USER_CARD):
                if(input_data["card_id"] == self.auth_user_id):
                    self.next_state(RunningAuthUser)
            else:
                self.next_state(IdleUnknownCard)

        elif(
                self.grace_expired or
                input_data["button_pressed"]
            ):
            self.next_state(IdleNoCard)

    def on_enter(self, input_data):
        self.grace_start = datetime.now()
        self.service.box.flash_display("no_card_grace_color")

class RunningTimeout(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard)

        if(self.grace_expired()):
            self.next_state(IdleAuthCard)

        if(input_data["button_pressed"]):
            if(input_data["card_type"] == CardType.PROXY_CARD):
                self.next_state(RunningProxyCard)
            elif(input_data["card_type"] == CardType.TRAINING_CARD):
                self.next_state(RunningTrainingCard)
            elif(input_data["card_type"] == CardType.USER_CARD):
                if(input_data["card_id"] == self.auth_user_id):
                    self.next_state(RunningAuthUser)
            else:
                self.next_state(IdleUnknownCard)

    def on_enter(self, input_data):
        self.grace_start = datetime.now()
        self.service.box.flash_display(self.service.settings["grace_timeout_color"])

class IdleAuthCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard)

    def on_enter(self, input_data):
        self.service.box.set_equipment_power_on(False)
        self.service.send_user_email(input_data["card_id"])
        self.service.box.set_display(self.service.settings["timeout_color"])

class RunningProxyCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout)

    def on_enter(self, input_data):
        self.training_id = 0
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display(self.service.settings["proxy_color"])
        self.proxy_id = input_data["card_id"]
        self.service.db.log_access_attempt(input_data["card_id"], self.equipment_id, True)

class RunningTrainingCard(State):

    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout)

    def on_enter(self, input_data):
        self.proxy_id = 0
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display(self.service.settings["training_color"])
        self.training_id = input_data["card_id"]
        self.service.db.log_access_attempt(input_data["card_id"], self.equipment_id, True)
