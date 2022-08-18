
# Maker Portal Box Application

## About
Portal Box is the access control system used in Makerspaces at Bucknell University. The current hardware consists of a Raspberry Pi 4 or Pi 0  connected to a custom PCB with a MiFare MFRC522 RFID reader, power interlock relays, a buzzer, and 15 DotStar(or Neopixel if using the Pi 0 setup) LEDS. This project is the software which runs on the Portal Box hardware. It is designed to be run by `systemd` as a "service" though for testing it can be run manually

### Note on Conventions
In some shell commands you may need to provide values left up to you. These values are denoted using the semi-standard shell variable syntax e.g. ${NAME_OF_DATA} 

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details

## Dependencies
A MySQL or compatible (MariaDB) database loaded with the appropriate schema and website with appropiate API calls setup
Systemd based Linux, tested with Raspbian Stretch and Buster
Python 3.7+ 
Software Libraries
- Available as python modules
	- configparser 
	- mysql-connector
	- RPi.GPIO
	- spi 
	- spidev
	- pyserial

## Configuration
Configuration of Portal-Boxes occurs in two phases. First the Raspberry Pi at its heart must be put in a usable state. Then after the service is installed you can configure the service.

### Configure Raspberry Pi
- Configure networking for the Raspberry Pi. Networking is required in order to connect to and use the database. Depending on the exact Raspberry Pi model used and your network setup, the steps to do this will vary. If you are using a model with wired networking (more reliable but you have to run network cable) then configuration is typically automatic, just plug in the network cable. If you use WiFi with a preshared key (most common) to connect see: https://www.raspberrypi.org/documentation/configuration/wireless/wireless-cli.md and if you use WiFi with 802.11X authentication see: http://arduino.scholar.bucknell.edu/2019/04/05/customizing-raspbian-images/#setup_wireless_networking for some hints.
- FOR PI0
	- In /boot/cmdline.txt

		Delete `console=serial0,115200`

		And add `fsck.mode=force`
	- Enable i2c and spi interfaces by editing /boot/config.txt and changing:

		`#dtparam=i2c_arm=on`

		to:

		`dtparam=i2c_arm=on`

		and changing:

		`#dtparam=spi=on`

		to:

		`dtparam=spi=on`

		and adding the lines:

		`dtoverlay=spi0-hw-cs`

		`enable_uart=1`
- FOR PI4
	- In /boot/config.txt

		Change 

		`#dtparam=spi=on`

		to:

		`dtparam=spi=on`

		and add the lines 

		`enable_uart=1`

		`dtoverlay=spi0-1cs`

		`dtoverlay=spi1-1cs`
		
		`dtoverlay=gpio-shutdown`
		
		`dtoverlay=gpio-fan,gpio-pin=12,temp=55000`


### Configure Service
An example configuration file, `example-config.ini` has been provided in the repository. The simplest way to configure the service is to copy it to `config.ini` and edit the `config.ini` file, replacing the "YOUR_*" placeholders with the relevant values.

## Installation
You will need a MySQL (or compatible) database running somewhere that the Portal-Boxes can connect to. This could be a server on your network or a database in a shared hosting account though the portal boxes must be able to connect directly to the database which few shared hosting providers offer today. Instructions for loading our database schema are available in the companion "Database" repository. The companion "Management Portal" repository, likewise can be used to setup a website for managing the system e.g. adding users, cards, and equipment types (policies) to the database, assigning equipment types to portal boxes, and managing which users are authorized for equipment.

To install the service on a Portal Box:
1) Clone this project to the Raspberry Pi. The typical location for such services is /opt though for development purposes you may want to choose something in your home directory

```
cd /opt
sudo git clone https://github.com/Bucknell-ECE/PortalBox-application portalbox
```

2) Install the dependencies
	```sh
	cd /opt/portalbox
	sudo pip3 install -r requirements.txt
	```

3) Configure the service (see Configuration)

4) Register with systemd
We use systemd to start and stop our service upon startup and before shutdown therefore we need to register our service file with systemd. If you installed the software to the usual place: /opt/portalbox you can register the service by copying the provided service unit file to /etc/systemd/system.

```
cd /opt/portalbox
sudo cp portalbox.service /etc/systemd/system/portalbox.service
sudo chmod 644 /etc/systemd/system/portalbox.service
sudo systemctl daemon-reload
sudo systemctl enable portalbox.service
```

## Known Bugs
- Starting the service with an invalid config file or an invalid path to a config file fails in odd ways. This should be cleaned up.
- Email messages are hard coded in well code, templates should be used
	- should be able to configure the location of email template files
- GMail uses weak certificates which recent raspbian releases reject as invalid. We need to configure smtplib to ignore the weak certificates and use only the certificates raspbian find trustworthy (requires Python 3.x).
- We use a custom spi, we should consider moving to spidev or releasing our versionverion of spi on PyPi.


