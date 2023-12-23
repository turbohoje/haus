#!/usr/bin/env python3

#example script to listen to a device for motion events

import pyvera
import os
import sys
import time

#vera url
URL = "http://10.22.14.4:3480"

def device_info_callback(vera_device: pyvera.VeraDevice) -> None:
    """Print device info."""
    # Do what we want with the changed device information
    print(
        "{}_{} values: {}".format(
            vera_device.name, vera_device.device_id, vera_device.get_all_values()
        )
    )
    print(
        "{}_{} alerts: {}".format(
            vera_device.name, vera_device.device_id, vera_device.get_alerts()
        )
    )

def main() -> None:
    # sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))

    # parser = argparse.ArgumentParser(description="list-devices")
    # parser.add_argument(
    #     "-u", "--url", help="Vera URL, e.g. http://192.168.1.161:3480", required=True
    # )
    # args = parser.parse_args()

    # Start the controller
    controller = pyvera.VeraController(URL)
    controller.start()

    try:
        # Get a list of all the devices on the vera controller
        all_devices = controller.get_devices()

        # Print the devices out
        # for device in all_devices:
        #     print(device)
        #     print(
        #         "{} {} ({})".format(
        #             type(device).__name__, device.name, device.device_id
        #         )
        #     )
        
        found_device = controller.get_device_by_id(153)
        controller.register(found_device, device_info_callback)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Got interrupted by user")

        # Unregister our callback
        controller.unregister(found_device, device_info_callback)


    finally:
        # Stop the subscription listening thread so we can quit
        controller.stop()


if __name__ == "__main__":
    main()