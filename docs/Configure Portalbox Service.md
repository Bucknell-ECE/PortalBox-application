# Configure Portalbox Service

The software running on the Raspberry Pi is configured using a `config.ini` file. The simplest way to configure the service is to copy the provided `example-config.ini` to `/opt/portalbox/config.ini` then edit the `config.ini` file, replacing the "YOUR_*" placeholders with the relevant values.

## The INI File Format

We use the [ini file format](https://en.wikipedia.org/wiki/INI_file) for the config file because it is simple and does not require extra libraries for the service to read it simplifying setup and maintenance. However if you've never seen an ini file before it may help to know some basics. Text following a `;` or a `#` character until the end of the line is a comment intended to help humans and ignored by the software. If you need to include a `;` or `#` in a value e.g. `auth_password` you will need to put the value in quotes.

```ini
auth_password = "my#strong;password"
```

Settings are groups using headings in square braces

```ini
[grouping]
```

and include anf setting after the heading until another heading is found. Finally, values are provided as key-values pairs writen as the key or setting name followed by a space, an `=`, and another space then the value. So

```ini
grace_period = 2
```

sets the setting `grace_period` to `2` and

```ini
[logging]
level = error
```

sets `logging.level` aka "logging level" to `error`

## Settings

We group all settings under a heading in the ini file, which is to say the service ignores any top level or ungrouped settings.

### db

Settings in the `db` section control how the portalbox connects to the management website. Historically the portalbox talked directly to the database hence the section name. We will likely rename this section in the future.

#### website

`db.website` tells the service where the management website is running. You must include the "protocol" i.e. `http://` or `https://` whichever is correct for your website.

```ini
website = https://makerspace.tld
```

You must set this setting

#### bearer_token

`db.bearer_token` provides the API token which the portalbox will use to identify itself to the management website.

```ini
bearer_token = a3b4cd12fe6901
```

You must set this setting

### email

Settings in the `email` section control how the portalbox connects to your email service to send session timed out and forgotten card email notifications.

#### enabled

`email.enabled` controls whether the portalbox sends email. For historical reasons if this setting is not provided email notifications will be sent. This will likely change in the future.

Set to `True` or `False`

```ini
enabled = True
```

While optional, we recommend you set this setting

#### from_address

`email.from_address` controls the email address which email notification are to be sent from.

```ini
from_address = donotreply@makerspace.tld
```

This setting must be set if `email.enabled` is set to `True`

#### cc_address

`email.cc_address` controls the email address which will be carbon copied on email notifications.

```ini
cc_address = administrator@makerspace.tld
```

This setting is optional

#### bcc_address

`email.bcc_address` controls the email address which will be blind carbon copied on email notifications.

```ini
bcc_address = shoptech@makerspace.tld
```

This setting is optional

#### smtp_server

`email.smtp_server` controls the email server which the portalbox will use to send email notifications.

```ini
smtp_server = mail.makerspace.tld
```

This setting must be set if `email.enabled` is set to `True`

#### smtp_port

`email.smtp_port` controls the network port which the portalbox will use to connect to your smtp server.

```ini
smtp_server = 80
```

This setting must be set if `email.enabled` is set to `True`

#### auth_user

`email.auth_user` controls the smtp auth username which the portalbox will use to send email notifications.

```ini
auth_user = donotreply@makerspace.tld
```

This setting must be set if `email.enabled` is set to `True`

#### auth_password

`email.auth_password` controls the smtp auth password which the portalbox will use to connect to your smtp server.

```ini
auth_password = "A#really#strong#password"
```

This setting must be set if `email.enabled` is set to `True`

#### my_smtp_server_uses_a_weak_certificate

`email.my_smtp_server_uses_a_weak_certificate` disables checking of validity of the SSL certificate used by the smtp server. It defaults to `False` i.e. the portalbox will check the server certificate however we know some organizations do not use certificates with a trust chain reaching a root certificate enabled in Raspbian so this can solve some email issues.

```ini
auth_password = "A#really#strong#password"
```

We don't recommend that you use this.

#### reply_to

`email.reply_to` sets the reply to email address for email notifications sent by the portalbox. Note that some email services will reject emails as spam if this differs from the from address.

```ini
reply_to = administrator@makerspace.tld
```

This setting is optional

### logging

This section configures how the software reports errors to the operating system. This is most useful in software development.

#### level

`logging.level` the minimum severity of a log message to pass on to the operating system. Defaults to `error`. The possible values are: `critical`, `error`, `warning`, `info`, and `debug`.

```ini
level = error
```

Unless you are working on the software or a hardware issue we do not recommend changing this setting.

### user_exp

This group contains the policy settings for the portalbox

#### grace_period

This is the number of seconds the portalbox should wait after a card is removed before terminating the user session

```ini
grace_period = 5
```

You must set this setting

### display

These settings control how the portalbox provides feedback to the user.

#### flash_rate

The number of times per second that the portalbox will flash

```ini
flash_rate = 2
```

You must set this setting

#### enable_buzzer

Whether the buzzer should be used. Set to `True` or `False`

```ini
enable_buzzer = True
```

You must set this setting

#### buzzer_pwm

Whether the buzzer can be used to play tones. Set to `True` or `False`

```ini
buzzer_pwm = False
```

You must set this setting

#### led_type

The portalbox has used different LED components in various revisions. This setting tells the service which type of LEDs are attached. Set to `DOTSTARS` or `NEOPIXELS`

```ini
led_type = NEOPIXELS
```

You must set this setting

#### setup_color

The color to display while getting setup

```ini
setup_color = FF FF FF
```

This setting is optional

#### auth_color

The color to display while an authorized user is running the machine and their card is present

```ini
auth_color = 00 FF 00
```

This setting is optional

#### proxy_color

The color to display while an authorized user is running the machine and their card has been replaced by a proxy card

```ini
proxy_color = DF 20 00
```

This setting is optional

#### training_color

The color to display while a user is being trained on the machine

```ini
training_color = 80 00 80
```

This setting is optional

#### sleep_color

The color to display while idle

```ini
sleep_color = 00 00 FF
```

This setting is optional

#### unauth_color

The color to display when a card which is not authorized to activate the equipment is present

```ini
unauth_color = FF 00 00
```

This setting is optional

#### no_card_grace_color

The color to display while still active but after a card has been removed

```ini
no_card_grace_color = FF FF 00
```

This setting is optional

#### grace_timeout_color

The color to display while the equipment is still active but has timed out

```ini
grace_timeout_color = DF 20 00
```

This setting is optional

#### timeout_color

The color to display after the equipment is no longer active because it timed out

```ini
timeout_color = FF 00 00
```

This setting is optional

#### unauth_card_grace_color

The color to display when an unauthorized card was inserted to continue an active session

```ini
unauth_card_grace_color = FF 80 00
```

This setting is optional
