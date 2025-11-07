# Configure Raspbian

Raspbian is the Linux distribution which the Portalbox application is designed to run on. These instructions are written for Raspbian based on Debion 13 (Trixie).

## Networking

Basic networking just use Raspberry Pi Imager

Enterprise WiFi

`nmtui`
	Edit a connection
	Add
	Select Wi-Fi
	Create
	Enter SSID
	Choose Security
		Select WPA & WPA2 Enterprise
	Choose Authentication (PEAP)
	Enter inner authentication
		username
		password

## Install Software

`sudo apt update`
`sudo apt upgrade`
`sudo apt install git python3-serial`
