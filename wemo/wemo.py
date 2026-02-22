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

  # Rename a plug
  python wemo.py --ip 192.168.1.50 --rename "Porch Light"
  python wemo.py --name "WeMo Switch" --rename "Porch Light"

  # Set up a brand-new Wemo on your WiFi (interactive)
  python wemo.py --setup --ssid "MyNetwork" --password "mypassword"

  # Control by friendly name (slower — requires a full network scan)
  python wemo.py --name "Living Room Lamp" --state off
"""

import argparse
import sys

import pywemo

# IP used by Wemo devices in setup/AP mode (fallback: 192.168.1.1)
WEMO_SETUP_IP = "10.22.22.1"


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


def rename_device(device, new_name: str):
    """Change the friendly name stored on the Wemo device."""
    old_name = device.name
    try:
        device.basicevent.SetFriendlyName(FriendlyName=new_name)
        print(f"Renamed '{old_name}' -> '{new_name}'")
        print("Run --discover to confirm the new name is visible on the network.")
    except Exception as exc:
        print(f"Error renaming device: {exc}", file=sys.stderr)
        sys.exit(1)


def setup_new_device(ssid: str, password: str, security: str, setup_ip: str):
    """Walk through WiFi setup for a brand-new Wemo plug (AP mode)."""
    print()
    print("── Wemo WiFi Setup ──────────────────────────────────────────────")
    print("Step 1: Plug in your new Wemo and wait ~30 seconds for it to")
    print("        enter setup mode (LED blinks orange/amber).")
    print()
    print("Step 2: On THIS computer, join the Wemo's WiFi hotspot.")
    print("        It will appear as 'Wemo.Setup.XXXX' or 'Belkin.Setup.XXXX'")
    print("        in your network list.")
    print()
    input("        Press Enter once you're connected to the Wemo AP... ")
    print()

    print(f"Looking for Wemo at {setup_ip}...")
    port = pywemo.discovery.probe_wemo(setup_ip)
    if port is None:
        fallback_ip = "192.168.1.1"
        print(f"  Not found at {setup_ip}, trying {fallback_ip}...")
        port = pywemo.discovery.probe_wemo(fallback_ip)
        if port is None:
            print(
                "\nError: No Wemo device found in setup mode.\n"
                "  - Confirm you are connected to the Wemo's AP network\n"
                "  - Try unplugging and re-plugging the device, wait 30s, and retry",
                file=sys.stderr,
            )
            sys.exit(1)
        setup_ip = fallback_ip

    url = f"http://{setup_ip}:{port}/setup.xml"
    try:
        device = pywemo.discovery.device_from_description(url)
    except Exception as exc:
        print(f"Error reading device description: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Found: {device.name} (firmware: {device.firmware_version})")
    print(f"\nStep 3: Pushing WiFi credentials for '{ssid}'...")

    try:
        # Optional: check if the target SSID is visible to the device
        try:
            ap_result = device.WiFiSetup.GetApList()
            available = ap_result.get("ApList", "")
            if ssid in available:
                print(f"  '{ssid}' found in device scan.")
            else:
                print(f"  Warning: '{ssid}' not seen in device scan — proceeding anyway.")
        except Exception:
            pass  # GetApList is optional; not all models/firmware support it

        device.WiFiSetup.ConnectHomeNetwork(
            ssid=ssid,
            password=password,
            authmode=security,
            encryptmethod="AES",
            keytype="1",
        )

        try:
            device.WiFiSetup.CloseSetup()
        except Exception:
            pass  # Some models finalize automatically without this call

    except AttributeError:
        print(
            "\nError: This device does not expose a WiFiSetup service through pywemo.\n"
            "  Your firmware may require the official Wemo app for initial setup.",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"\nError during WiFi setup: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\nCredentials sent! The Wemo will restart and join '{ssid}'.")
    print()
    print("Step 4: Reconnect this computer to your main WiFi network.")
    print("        Wait ~30 seconds, then run:")
    print("          python wemo.py --discover")
    print("        to find the device's new IP for use in cron jobs.")


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
        help="IP address of the plug (fastest; no discovery needed)",
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
    target.add_argument(
        "--setup",
        action="store_true",
        help="Set up a brand-new Wemo on your WiFi (interactive)",
    )

    # Actions on an existing device
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
    parser.add_argument(
        "--rename",
        metavar="NEW_NAME",
        help="Set a new friendly name on the device",
    )

    # Setup-specific options
    parser.add_argument(
        "--ssid",
        metavar="SSID",
        help="WiFi network name (required with --setup)",
    )
    parser.add_argument(
        "--password",
        metavar="PASS",
        help="WiFi password (required with --setup)",
    )
    parser.add_argument(
        "--security",
        metavar="TYPE",
        default="WPA2PSK",
        choices=["WPA2PSK", "WPA1PSK", "WPA1AND2PSK", "WEP", "OPEN"],
        help="WiFi security type for --setup (default: WPA2PSK)",
    )
    parser.add_argument(
        "--setup-ip",
        metavar="ADDRESS",
        default=WEMO_SETUP_IP,
        help=f"IP of the Wemo in AP mode (default: {WEMO_SETUP_IP})",
    )

    args = parser.parse_args()

    # No arguments — show help
    if not any([args.ip, args.name, args.discover, args.setup]):
        parser.print_help()
        sys.exit(0)

    if args.setup:
        if not args.ssid or not args.password:
            parser.error("--setup requires --ssid SSID and --password PASS")
        setup_new_device(args.ssid, args.password, args.security, args.setup_ip)
        return

    if args.discover:
        discover_all()
        return

    # Targeting a specific device
    if not any([args.state, args.status, args.rename]):
        parser.error("specify at least one of --state on|off, --status, or --rename NEW_NAME")

    device = get_device_by_ip(args.ip) if args.ip else get_device_by_name(args.name)

    if args.status:
        state = "ON" if device.get_state() else "OFF"
        print(f"{device.name} ({device.host}) is currently {state}")

    if args.state:
        set_state(device, args.state)

    if args.rename:
        rename_device(device, args.rename)


if __name__ == "__main__":
    main()
