# Configure Peripheral Access

Raspbian, the Linux variant most widely used on Raspberry Pi hardware, uses a safe, minimal configuration by default. This configuration does not enable UART, I2C, and SPI communications via the GPIO header block. As the portalbox hardware attaches devices expecting to communicate using these protocol we need to do a bit of pre-boot configuration.

## Configuration for Portalboxes Built Around a Raspberry Pi 0

In `/boot/cmdline.txt` delete the line:

```ini
console=serial0,115200
```

> moved to /boot/firmware/cmdline.txt remove the part of line
And add a new line:

```ini
fsck.mode=force
```

Then enable the i2c and spi interfaces by editing `/boot/config.txt` and change

> moved to /boot/firmware/config.txt

```ini
#dtparam=i2c_arm=on
```

to:

```ini
dtparam=i2c_arm=on
```

and change:

```ini
#dtparam=spi=on
```

to:

```ini
dtparam=spi=on
```

finally add the lines:

```ini
dtoverlay=spi0-hw-cs
enable_uart=1
```

## Configuration for Portalboxes Built Around a Raspberry Pi 4

In `/boot/config.txt` change

```ini
#dtparam=spi=on
```

to:

```ini
dtparam=spi=on
```

and add the lines:

```ini
enable_uart=1
dtoverlay=spi0-1cs
dtoverlay=spi1-1cs
dtoverlay=gpio-shutdown
dtoverlay=gpio-fan,gpio-pin=12,temp=55000
```
