"""
2021-07-27 Version James Howe
    - Made it so that a color command will stop the blinking

2021-05-26 Version   KJHass
  - Change end frame for Dotstar compatibility issue
    https://cpldcpu.wordpress.com/2016/12/13/sk9822-a-clone-of-the-apa102/
"""
import logging
import os
import signal

import multiprocessing
import time
import spidev

# Brightness parameters
# For Dotstars, brightness is a 5-bit value from 0 to 31
DEFAULT_BRIGHTNESS = 16
MAX_PULSE_BRIGHTNESS = 30
MIN_PULSE_BRIGHTNESS = 1
PULSE_BRIGHTNESS_STEP = 2
# Color definitions
BLACK = (0, 0, 0)
DARKRED = (16, 0, 0)

# Actual order of colors in LED message. Sigh. It varies for different
# versions of the dotstar chip.
#COLOR_ORDER = "RBG" # Original dotstars
COLOR_ORDER = "BRG"  # Dotstars in V3 boxes

# The driver runs in an infinite loop, checking for new commands or updating
# the pixels. This is the duration of each loop, in milliseconds.
LOOP_MS = 50

class DotstarStrip:
    """
    A simple class definition for a strip of Dotstars.

    TODO A pixel's color is stored as a red/green/blue tuple but the order that
    colors are transmitted to a Dotstar is B-blue-green.
    """

    def __init__(self, length, spi_bus, spi_device):
        logging.info("DRVR Creating DotstarStrip")
        # number of pixels in the strip
        self.length = length
        # each pixel has its own brightness and color tuple
        self.brightness = [DEFAULT_BRIGHTNESS] * length
        self.led_colors = [BLACK] * length

        # Generic effect parameters
        self.effect = "none"  # name of the effect
        self.duration = 0     # total duration of the effect
        self.wait_ms = 0      # how often to change effect
        self.effect_time = 0  # current effect elapsed time

        # Pulse effect parameters
        self.brightness_step = 0    # How much to change brightness every loop
        self.effect_rising = False  # Whether brightness going up or down

        # Scroll/bounce/wipe effect parameters
        self.dir_down = 0     # moving down (pixel (length-1) down to 0) or
                              # up (pixel 0 up to pixel (length-1))

        # Bounce
        self.pixel_index = 0  # Which pixel to change

        # Scroll
        self.center = 0       # number of pixel just higher than strip center
        self.back_pixels = 0  # background for scroll


        # Create signal handlers
        signal.signal(signal.SIGTERM, self.catch_signal)
        signal.signal(signal.SIGINT, self.catch_signal)
        self.signalled = False

        # Connect this driver to a specific SPI interface, which should
        # have been enabled in /boot/config.txt
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = 100000
        self.spi.mode = 0
        self.spi.bits_per_word = 8
        self.spi.no_cs = True

    def set_brightness(self, brightness):
        """Set the common brightness value for all pixels"""
        self.brightness = [brightness] * self.length

    def set_pixel_brightness(self, brightness, number):
        """Set the brightness value of one pixel"""
        self.brightness[number] = brightness

    def get_pixel_brightness(self, number):
        """Set the brightness value of one pixel"""
        return self.brightness[number]

    def fill_pixels(self, color):
        """Change the color of all pixels."""
        self.led_colors = [(color)] * self.length

    def set_pixel_color(self, color, number):
        """Change the color of a single pixel."""
        self.led_colors[number] = color

    def get_pixel_color(self, number):
        """Return the color of a single pixel."""
        return self.led_colors[number]

    def swap_pixels(self, number1, number2):
        """Swaps the color and brightness of two pixels."""
        temp = self.led_colors[number2]
        self.led_colors[number2] = self.led_colors[number1]
        self.led_colors[number1] = temp
        temp = self.brightness[number2]
        self.brightness[number2] = self.brightness[number1]
        self.brightness[number1] = temp

    def calc_step_time(self, numerator, denominator, multiplier):
        """ Calculate the time for each step of the effect, round to nearest LOOP_MS,
            minimum is LOOP_MS. This is integer math! """
        self.wait_ms = numerator // denominator
        self.wait_ms = (self.wait_ms + (LOOP_MS // 2)) // LOOP_MS * LOOP_MS
        if self.wait_ms < LOOP_MS:
            self.wait_ms = LOOP_MS
        self.duration = self.wait_ms * multiplier


    def show(self):
        """Transmit the desired brightness and colors to the Dotstars.

        The dotstars require a "begin frame" consisting of four all-zero
        bytes before actual data is sent, and an "end frame" of four all-one
        bytes after the data is sent
        """
        self.spi.writebytes([0x00] * 4)  # begin frame

        if COLOR_ORDER == "RBG": # swap green and blue
            for pixel in range(self.length):
                self.spi.writebytes(
                    [
                        0xE0 + self.brightness[pixel],
                        self.led_colors[pixel][0],
                        self.led_colors[pixel][2],
                        self.led_colors[pixel][1],
                    ]
                )
        elif COLOR_ORDER == "BRG": # swap green and blue
            for pixel in range(self.length):
                self.spi.writebytes(
                    [
                        0xE0 + self.brightness[pixel],
                        self.led_colors[pixel][2],
                        self.led_colors[pixel][1],
                        self.led_colors[pixel][0],
                    ]
                )
        else:  # default is RGB
            for pixel in range(self.length):
                self.spi.writebytes(
                    [
                        0xE0 + self.brightness[pixel],
                        self.led_colors[pixel][0],
                        self.led_colors[pixel][1],
                        self.led_colors[pixel][2],
                    ]
                )
        self.spi.writebytes([0x00] * 4)  # SK9822 frame
        self.spi.writebytes([0x00] * (self.length // 16 + 1))  # end frame

    def catch_signal(self, signum, frame):
        """Handle OS signals."""
        logging.info("DRVR caught signal")
        self.signalled = True


def process_command(command, strip):
    """
    Process command strings from the controller.

    The length of these strings is verified in the abstract base class, which
    also verifies the integer parameter ranges.
    """
    errno = 0

    # split the string into a list of tokens TOKENS MUST BE INTEGERS
    tokens = command.split()
    params = [int(token) for token in tokens[1:]]
    # get command part of string and determine if it is recognized
    if tokens[0] == "blink":
        # the blink command requires a color triplet, a duration (ms),
        # and a repeat count as inputs
        red, green, blue, strip.duration, strip.repeats = params
        strip.fill_pixels((red, green, blue))
        strip.effect = "blink"

        # Initialize effect parameters
        strip.effect_time = 0
        strip.set_brightness(MIN_PULSE_BRIGHTNESS)

        strip.calc_step_time(strip.duration, 2 * strip.repeats, 2 * strip.repeats)

    elif tokens[0] == "wipe":
        # The wipe command changes the pixel colors one pixel at a time.
        # The command requires four integer values: red, green, blue, and
        # duration. Duration is milliseconds.
        red, green, blue, strip.duration, strip.dir_down = params

        strip.effect = "wipe"
        strip.set_brightness(DEFAULT_BRIGHTNESS)
        strip.effect_time = 0

        strip.calc_step_time(strip.duration, strip.length, strip.length)

        # Change the first pixel color to the wipe color
        if strip.dir_down == 0:
            strip.set_pixel_color((red, green, blue), 0)
        else:
            strip.set_pixel_color((red, green, blue), strip.length - 1)


    elif tokens[0] == "color":
        # The color command sets all of the pixels to the same color.
        red, green, blue = params
        strip.effect = "color"

        # Go to default brightness if no other effect in progress
        strip.set_brightness(DEFAULT_BRIGHTNESS)
        strip.fill_pixels((red, green, blue))

    elif tokens[0] == "pulse" and strip.effect != "pulse":
        # The pulse command changes the brightness of all pixels so they are
        # pulsing. The pulse rate is hard coded using constant parameters.
        # The command requires three integer values: red, green, and blue.
        red, green, blue = params
        strip.fill_pixels((red, green, blue))
        strip.set_brightness(DEFAULT_BRIGHTNESS)
        strip.effect = "pulse"

    elif tokens[0] == "scroll" and strip.effect != "scroll":
        # The scroll command. Scrolls a pattern of single pixels in specified color
        # separated by 'back_pixels' of the previous color. If center != 0 then the
        # scrolling is toward the center pixel. If center == 0 then dir_down determines
        # scrolling from pixel 0 to N (dir_down == 0) or from N down to 0 (dir_down == 1).
        (red, green, blue, duration, strip.back_pixels, strip.dir_down, strip.center) = params

        strip.effect = "scroll"
        strip.effect_time = 0

        strip.calc_step_time(duration, strip.back_pixels, strip.length)

        # Set the initial pixel colors for the scrolling pixels.
        for i in range(strip.center, strip.length):
            if ((i - strip.center) % (strip.back_pixels + 1)) == 0:
                strip.set_pixel_color((red, green, blue), i)
                strip.set_pixel_brightness(DEFAULT_BRIGHTNESS, i)
        for i in range(strip.center - 1, -1, -1):
            if ((i - (strip.center - 1)) % (strip.back_pixels + 1)) == 0:
                strip.set_pixel_color((red, green, blue), i)
                strip.set_pixel_brightness(DEFAULT_BRIGHTNESS, i)

    elif tokens[0] == "bounce" and strip.effect != "bounce":
        # The bounce effect. A single pixel of specified color moves from right to left
        # then from left to right, repeated until a different command is issued
        (red, green, blue, duration) = params

        strip.effect = "bounce"
        strip.effect_time = 0
        strip.dir_down = 0
        strip.pixel_index = 0

        strip.calc_step_time(duration, strip.length, strip.length)

        # Set the initial pixel color and brightness
        strip.set_pixel_color((red, green, blue), 0)
        strip.set_pixel_brightness(DEFAULT_BRIGHTNESS, 0)

    else:
        errno = 1

    return errno


def strip_driver(command_queue, led_count, spi_bus, spi_dev):
    """
    This is the main process of the driver.

    It waits until a command is received or the queue "get" times out.
    If the "get" times out then we handle a single step of any current effect.
    This is an infinite loop.
    """
    # Create and initialize an LED strip
    strip = DotstarStrip(led_count, spi_bus, spi_dev)
    strip.show()

    # loop forever (until OS kills us)
    while not strip.signalled:
        # Wait up to LOOP_MS for a command.
        try:
            command = command_queue.get(True, (LOOP_MS / 1000))
            process_command(command, strip)
            command_queue.task_done()
        except:
            if strip.effect == "blink":
                # Are we done blinking?
                if strip.effect_time < strip.duration:
                    # Is the current effect time an even or odd multiple of
                    # the wait_ms time? If even, go to low brightness level.
                    if (strip.effect_time // strip.wait_ms) % 2 == 0:
                        strip.set_brightness(MIN_PULSE_BRIGHTNESS)
                    # If odd, go to high brightness level.
                    else:
                        strip.set_brightness(MAX_PULSE_BRIGHTNESS)

                    strip.effect_time = strip.effect_time + LOOP_MS
                # Done blinking.
                else:
                    strip.effect = "none"

            if strip.effect == "wipe":
                # Are we done wiping?
                if strip.effect_time < strip.duration:
                    # After each wait_ms we change the color of the next LED
                    index = strip.effect_time // strip.wait_ms
                    if strip.dir_down == 1:
                        index = strip.length - index - 1
                        strip.set_pixel_color(strip.get_pixel_color(strip.length - 1), index)
                    else:
                        strip.set_pixel_color(strip.get_pixel_color(0), index)
                    strip.effect_time = strip.effect_time + LOOP_MS

            if strip.effect == "pulse":
                # All pixels will have the same brightness. Get that value
                # from pixel 0
                brightness = strip.brightness[0]
                # If getting brighter, add to the brightness
                if strip.effect_rising:
                    brightness += PULSE_BRIGHTNESS_STEP
                    if brightness >= MAX_PULSE_BRIGHTNESS:
                        strip.effect_rising = False
                        brightness = MAX_PULSE_BRIGHTNESS
                # If getting darker, subtract from the brightness
                else:
                    brightness -= PULSE_BRIGHTNESS_STEP
                    if brightness <= MIN_PULSE_BRIGHTNESS:
                        strip.effect_rising = True
                        brightness = MIN_PULSE_BRIGHTNESS
                # Set all pixels to the new brightness level.
                strip.set_brightness(brightness)

            if strip.effect == "scroll":

                if strip.effect_time < strip.wait_ms:
                    strip.effect_time = strip.effect_time + LOOP_MS
                else:
                    # Move pixels up
                    if strip.dir_down == 0 or strip.center != 0:
                        if strip.center != 0 and strip.dir_down == 0:
                            rightmost = strip.center - 1
                            leftmost  = 0
                        elif strip.center != 0 and strip.dir_down == 1:
                            rightmost  = strip.length - 1
                            leftmost = strip.center
                        else:
                            rightmost = strip.length - 1
                            leftmost  = 0

                        for i in range(rightmost, leftmost, -1):
                            strip.set_pixel_color(strip.get_pixel_color(i - 1), i)
                        strip.set_pixel_color(
                            strip.get_pixel_color(leftmost + strip.back_pixels + 1),
                            leftmost
                        )
                    # Move pixels down
                    if strip.dir_down == 1 or strip.center != 0:
                        if strip.center != 0 and strip.dir_down == 1:
                            rightmost = strip.center - 1
                            leftmost = 0
                        elif strip.center != 0 and strip.dir_down == 0:
                            rightmost = strip.length - 1
                            leftmost = strip.center
                        else:
                            rightmost = strip.length - 1
                            leftmost = 0

                        for i in range(leftmost, rightmost):
                            strip.set_pixel_color(strip.get_pixel_color(i+1), i)
                        strip.set_pixel_color(
                            strip.get_pixel_color(rightmost - strip.back_pixels - 1),
                            rightmost
                        )

                    strip.effect_time = 0

            if strip.effect == "bounce":

                if strip.effect_time < strip.wait_ms:
                    strip.effect_time = strip.effect_time + LOOP_MS
                else:
                    if strip.dir_down == 1:
                        if strip.pixel_index > 0:
                            strip.swap_pixels(strip.pixel_index - 1, strip.pixel_index)
                            strip.pixel_index -= 1
                        else:
                            strip.dir_down = 0
                    elif strip.dir_down == 0:
                        if strip.pixel_index < (strip.length - 1):
                            strip.swap_pixels(strip.pixel_index + 1, strip.pixel_index)
                            strip.pixel_index += 1
                        else:
                            strip.dir_down = 1

                    strip.effect_time = 0

            # Send the new brightness and color values out to the Dotstars
            strip.show()

    # Caught TERM or KILL from OS
    # Set the LEDs to a dim red
    logging.info("DRVR stopping")
    strip.brightness = [MIN_PULSE_BRIGHTNESS] * strip.length
    strip.led_colors = [DARKRED] * strip.length
    strip.effect = "none"
    strip.show()
