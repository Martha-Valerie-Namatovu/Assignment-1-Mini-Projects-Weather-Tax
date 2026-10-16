# OOP with Python, Assignment 2 (Advent 2026)

Two mini-projects, each in its own notebook, with the reusable logic in `src/` and the tests in `tests/`.

| # | Notebook | Package | What it does |
|---|---|---|---|
| 1 | `project1_weather.ipynb` | `src/weather/` | Geocodes a place, fetches a forecast from Open-Meteo, compares it with MET Norway, and shows a table, a chart and a text summary. HTTP calls are made by hand with `urllib` and `requests`, with timeouts, retries, exponential backoff and custom exceptions. |
| 2 | `project2_tax.ipynb` | `src/tax/` | An extensible Uganda tax engine covering PAYE, NSSF, Local Service Tax, VAT and corporate income tax, plus withholding tax, rental income tax and a salary-vs-dividend `TaxPlanner` as extensions. All money is `Decimal`. |

## Repository layout

```
├── project1_weather.ipynb      mini-project 1 (includes the 1,000-1,500-word Part D report)
├── project2_tax.ipynb          mini-project 2 (includes the discussion questions)
├── src/
│   ├── weather/
│   │   ├── http.py             urllib call (Part A) and fetch_json: timeout, raise_for_status, retry + backoff
│   │   ├── errors.py           WeatherError -> WeatherAPIError, LocationNotFoundError, ConfigurationError
│   │   ├── geocoding.py        geocode(), parse_geocoding(), choose_location(), Location
│   │   ├── openmeteo.py        get_forecast(), forecast_to_dataframe()
│   │   ├── metno.py            MET Norway client: User-Agent check, UTC -> local daily aggregation
│   │   ├── weather_codes.py    WMO code -> description (from the Open-Meteo docs)
│   │   └── display.py          summary text, formatted table, chart, source comparison
│   └── tax/
│       ├── money.py            Money value object (Decimal, UGX, half-up rounding, operator overloading)
│       ├── errors.py           TaxError -> InvalidIncomeError, NoScheduleForDateError, UnsupportedContextError
│       ├── context.py          TaxContext and subclasses, Invoice, TaxResult, TaxLine
│       ├── schedules.py        Band, ProgressiveSchedule, date-keyed ScheduleRegistry, rate tables + sources
│       ├── base.py             abstract Tax: calculate(self, ctx: TaxContext) -> TaxResult
│       ├── paye.py · nssf.py · lst.py · vat.py · cit.py
│       ├── payroll.py          PayrollPipeline (LST -> PAYE -> NSSF -> net) and Payslip
│       ├── withholding.py      extension A: WithholdingTax, RentalIncomeTax
│       └── planner.py          extension B: TaxPlanner with Salary/Dividend scenarios
├── tests/
│   ├── test_weather.py         22 offline tests on parsing and retries, using data/samples/*.json
│   ├── test_tax.py             band-edge boundary tests, hypothesis properties, every tax module
│   └── test_money.py           Money behaviour and hypothesis properties
├── data/samples/               saved API responses (Kampala, Springfield, no match, invalid latitude, MET Norway)
└── figures/                    every chart, saved by the notebooks
```

