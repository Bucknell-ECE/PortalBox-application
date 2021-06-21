#!python3

# PortalBox.py acts as a hardware abstraction layer exposing a somewhat
# simple API to the hardware
"""
2021-03-25 Version   KJHass
  - imports os and periodically writes to files in /tmp to feed the watchdog
  - defines colors RED and YELLOW for display if RFID hangs
  - verifies that RFID serial # is correct, else decide RFID hanging
  - verifies that another specific register in RFID is valid, else decide
    that RFID is hanging
  - if the RFID hangs, go into an infinite loop of beeping and flashing, wait
    for the watchdog timer to restart this service
  - defines the NRST pin for the RFID module, defines it as an output, and
    sets its state appropriately
  - adds more logging for debugging purposes
"""
# from standard library
import os
import logging
from time import sleep, time_ns
import threading

# Our libraries
from .MFRC522 import MFRC522 # this is a modified version of https://github.com/mxgxw/MFRC522-python
                            # bundling it is sort of a license violation (can't change license)
                            # however the library has issues and is in need of replacement
from .display.AbstractController import BLACK

# third party
import RPi.GPIO as GPIO


# Constants defining how peripherals are connected
REVISION_ID_RASPBERRY_PI_0_W = "9000c1"

GPIO_INTERLOCK_PIN = 11
GPIO_BUZZER_PIN = 33
GPIO_BUTTON_PIN = 35
GPIO_SOLID_STATE_RELAY_PIN = 37
GPIO_RFID_NRST_PIN = 13


RED = b'\xFF\x00\x00'
YELLOW = b'\xFF\xFF\x00'

# Utility functions
def get_revision():
        file = open("/proc/cpuinfo","r")
        for line in file:
            if "Revisio" in line:
                file.close()
                return line.rstrip().split(' ')[1]
        file.close()
        return -1


