"""
2021-07-27 Version James Howe
    - Created intial version, based on KJHass's DotstartDriver
2021-07-29
    - Added all the functionality
"""
import logging
import os
import signal

import multiprocessing
import time
import spidev
import RPi.GPIO as GPIO


#Default values
DEFAULT_TONE = 800.0
DEFAULT_DUTY = 50.0
GPIO_BUZZER_PIN = 33

# The driver runs in an infinite loop, checking for new commands or updating
# buzzer. This is the duration of each loop, in milliseconds.
LOOP_MS = 100

NOTES_4TH_OCTAVE = {
    "C":  261.63,
    "Db": 277.18,
    "D":  293.66,
    "Eb": 311.13,
    "E":  329.63,
    "F":  349.23,
    "Gb": 369.99,
    "G":  392,
    "Ab": 415.3,
    "A":  440,
    "Bb": 466.16,
    "B":  493.88
}

class BuzzerController:
    
    def __init__(self, buzzer_pin = GPIO_BUZZER_PIN, settings = {}):
        
        pwm_enabled = True
        if "buzzer_pwm" in settings["display"]:
            if settings["display"]["buzzer_pwm"].lower() in ("no", "false", "0"):
                pwm_enabled = False
        
        self.command_queue = multiprocessing.JoinableQueue()
        self.driver = multiprocessing.Process(
            target=buzzer_driver,
            name="buzzer",
            args=(self.command_queue, buzzer_pin, pwm_enabled),
        )
        self.driver.daemon = True
        self.driver.start()
        
    def _transmit(self,command):
        """Put a command string in the queue."""
        self.command_queue.put(command)
        
    def play_song(self, file_name, sn_len = .1, spacing = .05):
        """
            Plays a song on the buzzer
        """
        command = "sing {} {} {}".format(file_name, sn_len, spacing)
        
        self._transmit(command)
    
    def buzz_tone(self, freq, length = 0.2, stop_song = False, stop_beeping = False):
        """
            Plays the specified tone on the buzzer for the specified length
        """
        command = "buzz {} {} {} {}".format(freq, length, stop_song, stop_beeping)
        self._transmit(command)
        
    def beep(self, freq, duration = 2.0, beeps = 10):
        """
            Beeps the buzzer the specified number of times in the duration
        """
        command = "beep {} {} {}".format(freq, duration, beeps)
        self._transmit(command)
        
    def stop(self, stop_singing = False, stop_buzzing = False, stop_beeping = False):
        """
            Stops the specified effect(s) on the buzzer 
        """        
        command = "stop {} {} {}".format(stop_singing, stop_buzzing, stop_beeping)
        self._transmit(command)
        
    def shutdown_buzzer(self):
        """
            Stops any current effects and shutsdown the driver
        """

        self.stop(True, True, True)

        self.command_queue.close()
        self.driver.terminate()
        if self.driver.is_alive():
            self.driver.kill()
        return

class Buzzer:
    """
    A simple class definition for the Buzzer
    """

    def __init__(self, buzzer_pin = GPIO_BUZZER_PIN, pwm_buzzer = True):
        logging.info("Creating Buzzer Controller")
        self.buzzer_pin = buzzer_pin
        
        #If we don't have the hardware for PWM then don't set it up
        self.pwm_buzzer = pwm_buzzer
        GPIO.setup(self.buzzer_pin, GPIO.OUT)
        if(self.pwm_buzzer):
            self.buzzer = GPIO.PWM(self.buzzer_pin, DEFAULT_TONE)
            self.buzzer.ChangeDutyCycle(DEFAULT_DUTY)
            self.buzzer.stop()
        
        #Whether it is currently playing a sound
        self.state = False
        
        #A flag for each state, and the corresponding info for each effect
        self.is_singing = False
        self.song_list = []
        
        self.is_buzzing = False
        self.buzz_info = {
            "freq": -1,
            "num_of_loops": 0
            }
        
        self.is_beeping = False
        self.beep_info = {
            "freq": -1,
            "duration_ms": 0,
            "wait_ms": 0,
            "effect_time": 0
            }
        
        
        # Create signal handlers
        signal.signal(signal.SIGTERM, self.catch_signal)
        signal.signal(signal.SIGINT, self.catch_signal)
        self.signalled = False
        
        
    def start_buzzer(self, freq = DEFAULT_TONE, duty = DEFAULT_DUTY):
        self.state = True

        if(self.pwm_buzzer):
            self.buzzer.ChangeFrequency(freq)
            self.buzzer.start(duty)
            self.buzzer.ChangeDutyCycle(duty)
        else:
            GPIO.output(self.buzzer_pin, True)

    def stop_buzzer(self):
        self.state = False
        if(self.pwm_buzzer):
            self.buzzer.stop()
        else:
            GPIO.output(self.buzzer_pin, False)
        
    def catch_signal(self, signum, frame):
        logging.info("Buzzer DRVR caught signal")
        self.signalled = True
            
    def create_song_string(self, file_name, sn_len = .1, spacing = .05):
        """
            Takes in a 
        """
        song_file = open(file_name,"r")
        freq_list = []
        #Determines the spacing as a number of loops with a min of 1 loop
        loop_spacing = (spacing*1000)//LOOP_MS
        if loop_spacing < 1:
            loop_spacing = 1
            
        #Take each line/note in the song and split it into the note, the octave, and length
        for line in song_file:
            split_line = line.split(",")
            note_oct = split_line[0]
            
            #determines if a note is flat
            if(note_oct[1] == "b"):
                note = note_oct[0:2]
                octave = int(note_oct[2])
            else:
                note = note_oct[0]
                octave = int(note_oct[1])
                
            #Gets the frequency by shifting up or down from the 4th octave
            freq = NOTES_4TH_OCTAVE[note] * (2**(octave-4))
            
            #Gets the length in seconds by mutiplying the length given by the 16th note length 
            length = float(split_line[1]) * sn_len
            
            #Determines the number of loops which corresponds to the calculated time with a min of 1 loop
            loop_length = (length*1000)//LOOP_MS
            if loop_length < 1:
                loop_length = 1
            
            #Adds the note to the list of frequencies, with the apropriate spacing afterwards
            freq_list.append([freq,loop_length])
            freq_list.append([-1,loop_spacing])
            
            
        return freq_list

