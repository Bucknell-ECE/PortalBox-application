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
        self.flash_rate = 3

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
        if(
            self.service.timeout_minutes > 0 and # The timeout period for the equipment type isn't infinite
            (datetime.now() - self.timeout_start) > self.timeout_delta # And that its actaully timed out
          ):
            logging.debug("Timeout period expired with time passed = {}".format((datetime.now() - self.timeout_start)))
            return True
        else:
            return False


    def grace_expired(self):
        """
        Determines whether or not the grace period has expired
        @return a boolean which is True when the grace period has expired
        """
        if((datetime.now() - self.grace_start) > self.grace_delta):
            logging.debug("Grace period expired with time passed = {}".format((datetime.now() - self.grace_start)))
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
            try:
                self.service.connect_to_database()
            except Exception as e:
                raise e

            self.service.box.set_display_color(self.service.settings["display"]["setup_color_db"])

            try:
                self.service.connect_to_email()
            except Exception as e:
                raise e

            self.service.box.set_display_color(self.service.settings["display"]["setup_color_email"])

            try:
                self.service.get_equipment_role()
            except Exception as e:
                raise e

            try:
                self.service.record_ip()
            except Exception as e:
                raise e

            self.service.box.set_display_color(self.service.settings["display"]["setup_color_role"])

            self.timeout_delta = timedelta(minutes = self.service.timeout_minutes)
            self.grace_delta = timedelta(seconds = self.service.settings.getint("user_exp","grace_period"))
            self.allow_proxy = self.service.allow_proxy
            self.flash_rate = self.service.settings.getint("display","flash_rate")
            self.next_state(IdleNoCard, input_data)
            self.service.box.buzz_tone(500,.2)
            #self.service.box.play_song("/opt/portal-box/portalbox/RickRoll.txt")
        except Exception as e:
            logging.error("Unable to complete setup exception raised: \n\t{}".format(e))
            self.next_state(Shutdown, input_data)
            raise(e)




class Shutdown(State):
    """
    Shuts down the box
    """
    def __call__(self, input_data):
        self.service.box.set_equipment_power_on(False)
        self.service.shutdown(input_data["card_id"]) #logging the shutdown is done in this method



class IdleNoCard(State):
    """
    The state that it will spend the most time in, waits for some card input
    """
    def __call__(self, input_data):
        if(input_data["card_id"] > 0):
            self.next_state(IdleUnknownCard, input_data)

    def on_enter(self, input_data):
        #self.service.box.set_display_color(self.service.settings["display"]["sleep_color"])
        self.service.box.sleep_display()

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
        logging.debug("is USER? {}".format(input_data["card_type"] == CardType.USER_CARD))
        logging.debug(f"User authority level:{self.user_authority_level}")
        logging.debug(f"Proxy Id:{self.proxy_id}")
        #Proxy card, AND not coming from training mode
        if(
            input_data["card_type"] == CardType.PROXY_CARD and
            self.training_id <= 0 
          ):
            #If the machine allows proxy cards then go into proxy mode
            if(self.allow_proxy == 1):
                self.next_state(RunningProxyCard, input_data)
                self.service.box.stop_buzzer(stop_beeping = True)
            #Otherwise go into a grace period 
            else:
                self.next_state(RunningUnauthCard, input_data)
                self.service.box.stop_buzzer(stop_beeping = True)

        #If its the same user as before then just go back to auth user
        elif(input_data["card_id"] == self.auth_user_id):
            self.next_state(RunningAuthUser, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)

        #User card, AND
        #The box was intially authorized by a trainer or admin AND
        #Not coming from proxy mode AND
        #Not coming from training mode, OR the card is the same one that was being trained AND
        #An unathorized user

        elif(
            input_data["card_type"] == CardType.USER_CARD and
            self.user_authority_level >= 3 and
            self.proxy_id <= 0 and
            (self.training_id <= 0 or self.training_id == input_data["card_id"]) and
            not input_data["user_is_authorized"]
            ):
            self.next_state(RunningTrainingCard, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)

        elif(self.grace_expired()):
            logging.debug("Exiting Grace period because the grace period expired")
            self.next_state(AccessComplete, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)

        if(input_data["button_pressed"]):
            logging.debug("Exiting Grace period because button was pressed")
            self.next_state(AccessComplete, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)
#        else:
#            self.next_state(AccessComplete, input_data)

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

        #If the card is new ie, not coming from a timeout then don't log this as a new session
        if self.auth_user_id != input_data["card_id"]:
            self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, True)

        
        self.auth_user_id = input_data["card_id"]
        self.user_authority_level = input_data["user_authority_level"]




