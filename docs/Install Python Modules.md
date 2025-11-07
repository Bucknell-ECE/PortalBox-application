# Install Python Modules

The typical method for install python modules which your software depends on; creating a virtual environment, activating the virtual environment, and using `pip` to install the dependencies; does not work well for software controlled by `systemd`. While possible it makes supporting portalboxes more difficult in our experience. Fortunately, most of our dependencies are pre-installed as part of the base Raspbian install so we take it as a cue along with [PEP 668](https://peps.python.org/pep-0668/) that we should simply use the OS package manager to manage our dependencies. On Raspbian (Trixie) we need only install one additional Python module; `pyserial` which can be installed with:

```sh
sudo apt install python3-serial
```
