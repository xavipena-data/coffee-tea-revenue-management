# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "21b76e1d-eb41-4713-ac68-03b2bf7901ca",
# META       "default_lakehouse_name": "lh_rm",
# META       "default_lakehouse_workspace_id": "3089dcb5-019c-432a-b624-0c1396348d46",
# META       "known_lakehouses": [
# META         {
# META           "id": "21b76e1d-eb41-4713-ac68-03b2bf7901ca"
# META         }
# META       ]
# META     }
# META   }
# META }

# CELL ********************

# ---------------------------------------------------------------
# Inspect the raw files in Files/raw before writing any cleaning code.
# - Lists the files in each raw folder.
# - Prints the first lines of the ECB CSV to see its real layout
#   (separator, column names, date format, decimal mark).
# ---------------------------------------------------------------
import os

RAW = "/lakehouse/default/Files/raw"
for folder in ["pink_sheet", "ecb"]:
    print(folder, os.listdir(f"{RAW}/{folder}"))

ecb_file = os.listdir(f"{RAW}/ecb")[0]
with open(f"{RAW}/ecb/{ecb_file}", encoding="utf-8-sig") as f:
    for _ in range(5):
        print(f.readline().rstrip())


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# ECB monthly USD/EUR: read the raw CSV and clean it (silver layer).
# - The raw file has 3 columns: DATE (month end), TIME PERIOD, rate.
# - We keep the value exactly as published (USD per 1 EUR); no changes.
# - month_start = first day of the month, to join with monthly commodity prices.
# ---------------------------------------------------------------
import os
import pandas as pd

RAW = "/lakehouse/default/Files/raw"
ecb_file = os.listdir(f"{RAW}/ecb")[0]
ecb_raw = pd.read_csv(f"{RAW}/ecb/{ecb_file}", encoding="utf-8-sig")

ecb = pd.DataFrame({
    "period_end": pd.to_datetime(ecb_raw.iloc[:, 0]),
    "usd_per_eur": ecb_raw.iloc[:, 2].astype(float),
})
ecb["month_start"] = ecb["period_end"].dt.to_period("M").dt.to_timestamp()
ecb = ecb[["month_start", "usd_per_eur"]]

print(len(ecb), ecb["month_start"].min().date(), ecb["month_start"].max().date())
print("nulls:", ecb["usd_per_eur"].isna().sum(), "| months unique:", ecb["month_start"].is_unique)
ecb.tail(3)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# World Bank Pink Sheet (monthly prices): read the raw Excel and clean it.
# Layout of the sheet "Monthly Prices": header names on Excel row 5, units on
# row 6, data from row 7, first column = period like "1960M01".
# Steps: skip the units row -> keep only the 7 series we need -> parse the
# period into the first day of the month -> make the prices numeric.
# All 7 series are in USD per kg, as published (nothing converted here).
# ---------------------------------------------------------------
pink_file = os.listdir(f"{RAW}/pink_sheet")[0]
pink_raw = pd.read_excel(f"{RAW}/pink_sheet/{pink_file}", sheet_name="Monthly Prices", header=4)
pink_raw = pink_raw.iloc[1:]          # drop the units row

series = {
    "Coffee, Arabica":     "coffee_arabica_usd_kg",
    "Coffee, Robusta":     "coffee_robusta_usd_kg",
    "Tea, avg 3 auctions": "tea_avg_usd_kg",
    "Cocoa":               "cocoa_usd_kg",
    "Sugar, EU":           "sugar_eu_usd_kg",
    "Sugar, US":           "sugar_us_usd_kg",
    "Sugar, world":        "sugar_world_usd_kg",
}

period_col = pink_raw.columns[0]
pink = pink_raw[[period_col] + list(series)].rename(columns={period_col: "period", **series})
pink = pink[pink["period"].astype(str).str.match(r"^\d{4}M\d{2}$")]     # keep only real data rows

pink["month_start"] = pd.to_datetime(pink["period"].str.replace("M", "-"), format="%Y-%m")
for col in series.values():
    pink[col] = pink[col].astype(float)

pink = pink[["month_start"] + list(series.values())].reset_index(drop=True)

print(len(pink), pink["month_start"].min().date(), pink["month_start"].max().date())
print("nulls:", int(pink.isna().sum().sum()))
pink[pink["month_start"].isin(pd.to_datetime(["2023-01-01", "2025-01-01"]))]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Write the two cleaned real series to the Lakehouse as Delta tables (silver layer).
# month_start is converted to a pure date (no time part) so Delta stores a DATE.
# Values stay exactly as published: USD per EUR (ECB) and USD per kg (World Bank).
# "overwrite" lets us re-run the cell safely; the final spark.table() calls
# read the tables back from the Lakehouse to confirm what was really saved.
# ---------------------------------------------------------------
silver_tables = {
    "slv_ecb_usd_eur": ecb,
    "slv_pink_sheet_monthly": pink,
}

for name, pdf in silver_tables.items():
    pdf = pdf.copy()
    pdf["month_start"] = pdf["month_start"].dt.date
    (spark.createDataFrame(pdf)
          .write.mode("overwrite")
          .option("overwriteSchema", "true")
          .format("delta")
          .saveAsTable(name))

for name in silver_tables:
    print(name, spark.table(name).count())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
