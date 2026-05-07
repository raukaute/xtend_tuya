# Migration strategy: away from Tuya cloud

Captured 2026-05-07. Owner: raukaute fork (FDM5KW solar irrigation valves, 21-unit fleet, growing past 50).

## Problem

Tuya cloud has burned through repeated cycles of pain:

1. **Quota cap.** Trial Edition allows ~$0.20/month of API calls (~54k EU calls). Per-second polling × 21 valves exhausted the cap in a single day on 4.4.118. Flagship paid tier is $25,000/yr — a non-starter.
2. **Device cap.** Trial Edition limits 50 devices per cloud project. The fleet is at 21 today, expected to exceed 50 within 1–2 seasons.
3. **Two-tier timer model.** FDM5KW stores schedules in the device-side `time_task` DP (authoritative, executes locally). The Tuya cloud timer registry is a separate, redundant server-side abstraction. The fork tried to keep both in sync, which was the root cause of multiple regressions in 4.4.112–119.
4. **Cloud reauth flakiness.** Sharing API tokens expire and require Smart Life QR scan via HA Repairs panel — repeated sessions of yak-shaving.

## Conclusion

Move away from Tuya cloud as the runtime path. Keep cloud only for one-time pairing / key extraction.

## Options evaluated

| Option | Cloud independence | Hardware cost | Effort | Risk |
|--------|-------------------|---------------|--------|------|
| 1. Strip OpenAPI from fork (sharing API only) | Partial — still uses cloud MQTT | €0 | 1–3 days | Low |
| 2. LocalTuya / tuya-local on existing valves | 99% — cloud needed once for `local_key` extraction | €0 | 2–3 days (DP mapping for FDM5KW) | Low |
| 3. Cloudcutter + ESPHome (LibreTiny) on existing valves | 100% — Tuya account becomes irrelevant | €0 + brick risk | 2–4 weeks staged | Medium (per-device flash risk) |
| 4. Sonoff SWV-NH (Zigbee) fleet swap | 100% | ~€800 + Zigbee router infra €200 | 1–2 weeks install | Mesh-range planning |
| 5. Eve Aqua 3rd gen (Thread/Matter) | 100% | ~€2100 | Install only | Single-tap form factor — wrong topology |
| 6. OpenSprinkler central panel | 100% | ~€310 | Full field re-trench | Wrong topology — distributed solar valves can't slot in |
| 7. Pay Tuya Flagship | None | $25k/yr | None | Hostile pricing |

## Recommended trajectory

### Phase 1 — Now (Q2 2026)

**Strip OpenAPI from fork.** Replace cloud-timer-registry sync with on-device `time_task` DP as single source of truth. Cloud sharing-API push remains for status events (free, no quota meter).

Outcome: existing fleet runs forever on Trial Edition without burning cap.

### Phase 2 — Q3 2026

**Add LocalTuya in parallel** on one valve. Verify push-update latency vs cloud path. Map FDM5KW DPs to a tuya-local YAML profile (no existing profile — must contribute new one). Roll out to fleet over 2–3 weeks.

After Phase 2: cloud path becomes pure fallback. Smart Life app keeps working for field diagnostics. HA Companion app preferred for admin.

### Phase 3 — Q4 2026 / Winter 2026/27

**Cloudcutter trial** on one spare FDM5KW. If `tuya-cloudcutter` profile exists for the firmware version (BK7231N expected) and OTA flash succeeds → schedule fleet-wide reflash during dry/dormant season when valves can be off.

After Phase 3: Tuya account can be deleted. Fleet runs ESPHome native, exposed to HA via native API. No quotas, no caps, no reauth.

### Phase 4 — Beyond (2027+)

Watch Matter 1.5 irrigation cluster + Sub-GHz Thread / Long-Range WiFi. If outdoor distributed Matter devices ship at sane prices, evaluate as next-gen replacement when current fleet ages out.

## Decisions made

- **Do not pay Tuya.** Flagship $25K is hostile; Trial cap is workable post-OpenAPI-strip.
- **Do not swap to Zigbee yet.** Existing WiFi infrastructure already covers the field; Zigbee mesh would require new router infra outdoors.
- **Do not retrench to OpenSprinkler.** Distributed solar valve topology is incompatible with central AC panel.
- **Single source of truth = device-side `time_task` DP.** Cloud timer registry is no longer mirrored by HA.
- **Mobile diagnostics path = HA Companion (primary) + Smart Life (read-only fallback).** Workers install HA Companion app + Tailscale for remote access.

## Open questions

1. What does the fork's OpenAPI dependency actually do beyond timer registry sync? Audit `device_manager.api.*` and `customer_api.*` call sites.
2. Does FDM5KW firmware match an existing `tuya-cloudcutter` profile? Need to dump firmware ID before committing to Phase 3.
3. Push-only sharing channel reliability over 24h+ without OpenAPI safety-net resync — was the 5-min resync covering for missed pushes, or paranoia?
4. tuya-local YAML profile for FDM5KW — does any maintainer want to merge upstream, or carry as a fork-local YAML?

## References

- [tuya-local DEVICES.md](https://github.com/make-all/tuya-local/blob/main/DEVICES.md)
- [tuya-cloudcutter](https://github.com/tuya-cloudcutter/tuya-cloudcutter)
- [LibreTiny + ESPHome](https://docs.libretiny.eu/)
- [Sonoff SWV-NH](https://sonoff.tech/en-us/products/sonoff-zigbee-smart-water-valve)
- [MOiST distributed solar irrigation controller](https://github.com/cybershoe/moist-controller)
- [Tuya Trial Edition pricing](https://developer.tuya.com/en/docs/iot/membership-service?id=K9m8k45jwvg9j)