## Setup and running

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest                                 # 80 tests, all offline
jupyter lab                            # open a notebook -> Kernel -> Restart & Run All
```

Start Jupyter **from the repository root**, because the notebooks import from `src/` and read and write `data/` and `figures/`.

**Contact email (mini-project 1).** MET Norway requires real contact details in the User-Agent. Do not type them into the notebook; set an environment variable before starting Jupyter:

```bash
export WEATHER_CONTACT_EMAIL="firstname.lastname@ucu.ac.ug"   # your own university email
```

While it is unset, the configuration cell holds a placeholder. The code refuses to send the placeholder, and the MET Norway section uses the saved sample in `data/samples/metno_kampala.json` instead, saying so in its output. The notebook therefore always runs top to bottom. It also falls back to the saved samples if there is no network.

**Reproducibility.** Mini-project 1 shows live forecasts, so its numbers change from day to day; the tests use the saved samples. Mini-project 2 is deterministic, and hypothesis is configured to derandomize (`tests/conftest.py`). Both notebooks were executed top to bottom without errors, and the committed outputs come from that run (14 October 2026).

## Summary of findings

**Mini-project 1: Weather.**
* `requests` replaces about 10 lines of `urllib` (manual URL encoding, charset decoding, separate exception types) with 3, and makes headers, sessions and error handling simpler. A typical geocoding call took 600-750 ms from Kampala, returning `200 OK`, `application/json; charset=utf-8`.
* Open-Meteo omits the `results` key when nothing matches, and "Kampala" also matches places in Côte d'Ivoire, DR Congo, Zambia and Indonesia. Both cases are handled: a clear `LocationNotFoundError`, and a candidate list with re-prompting.
* MET Norway reports UTC at mixed hourly and 6-hourly resolution. Aggregating it into Kampala-local days without double-counting rain is the non-obvious step. Over six fully covered days, the two sources differed by about 1 °C in daily maximum temperature and about 3.5 mm/day in rain. They agree on the shape of the week, not the exact amounts.
* Part D covers the data flow, licences (CC BY 4.0 data for both; Open-Meteo's free API is non-commercial only; MET Norway requires identification, caching and rate limits), reliability, and privacy under Uganda's Data Protection and Privacy Act 2019.

**Mini-project 2: Tax engine.**
* The brief's PAYE baseline is the **Income Tax (Amendment) Act 2026** schedule, effective 1 July 2026. The engine also keeps the 2012-2026 schedule it replaced and selects by date. Every band edge in the brief is verified (for example 10,000,000 → UGX 2,888,250).
* The amendment saves residents up to a flat **UGX 13,750 per month** (for everyone above UGX 485,000).
* VAT handles standard-rated, zero-rated and exempt supplies, including input-VAT apportionment and refund positions. Corporate tax reports assessed losses instead of taxing them.
* `TaxPlanner`: taking profit as salary is cheaper than as a dividend below roughly **UGX 11.7 million a month**; above that, dividends (a flat 40.5%) win.
* Float is unsafe because of representation errors, non-associative sums and banker's rounding. The notebook shows a reconciliation where per-line VAT ≠ VAT on the total in float but matches exactly with `Money`.

## Rates and data sources

* PAYE 2012-2026: Income Tax Act Cap 340, Third Schedule; URA "PAYE" page, https://ura.go.ug (accessed 14 Oct 2026).
* PAYE 2026/27: Income Tax (Amendment) Act 2026, as reported by AfroTools, https://afrotools.com/fr/blog/uganda-paye-tax-2026-27/ (accessed 14 Oct 2026). The 2026/27 non-resident schedule is **assumed unchanged**, because it was not published in the sources found.
* NSSF: NSSF Act Cap 230. VAT, corporate tax, WHT: PwC Worldwide Tax Summaries, Uganda (reviewed Jan 2026), https://taxsummaries.pwc.com/uganda. Rental tax: URA, https://ura.go.ug/?p=40935. LST: KCCA "Local Service Tax FAQs", https://kcca.go.ug/uDocs/Local_Service_Tax_FAQs.pdf.
* Weather data: Open-Meteo.com (CC BY 4.0), MET Norway (NLOD 2.0 / CC BY 4.0), GeoNames (CC BY 4.0).

These rates are for coursework. Check the gazetted law and URA's current tables before using them on a real payroll.

## AI use declaration

Generative AI was used strictly in an assistive and investigative capacity during this assignment across the following areas:

* **Architecture & Scaffolding:** Brainstorming the OOP class hierarchies (specifically structuring `TaxContext`, `TaxSchedule`, and `Money` value object patterns), and establishing the initial retry/exponential backoff wrapper for `fetch_json`.
* **Testing & Hypothesis Properties:** Brainstorming edge cases and property definitions for `hypothesis` testing in `test_tax.py` and `test_money.py` (e.g., non-associative float addition vs. `Decimal` invariance).
* **Boilerplate & Syntax:** Assisting with repetitive data structure mappings (such as mapping WMO weather interpretation codes) and drafting standard docstrings.
* **Error Diagnosis:** Interrogating stack traces during test harness configuration, timezone aggregation edge cases, and mocked HTTP responses.

**Authorship Affirmation:** All core financial algorithms, domain logic (Ugandan tax schedules, VAT apportionment, and PAYE band calculations), MET Norway UTC-to-local daily aggregation algorithms, and final written report analyses (Part D) were designed, implemented, verified, and reconciled by the author. I retain full ownership of the codebase and can defend every architectural decision.