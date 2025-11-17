📌 Achievements
✔ 1. Unified data structure

A standard format was defined for all sources:
```
timestamp;host;service;valor
```

Example:
```
2025-11-16T21:28:45;HBTM03;/rpool;27.31
```

This ensures that any new source can be integrated without modifying the pipeline.
Esto permite que cualquier integración nueva se conecte al sistema sin modificar el pipeline.

✔ 2. Modular extractors

Each integration (CheckMK, Zabbix, Orion, Windows, etc.) has its own dedicated extractor script:
Cada integración (CheckMK, Zabbix, Orion, Windows, etc.) implementa su propio script:
```
extractor_${INTEGRATION}.sh
extractor_${INTEGRATION}.sh
extractor_${INTEGRATION}.sh
extractor_${INTEGRATION}.sh
...
```

Each extractor:
reads its original input (CSV, API, remote command output)
cleans and normalizes data (comma → dot, removing noise, fix formatting)
generates a standardized CSV:
```
../csv/infra_${INTEGRATION}.csv
```

Adding a new data source only requires dropping in a new extractor.

✔ 3. Centralized integration layer (SQLite loader)
A single script performs the integration:
```
extractor_infra.sh
```

Responsibilities:
creates the table if it does not exist
iterates through all infra_*.csv files
automatically imports each CSV into SQLite
no changes needed when new extractors are added

Table structure:
```
CREATE TABLE IF NOT EXISTS discos (
    timestamp TEXT NOT NULL,
    host TEXT NOT NULL,
    service TEXT NOT NULL,
    valor REAL NOT NULL
);
```
✔ 4. Efficient SQLite persistence

The database is stored at:
```
/usr/lib/nagios/plugins/INFRA/dbs/infra.db
```

Benefits:
    very fast queries
    ideal for medium-sized time-series datasets
    easy export capabilities
    perfect foundation for trend prediction and historical analysis

✔ 5. Pipeline - Extremely fast processing

The old pipeline processed large files slowly.
    The new architecture:
    processes thousands of lines in under one second
    uses optimized grep, awk, and sed pipelines
    imports efficiently into SQLite

✔ 6. Future-proof scalability

This design allows:
    adding new integrations with zero impact
    extending prediction models
    building historical dashboards
    creating intelligent alerts based on trend changes

📦 Final system structure
```
/usr/lib/nagios/plugins/
│
├── collectors/
│   ├── extractor_chmk.sh
│   ├── extractor_orion.sh
│   ├── extractor_zabbix.sh
│   └── extractor_infra.sh   ← loader central
│
├── dbs/
│   └── infra.db /
│   └── csv/
│       ├── infra_chmk.csv
│       ├── infra_orion.csv
│       ├── infra_zabbix.csv
│       └── ...
│
└── logsscripts/
    └── clean_infra_*.csv    ← CSVs normalizados listo para importarse
```

🔮 Recommended next steps

Add indexes (host, service, timestamp) for faster historical queries
Implement a trend-prediction function (simple linear regression)
Detect abrupt consumption spikes
Add smart alerts, such as:
```
WARNING – Disk will fill in 148 days (82.3%)
CRITICAL – Trend change detected, disk will fill in < 1 day
```

🎉 Conclusión

    The implemented architecture provides:
    real modularity
    excellent performance
    uniform data format
    robust and extensible pipeline
    a solid foundation for prediction and analytics


