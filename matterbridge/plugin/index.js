/**
 * matterbridge-haus — bridges the hausphone PWA's Z-Wave switches into Matter.
 *
 * hausphone (../../hausphone) owns every device: this plugin never talks to
 * zwave-js, it drives the same REST routes the PWA uses. That is deliberate —
 * going through POST /api/zwave/{key}/power means a fireplace turned on by
 * Google still gets hausphone's 90-minute auto-off, and the LD Floor still
 * honours its warm-window and occupancy automation.
 *
 * Which devices appear here is decided in hausphone, not here: DEVICES entries
 * in app/devices/zwave.py carry a `matter` block, and GET /api/matter/devices
 * serves that as a manifest. Add a device there and it shows up on restart.
 *
 * State flows the other way over hausphone's existing /ws socket, so a switch
 * flipped at the wall remote or by an automation reaches Google Home without
 * anyone polling. hausphone re-broadcasts full state every 60 s on its own poll
 * loop, which doubles as this plugin's safety net against a missed message.
 *
 * Written in plain ESM rather than TypeScript so the container needs no build
 * step — the plugin directory is installed as-is.
 */
import * as matterbridge from 'matterbridge';
import https from 'node:https';
import http from 'node:http';
import WebSocket from 'ws';

const { MatterbridgeDynamicPlatform, MatterbridgeEndpoint, bridgedNode, powerSource } = matterbridge;

/**
 * Matterbridge renamed its device-type constants between 3.0 and 3.10
 * (onOffOutlet -> onOffPlugInUnit) without changing the underlying Matter code,
 * and the container floats on luligu/matterbridge:latest. Resolve by whichever
 * name the installed build exports instead of pinning to one spelling.
 */
function deviceType(...names) {
  for (const name of names) {
    if (matterbridge[name]) return matterbridge[name];
  }
  throw new Error(`This matterbridge build exports none of: ${names.join(', ')}`);
}

/**
 * The Matter device types hausphone's `matter.type` can name.
 *
 * Note there is no "switch": Matter's On/Off Switch (0x0103) is a *client*
 * device type — it carries OnOff as a client cluster and binds to other nodes,
 * so Google Home commissions one and then offers no way to turn it on. On/Off
 * Plug-in Unit (0x010A) is the simplest server type Google both renders and
 * controls.
 */
const DEVICE_TYPES = {
  outlet: deviceType('onOffPlugInUnit', 'onOffOutlet'),
  light: deviceType('onOffLight'),
};

const MANIFEST_RETRY_MS = 5_000;
// hausphone's device backends take ~20 s to come up. Matterbridge waits for
// onStart, so this is also how long a down hausphone stalls the bridge before
// the plugin gives up and reports the error — recover with a restart.
const MANIFEST_TIMEOUT_MS = 120_000;
const WS_RETRY_MS = 5_000;

export default function initializePlugin(matterbridge, log, config) {
  return new HausPlatform(matterbridge, log, config);
}

export class HausPlatform extends MatterbridgeDynamicPlatform {
  constructor(matterbridge, log, config) {
    super(matterbridge, log, config);
    this.verifyMatterbridgeVersion('3.0.0');

    this.baseUrl = (config.hausphoneUrl ?? 'https://127.0.0.1:3000').replace(/\/+$/, '');
    // hausphone serves a self-signed cert (see its entrypoint.sh) and has no
    // auth — it is a LAN-only service and we normally reach it over loopback.
    // Scoping the exemption to these requests keeps it out of the rest of the
    // matterbridge process, which does verify certs when it talks to npm.
    this.tlsInsecure = config.tlsInsecure !== false;

    this.devices = new Map(); // hausphone device key -> MatterbridgeEndpoint
    this.ws = null;
    this.wsRetry = null;
    this.stopping = false;
  }

  // ── lifecycle ─────────────────────────────────────────────────────────────

  async onStart(reason) {
    this.log.info(`Starting matterbridge-haus${reason ? `: ${reason}` : ''}`);
    await this.ready;
    await this.clearSelect();

    const manifest = await this.fetchManifest();
    this.log.info(`hausphone exports ${manifest.length} device(s) to Matter`);

    for (const device of manifest) {
      await this.addDevice(device);
    }
  }

  async onConfigure() {
    await super.onConfigure();
    // Only now is every endpoint Active — updateAttribute rejects an endpoint
    // that is still constructing, so the socket must not open before this.
    this.connectWebSocket();
  }

  async onShutdown(reason) {
    this.stopping = true;
    if (this.wsRetry) {
      clearTimeout(this.wsRetry);
      this.wsRetry = null;
    }
    if (this.ws) {
      this.ws.removeAllListeners();
      this.ws.close();
      this.ws = null;
    }
    await super.onShutdown(reason);
    if (this.config.unregisterOnShutdown === true) await this.unregisterAllDevices(500);
    this.log.info(`Stopped matterbridge-haus${reason ? `: ${reason}` : ''}`);
  }

  // ── device setup ──────────────────────────────────────────────────────────

