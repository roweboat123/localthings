# Legacy oven capability capture

The NV51K7770SG/AA lamp investigation found no changing fields in 21 advertised
resource responses with the lamp on and off. Those requests did not include
`/capability`. Older Samsung appliances advertise that endpoint in SSDP LOCATION
headers, as recorded in [this first-hand packet capture](https://community.ezlo.com/t/samsung-smart-home-plugin/192382?page=2).

The 2026-10-14 capture from this oven returned HTTP 200 and:

```json
{"Capability":{"DevicesLink":{"href":"/devices"},"SubscriptionsLink":{"href":"/subscriptions"}}}
```

This establishes that the oven advertises `/subscriptions`; it does not establish
working subscriptions or lamp events. The legacy transport's lack of CoAP
OBSERVE support does not rule out this separate HTTP notification mechanism.

Run the standalone helper from the same Home Assistant terminal used for the
previous captures:

```sh
python3 /config/legacy_oven_capture.py --capability
```

It selects the existing `LCD_OV_WALL_16K` entry and sends one authenticated GET
to `/capability`. It records JSON or parsed XML, applies the existing credential
and identity redaction plus descriptor-name and UUID redaction, and saves an
`oven-capability-<timestamp>.json` report in `/config`. The terminal prints both
the saved path and report. No physical lamp-state label is required.

An error response is useful evidence and is saved too. The helper does not
follow redirects or descriptor links, subscribe to events, send appliance
controls, or change installed integration code. Existing capture scopes retain
their endpoint lists. Unknown, oversized, HTML and entity-bearing XML responses
are not exported as raw text.

## Read the subscription list

Static inspection of the user-supplied Samsung Oven plug-in
`com.samsung.smarthome.oven` version `1.1040.8.0` confirms that
`SubscriptionCommunicatorJs.getSubscriptions()` sends GET `/subscriptions`
(request ID 22001). Its `SubscriptionRegisterer` also contains registration
code using a local HTTPS `/notifications` callback and `resourceURIs` containing
`/devices`. Those app paths support investigating events, but do not prove what
this oven emits.

```sh
python3 /config/legacy_oven_capture.py --subscriptions
```

This scope sends one GET to `/subscriptions` and saves an
`oven-subscriptions-<timestamp>.json` report. It redacts callback addresses and
subscription identifiers while keeping resource paths, durations and timeouts.
No lamp-state label is needed. It does not register, renew or delete subscriptions.
An empty list would mean no registrations were returned, not that events are
unsupported. A rejection would need to be interpreted with its status and body.

The app's `SubscriptionJs` declares `notificationURI`, `resourceURIs`, `uuid`,
`duration` and `timeout`, plus inherited `id` and `description`. The registration
code repeats every 600,000 ms; the effective device lease is not established.
No event listener has been tested on the oven yet, and the GET-only helper
has sent no callback or subscription write.

The follow-up capture at 2026-10-14 19:33 UTC returned HTTP 200 with
`{"Subscriptions": []}`. The list is readable on this oven and no registrations
were returned. Subscription creation and notification delivery remain unverified
on the appliance.

## Temporary notification capture

`legacy_oven_events.py` is a separate interactive experiment. Keep
`legacy_oven_capture.py` beside it; the latter remains a GET-only helper.

```sh
python3 /config/legacy_oven_events.py
```

Start with the oven idle and cool, the door closed and the lamp off. After
registration, follow the terminal prompts to switch Lamp on, switch it off,
open the door, and close the door, pressing Enter after each action. The marker
times are user confirmations, not precise button-press timestamps. The door
steps provide a comparison event: without any confirmed notification delivery,
silence during Lamp changes cannot establish that lamp events are absent.

The script binds a local HTTPS listener on port 8889 using the installed
LocalThings certificate and accepts connections only from the selected oven's
address. It reads the subscription list first and stops if it is unavailable
or nonempty. It then sends exactly one POST to `/subscriptions` with:

```json
{"Subscription":{"uuid":"<fresh UUID>","notificationURI":"https://<local address>:8889/notifications","resourceURIs":["/devices"],"duration":180}}
```

The `Subscription` root is confirmed by the APK's Jackson `JsonRootName`
annotation and `UtilForJson.obj2Json()` root wrapping. The resource and callback
format come from `SubscriptionRegisterer`. The `duration` field exists in the
app's schema; requesting 180 is an experimental bounded lease request. Its
units and enforcement on this firmware are unverified, so cleanup does not
rely on expiration.

Observation ends after the prompts or at most 150 seconds after registration
checks. The script attempts DELETE only for a validated ID returned by its own
successful POST, or a list entry matching both its fresh UUID and callback.
It reconciles a timed-out POST too, then checks the list again and reports
cleanup as confirmed absent, still present, or unverified. Ctrl+C and normal
termination signals enter this cleanup path. A hard process kill or power loss
can prevent cleanup; an unexplained nonempty list stops a subsequent run.
The helper never sends cooking, configuration, or lamp-control requests.

Reports are saved as `oven-events-<timestamp>.json` with private file permissions.
They retain JSON notification bodies without resource mapping, redact identities
and credentials, and count connections, TLS failures, request failures and
dropped bodies. Headers and unparsed bodies are excluded. The current listener
supports Content-Length framing; unsupported framing is recorded as an error,
not interpreted as an absence of events. A maximum of 100 records and 8 MiB of
body data bounds the report. No returned URL is followed.

The callback server and cleanup paths have automated local tests. These tests
do not establish compatibility with the oven or discover lamp support.

Other avenues remain a bounded time-series capture while operating Lamp
manually, or a network capture at the router or access point. Correlated
encrypted traffic alone is not a verified light state. Neither capture has
been performed in this step.
