# Legacy oven capability capture

The NV51K7770SG/AA lamp investigation found no changing fields in 21 advertised
resource responses with the lamp on and off. Those requests did not include
`/capability`. Older Samsung appliances advertise that endpoint in SSDP LOCATION
headers, as recorded in [this first-hand packet capture](https://community.ezlo.com/t/samsung-smart-home-plugin/192382?page=2).
Its support and contents on this oven remain unverified.

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

After inspecting this result, consider a bounded time-series capture while
operating Lamp manually. A network capture at the router or access point is a
separate avenue; correlated encrypted traffic alone is not a verified light
state. No such time-series or network capture has been performed in this step.
