#!/opt/prisma/pythonServiciosTI/virtualEnvironments/venv_trend/bin/python3

import sqlite3
import numpy as np
import datetime
import sys

# ==============================
# CONFIGURACIÓN
# ==============================
CAIDA_PURGA = 5.0
DELTA_PURGA_MIN = 10.0
MIN_PUNTOS_CICLO = 4
MIN_INCREMENTO_PENDIENTE = 0.02
MUESTRAS_POR_HORA = 12
MIN_USO_ALERTA = 5.0

SALTO_BRUSCO_MIN = 10.0
VENTANA_SALTO = 3
MIN_USO_POST_SALTO = 5.0

DELTA_ESTABILIDAD = 10.0
DELTA_MINIMO_TENDENCIA = 2.0

DB = "/usr/lib/nagios/plugins/nagioscfg/dbs/infra.db"

# ==============================
# FUNCIONES
# ==============================
def pendiente_simple(y):
    n = len(y)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    y = y.astype(np.float64)
    return (n * np.dot(x, y) - x.sum() * y.sum()) / (n * np.dot(x, x) - x.sum() ** 2)


def detectar_ciclos_por_purga(timestamps, uso):
    ciclos = []
    inicio = 0

    for i in range(1, len(uso)):
        if uso[i - 1] - uso[i] >= CAIDA_PURGA:
            ciclos.append((timestamps[inicio:i], uso[inicio:i]))
            inicio = i

    ciclos.append((timestamps[inicio:], uso[inicio:]))
    return ciclos


def analizar_ciclo(timestamps, uso):
    if len(uso) < MIN_PUNTOS_CICLO:
        return None

    return {
        "minimo": float(uso.min()),
        "maximo": float(uso.max()),
        "pendiente": float(pendiente_simple(uso)),
        "inicio": timestamps[0],
        "fin": timestamps[-1],
    }


def detectar_salto_brusco(timestamps, uso):
    if len(uso) < VENTANA_SALTO + 1:
        return None

    u = uso[-(VENTANA_SALTO + 1):]
    t = timestamps[-(VENTANA_SALTO + 1):]
    diffs = np.diff(u)

    max_salto = diffs.max()
    uso_final = u[-1]

    if max_salto >= SALTO_BRUSCO_MIN and uso_final >= MIN_USO_POST_SALTO:
        idx = diffs.argmax()
        return {
            "salto": float(max_salto),
            "uso": float(uso_final),
            "inicio": t[idx],
            "fin": t[idx + 1],
        }

    return None


# ==============================
# CONEXIÓN DB + STATE
# ==============================
try:
    conn = sqlite3.connect(DB, timeout=30)
except sqlite3.Error as e:
    print(f"ERROR: No se pudo abrir la base de datos: {e}")
    sys.exit(1)

conn.execute("""
CREATE TABLE IF NOT EXISTS disk_state (
    host TEXT NOT NULL,
    service TEXT NOT NULL,
    last_ts TEXT NOT NULL,
    min_prev REAL,
    max_prev REAL,
    pendiente_prev REAL,
    ciclos_previos INTEGER,
    PRIMARY KEY (host, service)
)
""")
conn.commit()

# ==============================
# LISTAR DISCOS
# ==============================
try:
    discos = conn.execute("""
        SELECT DISTINCT host, service
        FROM discos
        WHERE timestamp >= datetime('now', '-3 days')
    """).fetchall()
except sqlite3.Error as e:
    print(f"ERROR consultando discos: {e}")
    conn.close()
    sys.exit(1)

alertas = []

