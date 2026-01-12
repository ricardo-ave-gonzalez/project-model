#!/bin/bash

# ==============================
# DEBUG
# ==============================
DEBUG=2
DBGF=$(basename "$0")
DBGFL="/var/log/logsscripts/${DBGF}.debug"

log() {
    [[ "$DEBUG" -ge 1 ]] && \
    echo "$(date '+%Y-%m-%d %H:%M:%S') | $*" >> "$DBGFL"
}

log "Inicio extractor_infra CHMK"

# ==============================
# CONFIG FIJA
# ==============================
INTEGRACION="chmk"

CSV_SRC="/usr/lib/nagios/plugins/nagioscfg/dbs/nagios.discos"
CSV_OUT="/usr/lib/nagios/plugins/nagioscfg/dbs/csv/infra_${INTEGRACION}.csv"
CLEAN="/opt/prisma/logsscripts/clean.csv"

DB="/usr/lib/nagios/plugins/nagioscfg/dbs/infra.db"
TABLE="discos"

TS=$(date +"%Y-%m-%dT%H:%M:%S")

# ==============================
# 1) EXTRACCIÓN (MISMA QUE FUNCIONA)
# ==============================
log "Extrayendo datos desde nagios.discos"

grep -E "/[^;]*;|:[A-Z];|[A-Z]:(;|$)" "$CSV_SRC" \
| awk -v TS="$TS" -F';' '
{
    host=$1
    service=$2
    info=$4

    match(info, /\(([0-9.]+)%\)/, arr)
    percent=arr[1]

    if (percent != "")
        printf "%s|%s|%s|%s\n", TS, host, service, percent
}' > "$CSV_OUT"

if [[ $? -ne 0 ]]; then
    log "ERROR en extracción"
    exit 1
fi

log "CSV generado: $CSV_OUT"

# ==============================
# 2) CREAR TABLA + ÍNDICE (MISMO ESQUEMA ORIGINAL)
# ==============================
log "Validando estructura de base e índice"

sqlite3 "$DB" <<EOF
CREATE TABLE IF NOT EXISTS discos (
    timestamp TEXT NOT NULL,
    host      TEXT NOT NULL,
    service   TEXT NOT NULL,
    valor     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_discos_host_service_ts
ON discos (host, service, timestamp);
EOF

# ==============================
# 3) NORMALIZACIÓN + IMPORT (MISMA LÓGICA ORIGINAL)
# ==============================
log "Normalizando e importando datos"

sed 's/,/./g' "$CSV_OUT" \
| sed 's/;/|/g' \
> "$CLEAN"

sqlite3 "$DB" <<EOF
.mode csv
.separator "|"
.import $CLEAN $TABLE
EOF

if [[ $? -ne 0 ]]; then
    log "ERROR al importar datos"
    exit 1
fi

# ==============================
# 4) RETENCIÓN 7 DÍAS
# ==============================
log "Aplicando retención de 3 días"

sqlite3 "$DB" <<EOF
DELETE FROM $TABLE
WHERE datetime(timestamp) < datetime('now', '-3 days');
EOF

log "Fin extractor_infra CHMK"
exit 0
