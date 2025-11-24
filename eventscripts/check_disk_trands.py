#!/home/project-model/venv/bin/python3
import pandas as pd
import numpy as np
import pwlf

# -----------------------------------------------------
# Load data from string or file
# -----------------------------------------------------

data_str = """2025-11-16T21:28:45;SERVER-LINUX-01;/;27.31
2025-11-16T21:28:45;SERVER-LINUX-02;/;23.12
2025-11-16T21:28:45;SERVER-LINUX-03;/;77.77
2025-11-16T21:28:45;SERVER-LINUX-01;/opt;2.31
2025-11-16T21:28:45;SERVER-LINUX-02;/opt;12.12
2025-11-16T21:28:45;SERVER-LINUX-03;/opt;17.77
2025-11-16T21:28:45;SERVER-WINDOWS-01;:C;22.31
2025-11-16T21:28:45;SERVER-WINDOWS-02;:C;19.12
2025-11-16T21:28:45;SERVER-WINDOWS-03;:C;29.77
2025-11-16T21:28:45;SERVER-WINDOWS-01;:E;1.31
2025-11-16T21:28:45;SERVER-WINDOWS-02;:E;1.12
2025-11-16T21:28:45;SERVER-WINDOWS-03;:E;20.67
2025-11-16T21:33:45;SERVER-LINUX-01;/;27.31
2025-11-16T21:33:45;SERVER-LINUX-02;/;23.12
2025-11-16T21:33:45;SERVER-LINUX-03;/;77.77
2025-11-16T21:33:45;SERVER-LINUX-01;/opt;2.31
2025-11-16T21:33:45;SERVER-LINUX-02;/opt;12.12
2025-11-16T21:33:45;SERVER-LINUX-03;/opt;18.77
2025-11-16T21:33:45;SERVER-WINDOWS-01;:C;22.31
2025-11-16T21:33:45;SERVER-WINDOWS-02;:C;19.12
2025-11-16T21:33:45;SERVER-WINDOWS-03;:C;29.77
2025-11-16T21:33:45;SERVER-WINDOWS-01;:E;1.31
2025-11-16T21:33:45;SERVER-WINDOWS-02;:E;1.12
2025-11-16T21:33:45;SERVER-WINDOWS-03;:E;20.67
2025-11-16T21:38:45;SERVER-LINUX-01;/;27.31
2025-11-16T21:38:45;SERVER-LINUX-02;/;23.12
2025-11-16T21:38:45;SERVER-LINUX-03;/;77.77
2025-11-16T21:38:45;SERVER-LINUX-01;/opt;2.31
2025-11-16T21:38:45;SERVER-LLINUX-02;/opt;12.12
2025-11-16T21:38:45;SERVER-LINUX-03;/opt;19.77
2025-11-16T21:38:45;SERVER-WINDOWS-01;:C;22.31
2025-11-16T21:38:45;SERVER-WINDOWS-02;:C;19.12
2025-11-16T21:38:45;SERVER-WINDOWS-03;:C;29.77
2025-11-16T21:38:45;SERVER-WINDOWS-01;:E;1.31
2025-11-16T21:38:45;SERVER-WINDOWS-02;:E;1.12
2025-11-16T21:38:45;SERVER-WINDOWS-03;:E;20.67
2025-11-16T21:43:45;SERVER-LINUX-01;/;27.31
2025-11-16T21:43:45;SERVER-LINUX-02;/;23.12
2025-11-16T21:43:45;SERVER-LINUX-03;/;77.77
2025-11-16T21:43:45;SERVER-LINUX-01;/opt;2.31
2025-11-16T21:43:45;SERVER-LINUX-02;/opt;12.12
2025-11-16T21:43:45;SERVER-LINUX-03;/opt;29.77
2025-11-16T21:43:45;SERVER-WINDOWS-01;:C;22.31
2025-11-16T21:43:45;SERVER-WINDOWS-02;:C;19.12
2025-11-16T21:43:45;SERVER-WINDOWS-03;:C;29.77
2025-11-16T21:43:45;SERVER-WINDOWS-01;:E;1.31
2025-11-16T21:43:45;SERVER-WINDOWS-02;:E;1.12
2025-11-16T21:43:45;SERVER-WINDOWS-03;:E;20.67
2025-11-16T21:48:45;SERVER-LINUX-01;/;27.31
2025-11-16T21:48:45;SERVER-LINUX-02;/;23.12
2025-11-16T21:48:45;SERVER-LINUX-03;/;77.77
2025-11-16T21:48:45;SERVER-LINUX-01;/opt;2.31
2025-11-16T21:48:45;SERVER-LINUX-02;/opt;12.12
2025-11-16T21:48:45;SERVER-LINUX-03;/opt;39.77
2025-11-16T21:48:45;SERVER-WINDOWS-01;:C;22.31
2025-11-16T21:48:45;SERVER-WINDOWS-02;:C;19.12
2025-11-16T21:48:45;SERVER-WINDOWS-03;:C;29.77
2025-11-16T21:48:45;SERVER-WINDOWS-01;:E;1.31
2025-11-16T21:48:45;SERVER-WINDOWS-02;:E;1.12
2025-11-16T21:48:45;SERVER-WINDOWS-03;:E;20.67
2025-11-16T21:53:45;SERVER-LINUX-01;/;27.31
2025-11-16T21:53:45;SERVER-LINUX-02;/;23.12
2025-11-16T21:53:45;SERVER-LINUX-03;/;77.77
2025-11-16T21:53:45;SERVER-LINUX-01;/opt;2.31
2025-11-16T21:53:45;SERVER-LINUX-02;/opt;12.12
2025-11-16T21:53:45;SERVER-LINUX-03;/opt;49.77
2025-11-16T21:53:45;SERVER-WINDOWS-01;:C;22.31
2025-11-16T21:53:45;SERVER-WINDOWS-02;:C;19.12
2025-11-16T21:53:45;SERVER-WINDOWS-03;:C;29.77
2025-11-16T21:53:45;SERVER-WINDOWS-01;:E;1.31
2025-11-16T21:53:45;SERVER-WINDOWS-02;:E;1.12
2025-11-16T21:53:45;SERVER-WINDOWS-03;:E;20.67
"""

