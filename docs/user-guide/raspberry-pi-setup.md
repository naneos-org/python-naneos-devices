# Raspberry Pi Setup

## Basic Setup of the Raspberry

With the [Raspberry Pi Imager](https://www.raspberrypi.com/software/) install the desired Raspberry Pi Os Version on a SD-Card.
If your system becomes headless, then you need to have SSH connection to the raspberry.
Later on we need to use the terminal on the Raspberry Pi.

Now put the SD-Card into the Raspberry Pi and boot for the first time.
To bring you system up to date I would run the following 3 commands and reboot the raspberry afterweards.

```bash
sudo apt update
sudo apt full-upgrade
sudo apt autoremove
sudo reboot now
```

## Installation of Python and Pip
Install python and pip with the following command:

```bash
sudo apt install python3-full python3-pip
```

## Installation of the Naneos Package in an virtual environment
Create a folder, where you want to execute the naneos Manager and go into this folder.
```bash
mkdir naneos-uploader
cd naneos-uploader
```

Now we create the virtual environment in an hidden folder called .venv:
```bash
python -m venv .venv
```

Now we activate the virtual environment and install the naneos package that we need for our uploader.
```bash
source .venv/bin/activate
pip install naneos-devices
```

After the installation we can exit the virtual environment.
```bash
deactivate
```

# Creation of the uploader script:
Create a script and copy in the following content.
```bash
vim uploader-script.py
```

```python
#!/home/pi/naneos-uploader/.venv/bin/python

import signal
import time

from naneos.manager import NaneosDeviceManager

running = True  # global flag to control the main loop


def handle_signal(signum, frame):
    global running
    running = False


# register signal handlers for SIGTERM and SIGINT
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


def rp_service_main() -> None:
    manager = NaneosDeviceManager(
        use_serial=True, use_ble=True, upload_active=True, gathering_interval_seconds=30
    )
    manager.start()

    try:
        while running:
            remaining = manager.get_seconds_until_next_upload()

            slept = 0
            while running and slept < remaining + 1:
                time.sleep(1)
                slept += 1

            if not running:
                break

    finally:
        manager.stop()
        manager.join()


if __name__ == "__main__":
    rp_service_main()
```

Now we need to make our script executable mit:
```bash
chmod +x uploader-script.py
```

# Creation of the service

First we need to create the service-file:
```bash
sudo vim /etc/systemd/system/naneos_uploader.service
```

Then we can enter the following to link the python file and the service.
```bash
[Unit]
Description=Naneos Uploader Service Example
After=network.target

[Service]
ExecStart=/home/pi/naneos-uploader/uploader-script.py
WorkingDirectory=/home/pi/naneos-uploader
StandardOutput=inherit
StandardError=inherit
Restart=always
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
```

Now we need to reload the daemons and enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable naneos_uploader.service
sudo systemctl start naneos_uploader.service
```

