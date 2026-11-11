import math
from pathlib import Path
import matplotlib.pyplot as plt
from fmpy import read_model_description, extract
from fmpy.fmi2 import FMU2Slave

root = Path(__file__).resolve().parent.parent
md = read_model_description(str(root / "modelica" / "Kuehlraum.fmu"))
unzipdir = extract(str(root / "modelica" / "Kuehlraum.fmu"))
vr = {v.name: v.valueReference for v in md.modelVariables}

K, DT = 273.15, 30.0
N_DAYS = 3
T_STOP = N_DAYS * 24 * 3600.0
DAY = int(24 * 3600 / DT)          # Schritte pro Tag
EVAL = (N_DAYS - 1) * DAY          # Auswertung: letzter Tag

def T_amb_profile(t_s):
    return K + 18 + 7 * math.sin(2 * math.pi * (t_s / 3600 - 9) / 24)

def price(t_s, s):
    """Illustrativer Tarif: Mittel 0,30 EUR/kWh, Spreizung s."""
    h = (t_s / 3600) % 24
    return 0.30 + s if 17 <= h < 21 else 0.30 if 6 <= h < 17 else 0.30 - s

def band_baseline(h): return K + 4, K + 6
def band_wide(h):     return K + 3, K + 7
def band_price(h):
    if h < 6 or h >= 21: return K + 2, K + 5     # Niedrigpreis: vorkühlen
    if 17 <= h < 21:     return K + 5, K + 8     # Hochpreis: auslaufen lassen
    if 15 <= h < 17:     return K + 2, K + 5     # vor Hochpreis: vorkühlen
    return K + 3, K + 7

STRATEGIES = {"A Baseline 4-6 °C": band_baseline,
              "B Breites Band 3-7 °C": band_wide,
              "C Tarifgeführt": band_price}

def run(band_fn, C=5e5, s=0.10):
    fmu = FMU2Slave(guid=md.guid, unzipDirectory=unzipdir,
                    modelIdentifier=md.coSimulation.modelIdentifier)
    fmu.instantiate()
    fmu.setupExperiment(startTime=0.0, stopTime=T_STOP)
    fmu.setReal([vr["C"]], [C])                       # Parameter vor Init
    fmu.enterInitializationMode()
    try:                                              # Start im Sollband
        fmu.setReal([vr["T_raum"]], [K + 5.0])
    except Exception:
        pass
    fmu.setReal([vr["n"], vr["T_amb"]], [0.0, T_amb_profile(0.0)])
    fmu.exitInitializationMode()

    T_now = fmu.getReal([vr["T_raum_out"]])[0]
    r = {"t": [], "T": [], "P": [], "n": [], "cop": []}
    n, time = 0.0, 0.0
    while time < T_STOP:
        lo, hi = band_fn((time / 3600) % 24)
        if T_now > hi:   n = 1.0
        elif T_now < lo: n = 0.0
        fmu.setReal([vr["n"], vr["T_amb"]], [n, T_amb_profile(time)])
        fmu.doStep(time, DT)
        T_now, p_el, c = fmu.getReal([vr["T_raum_out"], vr["P_el"], vr["COP"]])
        r["t"].append(time / 3600); r["T"].append(T_now - K)
        r["P"].append(p_el); r["n"].append(n); r["cop"].append(c)
        time += DT
    fmu.terminate(); fmu.freeInstance()

    P, T, nl = r["P"][EVAL:], r["T"][EVAL:], r["n"][EVAL:]
    r["kwh"] = sum(P) * DT / 3.6e6
    r["eur"] = sum(p * DT / 3.6e6 * price((EVAL + i) * DT, s)
                   for i, p in enumerate(P))
    r["sw"] = sum(1 for a, b in zip(nl, nl[1:]) if a != b)
    r["Tmin"], r["Tmax"] = min(T), max(T)
    r["drift"] = T[-1] - T[0]                         # K über den Tag
    cops = [c for p, c in zip(P, r["cop"][EVAL:]) if p > 0]
    cop_m = sum(cops) / len(cops)
    extra_kwh = C * r["drift"] / 3.6e6 / cop_m        # Speicherkorrektur
    r["kwh_c"] = r["kwh"] + extra_kwh
    r["eur_c"] = r["eur"] + extra_kwh * r["eur"] / r["kwh"]
    return r

# ---------- Basisfall: C = 5e5, Spreizung 0,10 ----------
base = {n: run(f) for n, f in STRATEGIES.items()}
A, B = base["A Baseline 4-6 °C"], base["B Breites Band 3-7 °C"]
print("\n=== Basisfall (Tag 3, C=5e5 J/K, Spreizung 0,10) ===")
print(f"{'Strategie':24}{'kWh':>6}{'EUR':>7}{'EUR korr.':>10}{'Δ vs B':>8}"
      f"{'Schalt.':>8}{'Tmin':>6}{'Tmax':>6}{'Drift K':>8}")
for name, r in base.items():
    print(f"{name:24}{r['kwh']:6.2f}{r['eur']:7.3f}{r['eur_c']:10.3f}"
          f"{(r['eur_c']/B['eur_c']-1)*100:+7.1f}%{r['sw']:8d}"
          f"{r['Tmin']:6.1f}{r['Tmax']:6.1f}{r['drift']:8.2f}")

# ---------- Parameterstudie ----------
CS = [5e5, 2e6, 1e7]
SPREADS = [0.05, 0.10, 0.20]
print("\n=== Studie: Kosten C (tarifgeführt) gegen B (breites Band), "
      "driftkorrigiert ===")
print(f"{'C [J/K]':>9}{'Spreizung':>10}{'EUR B':>8}{'EUR C':>8}{'Δ':>8}"
      f"{'Drift C [K]':>12}")
study = {}
for C in CS:
    for s in SPREADS:
        rb, rc = run(band_wide, C, s), run(band_price, C, s)
        d = (rc["eur_c"] / rb["eur_c"] - 1) * 100
        study[(C, s)] = d
        print(f"{C:9.0e}{s:10.2f}{rb['eur_c']:8.3f}{rc['eur_c']:8.3f}"
              f"{d:+7.1f}%{rc['drift']:12.2f}")

# ---------- Plots ----------
out = root / "results"; out.mkdir(exist_ok=True)
fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
for name, r in base.items():
    ax[0].plot(r["t"][EVAL:], r["T"][EVAL:], label=name, lw=1.2)
    ax[1].plot(r["t"][EVAL:], r["P"][EVAL:], label=name, lw=0.8)
ax[0].set_ylabel("T_raum [°C]"); ax[0].legend(fontsize=8)
ax[1].set_ylabel("P_el [W]"); ax[1].set_xlabel("Zeit [h]")
for a in ax: a.grid(True)
fig.suptitle("Kühlraum, Tag 3 (eingeschwungen): Regelstrategien")
fig.tight_layout(); fig.savefig(out / "comparison_day3.png", dpi=150)

fig2, a2 = plt.subplots(figsize=(7, 4))
for s in SPREADS:
    a2.plot([str(f"{C:.0e}") for C in CS], [study[(C, s)] for C in CS],
            marker="o", label=f"Spreizung {s:.2f} EUR/kWh")
a2.axhline(0, c="gray", ls="--")
a2.set_xlabel("Thermische Masse C [J/K]")
a2.set_ylabel("Kostenänderung C vs. B [%]")
a2.grid(True); a2.legend(); fig2.tight_layout()
fig2.savefig(out / "savings_study.png", dpi=150)
plt.show()