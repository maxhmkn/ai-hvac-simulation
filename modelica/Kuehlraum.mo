model Kuehlraum
  Modelica.Blocks.Interfaces.RealInput n(start = 0.4) "Relative Verdichterdrehzahl 0..1";
  Modelica.Blocks.Interfaces.RealInput T_amb(start = 303.15) "Außentemperatur [K]";
  Modelica.Blocks.Interfaces.RealOutput T_raum_out "Raumtemperatur [K]";
  Modelica.Blocks.Interfaces.RealOutput COP "Leistungszahl [-]";
  Modelica.Blocks.Interfaces.RealOutput P_el "Elektr. Leistung [W]";

  parameter Real C = 5e5 "Therm. Kapazität Raum [J/K]";
  parameter Real UA = 50 "Transmission [W/K]";
  parameter Real Q_last = 500 "Innere Last [W]";
  parameter Real Q0_nom = 3000 "Kälteleistung bei n=1 [W]";
  parameter Real eta_c = 0.45 "Gütegrad vs. Carnot";
  parameter Real dT_ev = 8 "Verdampfer-Grädigkeit [K]";
  parameter Real dT_cd = 10 "Kondensator-Grädigkeit [K]";

  Real T_raum(start = 293.15, fixed = true);
  Real Q0;
  Real T_0;
  Real T_c;
equation
  T_0 = T_raum - dT_ev;
  T_c = T_amb + dT_cd;
  COP = eta_c * T_0 / (T_c - T_0);
  Q0 = max(n, 0) * Q0_nom;
  P_el = Q0 / COP;
  C * der(T_raum) = UA * (T_amb - T_raum) + Q_last - Q0;
  T_raum_out = T_raum;
end Kuehlraum;