#!/home/project-model/venv/bin/python3
import pandas as pd
import numpy as np
import pwlf
import subprocess
import datetime
from io import StringIO

# -----------------------------------------------------
# load data from SQLite
# -----------------------------------------------------
cmd = [
    "sqlite3",
    "/usr/lib/nagios/plugins/nagioscfg/dbs/infra.db",
    "select * from discos"
]

output = subprocess.check_output(cmd).decode().strip()

df = pd.read_csv(
    StringIO(output),
    sep="|",
    header=None,
    names=["timestamp", "server", "disk", "usage"]
)

df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp")

# -----------------------------------------------------
# trend analysis function
# -----------------------------------------------------
def analyze_trend(group):
    y = group["usage"].values
    x = np.arange(len(y))

    # Requires minimum 4 points
    if len(y) < 4:
        return None

    model = pwlf.PiecewiseLinFit(x, y)
    breaks = model.fit(2)
    slopes = model.slopes

    return {
        "breaks": breaks,
        "previous_slope": slopes[0],
        "current_slope": slopes[1],
        "delta": slopes[1] - slopes[0],
    }

# -----------------------------------------------------
# approximate calculation for estimated fill time
# -----------------------------------------------------
def time_to_full(current_usage, current_slope):
    # If the slope is very small or negative → it won't fill
    if current_slope <= 0.0001:
        return None

    # Percentage remaining until 100%
    remaining = 100 - current_usage

    # Approximate hours (each sample = 5 minutes → 12 samples/hour)
    hours = (remaining / current_slope) / 12
    return hours

# -----------------------------------------------------
# process each server + disk
# -----------------------------------------------------
alerts = []

for (server, disk), group in df.groupby(["server", "disk"]):

    result = analyze_trend(group)
    if result is None:
        continue

    previous_slope = result["previous_slope"]
    current_slope = result["current_slope"]

    # only real increasing trends
    if current_slope <= 0.05:   # minimum threshold → ignore noise
        continue

    current_usage = group["usage"].iloc[-1]
    hours = time_to_full(current_usage, current_slope)

    alerts.append({
        "server": server,
        "disk": disk,
        "current_usage": current_usage,
        "previous_slope": previous_slope,
        "current_slope": current_slope,
        "delta": result["delta"],
        "hours_to_full": hours,
        "breaks": result["breaks"]
    })


# -----------------------------------------------------
# show only real ALERTS
# -----------------------------------------------------
print("\n=== INCREASING TREND ALERTS ===\n")

if not alerts:
    print("No disks with significant growth.\n")
    exit(0)

for a in alerts:
    print(f"Server: {a['server']}  |  Disk: {a['disk']}")
    print(f"  Current usage: {a['current_usage']:.2f}%")
    print(f"  Current slope: {a['current_slope']:.4f} % per sample")
    print(f"  Trend change (delta): {a['delta']:.4f}")
    print(f"  Breakpoints: {a['breaks']}")

    if a["hours_to_full"] is None:
        print("  Estimated time to full: Not applicable (weak growth)\n")
    else:
        hours = a["hours_to_full"]
        days = hours / 24

        now = datetime.datetime.now()
        full_date = now + datetime.timedelta(hours=hours)

        formatted_date = full_date.strftime("%Y-%m-%d %H:%M")

        print(f"  Estimated time: {hours:.2f} hours  (fills on {formatted_date})\n")
 