def process_command(command, buzz_con):
    """
    Process command strings from the controller.

    The length of these strings is verified in the abstract base class, which
    also verifies the integer parameter ranges.
    """
    logging.debug("Buzzer Driver is processing a command")
    errno = 0

    # split the string into a list of tokens
    tokens = command.split()
    params = [token for token in tokens[1:]]
    # get command part of string and determine if it is recognized
    if tokens[0] == "buzz":
        #Buzz the buzzer once
        if params[2] == "True":
            buzz_con.is_singing = False
            
        buzz_con.is_buzzing = True
        
        if params[3] == "True":
            buzz_con.is_beeping = False
            
        buzz_con.buzz_info = {
            "freq": float(params[0]),
            "num_of_loops": (float(params[1])*1000)//LOOP_MS
            }
        
    elif tokens[0] == "beep":
        #Beep the buzzer at a specified freq
        buzz_con.is_singing = False
        buzz_con.is_buzzing = False
        buzz_con.is_beeping = True
        
        duration = float(params[1])
        beeps = int(params[2])
        
        wait_ms = duration // (2 * beeps)
        wait_ms = (wait_ms + (LOOP_MS // 2)) // LOOP_MS * LOOP_MS
        if wait_ms < LOOP_MS:
            wait_ms = LOOP_MS
        
        duration = wait_ms * 2 * beeps
        
        buzz_con.beep_info = {
            "freq": float(params[0]),
            "duration_ms": duration,
            "wait_ms": wait_ms,
            "effect_time": 0
            }
        
    elif tokens[0] == "sing":
        buzz_con.is_singing = True
        buzz_con.is_buzzing = False
        buzz_con.is_beeping = False
        buzz_con.song_list = buzz_con.create_song_string(params[0],float(params[1]),float(params[2]))
        
    elif tokens[0] == "stop":
        if params[0] == "True":
            buzz_con.is_singing = False
        if params[1] == "True":
            buzz_con.is_buzzing = False
        if params[2] == "True":
            buzz_con.is_beeping = False
  
    else:
        errno = 1

    return errno


def buzzer_driver(command_queue, buzzer_pin, pwm_buzzer):
    """
    This is the main process of the driver.

    It waits until a command is received or the queue "get" times out.
    If the "get" times out then we handle a single step of any current effect.
    This is an infinite loop.
    """
    # Create and the buzzer controller
    buzz_con = Buzzer(buzzer_pin, pwm_buzzer)

    # loop forever (until OS kills us)
    while not buzz_con.signalled:
        # Wait up to LOOP_MS for a command.
        try:
            command = command_queue.get(True, (LOOP_MS / 1000))
            process_command(command, buzz_con)
            command_queue.task_done()
        except:
            if buzz_con.is_singing:
                #If there are still notes left in the song list then play them
                if len(buzz_con.song_list) > 0:
                    
                    
                    freq,length = buzz_con.song_list[0]
                    
                    #Turn off the buzzer if its on and the frequency is <= 0
                    if freq <= 0 and buzz_con.state == True:
                        buzz_con.stop_buzzer()
                    #Turn on the buzzer if its off and the frequency is > 0
                    elif freq > 0 and buzz_con.state == False:
                        buzz_con.start_buzzer(freq)
                    #Remove one from the length of the note 
                    buzz_con.song_list[0][1] -= 1
                    
                    #If the length of the note os 0 then remove the note from the list
                    if buzz_con.song_list[0][1] <= 0:
                        buzz_con.freq_list.pop(0)
                    
                else:
                    buzz_con.stop_buzzer() 
                    buzz_con.is_singing = False

            if buzz_con.is_beeping:
                # Are we done beeping?
                if buzz_con.beep_info["effect_time"] < buzz_con.beep_info["duration_ms"]:
                    # Is the current effect time an even or odd multiple of
                    # the wait_ms time? If even, buzz
                    if (buzz_con.beep_info["effect_time"] // buzz_con.beep_info["wait_ms"]) % 2 == 0:
                        buzz_con.start_buzzer(buzz_con.beep_info["freq"])
                    # If odd, stop buzzing
                    else:
                        buzz_con.stop_buzzer() 

                    buzz_con.beep_info["effect_time"] += LOOP_MS
                else:
                    buzz_con.stop_buzzer() 
                    buzz_con.is_beeping = False
                
            if buzz_con.is_buzzing:
                if(buzz_con.buzz_info["num_of_loops"] > 0):
                    if(buzz_con.state == False):
                        buzz_con.start_buzzer(buzz_con.buzz_info["freq"])
                    buzz_con.buzz_info["num_of_loops"] -= 1
                else:
                    buzz_con.stop_buzzer() 
                    buzz_con.is_buzzing = False
            #If theres no effect going on then stop the buzzer 
            if not( buzz_con.is_buzzing or buzz_con.is_beeping or buzz_con.is_singing):
                buzz_con.stop_buzzer() 


    # Caught TERM or KILL from OS
    logging.info("Buzzer DRVR stopping")
    buzz_con.is_singing = False
    buzz_con.is_beeping = False
    buzz_con.is_buzzing = False

