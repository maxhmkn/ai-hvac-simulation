from pathlib import Path
import matplotlib.pyplot as plt
from fmpy import read_model_description, extract
from fmpy.fmi2 import FMU2Slave

# --- Pfade (relativ zum Skript, funktioniert auf jedem Rechner) ---
root = Path(__file__).resolve().parent.parent
fmu_path = str(root / "modelica" / "Kuehlraum.fmu")

md = read_model_description(fmu_path)
unzipdir = extract(fmu_path)
vr = {v.name: v.valueReference for v in md.modelVariables}

# --- Simulationsparameter ---
t_stop = 6 * 3600.0      # 6 h
dt = 30.0                # Kommunikationsschritt [s]
T_set = 278.15           # Sollwert 5 °C
hyst = 1.0               # Hysterese +-1 K

fmu = FMU2Slave(guid=md.guid,
                unzipDirectory=unzipdir,
                modelIdentifier=md.coSimulation.modelIdentifier)
fmu.instantiate()
fmu.setupExperiment(startTime=0.0, stopTime=t_stop)
fmu.enterInitializationMode()
fmu.exitInitializationMode()

t, T, n_log, P, cop = [], [], [], [], []
n = 0.0
time = 0.0
T_now = 293.15

while time < t_stop:
    # --- Zweipunktregler: hier kommt später MPC / RL hin ---
    if T_now > T_set + hyst:
        n = 1.0
    elif T_now < T_set - hyst:
        n = 0.0

    fmu.setReal([vr["n"]], [n])
    fmu.doStep(time, dt)
    T_now, p_el, c = fmu.getReal([vr["T_raum_out"], vr["P_el"], vr["COP"]])

    time += dt
    t.append(time / 3600)
    T.append(T_now - 273.15)
    n_log.append(n)
    P.append(p_el)
    cop.append(c)

fmu.terminate()
fmu.freeInstance()

energy_kwh = sum(p * dt for p in P) / 3.6e6
print(f"Energieverbrauch Verdichter: {energy_kwh:.2f} kWh")
print(f"Mittlere Raumtemperatur (letzte 2 h): {sum(T[-240:])/240:.2f} °C")

# --- Plot ---
fig, ax = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
ax[0].plot(t, T); ax[0].axhline(T_set - 273.15, ls="--", c="gray")
ax[0].set_ylabel("T_raum [°C]")
ax[1].step(t, n_log, where="post"); ax[1].set_ylabel("Drehzahl n [-]")
ax[2].plot(t, P); ax[2].set_ylabel("P_el [W]"); ax[2].set_xlabel("Zeit [h]")
for a in ax: a.grid(True)
fig.suptitle("Kühlraum: Zweipunktregler (Baseline)")
fig.tight_layout()
out = root / "results"; out.mkdir(exist_ok=True)
fig.savefig(out / "baseline_two_point.png", dpi=150)
plt.show()