class IdleUnauthCard(State):
    """
    An unauthorized card has been put into the machine, turn off machine
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard, input_data)

    def on_enter(self, input_data):
        self.service.box.beep_once()
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
        if(input_data["card_id"] > 0 and input_data["card_type"] != CardType.INVALID_CARD):
            self.next_state(RunningUnknownCard, input_data)
           # self.service.box.stop_buzzer(stop_beeping = True)

        if(self.grace_expired()):
            logging.debug("Exiting Grace period because the grace period expired")
            self.next_state(AccessComplete, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)
                
        if(input_data["button_pressed"]):
            logging.debug("Exiting Grace period because button was pressed")
            self.next_state(AccessComplete, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)

    def on_enter(self, input_data):
        logging.info("Grace period started")
        self.grace_start = datetime.now()
        self.service.box.flash_display(
            self.service.settings["display"]["no_card_grace_color"],
            self.grace_delta.seconds * 1000,
            int(self.grace_delta.seconds * self.flash_rate)
            )
        
        self.service.box.start_beeping(
            800,
            self.grace_delta.seconds * 1000,
            int(self.grace_delta.seconds * self.flash_rate)
            )

class RunningUnauthCard(State):
    """
    A card type which isn't allowed on this machine has been read while the machine is running, gives the user time to put back their authorized card
    """
    def __call__(self, input_data):
        #Card detected and its the same card that was using the machine before the unauth card was inserted 
        if(
            input_data["card_id"] > 0 and
            input_data["card_id"] == self.auth_user_id
          ):
            self.next_state(RunningUnknownCard, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)

        if(self.grace_expired()):
            logging.debug("Exiting Running Unauthorized Card because the grace period expired")
            self.next_state(AccessComplete, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)
                
        if(input_data["button_pressed"]):
            logging.debug("Exiting  Running Unauthorized Card because button was pressed")
            self.next_state(AccessComplete, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)

    def on_enter(self, input_data):
        logging.info("Unauthorized Card grace period started")
        logging.info("Card type was {}".format(input_data["card_type"]))
        self.grace_start = datetime.now()
        self.service.box.set_display_color(self.service.settings["display"]["unauth_card_grace_color"])
        self.service.box.flash_display(
            self.service.settings["display"]["unauth_card_grace_color"],
            self.grace_delta.seconds * 1000,
            int(self.grace_delta.seconds * self.flash_rate)
            )
        
        self.service.box.start_beeping(
            800,
            self.grace_delta.seconds * 1000,
            int(self.grace_delta.seconds * self.flash_rate)
            )


class RunningTimeout(State):
    """
    The machine has timed out, has a grace period before going to the next state
    """
    def __call__(self, input_data):
        #If the button has been pressed, then re-read the card
        if(input_data["button_pressed"]):
            self.next_state(RunningUnknownCard, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)
        #If the card is removed then finish the access attempt
        if(input_data["card_id"] <= 0):
            self.next_state(AccessComplete, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)

        if(self.grace_expired()):
            self.next_state(IdleAuthCard, input_data)
            self.service.box.stop_buzzer(stop_beeping = True)

    def on_enter(self, input_data):
        logging.info("Machine timout, grace period started")
        self.grace_start = datetime.now()
        self.service.box.flash_display(
            self.service.settings["display"]["grace_timeout_color"],
            self.grace_delta.seconds * 1000,
            int(self.grace_delta.seconds * self.flash_rate)
            )
        self.service.box.start_beeping(
            800,
            self.grace_delta.seconds * 1000,
            int(self.grace_delta.seconds * self.flash_rate)
            )

class IdleAuthCard(State):
    """
    The timout grace period is expired and the user is sent and email that
        their card is still in the machine, waits until the card is removed
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(IdleNoCard, input_data)

    def on_enter(self, input_data):
        self.service.box.set_equipment_power_on(False)
        self.service.db.log_access_completion(self.auth_user_id, self.service.equipment_id)
        
        #If its a proxy card 
        if(self.proxy_id > 0):
            self.service.send_user_email_proxy(self.auth_user_id)
        if(self.training_id > 0):
            self.service.send_user_email_training(self.auth_user_id, self.training_id)
        else:
            self.service.send_user_email(input_data["card_id"])
        self.service.box.set_display_color(self.service.settings["display"]["timeout_color"])
        self.proxy_id = 0
        self.training_id = 0
        self.auth_user_id = 0
        self.user_authority_level = 0

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
        self.timeout_start = datetime.now()
        self.training_id = 0
        
        #If the same proxy card is being reinserted then don't log it
        if self.proxy_id != input_data["card_id"]:
            self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, True)
        self.proxy_id = input_data["card_id"]
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display_color(self.service.settings["display"]["proxy_color"])
        self.service.box.beep_once()

class RunningTrainingCard(State):
    """
    Runs the machine in the training mode
    """
    def __call__(self, input_data):
        if(input_data["card_id"] <= 0):
            self.next_state(RunningNoCard, input_data)
        if(self.timeout_expired()):
            self.next_state(RunningTimeout, input_data)

    def on_enter(self, input_data):
        self.timeout_start = datetime.now()
        self.proxy_id = 0
        #If the training card is new and not just reinserted after a grace period
        if self.training_id != input_data["card_id"]:
            self.service.db.log_access_attempt(input_data["card_id"], self.service.equipment_id, True)
        self.training_id = input_data["card_id"]
        
        self.service.box.set_equipment_power_on(True)
        self.service.box.set_display_color(self.service.settings["display"]["training_color"])
        self.service.box.beep_once()
