#!/opt/prisma/pythonServiciosTI/virtualEnvironments/venv_trend/bin/python3

import sqlite3
import numpy as np
import datetime
import sys

# ==============================
# CONFIGURACIÓN
# ==============================
#parametros para controlar purgas
CAIDA_PURGA = 5.0
DELTA_PURGA_MIN = 10.0
MIN_PUNTOS_CICLO = 4
MIN_INCREMENTO_PENDIENTE = 0.02
MUESTRAS_POR_HORA = 12
MIN_USO_ALERTA = 5.0
#parametros para saltos bruscos
SALTO_BRUSCO_MIN = 10.0
VENTANA_SALTO = 3
MIN_USO_POST_SALTO = 5.0
#parametros para delta tendencia
DELTA_ESTABILIDAD = 10.0
DELTA_MINIMO_TENDENCIA = 2.0
#parametros para
VENTANA_RAMP = 12        # 1 hora (12 muestras de 5 min)
DELTA_RAMP_MIN = 25.0   # +25 %
MIN_USO_RAMP = 15.0     # evitar discos chicos
#parametros para funcion post purga
CAIDA_PURGA_MIN          = 15.0   # % mínimo de caída
REFILL_MIN_TOTAL         = 20.0   # % recuperado tras purga
MAX_HORAS_POST_PURGA     = 48     # tiempo máximo para volver a warning
PENDIENTE_MIN_REFILL     = 0.01   # crecimiento sostenido (muy bajo)

NAGIOSDIR = "/usr/lib/nagios/plugins/nagioscfg"
DB = f"{NAGIOSDIR}/dbs/infra.db"
LOG_FILE = f"{NAGIOSDIR}/logs/{datetime.datetime.now().strftime('%Y-%m-%d')}_disk_trands.log"