class PortalBox:
    '''
    Wrapper to manage peripherals
    '''
    def __init__(self, settings):
        #detect raspberry pi version
        self.is_pi_zero_w = REVISION_ID_RASPBERRY_PI_0_W == get_revision()

        ## set GPIO to known good state
        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)

        ## GPIO pin assignments and initializations
        GPIO.setup(GPIO_RFID_NRST_PIN, GPIO.OUT)
        GPIO.output(GPIO_RFID_NRST_PIN, 0)       # Reset RFID

        GPIO.setup(GPIO_INTERLOCK_PIN, GPIO.OUT)
        GPIO.setup(GPIO_BUZZER_PIN, GPIO.OUT)
        GPIO.setup(GPIO_SOLID_STATE_RELAY_PIN, GPIO.OUT)

        GPIO.setup(GPIO_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.add_event_detect(GPIO_BUTTON_PIN, GPIO.RISING)

        GPIO.output(GPIO_RFID_NRST_PIN, 1)       # Deassert RFID reset

        self.set_equipment_power_on(False)

        # Create display controller
        if self.is_pi_zero_w:
            logging.debug("Creating display controller")
            from .display.R2NeoPixelController import R2NeoPixelController
            self.display_controller = R2NeoPixelController(settings)
        else:
            logging.info("Did not connect to display driver, display methods will be unavailable")
            self.display_controller = None

        # Get buzzer enabled from settings
        self.buzzer_enabled = True
        if "buzzer_enabled" in settings["display"]:
            if settings["display"]["buzzer_enabled"].lower() in ("no", "false", "0"):
                self.buzzer_enabled = False

        # Create a proxy for the RFID card reader
        logging.debug("Creating RFID reader")
        self.RFIDReader = MFRC522()

        # set up some state
        self.sleepMode = False
        # keep track of values in RFID module registers
        self.outlist = [0] * 64


    def set_equipment_power_on(self, state):
        '''
        Turn on/off power to the attached equipment by swithing on/off relay
            and interlock
        @param (boolean) state - True to turn on power to equipment, False to
            turn off power to equipment
        '''
        if state:
            logging.info("Turning on equipment power and interlock")
            os.system("echo True > /tmp/running")
        else:
            logging.info("Turning off equipment power and interlock")
            os.system("echo False > /tmp/running")
        ## Turn off power to SSR
        GPIO.output(GPIO_SOLID_STATE_RELAY_PIN, state)
        ## Open interlock
        if self.is_pi_zero_w:
            GPIO.output(GPIO_INTERLOCK_PIN, state)
        else:
            GPIO.output(GPIO_INTERLOCK_PIN, (not state))


    def set_buzzer(self, state):
        '''
        :param state: True -> Buzzer On; False -> Buzzer Off
        :return: None
        '''
        if(self.buzzer_enabled):
            GPIO.output(GPIO_BUZZER_PIN, state)
        else:
            return


    def get_button_state(self):
        '''
        Determine the current button state
        '''
        if GPIO.input(GPIO_BUTTON_PIN):
            return True
        else:
            return False


    def has_button_been_pressed(self):
        '''
        Use GPIO event detection to determine if the button has been pressed
        since the last call to this method
        '''
        return GPIO.event_detected(GPIO_BUTTON_PIN)


    def read_RFID_card(self):
        '''
        @return a positive integer representing the uid from the card on a
            successful read, -1 otherwise
        '''
        rfid_hang = False

        # Version should be 0x92 for Version 2 MFRC522
        #                   0x91 for Version 1
        version = self.RFIDReader.Read_MFRC522(MFRC522.VersionReg)
        version = version & 0xFC
        if version != 0x90:
            logging.info("MFRC522 communication FAIL")
            rfid_hang = True

        # These three registers appear to change to specific values if the
        # RFID module hangs
        reglist = [17, 20, 21]
        for reg in reglist:
            regval = self.RFIDReader.Read_MFRC522(reg)
            # If register 20 changes from 0x83 to 0x80 then the transmit
            # antennas are turned off
            if (reg == 20) and (self.outlist[reg] == 0x83) and (regval == 0x80):
                rfid_hang = True
            # Log all changes to these three registers
            if regval != self.outlist[reg]:
                logging.info("Reg {0:02x} changed from {1:02x} to {2:02x}".format(reg, self.outlist[reg], regval))
                self.outlist[reg] = regval

       # If the RFID module hangs then we need to restart the portal-box
       # service. This is an infinite loop...the watchdog timer should
       # detect this and restart the service. Meanwhile, we beep and an
       # flash a red and yellow display
        while rfid_hang:
           self.set_buzzer(True)
           self.set_display_color(RED)
           sleep(0.05)
           self.set_buzzer(False)
           self.set_display_color(YELLOW)
           sleep(10)

        # Scan for cards
        (status, TagType) = self.RFIDReader.MFRC522_Request(MFRC522.PICC_REQIDL)

        if MFRC522.MI_OK == status:
            # Get the UID of the card
            #logging.debug("MFRC522 request status, uid")
            (status, uid) = self.RFIDReader.MFRC522_Anticoll()
            #logging.debug("MFRC522 Request returned: %s, %s", status, uid)

            if MFRC522.MI_OK == status:
                # We have the UID, generate unsigned integer
                # uid is a MSB order byte array of theoretically 4 bytes
                result = 0
                for i in range(4):
                    result += (uid[i] << (8 * (3 - i)))
                return result
            logging.info("MFRC522 request status, MI_OK failed")
            return -1
        return -1

    def wake_display(self):
        if self.display_controller:
            self.display_controller.wake_display()
        else:
            logging.info("PortalBox wake_display failed")

    def pulse_display(self, color = BLACK):
        '''
        Pulses the display with the specified color
        @param (bytes len 3) color - the color to set. Defaults to LED's off
        '''

        if self.display_controller:
            self.display_controller.pulse_display(bytes.fromhex(color))
        else:
            logging.info("PortalBox pulse_display_color failed")

    def sleep_display(self):
        '''
        Sets LED display to indicate the box is in a low power mode

        :return: None
        '''
        if self.display_controller:
            self.display_controller.sleep_display()
        else:
            logging.info("PortalBox sleep_display failed")




    def set_display_color(self, color = BLACK):
        '''
        Set the entire strip to specified color.
        @param (bytes len 3) color - the color to set. Defaults to LED's off
        '''
        self.wake_display()
        if self.display_controller:
            self.display_controller.set_display_color(bytes.fromhex(color))
        else:
            logging.info("PortalBox set_display_color failed")


    def set_display_color_wipe(self, color = BLACK, duration = 1000):
        '''
        Set the entire strip to specified color using a "wipe" effect.
        @param (bytes len 3) color - the color to set. Defaults to LED's off
        @param (int) duration -  how long in milliseconds the effect should
                                take.  Defaults to 1 second
        '''
        self.wake_display()
        if self.display_controller:
            self.display_controller.set_display_color_wipe(bytes.fromhex(color), duration)
        else:
            logging.info("PortalBox color_wipe failed")


    def flash_display(self, color, rate = 2):
        """Flash color across all display pixels multiple times. rate is in Hz"""
        self.wake_display()
        if self.display_controller:
            flash_thread = threading.Thread(
                target = self.display_controller.flash_display,
                args = (rate,),
                name = "flashing_thread"
             )
            flash_thread.start()
        else:
            logging.info("PortalBox flash_display failed")

    def stop_flashing(self):
        "Stops the flashing thread"
        if self.display_controller:
            self.display_controller.flash_signal = False
            while("flashing_thread" in [t.getName() for t in threading.enumerate()]):
                pass
        else:
            logging.info("PortalBox stop_flashing failed")



    def cleanup(self):
        logging.info("PortalBox.cleanup() starts")
        os.system("echo False > /tmp/running")
        self.set_buzzer(False)
        self.set_display_color()
        GPIO.cleanup()
