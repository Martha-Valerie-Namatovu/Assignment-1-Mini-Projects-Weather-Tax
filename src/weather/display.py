"""Presentation helpers: text summary, chart and source comparison (Part B.4, Part C)."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from .geocoding import Location


def summarise(df: pd.DataFrame, location: Location, source: str = "Open-Meteo") -> str:
    """Write a short plain-English summary of a daily forecast table."""
    if df.empty:
        return f"No forecast data for {location.label}."
    wettest = df["Precipitation (mm)"].idxmax()
    hottest = df["Max temp (°C)"].idxmax()
    rainy_days = int((df["Precipitation (mm)"] >= 1.0).sum())
    total = df["Precipitation (mm)"].sum()
    return (
        f"{len(df)}-day forecast for {location.label} "
        f"({df.index[0]:%a %d %b} to {df.index[-1]:%a %d %b}).\n"
        f"Temperatures range from {df['Min temp (°C)'].min():.0f} °C to {df['Max temp (°C)'].max():.0f} °C; "
        f"the warmest day is {hottest:%A} ({df.loc[hottest, 'Max temp (°C)']:.1f} °C).\n"
        f"Rain of 1 mm or more is expected on {rainy_days} of {len(df)} days, {total:.0f} mm in total; "
        f"the wettest day is {wettest:%A} ({df.loc[wettest, 'Precipitation (mm)']:.1f} mm, "
        f"{df.loc[wettest, 'Conditions'].lower() if 'Conditions' in df else 'n/a'}).\n"
        f"Strongest wind: {df['Max wind (m/s)'].max():.1f} m/s.\n"
        f"Source: {source} (data licensed CC BY 4.0)."
    )


def format_table(df: pd.DataFrame):
    """Return a styled table (rendered as HTML in Jupyter) with one decimal place."""
    shown = df.copy()
    shown.index = shown.index.strftime("%a %d %b")
    numeric = shown.select_dtypes("number").columns
    return shown.style.format({c: "{:.1f}" for c in numeric}, na_rep="–")


def plot_forecast(df: pd.DataFrame, location: Location, source: str = "Open-Meteo",
                  ax: plt.Axes | None = None) -> plt.Figure:
    """Temperature range as a shaded band with min/max lines, precipitation as bars on a second axis."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 4.5))
    else:
        fig = ax.figure
    rain_ax = ax.twinx()
    rain_ax.bar(df.index, df["Precipitation (mm)"], width=0.6, color="tab:blue", alpha=0.35,
                label="Precipitation (mm)")
    rain_ax.set_ylabel("Precipitation (mm/day)")
    # Bars use the bottom ~40% of the panel and temperatures the top ~60%, so neither hides the other.
    rain_ax.set_ylim(0, max(10.0, df["Precipitation (mm)"].max()) * 2.5)
    t_lo, t_hi = df["Min temp (°C)"].min(), df["Max temp (°C)"].max()
    ax.set_ylim(t_lo - (t_hi - t_lo) * 0.9, t_hi + 1.0)
    ax.fill_between(df.index, df["Min temp (°C)"], df["Max temp (°C)"], color="tab:orange", alpha=0.12,
                    label="Daily temperature range")
    ax.plot(df.index, df["Max temp (°C)"], "o-", color="tab:red", label="Max temp (°C)")
    ax.plot(df.index, df["Min temp (°C)"], "o-", color="tab:orange", label="Min temp (°C)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_xlabel("Date (local time)")
    ax.set_zorder(rain_ax.get_zorder() + 1)
    ax.patch.set_visible(False)
    ax.set_xticks(df.index)
    ax.set_xticklabels([d.strftime("%a\n%d %b") for d in df.index])
    handles = ax.get_legend_handles_labels()[0] + rain_ax.get_legend_handles_labels()[0]
    ax.legend(handles, [h.get_label() for h in handles], loc="upper center", bbox_to_anchor=(0.5, -0.2),
              ncol=4, fontsize=9, frameon=False)
    ax.set_title(f"Daily forecast for {location.label}\nSource: {source}, CC BY 4.0")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def compare_sources(primary: pd.DataFrame, secondary: pd.DataFrame, min_hours: float = 24.0) -> pd.DataFrame:
    """Side-by-side differences (secondary − primary) on days both sources cover fully."""
    full = secondary[secondary["Hours covered"] >= min_hours] if "Hours covered" in secondary else secondary
    days = primary.index.intersection(full.index)
    cols = ["Max temp (°C)", "Min temp (°C)", "Precipitation (mm)", "Max wind (m/s)"]
    out = pd.concat({"Open-Meteo": primary.loc[days, cols], "MET Norway": full.loc[days, cols]}, axis=1)
    for c in cols:
        out[("Difference", c)] = out[("MET Norway", c)] - out[("Open-Meteo", c)]
    return out