# Convert string into dataframe
from io import StringIO
df = pd.read_csv(StringIO(data_str), sep=';', header=None,
                 names=["timestamp", "server", "disk", "usage"])

# Convert timestamp to datetime
df["timestamp"] = pd.to_datetime(df["timestamp"])

print("\nLoaded data:")
print(df.head())

# -----------------------------------------------------
# Function to detect trend change
# -----------------------------------------------------
def analyze_trend(series):
    y = series["usage"].values
    x = np.arange(len(y))

    # If not enough data, skip segmentation
    if len(y) < 4:
        return None

    model = pwlf.PiecewiseLinFit(x, y)
    breaks = model.fit(2)      # two segments
    slopes = model.slopes

    return {
        "breaks": breaks,
        "slopes": slopes,
        "slope_change": slopes[-1] - slopes[-2],
        "slope_ratio": slopes[-1] / slopes[-2] if slopes[-2] != 0 else np.inf
    }

# -----------------------------------------------------
# Process each server + disk
# -----------------------------------------------------

results = []

for (server, disk), group in df.groupby(["server", "disk"]):

    trend = analyze_trend(group)

    if trend is None:
        continue

    results.append({
        "server": server,
        "disk": disk,
        "breaks": trend["breaks"],
        "slope_prev": trend["slopes"][0],
        "slope_now": trend["slopes"][1],
        "slope_change": trend["slope_change"],
        "slope_ratio": trend["slope_ratio"]
    })

# Display results
print("\n=== TREND ANALYSIS RESULTS ===")
for r in results:
    print(f"\nServer: {r['server']}  Disk: {r['disk']}")
    print(f"  Segment 1 slope: {r['slope_prev']:.4f}")
    print(f"  Segment 2 slope: {r['slope_now']:.4f}")
    print(f"  Slope change: {r['slope_change']:.4f}")
    print(f"  Ratio: {r['slope_ratio']:.2f}x")
    print(f"  Breakpoints (trend change): {r['breaks']}")
 
