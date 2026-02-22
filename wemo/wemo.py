#!/usr/bin/env python3
"""Control Wemo smart plugs via pywemo.

Usage examples:
  # List all plugs on the network (grab IPs from here for cron)
  python wemo.py --discover

  # Turn a plug on/off by IP (fast, no discovery scan — use this in cron)
  python wemo.py --ip 192.168.1.50 --state on
  python wemo.py --ip 192.168.1.50 --state off

  # Check current state
  python wemo.py --ip 192.168.1.50 --status

  # Control by friendly name (slower — requires a full network scan)
  python wemo.py --name "Living Room Lamp" --state off
"""

import argparse
import sys

import pywemo


def get_device_by_ip(ip: str):
    """Connect to a Wemo device at a known IP address."""
    try:
        port = pywemo.discovery.probe_wemo(ip)
        if port is None:
            print(f"Error: no Wemo device responded at {ip}", file=sys.stderr)
            sys.exit(1)
        url = f"http://{ip}:{port}/setup.xml"
        device = pywemo.discovery.device_from_description(url)
        return device
    except Exception as exc:
        print(f"Error connecting to {ip}: {exc}", file=sys.stderr)
        sys.exit(1)


def discover_all():
    """Discover every Wemo device on the local network and print a summary."""
    print("Scanning for Wemo devices (this may take a few seconds)...")
    devices = pywemo.discover_devices()
    if not devices:
        print("No Wemo devices found.")
        return []
    print(f"\nFound {len(devices)} device(s):\n")
    print(f"  {'Name':<30} {'IP':<18} State")
    print(f"  {'-'*30} {'-'*18} -----")
    for d in devices:
        state = "ON" if d.get_state() else "OFF"
        print(f"  {d.name:<30} {d.host:<18} {state}")
    print()
    return devices


def get_device_by_name(name: str):
    """Find a device by its friendly name via a full network discovery scan."""
    print(f"Searching for device named '{name}' (scanning network)...")
    devices = pywemo.discover_devices()
    matches = [d for d in devices if d.name.lower() == name.lower()]
    if not matches:
        print(f"Error: no device named '{name}' found on the network.", file=sys.stderr)
        sys.exit(1)
    return matches[0]


def set_state(device, state: str):
    if state == "on":
        device.on()
        print(f"{device.name} ({device.host}) -> ON")
    else:
        device.off()
        print(f"{device.name} ({device.host}) -> OFF")


def main():
    parser = argparse.ArgumentParser(
        description="Control Wemo smart plugs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--ip",
        metavar="ADDRESS",
        help="IP address of the Wemo plug (fastest; no discovery needed)",
    )
    target.add_argument(
        "--name",
        metavar="NAME",
        help="Friendly name of the plug (triggers a full network scan)",
    )
    target.add_argument(
        "--discover",
        action="store_true",
        help="Scan the network and list all Wemo devices",
    )

    parser.add_argument(
        "--state",
        choices=["on", "off"],
        help="Desired power state",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the current power state of the device",
    )

    args = parser.parse_args()

    # No arguments at all — show help
    if not any([args.ip, args.name, args.discover]):
        parser.print_help()
        sys.exit(0)

    if args.discover:
        discover_all()
        return

    # Targeting a specific device: need at least one action
    if not args.state and not args.status:
        parser.error("specify --state on|off and/or --status when targeting a device")

    device = get_device_by_ip(args.ip) if args.ip else get_device_by_name(args.name)

    if args.status:
        state = "ON" if device.get_state() else "OFF"
        print(f"{device.name} ({device.host}) is currently {state}")

    if args.state:
        set_state(device, args.state)


if __name__ == "__main__":
    main()
