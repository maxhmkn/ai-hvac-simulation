import math
from pathlib import Path
import matplotlib.pyplot as plt
from fmpy import read_model_description, extract
from fmpy.fmi2 import FMU2Slave

root = Path(__file__).resolve().parent.parent
fmu_path = str(root / "modelica" / "Kuehlraum.fmu")

md = read_model_description(fmu_path)
unzipdir = extract(fmu_path)
vr = {v.name: v.valueReference for v in md.modelVariables}

# --- Szenario ---
t_stop = 24 * 3600.0
dt = 30.0
T_set, hyst = 278.15, 1.0        # 5 °C +-1 K

def T_amb_profile(t_s):
    """Tagesgang: Mittel 18 °C, Amplitude 7 K, Maximum 15 Uhr."""
    return 273.15 + 18 + 7 * math.sin(2 * math.pi * (t_s / 3600 - 9) / 24)

def price(t_s):
    """Beispiel-Tarif [EUR/kWh] (illustrativ, keine echten Marktdaten)."""
    h = (t_s / 3600) % 24
    if 17 <= h < 21:
        return 0.40
    if 6 <= h < 17:
        return 0.30
    return 0.20

fmu = FMU2Slave(guid=md.guid, unzipDirectory=unzipdir,
                modelIdentifier=md.coSimulation.modelIdentifier)
fmu.instantiate()
fmu.setupExperiment(startTime=0.0, stopTime=t_stop)
fmu.enterInitializationMode()
fmu.setReal([vr["n"], vr["T_amb"]], [0.0, T_amb_profile(0.0)])
fmu.exitInitializationMode()

t, T, Ta, n_log, P, cop, pr = [], [], [], [], [], [], []
n, time, T_now = 0.0, 0.0, 293.15

while time < t_stop:
    # --- Zweipunktregler: hier kommt später MPC / RL hin ---
    if T_now > T_set + hyst:
        n = 1.0
    elif T_now < T_set - hyst:
        n = 0.0

    fmu.setReal([vr["n"], vr["T_amb"]], [n, T_amb_profile(time)])
    fmu.doStep(time, dt)
    T_now, p_el, c = fmu.getReal([vr["T_raum_out"], vr["P_el"], vr["COP"]])

    t.append(time / 3600)
    T.append(T_now - 273.15)
    Ta.append(T_amb_profile(time) - 273.15)
    n_log.append(n)
    P.append(p_el)
    cop.append(c)
    pr.append(price(time))
    time += dt

fmu.terminate()
fmu.freeInstance()

energy_kwh = sum(p * dt for p in P) / 3.6e6
cost = sum(p * dt / 3.6e6 * pc for p, pc in zip(P, pr))
switches = sum(1 for a, b in zip(n_log, n_log[1:]) if a != b)
print(f"Energie:          {energy_kwh:.2f} kWh")
print(f"Kosten:           {cost:.2f} EUR")
print(f"Schaltvorgänge:   {switches}")
print(f"T_raum min/max (nach Abkühlung): "
      f"{min(T[200:]):.2f} / {max(T[200:]):.2f} °C")

fig, ax = plt.subplots(4, 1, figsize=(10, 10), sharex=True)
ax[0].plot(t, T, label="T_raum")
ax[0].plot(t, Ta, label="T_außen", alpha=0.6)
ax[0].axhline(T_set - 273.15, ls="--", c="gray")
ax[0].set_ylabel("Temperatur [°C]"); ax[0].legend()
ax[1].step(t, n_log, where="post"); ax[1].set_ylabel("n [-]")
ax[2].plot(t, P, label="P_el")
ax[2].set_ylabel("P_el [W]")
ax3 = ax[2].twinx(); ax3.step(t, pr, c="tab:orange", where="post")
ax3.set_ylabel("Preis [EUR/kWh]")
ax[3].plot(t, cop); ax[3].set_ylabel("COP [-]"); ax[3].set_xlabel("Zeit [h]")
for a in ax: a.grid(True)
fig.suptitle(f"Kühlraum 24 h, Zweipunktregler: {energy_kwh:.1f} kWh, {cost:.2f} EUR")
fig.tight_layout()
out = root / "results"; out.mkdir(exist_ok=True)
fig.savefig(out / "baseline_24h.png", dpi=150)
plt.show()