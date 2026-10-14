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
No event listener has been tested yet, and no callback or subscription write
has been sent by this helper.

Other avenues remain a bounded time-series capture while operating Lamp
manually, or a network capture at the router or access point. Correlated
encrypted traffic alone is not a verified light state. Neither capture has
been performed in this step.
