# Portal Box Application

This project is the software that runs on the Raspberry Pi at the heart of the portalbox device.

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details

## Dependencies

It is assumed that:

1. the Raspberry Pi is connected to a MiFare MFRC522 RFID reader, power interlock relays, a buzzer, and LEDs (either DotStars or NeoPixels) via the custom PCB.
2. the Raspberry Pi is connected to a network that allows it to communicate with the portalbox website instance for your organization. See [Configure Raspbian](docs/Configure%20Raspbian.md)
3. the Raspberry Pi is running Linux and Linux is configured to allow software to communicate with the attached peripherals. See [Configure Peripheral Access](docs/Configure%20Peripheral%20Access.md)
4. the necessary Python modules listed in [requirements.txt](requirements.txt) are installed on the Raspberry Pi. See [Install Python Modules](docs/Install%20Python%20Modules.md)

## Installation

We recommend installing this application by cloning it from our git repository:

```
cd /opt
sudo git clone https://github.com/Bucknell-ECE/PortalBox-application portalbox
```

## Configuration

The software running on the Raspberry Pi is configured using a `config.ini` file. The simplest way to configure the service is to copy the provided `example-config.ini` to `/opt/portalbox/config.ini` then edit the `config.ini` file, replacing the "YOUR_*" placeholders with the relevant values.

We recommend testing the application at this point using the command line (assuming `/opt/portalbox` is your working directory):

```sh
sudo python service.py config.ini
```

You can use `CTRL` + `C` to stop the application.

Once you are satisfied with your `config.ini` you can register the application with `systemd` so it is started automatically when the Raspberry Pi is powered on.

```sh
cd /opt/portalbox
sudo cp portalbox.service /etc/systemd/system/portalbox.service
sudo chmod 644 /etc/systemd/system/portalbox.service
sudo systemctl daemon-reload
sudo systemctl enable portalbox.service
```

## Setting Up Additional Portalboxes

We recommend pulling the SD Card/microSD Card and creating an image of the card then using the imaging software of your choice to write cards for additional Portalboxes.
