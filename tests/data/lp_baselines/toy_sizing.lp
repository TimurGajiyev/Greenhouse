\* greenhouse_sizing *\
Minimize
OBJ: 0.26 dg_kw_0 + 0.26 dg_kw_1 + 0.26 dg_kw_2 + 0.26 dg_kw_3
 + 1e-06 size_batt_kw + 0.00680599948388 size_batt_kwh
 + 0.00680599948388 size_dg_kw
Subject To
balance_0: - charge_kw_0 - curtail_kw_0 + dg_kw_0 + discharge_kw_0
 + shortfall_kw_0 = 150
balance_1: - charge_kw_1 - curtail_kw_1 + dg_kw_1 + discharge_kw_1
 + shortfall_kw_1 = 150
balance_2: - charge_kw_2 - curtail_kw_2 + dg_kw_2 + discharge_kw_2
 + shortfall_kw_2 = 150
balance_3: - charge_kw_3 - curtail_kw_3 + dg_kw_3 + discharge_kw_3
 + shortfall_kw_3 = 150
charge_cap_0: charge_kw_0 - size_batt_kw <= 0
charge_cap_1: charge_kw_1 - size_batt_kw <= 0
charge_cap_2: charge_kw_2 - size_batt_kw <= 0
charge_cap_3: charge_kw_3 - size_batt_kw <= 0
charge_no_overfill_0: - charge_kw_0 + size_batt_kwh - soc_kwh_3 >= 0
charge_no_overfill_1: - charge_kw_1 + size_batt_kwh - soc_kwh_0 >= 0
charge_no_overfill_2: - charge_kw_2 + size_batt_kwh - soc_kwh_1 >= 0
charge_no_overfill_3: - charge_kw_3 + size_batt_kwh - soc_kwh_2 >= 0
dg_cap_0: dg_kw_0 - size_dg_kw <= 0
dg_cap_1: dg_kw_1 - size_dg_kw <= 0
dg_cap_2: dg_kw_2 - size_dg_kw <= 0
dg_cap_3: dg_kw_3 - size_dg_kw <= 0
discharge_cap_0: discharge_kw_0 - size_batt_kw <= 0
discharge_cap_1: discharge_kw_1 - size_batt_kw <= 0
discharge_cap_2: discharge_kw_2 - size_batt_kw <= 0
discharge_cap_3: discharge_kw_3 - size_batt_kw <= 0
pv_split_0: charge_kw_0 + curtail_kw_0 <= 0
pv_split_1: charge_kw_1 + curtail_kw_1 <= 0
pv_split_2: charge_kw_2 + curtail_kw_2 <= 0
pv_split_3: charge_kw_3 + curtail_kw_3 <= 0
reliability_hard: shortfall_kw_0 + shortfall_kw_1 + shortfall_kw_2
 + shortfall_kw_3 = 0
soc_dyn_0: - charge_kw_0 + discharge_kw_0 + soc_kwh_0 - soc_kwh_3 = 0
soc_dyn_1: - charge_kw_1 + discharge_kw_1 - soc_kwh_0 + soc_kwh_1 = 0
soc_dyn_2: - charge_kw_2 + discharge_kw_2 - soc_kwh_1 + soc_kwh_2 = 0
soc_dyn_3: - charge_kw_3 + discharge_kw_3 - soc_kwh_2 + soc_kwh_3 = 0
soc_max_0: - size_batt_kwh + soc_kwh_0 <= 0
soc_max_1: - size_batt_kwh + soc_kwh_1 <= 0
soc_max_2: - size_batt_kwh + soc_kwh_2 <= 0
soc_max_3: - size_batt_kwh + soc_kwh_3 <= 0
soc_min_0: soc_kwh_0 >= 0
soc_min_1: soc_kwh_1 >= 0
soc_min_2: soc_kwh_2 >= 0
soc_min_3: soc_kwh_3 >= 0
Bounds
 size_batt_kw = 200
 size_batt_kwh = 100
 size_dg_kw <= 1000
End
