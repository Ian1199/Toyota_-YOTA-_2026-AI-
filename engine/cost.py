"""5 年持有成本（SPEC.md §7.3）。"""
from . import constants as C


def cost_5yr(annual_km=None, gas_km_per_l=None, gas_price_per_l=None,
              home_elec_price=None, home_charging='wallbox', years=5, efficiency_km_per_kwh=None):
    """efficiency_km_per_kwh：換車款時覆寫用（目前 demo 只有 bZ4X，預設讀 constants）。"""
    annual_km = annual_km or C.ANNUAL_KM_FOR_5YR_COST
    gas_km_per_l = gas_km_per_l or C.GAS_KM_PER_L_DEFAULT
    gas_price_per_l = gas_price_per_l or C.GAS_PRICE_PER_L_DEFAULT
    home_elec_price = home_elec_price if home_elec_price is not None else C.HOME_ELEC_PRICE_PER_KWH_DEFAULT
    efficiency_km_per_kwh = efficiency_km_per_kwh or C.ACTUAL_EFFICIENCY_KM_PER_KWH

    gas_energy_cost = annual_km / gas_km_per_l * gas_price_per_l * years

    annual_kwh = annual_km / efficiency_km_per_kwh
    if home_charging == 'none':
        home_ratio, dc_ratio = 0.0, 1.0
    else:
        home_ratio, dc_ratio = 0.85, 0.15
    ev_energy_cost = annual_kwh * (home_ratio * home_elec_price + dc_ratio * C.DC_PUBLIC_PRICE_PER_KWH) * years

    return {
        'years': years,
        'annual_km': annual_km,
        'gas_energy_cost': round(gas_energy_cost),
        'ev_energy_cost': round(ev_energy_cost),
        'maintenance_note': '依和泰實際資料填入（此處暫留空白，demo 不假裝有這筆數字）',
        'save_energy_only': round(gas_energy_cost - ev_energy_cost),
    }