# ==============================
# LOOP PRINCIPAL
# ==============================
for host, service in discos:

    try:
        state = conn.execute("""
            SELECT last_ts
            FROM disk_state
            WHERE host = ? AND service = ?
        """, (host, service)).fetchone()

        if state:
            rows = conn.execute("""
                SELECT timestamp, valor
                FROM discos
                WHERE host = ?
                  AND service = ?
                  AND timestamp > ?
                ORDER BY timestamp
            """, (host, service, state[0])).fetchall()
        else:
            rows = conn.execute("""
                SELECT timestamp, valor
                FROM discos
                WHERE host = ?
                  AND service = ?
                  AND timestamp >= datetime('now', '-3 days')
                ORDER BY timestamp
            """, (host, service)).fetchall()

        if not rows:
            continue

        timestamps = [r[0] for r in rows]
        uso = np.array([r[1] for r in rows], dtype=np.float32)

        # ------------------------------
        # STEP UP
        # ------------------------------
        salto = detectar_salto_brusco(timestamps, uso)

        ciclos_info = []
        if salto:
            ciclos = detectar_ciclos_por_purga(timestamps, uso)
            for t, u in ciclos:
                info = analizar_ciclo(t, u)
                if info:
                    ciclos_info.append(info)

            if len(ciclos_info) >= 3:
                prev = ciclos_info[:-2]
                rec = ciclos_info[-2:]

                min_prev = np.mean([c["minimo"] for c in prev])
                min_rec = np.mean([c["minimo"] for c in rec])
                max_prev = np.mean([c["maximo"] for c in prev])
                max_rec = np.mean([c["maximo"] for c in rec])

                if (
                    abs(min_rec - min_prev) < DELTA_ESTABILIDAD and
                    abs(max_rec - max_prev) < DELTA_ESTABILIDAD
                ):
                    salto = None

        if salto:
            alertas.append({
                "servidor": host,
                "disco": service,
                "uso": salto["uso"],
                "tipo": "STEP_UP",
                "detalle": salto
            })
            continue

        # ------------------------------
        # TENDENCIA
        # ------------------------------
        if not ciclos_info:
            ciclos = detectar_ciclos_por_purga(timestamps, uso)
            for t, u in ciclos:
                info = analizar_ciclo(t, u)
                if info:
                    ciclos_info.append(info)

        if len(ciclos_info) < 3:
            continue

        prev = ciclos_info[:-2]
        rec = ciclos_info[-2:]

        minimo_previo = np.mean([c["minimo"] for c in prev])
        minimo_reciente = np.mean([c["minimo"] for c in rec])

        pendiente_previa = np.mean([c["pendiente"] for c in prev])
        pendiente_reciente = np.mean([c["pendiente"] for c in rec])

        max_previo = np.mean([c["maximo"] for c in prev])
        max_reciente = np.mean([c["maximo"] for c in rec])

        if (minimo_reciente - minimo_previo) < DELTA_MINIMO_TENDENCIA:
            continue

        if minimo_previo - minimo_reciente >= DELTA_PURGA_MIN:
            continue

        if (
            abs(minimo_reciente - minimo_previo) < DELTA_ESTABILIDAD and
            abs(max_reciente - max_previo) < DELTA_ESTABILIDAD
        ):
            continue

        if pendiente_reciente <= pendiente_previa + MIN_INCREMENTO_PENDIENTE:
            continue

        uso_actual = float(uso[-1])

        horas = None
        if pendiente_reciente > 0:
            horas = ((100 - uso_actual) / pendiente_reciente) / MUESTRAS_POR_HORA

        alertas.append({
            "servidor": host,
            "disco": service,
            "uso": uso_actual,
            "min_previo": minimo_previo,
            "min_reciente": minimo_reciente,
            "pendiente_previa": pendiente_previa,
            "pendiente_reciente": pendiente_reciente,
            "horas": horas
        })

        # ------------------------------
        # GUARDAR STATE
        # ------------------------------
        last_ts = timestamps[-1]
        ultimo = ciclos_info[-1]

        conn.execute("""
            REPLACE INTO disk_state
            (host, service, last_ts, min_prev, max_prev, pendiente_prev, ciclos_previos)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            host,
            service,
            last_ts,
            ultimo["minimo"],
            ultimo["maximo"],
            ultimo["pendiente"],
            len(ciclos_info)
        ))

    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            print("WARNING: base de datos bloqueada, se reintentará en el próximo ciclo")
            conn.close()
            sys.exit(0)
        else:
            print(f"ERROR SQLite en {host} | {service}: {e}")
            continue

    except Exception as e:
        print(f"ERROR procesando {host} | {service}: {e}")
        continue

# ==============================
# COMMIT FINAL
# ==============================
try:
    conn.commit()
except sqlite3.Error as e:
    print(f"ERROR al hacer commit: {e}")

conn.close()

# ==============================
# SALIDA
# ==============================
print("\n=== ALERTAS DETECTADAS ===\n")

if not alertas:
    print("No se detectaron cambios relevantes.\n")
    sys.exit(0)

for alerta in alertas:
    print(f"Servidor: {alerta['servidor']} | Disco: {alerta['disco']}")

    if alerta.get("tipo") == "STEP_UP":
        print("  ALERTA: CAMBIO BRUSCO DE USO")
        print(f"  Uso actual: {alerta['uso']:.2f}%")
        print(
            f"  Salto detectado: +{alerta['detalle']['salto']:.2f}% "
            f"entre {alerta['detalle']['inicio']} y {alerta['detalle']['fin']}\n"
        )
        continue

    print("  ALERTA: ACELERACIÓN DE TENDENCIA")
    print(f"  Uso actual: {alerta['uso']:.2f}%")
    print(
        f"  Mínimo previo: {alerta['min_previo']:.2f}% → "
        f"Mínimo reciente: {alerta['min_reciente']:.2f}%"
    )
    print(f"  Pendiente previa: {alerta['pendiente_previa']:.4f}")
    print(f"  Pendiente reciente: {alerta['pendiente_reciente']:.4f}")

    if alerta["horas"] is None:
        print("  Tiempo estimado: No aplica\n")
    else:
        fecha = datetime.datetime.now() + datetime.timedelta(hours=alerta["horas"])
        print(f"  Se llenaría aprox: {fecha.strftime('%Y-%m-%d %H:%M')}\n")