# LOG
# ==============================
def log_event(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass  # nunca romper el monitoreo por un log


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

def detectar_ramp_up(timestamps, uso):
    if len(uso) < VENTANA_RAMP:
        return None

    u = uso[-VENTANA_RAMP:]
    t = timestamps[-VENTANA_RAMP:]

    u_min = u.min()
    u_max = u.max()
    delta = u_max - u_min

    if delta >= DELTA_RAMP_MIN and u_max >= MIN_USO_RAMP:
        return {
            "delta": float(delta),
            "min": float(u_min),
            "max": float(u_max),
            "inicio": t[u.argmin()],
            "fin": t[u.argmax()],
        }

    return None

# detecta discos que, tras una purga fuerte, vuelven a zona de riesgo en poco tiempo.
def detectar_post_purge_risk(t, uso, warning_level):

    for i in range(1, len(uso)):
        caida = uso[i - 1] - uso[i]

        if caida < CAIDA_PURGA_MIN: continue

        uso_min = uso[i]
        tiempo_purga = t[i]

        # analizar ventana post-purga
        j = i + 1
        while j < len(uso):
            horas = (t[j] - tiempo_purga).total_seconds() / 3600

            if horas > MAX_HORAS_POST_PURGA:
                break

            # se alcanzó warning?
            if uso[j] >= warning_level:
                refill = uso[j] - uso_min

                if refill >= REFILL_MIN_TOTAL:
                    # pendiente sostenida (no pico)
                    pendiente = (uso[j] - uso[i]) / max(j - i, 1)

                    if pendiente >= PENDIENTE_MIN_REFILL:
                        return True, {
                            "tipo": "POST_PURGE_RISK_REFILL",
                            "purga": caida,
                            "horas": round(horas, 1),
                            "refill": round(refill, 1),
                            "pendiente": round(pendiente, 4)
                        }
            j += 1

    return False, None

#detecta oscilaciones grandes de uso en una ventana corta, independientemente de purga.
def detectar_volatilidad_anormal(timestamps, uso):

    if len(uso) < MIN_PUNTOS_CICLO:
        return None

    uso_max = float(uso.max())
    uso_min = float(uso.min())
    delta = uso_max - uso_min

    if uso_max < MIN_USO_ALERTA:
        return None

    if delta < DELTA_RAMP_MIN:
        return None

    return {
        "delta": round(delta, 2),
        "min": round(uso_min, 2),
        "max": round(uso_max, 2),
        "inicio": timestamps[uso.argmin()],
        "fin": timestamps[uso.argmax()]
    }


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
        # RAMP UP
        # ------------------------------
        #rampa = detectar_ramp_up(timestamps, uso)

        #if rampa:
        #    alertas.append({
        #        "servidor": host,
        #        "disco": service,
        #        "uso": rampa["max"],
        #        "tipo": "RAMP_UP",
        #        "detalle": rampa
        #    })

         #   log_event(
         #       f"RAMP_UP | host={host} | disk={service} | "
         #       f"delta=+{rampa['delta']:.2f}% | "
         #       f"desde={rampa['inicio']} hasta={rampa['fin']} | "
         #       f"uso_max={rampa['max']:.2f}%"
         #   )

            continue



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

            log_event(
                f"STEP_UP | host={host} | disk={service} | "
                f"uso={salto['uso']:.2f}% | "
                f"salto=+{salto['salto']:.2f}% | "
                f"desde={salto['inicio']} hasta={salto['fin']}"
            )

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

        log_event(
            f"TREND_ACCEL | host={host} | disk={service} | "
            f"uso={uso_actual:.2f}% | "
            f"min_prev={minimo_previo:.2f}% | min_rec={minimo_reciente:.2f}% | "
            f"pend_prev={pendiente_previa:.4f} | pend_rec={pendiente_reciente:.4f} | "
            f"horas={'N/A' if horas is None else round(horas, 2)}"
        )

        # ------------------------------
        # POST PURGE REFILL RISK
        # ------------------------------
        warning_level = 75.0  # coherente con Nagios / Zabbix

        post_purge, detalle_purge = detectar_post_purge_risk(
            timestamps,
            uso,
            warning_level
        )

        if post_purge:
            alertas.append({
                "servidor": host,
                "disco": service,
                "uso": float(uso[-1]),
                "tipo": "POST_PURGE_REFILL",
                "detalle": detalle_purge
            })

            log_event(
                f"POST_PURGE_REFILL | host={host} | disk={service} | "
                f"purga=-{detalle_purge['purga']:.2f}% | "
                f"refill=+{detalle_purge['refill']:.2f}% | "
                f"pendiente={detalle_purge['pendiente']:.4f} | "
                f"horas={detalle_purge['horas']}"
            )

            continue

        # ------------------------------
        # VOLATILIDAD ANORMAL
        # ------------------------------
        volatilidad = detectar_volatilidad_anormal(timestamps, uso)

        if volatilidad:
            alertas.append({
                "servidor": host,
                "disco": service,
                "uso": volatilidad["max"],
                "tipo": "VOLATILIDAD_ANORMAL",
                "detalle": volatilidad
            })

            log_event(
                f"VOLATILIDAD | host={host} | disk={service} | "
                f"delta={volatilidad['delta']:.2f}% | "
                f"min={volatilidad['min']:.2f}% | "
                f"max={volatilidad['max']:.2f}% | "
                f"desde={volatilidad['inicio']} hasta={volatilidad['fin']}"
            )

            continue



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

    #regla
    #if alerta.get("tipo") == "RAMP_UP":
    #    print("  ALERTA: CRECIMIENTO ACELERADO (RAMP_UP)")
    #    print(f"  Uso mínimo: {alerta['detalle']['min']:.2f}%")
    #    print(f"  Uso máximo: {alerta['detalle']['max']:.2f}%")
    #    print(f"  Crecimiento total: +{alerta['detalle']['delta']:.2f}%")
    #    print(
    #        f"  Período: {alerta['detalle']['inicio']} → "
    #        f"{alerta['detalle']['fin']}\n"
    #    )
    #    continue

    if alerta.get("tipo") == "STEP_UP":
        print("  ALERTA: CAMBIO BRUSCO DE USO")
        print(f"  Uso actual: {alerta['uso']:.2f}%")
        print(
            f"  Salto detectado: +{alerta['detalle']['salto']:.2f}% "
            f"entre {alerta['detalle']['inicio']} y {alerta['detalle']['fin']}"
        )

        # agregado: tiempo estimado
        if alerta.get("horas") is None:
            print("  Tiempo estimado: No aplica\n")
        else:
            fecha = datetime.datetime.now() + datetime.timedelta(hours=alerta["horas"])
            print(f"  Se llenaría aprox: {fecha.strftime('%Y-%m-%d %H:%M')}\n")

        continue

    if alerta.get("tipo") == "POST_PURGE_REFILL":
        print("  ALERTA: RIESGO POST-PURGA CON REFILL")
        for k, v in alerta["detalle"].items():
            print(f"  {k}: {v}")
        print()
        continue

    if alerta.get("tipo") == "VOLATILIDAD_ANORMAL":
        print("  ALERTA: VOLATILIDAD ANORMAL DE USO")
        print(f"  Uso mínimo: {alerta['detalle']['min']:.2f}%")
        print(f"  Uso máximo: {alerta['detalle']['max']:.2f}%")
        print(f"  Delta: +{alerta['detalle']['delta']:.2f}%")
        print(
            f"  Período: {alerta['detalle']['inicio']} → "
            f"{alerta['detalle']['fin']}\n"
        )
        continue

    print("  ALERTA: ACELERACIÓN DE TENDENCIA")
    print(f"  Uso actual: {alerta['uso']:.2f}%")
    print(
        f"  Mínimo previo: {alerta['min_previo']:.2f}% → "
        f"  Mínimo reciente: {alerta['min_reciente']:.2f}%"
    )
    print(f"  Pendiente previa: {alerta['pendiente_previa']:.4f}")
    print(f"  Pendiente reciente: {alerta['pendiente_reciente']:.4f}")

    if alerta["horas"] is None:
        print("  Tiempo estimado: No aplica\n")
    else:
        fecha = datetime.datetime.now() + datetime.timedelta(hours=alerta["horas"])
        print(f"  Se llenaría aprox: {fecha.strftime('%Y-%m-%d %H:%M')}\n")