  async addDevice(device) {
    const definition = DEVICE_TYPES[device.type];
    if (!definition) {
      this.log.error(`Device ${device.key}: unknown matter type "${device.type}" — skipped`);
      return;
    }
    // The serial is what Google Home keys a bridged device on across restarts:
    // derive it from hausphone's device key so an endpoint keeps its identity
    // (and its room, name and routines) even if the display name is edited.
    const serial = `haus-${device.key}`;
    // Register with the frontend's picker before the filter, so a device you
    // have black-listed is still offered when you want it back.
    this.setSelectDevice(serial, device.name, undefined, 'hub');
    if (!this.validateDevice(device.name)) return;

    const endpoint = new MatterbridgeEndpoint([definition, bridgedNode, powerSource], { id: serial }, this.config.debug)
      .createDefaultBridgedDeviceBasicInformationClusterServer(device.name, serial, 0xfff1, 'Haus', 'Z-Wave switch')
      // Seed the real state before addRequiredClusterServers, which only fills
      // in clusters that are not already present.
      .createDefaultOnOffClusterServer(device.on)
      .addRequiredClusterServers();

    endpoint.addCommandHandler('on', async () => {
      await this.setPower(device.key, true);
    });
    endpoint.addCommandHandler('off', async () => {
      await this.setPower(device.key, false);
    });
    // Handlers run before matterbridge applies the command to the cluster, so
    // `attributes.onOff` is still the pre-toggle value.
    endpoint.addCommandHandler('toggle', async ({ attributes }) => {
      await this.setPower(device.key, !attributes.onOff);
    });

    await this.registerDevice(endpoint);
    this.devices.set(device.key, endpoint);
    this.log.info(`Bridged ${device.key} as "${device.name}" (${device.type})`);
  }

  async setPower(key, on) {
    try {
      await this.request('POST', `/api/zwave/${key}/power`, { on });
      this.log.debug(`Set ${key} ${on ? 'on' : 'off'}`);
    } catch (err) {
      // Matter has no "the command failed" response once we are past the
      // handler, so the endpoint may briefly show a state hausphone never
      // reached. The next /ws broadcast corrects it.
      this.log.error(`Failed to set ${key} ${on ? 'on' : 'off'}: ${err.message}`);
    }
  }

  // ── state in ──────────────────────────────────────────────────────────────

  connectWebSocket() {
    if (this.stopping) return;
    const url = `${this.baseUrl.replace(/^http/, 'ws')}/ws`;
    this.log.debug(`Connecting to ${url}`);

    const ws = new WebSocket(url, { rejectUnauthorized: !this.tlsInsecure });
    this.ws = ws;

    ws.on('open', () => this.log.info(`Connected to hausphone at ${this.baseUrl}`));
    ws.on('message', (raw) => this.handleMessage(raw));
    ws.on('error', (err) => this.log.error(`hausphone socket error: ${err.message}`));
    ws.on('close', () => {
      if (this.stopping || this.ws !== ws) return;
      this.log.info(`hausphone socket closed — retrying in ${WS_RETRY_MS / 1000}s`);
      this.wsRetry = setTimeout(() => {
        this.wsRetry = null;
        this.connectWebSocket();
      }, WS_RETRY_MS);
    });
  }

  handleMessage(raw) {
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return; // not ours to fix
    }
    // Every control action broadcasts a partial snapshot, so `zwave` is often
    // absent (a fan or lock change). Only full/zwave snapshots concern us.
    const zwave = msg?.type === 'state' ? msg.data?.zwave : undefined;
    if (!zwave) return;

    for (const [key, endpoint] of this.devices) {
      const on = zwave[key]?.on;
      if (typeof on !== 'boolean') continue;
      endpoint.updateAttribute('OnOff', 'onOff', on, endpoint.log).catch((err) => {
        this.log.error(`Failed to update ${key}: ${err.message}`);
      });
    }
  }

  // ── hausphone HTTP ────────────────────────────────────────────────────────

  /**
   * Both containers come up together and hausphone needs ~20 s to connect its
   * device backends, so a cold boot always loses this race at least once.
   */
  async fetchManifest() {
    const deadline = Date.now() + MANIFEST_TIMEOUT_MS;
    for (;;) {
      try {
        const body = await this.request('GET', '/api/matter/devices');
        return body.devices ?? [];
      } catch (err) {
        if (Date.now() >= deadline) {
          throw new Error(`hausphone unreachable at ${this.baseUrl} after ${MANIFEST_TIMEOUT_MS / 1000}s: ${err.message}`);
        }
        this.log.info(`hausphone not ready (${err.message}) — retrying in ${MANIFEST_RETRY_MS / 1000}s`);
        await new Promise((resolve) => setTimeout(resolve, MANIFEST_RETRY_MS));
      }
    }
  }

  request(method, path, body) {
    const url = new URL(this.baseUrl + path);
    const transport = url.protocol === 'https:' ? https : http;
    const payload = body === undefined ? undefined : JSON.stringify(body);

    return new Promise((resolve, reject) => {
      const req = transport.request(
        url,
        {
          method,
          rejectUnauthorized: !this.tlsInsecure,
          headers: payload ? { 'content-type': 'application/json', 'content-length': Buffer.byteLength(payload) } : {},
          timeout: 10_000,
        },
        (res) => {
          const chunks = [];
          res.on('data', (chunk) => chunks.push(chunk));
          res.on('end', () => {
            const text = Buffer.concat(chunks).toString();
            if (res.statusCode < 200 || res.statusCode >= 300) {
              reject(new Error(`${method} ${path} -> HTTP ${res.statusCode}`));
              return;
            }
            try {
              resolve(text ? JSON.parse(text) : {});
            } catch {
              reject(new Error(`${method} ${path} -> unparseable response`));
            }
          });
        },
      );
      req.on('error', reject);
      req.on('timeout', () => req.destroy(new Error('timeout')));
      if (payload) req.write(payload);
      req.end();
    });
  }
}
