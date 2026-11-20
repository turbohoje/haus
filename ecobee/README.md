# ecobee

**Superseded by the hausphone Ecobee card** — see `hausphone/CLAUDE.md` → "Ecobee thermostat".
hausphone now owns the thermostat: status, 2 h holds, and the weekday peak shutoff
(HVAC + humidifier + fan off 17:00–21:00, restored after).

- `humidifier.py` — old cron script (humidifier `off` 12:30 / `manual` 20:21 weekdays). Its crontab
  lines are commented out (`# moved to hausphone ecobee card: …`). **Don't re-enable them**: they
  would fight the PWA's peak shutoff/restore.
- `token.json` — empty since Apr 2026 (the script truncated it on a failed run), which is why the
  cron jobs had silently stopped working. Not used any more; hausphone keeps its own token in the
  `hausphone-certs` volume (`/certs/ecobee_token.json`) and re-links from Settings → Ecobee account.
- `get_access_token.py` — old manual PIN → token exchange; not needed (the PWA does the PIN flow).
