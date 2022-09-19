# woeden-scripts

Here you will find miscellaneous scripts for Woeden users to interface with our system from the command line. As this continues to grow, we will eventually transition to a CLI.

## Robot setup

If you are a registered user of Woeden, you can run the setup script on your personal computer or on a robot to register it within Woeden. This will provide your system with an identifier and password to interface with our backend.

```
$ bash setup.bash
```

## Batch bag upload

If you need to upload bags manually due to network limitations, you can follow the steps below. We are working on turning this into a PyPi package for easier use.

1. Install [stream-zip](https://github.com/uktrade/stream-zip). This is used to stream the contents of your bag into a zip file to preserve storage space on your device.
```
$ pip install stream-zip
```

2. Run our upload script by providing the path to the base `woeden` directory on the drive.
```
$ python3 upload.py /path/to/woeden
```
