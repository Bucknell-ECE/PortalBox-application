Portal Box LED Color Effects

Every LED color effect consists of a **background color**, which is assigned to most or all of the pixels, and an **effect**. The effect uses one or more of the pixels to give the visual illusion of motion.

The **bouncing** effect is a single pixel that moves from left to right and then from right to left, from one end of the pixel strip to another.  This effect is used in situations where the box is accessing some external resource and might hang indefinitely.

The **scrolling** effect is like a theater marquee. Multiple regularly-spaced pixels move either from left to right or from right to left. One can choose a pair of pixels to be the "center" of the strip, and the scrolling effect can be either toward or away from the center pixels. This is meant to suggest actions such as "insert a card", "remove the card", or "press the button".

The **wipe** effect starts at one end of the LED strip and changes one pixel at a time to the desired color. The wipe effect is used when entering the *Running* mode, where the equipment is turned on, or when changing from an authorized user card to the proxy or training mode.  This effect is only visible for a short time when the background color is changing.

::: center
  Background            Effect                         Meaning
  --------------------- ------------------------------ -------------------------------------------------------
  setup_color           None                           Box is setting itself up
  setup_color           Bouncing setup_color_db        Connecting to database
  setup_color           Bouncing setup_color_email     Connecting to email server
  setup_color           Bouncing access_db_color       Getting equipment info from database
  sleep_color           Pulsing                        Box is idle
  sleep_color           Scrolling unauth_color away    Unauthorized card present
                        from card slot
  sleep_color           Bouncing access_db_color       Logging end of session to database
  auth_color            None/Wipe background color     Equipment is running for authorized user
  auth_color            Bouncing access_db_color       Logging beginning of session to database
  unauth_color          Bouncing access_db_color       Logging unauthorized access attempt
                                                       to database
  no_card_grace_color   Scrolling unauth_color toward  No card present in grace period;
                        card slot                      insert card
  no_card_grace_color   Scrolling unauth_color away    Unauthorized card present in grace
                        from card slot                 period; remove card
  no_card_grace_color   Scrolling proxy_color away     Proxy card present in grace period;
                        from card slot                 equipment does not allow proxy cards;
                                                       remove card
  proxy_color           None/Wipe background color     Running in proxy mode
  proxy_color           Bouncing access_db_color       Logging change to proxy card in database
  training_color        None/Wipe background color     Running in training mode
  training_color        Bouncing access_db_color       Logging change to user card in database
  timeout_color         Scrolling grace_timeout_color  Timeout grace period; press button
                        toward pushbutton
  timeout_color         Bouncing email_connect_color   Timeout grace expired; sending email
                                                       to user
  timeout_color         Bouncing access_db_color       Timeout grace expired; logging event
                                                       to database
  shutdown_color        Bouncing access_db_color       Database access to log box shutdown
  shutdown_color        None                           Application is shut down
:::
