# haus
misc home automation

## TV
current crontab setup
```
45 05 * * * /home/turbohoje/haus/tv/vizio_cron.py --display=kitchen --min=100
30 05 * * 1 /home/turbohoje/haus/tv/vizio_cron.py --display=master --min=100
30 05 * * 2 /home/turbohoje/haus/tv/vizio_cron.py --display=master --min=100
30 05 * * 3 /home/turbohoje/haus/tv/vizio_cron.py --display=master --min=100
30 05 * * 4 /home/turbohoje/haus/tv/vizio_cron.py --display=master --min=100
30 05 * * 5 /home/turbohoje/haus/tv/vizio_cron.py --display=master --min=100
```