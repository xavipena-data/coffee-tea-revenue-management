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
# Setup: libraries, global parameters and random generator.
# - SEED makes every run produce exactly the same data.
# - START_DATE / N_WEEKS define the simulation window (weekly grain).
# - rng is the single random generator used by the whole notebook.
# ---------------------------------------------------------------

import numpy as np
import pandas as pd

SEED = 42
START_DATE = "2023-01-02"   # first Monday of 2023
N_WEEKS = 156               # 3 years, weekly grain (last week starts 2025-12-22)

rng = np.random.default_rng(SEED)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# dim_date: one row per week (the grain of the sales facts).
# - week_key is the integer key that fact tables will point to.
# - Each week belongs to the month of its Monday (documented rule).
# ---------------------------------------------------------------
week_start = pd.date_range(start=START_DATE, periods=N_WEEKS, freq="W-MON")

dim_date = pd.DataFrame({"week_start": week_start})
dim_date["week_key"] = np.arange(1, N_WEEKS + 1)
dim_date["week_end"] = dim_date["week_start"] + pd.Timedelta(days=6)
dim_date["year"] = dim_date["week_start"].dt.year
dim_date["quarter"] = dim_date["week_start"].dt.quarter
dim_date["month"] = dim_date["week_start"].dt.month
dim_date["month_name"] = dim_date["week_start"].dt.strftime("%b")
dim_date["year_month"] = dim_date["week_start"].dt.strftime("%Y-%m")

print(len(dim_date))
dim_date.head(3)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# dim_channel: the four sales channels (tiny, hand-written table).
# Kept as its own dimension so we can slice by channel in the report
# and, later, apply row-level security by channel.
# ---------------------------------------------------------------
dim_channel = pd.DataFrame({
    "channel_key": [1, 2, 3, 4],
    "channel": ["Horeca", "Retail", "Office & Vending", "Online"],
})

dim_channel

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Brand master: every brand defined once, with its ownership type.
# If a brand name ever needs to change, this is the only place to edit
# (the SKU lists below refer to these names).
# ---------------------------------------------------------------
BRANDS = {
    "Mas Albera":  "Own",
    "Brewlet":     "Distributed",   # coffee capsules
    "Casa Fulla":  "Distributed",   # tea
    "Tetera Alta": "Distributed",   # tea
    "Dolçor":      "Distributed",   # sugar and sweeteners
    "Cacau Nord":  "Distributed",   # cocoa and chocolate
}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Coffee SKUs: 14 own-brand (Mas Albera) + 6 distributed capsules (Brewlet).
# Each tuple is (brand, product_name, kg_per_unit).
# kg_per_unit is the approximate pack weight, used later for raw-material cost.
# Keys and SKU codes are assigned later, when all categories are merged.
# ---------------------------------------------------------------
coffee_skus = [
    # Own brand
    ("Mas Albera", "Espresso Blend 1 kg Beans",      1.00),
    ("Mas Albera", "Espresso Blend 250 g Beans",     0.25),
    ("Mas Albera", "Espresso Blend 250 g Ground",    0.25),
    ("Mas Albera", "Espresso Blend 5 kg Beans",      5.00),
    ("Mas Albera", "House Blend 1 kg Beans",         1.00),
    ("Mas Albera", "House Blend 250 g Ground",       0.25),
    ("Mas Albera", "Robusta Intenso 1 kg Beans",     1.00),
    ("Mas Albera", "Decaf Blend 250 g Beans",        0.25),
    ("Mas Albera", "Organic Blend 250 g Beans",      0.25),
    ("Mas Albera", "Cold Brew Blend 250 g Ground",   0.25),
    ("Mas Albera", "Single Origin Ethiopia 250 g",   0.25),
    ("Mas Albera", "Single Origin Colombia 250 g",   0.25),
    ("Mas Albera", "Single Origin Brazil 250 g",     0.25),
    ("Mas Albera", "Horeca Espresso 1 kg Ground",    1.00),
    # Distributed capsules
    ("Brewlet", "Espresso Intenso 10 Capsules",      0.06),
    ("Brewlet", "Espresso Lungo 10 Capsules",        0.06),
    ("Brewlet", "Ristretto 10 Capsules",             0.06),
    ("Brewlet", "Decaf 10 Capsules",                 0.06),
    ("Brewlet", "Vanilla 10 Capsules",               0.06),
    ("Brewlet", "Colombia 10 Capsules",              0.06),
]

# Quick check: how many SKUs per brand?
pd.DataFrame(coffee_skus, columns=["brand", "product_name", "kg_per_unit"]).groupby("brand").size()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Tea SKUs: 4 own-brand (Mas Albera) + 8 distributed (Casa Fulla, Tetera Alta).
# Same layout as coffee: (brand, product_name, kg_per_unit).
# The assert at the end makes the cell fail if a brand name is misspelled
# (i.e. not found in BRANDS), instead of silently creating a wrong brand.
# ---------------------------------------------------------------
tea_skus = [
    # Own brand
    ("Mas Albera", "English Breakfast 100 g",        0.10),
    ("Mas Albera", "Sencha 100 g",                   0.10),
    ("Mas Albera", "Mint Infusion 20 Bags",          0.04),
    ("Mas Albera", "Rooibos 20 Bags",                0.04),
    # Distributed: Casa Fulla
    ("Casa Fulla", "Earl Grey 25 Bags",              0.05),
    ("Casa Fulla", "Jasmine Green 25 Bags",          0.05),
    ("Casa Fulla", "Chai Masala 25 Bags",            0.05),
    ("Casa Fulla", "White Peony 50 g",               0.05),
    # Distributed: Tetera Alta
    ("Tetera Alta", "Matcha 30 g",                   0.03),
    ("Tetera Alta", "Oolong 100 g",                  0.10),
    ("Tetera Alta", "Pu-erh 100 g",                  0.10),
    ("Tetera Alta", "Genmaicha 100 g",               0.10),
]

tea_df = pd.DataFrame(tea_skus, columns=["brand", "product_name", "kg_per_unit"])
assert set(tea_df["brand"]) <= set(BRANDS), "Unknown brand in tea_skus"

tea_df.groupby("brand").size()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Sugar and sweetener SKUs: 8 distributed products, all from Dolçor.
# Same layout: (brand, product_name, kg_per_unit).
# Sachet and liquid weights are rough estimates (simulation values).
# ---------------------------------------------------------------
sugar_skus = [
    ("Dolçor", "White Sugar 1 kg",              1.00),
    ("Dolçor", "Brown Sugar 1 kg",              1.00),
    ("Dolçor", "Cane Sugar Sachets x500",       2.50),
    ("Dolçor", "White Sugar Sachets x1000",     5.00),
    ("Dolçor", "Stevia Sachets x200",           0.20),
    ("Dolçor", "Sweetener Tablets x1000",       0.10),
    ("Dolçor", "Agave Syrup 250 ml",            0.25),
    ("Dolçor", "Liquid Sweetener 500 ml",       0.50),
]

sugar_df = pd.DataFrame(sugar_skus, columns=["brand", "product_name", "kg_per_unit"])
assert set(sugar_df["brand"]) <= set(BRANDS), "Unknown brand in sugar_skus"

sugar_df.groupby("brand").size()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Cocoa and chocolate SKUs: 8 distributed products, all from Cacau Nord.
# Same layout: (brand, product_name, kg_per_unit).
# ---------------------------------------------------------------
cocoa_skus = [
    ("Cacau Nord", "Cocoa Powder 250 g",            0.25),
    ("Cacau Nord", "Cocoa Powder 1 kg",             1.00),
    ("Cacau Nord", "Drinking Chocolate 500 g",      0.50),
    ("Cacau Nord", "Drinking Chocolate 2 kg",       2.00),
    ("Cacau Nord", "Hot Chocolate Sachets x25",     0.63),
    ("Cacau Nord", "Dark Chocolate 70% 100 g",      0.10),
    ("Cacau Nord", "Milk Chocolate 100 g",          0.10),
    ("Cacau Nord", "Baking Chocolate 200 g",        0.20),
]

cocoa_df = pd.DataFrame(cocoa_skus, columns=["brand", "product_name", "kg_per_unit"])
assert set(cocoa_df["brand"]) <= set(BRANDS), "Unknown brand in cocoa_skus"

cocoa_df.groupby("brand").size()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# dim_product: merge the four category lists into one dimension table.
# - Adds category and ownership (looked up in BRANDS).
# - Assigns product_key (1..48) and a readable sku_code (e.g. COF-001).
# - Final checks: 48 rows, no missing ownership, unique SKU codes.
# ---------------------------------------------------------------
cols = ["brand", "product_name", "kg_per_unit"]
catalog = {
    "Coffee": coffee_skus,
    "Tea": tea_skus,
    "Sugar & Sweeteners": sugar_skus,
    "Cocoa & Chocolate": cocoa_skus,
}
prefix = {"Coffee": "COF", "Tea": "TEA", "Sugar & Sweeteners": "SUG", "Cocoa & Chocolate": "COC"}

dim_product = pd.concat(
    [pd.DataFrame(skus, columns=cols).assign(category=cat) for cat, skus in catalog.items()],
    ignore_index=True,
)

dim_product["ownership"] = dim_product["brand"].map(BRANDS)
dim_product["product_key"] = np.arange(1, len(dim_product) + 1)
seq = dim_product.groupby("category").cumcount() + 1
dim_product["sku_code"] = dim_product["category"].map(prefix) + "-" + seq.astype(str).str.zfill(3)

dim_product = dim_product[["product_key", "sku_code", "product_name", "category", "brand", "ownership", "kg_per_unit"]]

assert len(dim_product) == 48
assert dim_product["ownership"].notna().all()
assert dim_product["sku_code"].is_unique

pd.crosstab(dim_product["category"], dim_product["ownership"])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Customer specification: all the parameters that define the customer base.
# Nothing is generated here; this cell only holds the "rules":
# - number of customers per channel, tier mix and customer types (shares)
# - provinces and their weight
# - which sales rep covers which province / channel
# Online has only 3 accounts, so they are listed by hand.
# ---------------------------------------------------------------
CUSTOMER_SPEC = {
    "Horeca": {
        "channel_key": 1, "n": 180,
        "tiers": {"Small": 0.70, "Medium": 0.25, "Large": 0.05},
        "types": {"Hotel": 0.20, "Restaurant": 0.50, "Cafe": 0.30},
    },
    "Retail": {
        "channel_key": 2, "n": 40,
        "tiers": {"Small": 0.40, "Medium": 0.40, "Large": 0.20},
        "types": {"Supermarket": 0.50, "Specialty Store": 0.50},
    },
    "Office & Vending": {
        "channel_key": 3, "n": 40,
        "tiers": {"Small": 0.60, "Medium": 0.30, "Large": 0.10},
        "types": {"Corporate Office": 0.50, "Vending Operator": 0.50},
    },
}

PROVINCES = {"Barcelona": 0.40, "Girona": 0.30, "Tarragona": 0.20, "Lleida": 0.10}

REP_BY_PROVINCE = {
    "Barcelona": "Sales Rep 1", "Girona": "Sales Rep 2",
    "Tarragona": "Sales Rep 3", "Lleida": "Sales Rep 4",
}
REP_RETAIL = "Sales Rep 5"
REP_ONLINE = "Sales Rep 6"

# (customer_name, customer_type, tier)
ONLINE_ACCOUNTS = [
    ("Own E-shop",    "E-shop",      "Large"),
    ("Marketplace A", "Marketplace", "Large"),
    ("Marketplace B", "Marketplace", "Medium"),
]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# dim_customer: build the 263 customers from CUSTOMER_SPEC.
# - allocate() splits n customers into labels with EXACT counts
#   (largest-remainder method), then shuffles them with the seeded rng.
# - Names follow the pattern "<type> <province> <seq>", e.g. "Hotel Girona 017".
# - Online accounts are added by hand.
# - Final checks: 263 rows, unique names, tier mix per channel.
# ---------------------------------------------------------------
def allocate(n, shares):
    labels = list(shares.keys())
    raw = np.array([shares[k] * n for k in labels])
    counts = np.floor(raw).astype(int)
    leftover = n - counts.sum()
    order = np.argsort(-(raw - counts))
    counts[order[:leftover]] += 1
    out = np.repeat(labels, counts)
    rng.shuffle(out)
    return out

rows = []
for channel, spec in CUSTOMER_SPEC.items():
    n = spec["n"]
    tiers = allocate(n, spec["tiers"])
    types = allocate(n, spec["types"])
    provinces = allocate(n, PROVINCES)
    for i in range(n):
        rep = REP_RETAIL if channel == "Retail" else REP_BY_PROVINCE[provinces[i]]
        rows.append({
            "customer_name": f"{types[i]} {provinces[i]} {i + 1:03d}",
            "channel_key": spec["channel_key"],
            "customer_type": str(types[i]),
            "tier": str(tiers[i]),
            "province": str(provinces[i]),
            "sales_rep": rep,
        })

for name, ctype, tier in ONLINE_ACCOUNTS:
    rows.append({
        "customer_name": name, "channel_key": 4, "customer_type": ctype,
        "tier": tier, "province": "Not applicable", "sales_rep": REP_ONLINE,
    })

dim_customer = pd.DataFrame(rows)
dim_customer.insert(0, "customer_key", np.arange(1, len(dim_customer) + 1))

assert len(dim_customer) == 263
assert dim_customer["customer_name"].is_unique

pd.crosstab(dim_customer["channel_key"], dim_customer["tier"])

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Write the four dimensions to the Lakehouse as Delta tables.
# - spark is the Spark session Fabric provides in every notebook.
# - Dates are converted to pure dates (no time part) before writing.
# - mode("overwrite") lets us re-run the notebook safely: tables are replaced.
# ---------------------------------------------------------------
dim_date_out = dim_date.copy()
dim_date_out["week_start"] = dim_date_out["week_start"].dt.date
dim_date_out["week_end"] = dim_date_out["week_end"].dt.date

dims = {
    "dim_date": dim_date_out,
    "dim_channel": dim_channel,
    "dim_product": dim_product,
    "dim_customer": dim_customer,
}

for table_name, pdf in dims.items():
    sdf = spark.createDataFrame(pdf)
    (sdf.write
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .format("delta")
        .saveAsTable(table_name))
    print(table_name, sdf.count())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Add the customer lifecycle to dim_customer.
# Every customer gets start_week_key (first active week) and end_week_key
# (last active week). Defaults: start = 1, end = 156 (active the whole period).
# 8% of customers are "New" (start later) and 6% are "Lost" (end earlier).
# Only Small/Medium accounts of Horeca, Retail and Office & Vending can change;
# Large accounts and the Online accounts always stay active.
# A separate generator (SEED + 1) is used so this cell gives the same result
# no matter which cells ran before it. Exact counts come from rounding once.
# The imports are repeated here so the cell also works after a session restart.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

SEED = 42
rng_life = np.random.default_rng(SEED + 1)

cust = spark.table("dim_customer").toPandas()
cust = cust.drop(columns=[c for c in ["start_week_key", "end_week_key", "lifecycle"] if c in cust.columns])

n_total = len(cust)
n_new = round(0.08 * n_total)
n_lost = round(0.06 * n_total)

eligible = cust.index[(cust["tier"] != "Large") & (cust["channel_key"].isin([1, 2, 3]))].to_numpy()
chosen = rng_life.permutation(eligible)[: n_new + n_lost]
new_idx, lost_idx = chosen[:n_new], chosen[n_new:]

cust["start_week_key"] = 1
cust["end_week_key"] = 156
cust["lifecycle"] = "Existing"

cust.loc[new_idx, "start_week_key"] = rng_life.integers(10, 147, size=n_new)
cust.loc[new_idx, "lifecycle"] = "New"
cust.loc[lost_idx, "end_week_key"] = rng_life.integers(10, 147, size=n_lost)
cust.loc[lost_idx, "lifecycle"] = "Lost"

(spark.createDataFrame(cust)
      .write.mode("overwrite")
      .option("overwriteSchema", "true")
      .format("delta")
      .saveAsTable("dim_customer"))

print(len(eligible), "eligible customers")
print(cust["lifecycle"].value_counts().to_string())
print("New start weeks:", cust.loc[cust["lifecycle"] == "New", "start_week_key"].min(), "-", cust.loc[cust["lifecycle"] == "New", "start_week_key"].max())
print("Lost end weeks:", cust.loc[cust["lifecycle"] == "Lost", "end_week_key"].min(), "-", cust.loc[cust["lifecycle"] == "Lost", "end_week_key"].max())
print(pd.crosstab(cust["lifecycle"], cust["tier"]))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Monthly raw-material price in EUR per kg, from the two real silver series.
# EUR/kg = USD/kg (World Bank Pink Sheet) divided by USD per EUR (ECB).
# This division is our own calculation; the source series stay as published.
# The window starts in Oct 2022 (3 months before the simulation) because the
# distributed brands pay the supplier with a 3-month lag, and ends in Dec 2025.
# Own coffee blend = 70% arabica + 30% robusta. Distributed coffee = robusta only.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

ecb_s = spark.table("slv_ecb_usd_eur").toPandas()
pink_s = spark.table("slv_pink_sheet_monthly").toPandas()
ecb_s["month_start"] = pd.to_datetime(ecb_s["month_start"])
pink_s["month_start"] = pd.to_datetime(pink_s["month_start"])

m = pink_s.merge(ecb_s, on="month_start", how="inner")
m = m[(m["month_start"] >= "2022-10-01") & (m["month_start"] <= "2025-12-01")]
m = m.sort_values("month_start").reset_index(drop=True)

raw_eur = pd.DataFrame({
    "month_start": m["month_start"],
    "coffee_own_blend": (0.7 * m["coffee_arabica_usd_kg"] + 0.3 * m["coffee_robusta_usd_kg"]) / m["usd_per_eur"],
    "coffee_robusta":   m["coffee_robusta_usd_kg"] / m["usd_per_eur"],
    "tea":              m["tea_avg_usd_kg"] / m["usd_per_eur"],
    "sugar":            m["sugar_eu_usd_kg"] / m["usd_per_eur"],
    "cocoa":            m["cocoa_usd_kg"] / m["usd_per_eur"],
})

print(len(raw_eur), raw_eur["month_start"].min().date(), raw_eur["month_start"].max().date())
print("nulls:", int(raw_eur.isna().sum().sum()))
raw_eur[raw_eur["month_start"].isin(pd.to_datetime(["2022-10-01", "2023-01-01", "2025-12-01"]))].round(4)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Monthly unit cost per SKU (EUR per sales unit), 36 months from Jan 2023.
# The share of raw material in the Jan-2023 cost depends on category and
# ownership (RAW_SHARE below). That part follows the market; the rest
# (processing and packaging) grows 3% per year.
# Own brand: raw material follows the market month by month.
# Distributed brands: same starting point (calibrated on Oct-2022 raw material,
# so month 1 equals the base cost), but the supplier passes through only 50% of
# the raw-material change, with a 3-month lag.
# Roasting yield: 1.20 kg of green coffee per kg of roasted coffee, 1.00 elsewhere
# (a simulation assumption). raw_eur must exist from cell 9c-1.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

RAW_SHARE = {
    ("Coffee", "Own"): 0.60,
    ("Coffee", "Distributed"): 0.20,          # capsules: packaging dominates
    ("Tea", "Own"): 0.30,
    ("Tea", "Distributed"): 0.30,
    ("Sugar & Sweeteners", "Distributed"): 0.75,
    ("Cocoa & Chocolate", "Distributed"): 0.50,
}
INFL, PASS_THROUGH, LAG = 0.03, 0.50, 3
YIELD = {"Coffee": 1.20}

def material(category, ownership):
    if category == "Coffee":
        return "coffee_own_blend" if ownership == "Own" else "coffee_robusta"
    return {"Tea": "tea", "Sugar & Sweeteners": "sugar", "Cocoa & Chocolate": "cocoa"}[category]

prod = spark.table("dim_product").toPandas()
raw_i = raw_eur.set_index("month_start")
sim = raw_i.loc["2023-01-01":].index                      # 36 months
infl = (1 + INFL) ** (np.arange(len(sim)) / 12)

rows = []
for p in prod.itertuples():
    share = RAW_SHARE[(p.category, p.ownership)]
    raw_unit = p.kg_per_unit * YIELD.get(p.category, 1.0) * raw_i[material(p.category, p.ownership)]
    if p.ownership == "Own":
        base_total = raw_unit.loc["2023-01-01"] / share
        raw_part = raw_unit.loc[sim].to_numpy()
    else:
        r0 = raw_unit.loc["2022-10-01"]
        base_total = r0 / share
        lagged = raw_unit.shift(LAG).loc[sim].to_numpy()
        raw_part = base_total * share * (1 + PASS_THROUGH * (lagged / r0 - 1))
    other = (1 - share) * base_total * infl
    rows.append(pd.DataFrame({"product_key": p.product_key, "month_start": sim,
                              "raw_material_cost": raw_part, "other_cost": other}))

fact_cost = pd.concat(rows, ignore_index=True)
fact_cost["unit_cost"] = fact_cost["raw_material_cost"] + fact_cost["other_cost"]
fact_cost[["raw_material_cost", "other_cost", "unit_cost"]] = fact_cost[["raw_material_cost", "other_cost", "unit_cost"]].round(4)

print(len(fact_cost), "rows | nulls:", int(fact_cost.isna().sum().sum()))

# Sanity check: cost per kg by category and ownership, first and last month
chk = fact_cost.merge(prod[["product_key", "category", "ownership", "kg_per_unit"]], on="product_key")
chk["cost_per_kg"] = chk["unit_cost"] / chk["kg_per_unit"]
chk[chk["month_start"].isin(pd.to_datetime(["2023-01-01", "2025-12-01"]))] \
   .groupby(["category", "ownership", "month_start"])["cost_per_kg"].mean().round(2).unstack()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Write fact_cost to the Lakehouse as a Delta table (gold layer).
# Grain: one row per product and month (48 products x 36 months = 1,728 rows).
# month_start is stored as a pure date. All amounts are in EUR per sales unit.
# raw_material_cost is our own calculation from the real series (USD/kg from the
# World Bank Pink Sheet, converted with the ECB USD per EUR rate).
# The last lines read the table back to confirm what was saved.
# ---------------------------------------------------------------
out = fact_cost.copy()
out["month_start"] = out["month_start"].dt.date

(spark.createDataFrame(out)
      .write.mode("overwrite")
      .option("overwriteSchema", "true")
      .format("delta")
      .saveAsTable("fact_cost"))

saved = spark.table("fact_cost")
print("fact_cost", saved.count())
saved.orderBy("product_key", "month_start").show(3)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Base list price per SKU and price version (in memory, not written yet).
# Version 1 (week 1): base price = unit cost of Jan 2023 / (1 - target margin),
# 50% margin for own brand, 30% for distributed brands.
# Versions 2-6 (every January and July): the price moves by 65% of the change in
# unit cost since the cost used in the previous version. The cost is read with a
# random lag of 3 to 6 months (per SKU and revision), so prices react late.
# Each version starts on the first week whose Monday falls in that month.
# The base price is the one for index 1.00 (Horeca, Small tier); the channel and
# tier indexes are applied in the next cell.
# A separate generator (SEED + 2) keeps this cell reproducible on its own.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

SEED = 42
rng_price = np.random.default_rng(SEED + 2)
MARGIN = {"Own": 0.50, "Distributed": 0.30}
PASS_PRICE = 0.65
REVISIONS = [(1, 2023, 1), (2, 2023, 7), (3, 2024, 1), (4, 2024, 7), (5, 2025, 1), (6, 2025, 7)]

dim_date = spark.table("dim_date").toPandas()
dim_date["week_start"] = pd.to_datetime(dim_date["week_start"])

def first_week(year, month):
    mask = (dim_date["week_start"].dt.year == year) & (dim_date["week_start"].dt.month == month)
    return int(dim_date.loc[mask, "week_key"].min())

versions = pd.DataFrame(REVISIONS, columns=["price_version", "year", "month"])
versions["effective_week_key"] = [first_week(y, m) for _, y, m in REVISIONS]
versions["last_week_key"] = versions["effective_week_key"].shift(-1).fillna(157).astype(int) - 1

cost_df = spark.table("fact_cost").toPandas()
cost_df["month_start"] = pd.to_datetime(cost_df["month_start"])
cost = cost_df.pivot(index="month_start", columns="product_key", values="unit_cost")

prod = spark.table("dim_product").toPandas()
rows = []
for p in prod.itertuples():
    c_ref = cost.loc["2023-01-01", p.product_key]
    base = c_ref / (1 - MARGIN[p.ownership])
    rows.append((p.product_key, 1, 0, base))
    for version, year, month in REVISIONS[1:]:
        lag = int(rng_price.integers(3, 7))
        ref_month = pd.Timestamp(year=year, month=month, day=1) - pd.DateOffset(months=lag)
        c_new = cost.loc[ref_month, p.product_key]
        base = base * (1 + PASS_PRICE * (c_new / c_ref - 1))
        c_ref = c_new
        rows.append((p.product_key, version, lag, base))

base_prices = pd.DataFrame(rows, columns=["product_key", "price_version", "lag_months", "base_price"])
base_prices["base_price"] = base_prices["base_price"].round(4)

print(len(base_prices), "rows | nulls:", int(base_prices.isna().sum().sum()))
print(versions.to_string(index=False))
base_prices[base_prices["product_key"] == 1]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# fact_price_list: list price per SKU, channel, customer tier and price version.
# list_price = base_price x channel index x tier index, rounded to 2 decimals.
# Grain: 48 SKUs x 4 channels x 3 tiers x 6 versions = 3,456 rows.
# effective_week_key / last_week_key say when each version is in force.
# Needs base_prices and versions from cell 9d-1 (they live in memory).
# ---------------------------------------------------------------
CHANNEL_INDEX = {1: 1.00, 2: 0.90, 3: 0.95, 4: 1.15}     # Horeca, Retail, Office & Vending, Online
TIER_INDEX = {"Small": 1.00, "Medium": 0.97, "Large": 0.94}

combos = pd.DataFrame(
    [(ch, tier) for ch in CHANNEL_INDEX for tier in TIER_INDEX],
    columns=["channel_key", "tier"],
)
combos["channel_index"] = combos["channel_key"].map(CHANNEL_INDEX)
combos["tier_index"] = combos["tier"].map(TIER_INDEX)

fact_price_list = (
    base_prices.drop(columns="lag_months")
    .merge(versions[["price_version", "effective_week_key", "last_week_key"]], on="price_version")
    .merge(combos, how="cross")
)
fact_price_list["list_price"] = (
    fact_price_list["base_price"] * fact_price_list["channel_index"] * fact_price_list["tier_index"]
).round(2)

fact_price_list = fact_price_list[[
    "price_version", "effective_week_key", "last_week_key", "product_key", "channel_key",
    "tier", "base_price", "channel_index", "tier_index", "list_price",
]]

(spark.createDataFrame(fact_price_list)
      .write.mode("overwrite")
      .option("overwriteSchema", "true")
      .format("delta")
      .saveAsTable("fact_price_list"))

saved = spark.table("fact_price_list").toPandas()
print("fact_price_list", len(saved), "| nulls:", int(saved.isna().sum().sum()))
per_combo = saved.groupby(["product_key", "channel_key", "tier"])["price_version"].nunique()
weeks_covered = saved[saved["product_key"] == 1].drop_duplicates("price_version")
print("versions per combination:", per_combo.min(), "-", per_combo.max(),
      "| weeks covered:", int((weeks_covered["last_week_key"] - weeks_covered["effective_week_key"] + 1).sum()))
saved[(saved["product_key"] == 1) & (saved["price_version"] == 1)] \
    .sort_values(["channel_key", "tier"])[["channel_key", "tier", "list_price"]]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# fact_customer_terms: commercial terms per customer and year (2023-2025),
# as a fraction of gross sales (0.0725 = 7.25%). 263 customers x 3 years = 789 rows.
# Four layers: on-invoice discount, volume rebate (rappel), early-payment
# discount and marketing contribution.
# Each customer gets one "negotiating position" u in [0, 1]: Small accounts sit
# near the low end of each range, Large accounts near the high end, with random
# spread. A small noise per layer avoids perfect correlation between layers.
# Every year the on-invoice discount and the rappel drift up by 0 to 0.5
# percentage points (term creep). Early payment is a fixed 2% for half of the
# accounts in Horeca, Retail and Office & Vending, and 0 elsewhere.
# A separate generator (SEED + 3) keeps this cell reproducible on its own.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

SEED = 42
rng_terms = np.random.default_rng(SEED + 3)

RANGES = {                      # channel_key: (low, high) in percent
    "on_invoice": {1: (3, 8), 2: (8, 14), 3: (4, 9), 4: (0, 3)},
    "rappel":     {1: (1, 3), 2: (2, 5),  3: (1, 3), 4: (0, 0)},
    "marketing":  {1: (0, 2), 2: (1, 4),  3: (0, 0), 4: (0, 0)},
}
TIER_CENTER = {"Small": 0.25, "Medium": 0.50, "Large": 0.75}
YEARS = [2023, 2024, 2025]

cust = spark.table("dim_customer").toPandas()[["customer_key", "channel_key", "tier"]]

rows = []
for c in cust.itertuples():
    u_c = float(np.clip(TIER_CENTER[c.tier] + rng_terms.uniform(-0.25, 0.25), 0, 1))
    start = {}
    for layer, ranges in RANGES.items():
        lo, hi = ranges[c.channel_key]
        u = float(np.clip(u_c + rng_terms.uniform(-0.10, 0.10), 0, 1))
        start[layer] = (lo + u * (hi - lo)) / 100
    early = 0.02 if (c.channel_key in (1, 2, 3) and rng_terms.random() < 0.5) else 0.0

    on_invoice, rappel = start["on_invoice"], start["rappel"]
    for i, year in enumerate(YEARS):
        if i > 0:
            on_invoice += rng_terms.uniform(0, 0.5) / 100
            if rappel > 0:
                rappel += rng_terms.uniform(0, 0.5) / 100
        rows.append((c.customer_key, year, on_invoice, rappel, early, start["marketing"]))

terms = pd.DataFrame(rows, columns=["customer_key", "year", "on_invoice_pct", "rappel_pct",
                                    "early_payment_pct", "marketing_pct"]).round(4)
terms["total_terms_pct"] = terms[["on_invoice_pct", "rappel_pct", "early_payment_pct", "marketing_pct"]].sum(axis=1).round(4)

(spark.createDataFrame(terms)
      .write.mode("overwrite")
      .option("overwriteSchema", "true")
      .format("delta")
      .saveAsTable("fact_customer_terms"))

saved = spark.table("fact_customer_terms").toPandas()
print("fact_customer_terms", len(saved), "| nulls:", int(saved.isna().sum().sum()))
saved.merge(cust[["customer_key", "channel_key"]], on="customer_key") \
     .groupby(["channel_key", "year"])[["on_invoice_pct", "rappel_pct", "early_payment_pct", "marketing_pct", "total_terms_pct"]] \
     .mean().mul(100).round(2)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# fact_promotion: one row per promotion event (SKU x channel x weeks).
# 240 events: Online 90, Horeca 60, Office & Vending 60, Retail 30.
# Promotion rules (margin-aware):
#   - Only SKU x channel pairs with unit margin >= 20% of gross are promoted.
#   - The discount never exceeds 50% of that unit margin.
# Unit margin % of gross = (1 - channel terms %) - unit cost / list price,
# estimated from fact_price_list, fact_cost, fact_customer_terms and the assortment.
# Online follows a fixed calendar, the same dates for all Online accounts:
#   Black Friday (week of Black Friday + Cyber Monday week): 12 events per year
#   January Sales (3 weeks from the first week on/after Jan 7): 9 per year
#   Summer Sales (3 weeks from the first week on/after Jul 1): 9 per year
# The other channels get random dates between weeks 5 and 150, 2 to 4 weeks long.
# A SKU never has two events in the same channel closer than 3 weeks (the
# post-promotion dip needs room). Half of the events add visibility support.
# Uplift and dip are NOT stored here; they are applied later when we generate
# sales. The cost of the support will be defined as a % of promoted gross sales.
# A separate generator (SEED + 4) keeps this cell reproducible on its own.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

SEED = 42
rng_promo = np.random.default_rng(SEED + 4)

MIN_MARGIN = 0.20     # minimum unit margin (share of gross) to be promoted
CAP_SHARE = 0.50      # maximum discount as a share of the unit margin

dim_date = spark.table("dim_date").toPandas()
dim_date["week_start"] = pd.to_datetime(dim_date["week_start"])
week_of = dict(zip(dim_date["week_start"], dim_date["week_key"]))
year_of_week = dict(zip(dim_date["week_key"], dim_date["year"]))

# --- Unit margin (% of gross) per product x channel, from upstream tables ---
cust = spark.table("dim_customer").toPandas()[["customer_key", "channel_key"]]
assort = spark.table("sim_customer_assortment").toPandas().merge(cust, on="customer_key")
pairs = assort[["product_key", "channel_key"]].drop_duplicates()
price = (spark.table("fact_price_list").toPandas()
         .groupby(["product_key", "channel_key"], as_index=False)["list_price"].mean())
cost = (spark.table("fact_cost").toPandas()
        .groupby("product_key", as_index=False)["unit_cost"].mean())
terms = spark.table("fact_customer_terms").toPandas().merge(cust, on="customer_key")
scale = 100.0 if terms["total_terms_pct"].max() > 1 else 1.0
terms_ch = terms.groupby("channel_key", as_index=False)["total_terms_pct"].mean()
terms_ch["terms"] = terms_ch["total_terms_pct"] / scale
mg = (pairs.merge(price, on=["product_key", "channel_key"])
           .merge(cost, on="product_key")
           .merge(terms_ch[["channel_key", "terms"]], on="channel_key"))
mg["margin_pct"] = (1 - mg["terms"]) - mg["unit_cost"] / mg["list_price"]
margin_of = {(int(r.product_key), int(r.channel_key)): float(r.margin_pct) for r in mg.itertuples()}

def allowed_depths(pk, ch, depths):
    """Depths that do not exceed CAP_SHARE of the unit margin of this SKU x channel."""
    cap = CAP_SHARE * margin_of.get((int(pk), int(ch)), -1.0)
    return [d for d in depths if d <= cap + 1e-9]

def eligible(ch, depths):
    """SKUs sellable in the channel with enough margin and at least one allowed depth."""
    return sorted(pk for (pk, c), m_ in margin_of.items()
                  if c == ch and m_ >= MIN_MARGIN and allowed_depths(pk, c, depths))

DEPTHS_OTHER = [0.10, 0.15, 0.20, 0.25, 0.30]
MECHANICS = ["Price only", "Price + visibility support"]
events = []

def add_event(campaign, channel_key, product_key, start, duration, depth):
    events.append({
        "campaign": campaign, "channel_key": int(channel_key), "product_key": int(product_key),
        "mechanic": MECHANICS[int(rng_promo.random() < 0.5)],
        "discount_pct": float(depth), "start_week_key": int(start),
        "end_week_key": int(start + duration - 1), "duration_weeks": int(duration),
    })

def first_week_on_or_after(date):
    return int(dim_date.loc[dim_date["week_start"] >= date, "week_key"].min())

# --- Online: fixed commercial calendar (3 windows per year) ---
for year in (2023, 2024, 2025):
    nov = pd.date_range(f"{year}-11-01", f"{year}-11-30")
    thanksgiving = nov[nov.weekday == 3][3]                       # 4th Thursday of November
    windows = [
        ("Black Friday",  week_of[thanksgiving - pd.Timedelta(days=3)], 2, 12, [0.15, 0.20, 0.25, 0.30]),
        ("January Sales", first_week_on_or_after(pd.Timestamp(f"{year}-01-07")), 3, 9, [0.10, 0.15, 0.20, 0.25]),
        ("Summer Sales",  first_week_on_or_after(pd.Timestamp(f"{year}-07-01")), 3, 9, [0.10, 0.15, 0.20, 0.25]),
    ]
    for campaign, first_week, n_weeks, n_events, depths in windows:
        pool = np.array(eligible(4, depths))
        for pk in rng_promo.choice(pool, size=n_events, replace=False):
            duration = int(rng_promo.integers(1, 3))              # 1 or 2 weeks
            start = first_week + int(rng_promo.integers(0, n_weeks - duration + 1))
            depth = rng_promo.choice(allowed_depths(pk, 4, depths))
            add_event(campaign, 4, pk, start, duration, depth)

# --- Other channels: random dates, no overlap per SKU and channel ---
busy = {}
for channel_key, n_events in {2: 30, 3: 60, 1: 60}.items():
    pool = np.array(eligible(channel_key, DEPTHS_OTHER))
    made, tries = 0, 0
    while made < n_events:
        tries += 1
        if tries > 20000:
            raise RuntimeError(f"Cannot place {n_events} events in channel {channel_key}")
        pk = int(rng_promo.choice(pool))
        duration = int(rng_promo.integers(2, 5))                  # 2 to 4 weeks
        start = int(rng_promo.integers(5, 152 - duration))
        end = start + duration - 1
        if any(start <= e + 3 and s <= end + 3 for s, e in busy.get((pk, channel_key), [])):
            continue
        busy.setdefault((pk, channel_key), []).append((start, end))
        depth = rng_promo.choice(allowed_depths(pk, channel_key, DEPTHS_OTHER))
        add_event("Regular", channel_key, pk, start, duration, depth)
        made += 1

promo = pd.DataFrame(events).sort_values(["start_week_key", "channel_key", "product_key"]).reset_index(drop=True)
promo.insert(0, "promotion_id", np.arange(1, len(promo) + 1))
promo["discount_pct"] = promo["discount_pct"].round(2)

(spark.createDataFrame(promo)
      .write.mode("overwrite")
      .option("overwriteSchema", "true")
      .format("delta")
      .saveAsTable("fact_promotion"))

saved = spark.table("fact_promotion").toPandas()
print("fact_promotion", len(saved), "| nulls:", int(saved.isna().sum().sum()))

overlaps = 0
for _, g in saved.groupby(["product_key", "channel_key"]):
    g = g.sort_values("start_week_key")
    overlaps += int((g["start_week_key"].to_numpy()[1:] <= g["end_week_key"].to_numpy()[:-1] + 3).sum())
print("overlaps (including the 3-week gap):", overlaps, "| last end week:", int(saved["end_week_key"].max()))

# Rule checks: margin of the promoted pairs and discount versus margin
saved["margin_pct"] = [margin_of[(int(p), int(c))] for p, c in zip(saved["product_key"], saved["channel_key"])]
print("min margin among promoted pairs:", round(saved["margin_pct"].min(), 4))
print("events with discount > cap x margin:", int((saved["discount_pct"] > CAP_SHARE * saved["margin_pct"] + 1e-9).sum()))
print(saved.groupby("channel_key").agg(events=("promotion_id", "size"),
                                       products=("product_key", "nunique"),
                                       avg_margin=("margin_pct", "mean"),
                                       avg_discount=("discount_pct", "mean")).round(3).to_string())

online = saved[saved["channel_key"] == 4].copy()
online["year"] = online["start_week_key"].map(year_of_week)
online.pivot_table(index="campaign", columns="year", values="promotion_id", aggfunc="count")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Read-only: list every table in the Lakehouse with its columns and row count.
# Used to find which tables hold list price, commercial terms and unit cost.
for t in sorted(spark.catalog.listTables(), key=lambda x: x.name):
    df = spark.table(t.name)
    print(f"{t.name} ({df.count()} rows): {', '.join(df.columns)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Assortment: which SKUs each customer buys. Fixed for the whole period.
# Number of SKUs per customer is drawn inside a range that depends on channel
# and tier. Horeca and Office & Vending favour coffee, tea and sugar
# (40/25/25/10% by category); Retail and Online pick SKUs uniformly.
# Saved as sim_customer_assortment (simulation helper, not part of the model).
# A separate generator (SEED + 5) keeps this cell reproducible on its own.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

SEED = 42
rng_assort = np.random.default_rng(SEED + 5)

cust = spark.table("dim_customer").toPandas()[["customer_key", "channel_key", "tier"]]
prod = spark.table("dim_product").toPandas()[["product_key", "category"]]

SKU_RANGE = {
    (1, "Small"): (6, 10),  (1, "Medium"): (10, 16), (1, "Large"): (16, 24),     # Horeca
    (2, "Small"): (20, 28), (2, "Medium"): (28, 36), (2, "Large"): (36, 48),     # Retail
    (3, "Small"): (8, 14),  (3, "Medium"): (8, 14),  (3, "Large"): (8, 14),      # Office & Vending
    (4, "Medium"): (30, 40), (4, "Large"): (40, 48),                              # Online
}
CAT_SHARE = {"Coffee": 0.40, "Tea": 0.25, "Sugar & Sweeteners": 0.25, "Cocoa & Chocolate": 0.10}

n_in_cat = prod.groupby("category")["product_key"].transform("count")
w_focus = (prod["category"].map(CAT_SHARE) / n_in_cat).to_numpy()
w_focus = w_focus / w_focus.sum()
w_uniform = np.full(len(prod), 1 / len(prod))
WEIGHTS = {1: w_focus, 3: w_focus, 2: w_uniform, 4: w_uniform}

keys = prod["product_key"].to_numpy()
rows = []
for c in cust.itertuples():
    lo, hi = SKU_RANGE[(c.channel_key, c.tier)]
    k = int(rng_assort.integers(lo, hi + 1))
    chosen = rng_assort.choice(keys, size=k, replace=False, p=WEIGHTS[c.channel_key])
    rows += [(c.customer_key, int(pk)) for pk in chosen]

assort = pd.DataFrame(rows, columns=["customer_key", "product_key"])

(spark.createDataFrame(assort)
      .write.mode("overwrite")
      .option("overwriteSchema", "true")
      .format("delta")
      .saveAsTable("sim_customer_assortment"))

print("sim_customer_assortment", len(assort), "| customers:", assort["customer_key"].nunique())

per_cust = assort.groupby("customer_key").size().rename("n_skus").reset_index().merge(cust, on="customer_key")
print(per_cust.groupby(["channel_key", "tier"])["n_skus"].agg(["count", "min", "mean", "max"]).round(1))

horeca = assort.merge(cust[cust["channel_key"] == 1][["customer_key"]], on="customer_key").merge(prod, on="product_key")
print(horeca["category"].value_counts(normalize=True).round(2).to_string())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Demand parameters, saved as simulation helper tables (not part of the model):
#  - sim_param_elasticity: the TRUE price elasticity per category, ownership and
#    channel. Base value per category x channel multiplier. This is the ground
#    truth we will try to recover later with a log-log regression in Python.
#  - sim_param_seasonality: monthly seasonal index per channel, normalised so that
#    each channel averages 1.00 over the year. The month of a week is the month
#    of its Monday.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

EPS_BASE = {
    ("Coffee", "Own"): -1.1,
    ("Coffee", "Distributed"): -1.3,
    ("Tea", "Own"): -1.4,
    ("Tea", "Distributed"): -1.4,
    ("Sugar & Sweeteners", "Distributed"): -0.6,
    ("Cocoa & Chocolate", "Distributed"): -1.2,
}
CHANNEL_MULT = {1: 0.8, 2: 1.1, 3: 0.9, 4: 1.3}      # Horeca, Retail, Office & Vending, Online

prod_pairs = spark.table("dim_product").toPandas()[["category", "ownership"]].drop_duplicates()
assert set(map(tuple, prod_pairs.values)) == set(EPS_BASE), "category/ownership pairs do not match"

eps = pd.DataFrame(
    [(cat, own, ch, round(e * m, 3)) for (cat, own), e in EPS_BASE.items() for ch, m in CHANNEL_MULT.items()],
    columns=["category", "ownership", "channel_key", "elasticity"],
)

SEASON = {                                           # index per month, January to December
    1: [0.80, 0.75, 0.85, 0.95, 1.05, 1.25, 1.35, 1.35, 1.15, 0.95, 0.80, 0.75],
    2: [0.90] + [0.98] * 10 + [1.30],
    3: [1.03] * 7 + [0.80] + [1.03] * 3 + [0.90],
    4: [0.9818] * 11 + [1.20],
}
season_rows = []
for ch, vals in SEASON.items():
    arr = np.array(vals) / np.mean(vals)
    season_rows += [(ch, m + 1, round(float(v), 4)) for m, v in enumerate(arr)]
season = pd.DataFrame(season_rows, columns=["channel_key", "month", "seasonal_index"])

for name, pdf in {"sim_param_elasticity": eps, "sim_param_seasonality": season}.items():
    (spark.createDataFrame(pdf)
          .write.mode("overwrite")
          .option("overwriteSchema", "true")
          .format("delta")
          .saveAsTable(name))

print("sim_param_elasticity", spark.table("sim_param_elasticity").count(),
      "| sim_param_seasonality", spark.table("sim_param_seasonality").count())
print(eps.pivot_table(index=["category", "ownership"], columns="channel_key", values="elasticity"))
print(season.groupby("channel_key")["seasonal_index"].agg(["mean", "min", "max"]).round(2))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Generate weekly sales per customer x SKU (in memory, not written yet).
# Expected units per week = base units by tier x customer factor x SKU factor
#   x seasonal index x trend x (list price / initial list price)^elasticity
#   x promotion effect, and units are drawn from a Poisson distribution.
# Promotion effect: during the event the volume is multiplied by
#   1 + PROMO_RESPONSE x ((1 - discount)^elasticity x 1.20 if visibility support - 1).
# PROMO_RESPONSE = 4 makes promotions react about 4 times more than an ordinary price cut.
# In the 3 weeks after the event, 30% of the incremental volume is taken back
# (post-promotion dip), spread evenly over the 3 weeks, never below 30% of base demand.
# Customers only buy between start_week_key and end_week_key, and only the SKUs
# in their assortment. Weeks with 0 units do not create a row.
# Money columns: terms and promotion discount are % of gross sales (units x list
# price). Net sales = gross - promo discount - on-invoice - rappel - early
# payment - marketing contribution. promo_support_cost (3% of promoted gross
# sales for events with visibility support) is kept apart, not inside net sales.
# A separate generator (SEED + 6) keeps this cell reproducible on its own.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

SEED = 42
rng_sales = np.random.default_rng(SEED + 6)

BASE_UNITS = {"Small": 3, "Medium": 8, "Large": 20}
TREND, SIGMA_CUST, SIGMA_SKU = 0.02, 0.25, 0.35
VIS_UPLIFT, DIP_SHARE, DIP_WEEKS, SUPPORT_COST = 1.20, 0.30, 3, 0.03
PROMO_RESPONSE = 4.0   # promo volume response vs an ordinary price change (1.0 = same as list price change)

cust = spark.table("dim_customer").toPandas()[["customer_key", "channel_key", "tier", "start_week_key", "end_week_key"]]
cust = cust.sort_values("customer_key").reset_index(drop=True)
prod = spark.table("dim_product").toPandas()[["product_key", "category", "ownership"]]
prod = prod.sort_values("product_key").reset_index(drop=True)
assort = spark.table("sim_customer_assortment").toPandas()
dd = spark.table("dim_date").toPandas()
dd["week_start"] = pd.to_datetime(dd["week_start"])
dd["month"] = dd["week_start"].dt.month
dd["month_start"] = dd["week_start"].dt.to_period("M").dt.to_timestamp()
weeks = dd[["week_key", "year", "month", "month_start"]]

pl = spark.table("fact_price_list").toPandas()
cost = spark.table("fact_cost").toPandas()
cost["month_start"] = pd.to_datetime(cost["month_start"])
terms = spark.table("fact_customer_terms").toPandas()
promos = spark.table("fact_promotion").toPandas()
eps = spark.table("sim_param_elasticity").toPandas()
season = spark.table("sim_param_seasonality").toPandas()

# Random level per customer and per SKU (lognormal with mean 1)
cust["cust_factor"] = np.exp(rng_sales.normal(-SIGMA_CUST**2 / 2, SIGMA_CUST, len(cust)))
prod["sku_factor"] = np.exp(rng_sales.normal(-SIGMA_SKU**2 / 2, SIGMA_SKU, len(prod)))

# Customer x SKU x week grid, only active weeks
grid = assort.merge(cust, on="customer_key").merge(prod, on="product_key").merge(weeks, how="cross")
grid = grid[(grid["week_key"] >= grid["start_week_key"]) & (grid["week_key"] <= grid["end_week_key"])]
grid = grid.sort_values(["customer_key", "product_key", "week_key"]).reset_index(drop=True)

# List price in force, and the initial list price (version 1) as reference
eff = np.sort(pl["effective_week_key"].unique())
grid["price_version"] = np.searchsorted(eff, grid["week_key"].to_numpy(), side="right")
key = ["product_key", "channel_key", "tier"]
grid = grid.merge(pl[["price_version"] + key + ["list_price"]], on=["price_version"] + key, how="left")
ref = pl[pl["price_version"] == 1][key + ["list_price"]].rename(columns={"list_price": "list_price_ref"})
grid = grid.merge(ref, on=key, how="left")
grid = grid.merge(eps, on=["category", "ownership", "channel_key"], how="left")
grid = grid.merge(season, on=["channel_key", "month"], how="left")

# Promotion effect per (channel, SKU, week): uplift during the event, dip after it
pe = promos.merge(prod[["product_key", "category", "ownership"]], on="product_key") \
           .merge(eps, on=["category", "ownership", "channel_key"])
pe["uplift"] = 1 + PROMO_RESPONSE * ((1 - pe["discount_pct"]) ** pe["elasticity"] * np.where(pe["mechanic"] == "Price + visibility support", VIS_UPLIFT, 1.0) - 1)

in_promo = pe.loc[pe.index.repeat(pe["duration_weeks"])].copy()
in_promo["week_key"] = in_promo["start_week_key"] + in_promo.groupby("promotion_id").cumcount()
in_promo["promo_mult"] = in_promo["uplift"]
in_promo = in_promo[["channel_key", "product_key", "week_key", "promotion_id", "discount_pct", "mechanic", "promo_mult"]]

dip = pe.loc[pe.index.repeat(DIP_WEEKS)].copy()
dip["week_key"] = dip["end_week_key"] + 1 + dip.groupby("promotion_id").cumcount()
dip["promo_mult"] = (1 - DIP_SHARE * (dip["uplift"] - 1) * dip["duration_weeks"] / DIP_WEEKS).clip(lower=0.3)
dip = dip[dip["week_key"] <= 156][["channel_key", "product_key", "week_key", "promo_mult"]]
print("promo uplift: mean", round(float(pe["uplift"].mean() - 1), 3), "| max", round(float(pe["uplift"].max() - 1), 3),
      "| dip weeks floored at 0.3:", round(float((dip["promo_mult"] <= 0.3 + 1e-9).mean() * 100), 1), "%")
dip["promotion_id"], dip["discount_pct"], dip["mechanic"] = np.nan, 0.0, None

promo_effect = pd.concat([in_promo, dip], ignore_index=True)
grid = grid.merge(promo_effect, on=["channel_key", "product_key", "week_key"], how="left")
grid["promo_mult"] = grid["promo_mult"].fillna(1.0)
grid["discount_pct"] = grid["discount_pct"].fillna(0.0)

# Expected units and Poisson draw
trend = (1 + TREND) ** ((grid["week_key"] - 1) / 52)
lam = (grid["tier"].map(BASE_UNITS) * grid["cust_factor"] * grid["sku_factor"] * grid["seasonal_index"] * trend
       * (grid["list_price"] / grid["list_price_ref"]) ** grid["elasticity"] * grid["promo_mult"])
grid["units"] = rng_sales.poisson(lam.to_numpy())
sales = grid[grid["units"] > 0].copy()

# Money columns
sales = sales.merge(terms, on=["customer_key", "year"], how="left")
sales = sales.merge(cost[["product_key", "month_start", "unit_cost"]], on=["product_key", "month_start"], how="left")
sales["gross_sales"] = (sales["units"] * sales["list_price"]).round(2)
for col, pct in [("promo_discount", "discount_pct"), ("on_invoice_discount", "on_invoice_pct"), ("rappel", "rappel_pct"),
                 ("early_payment_discount", "early_payment_pct"), ("marketing_contribution", "marketing_pct")]:
    sales[col] = (sales["gross_sales"] * sales[pct]).round(2)
sales["net_sales"] = (sales["gross_sales"] - sales["promo_discount"] - sales["on_invoice_discount"] - sales["rappel"]
                      - sales["early_payment_discount"] - sales["marketing_contribution"]).round(2)
sales["cogs"] = (sales["units"] * sales["unit_cost"]).round(2)
sales["promo_support_cost"] = np.where(sales["mechanic"] == "Price + visibility support",
                                       (sales["gross_sales"] * SUPPORT_COST).round(2), 0.0)

sales = sales[["week_key", "customer_key", "product_key", "promotion_id", "units", "list_price", "unit_cost",
               "gross_sales", "promo_discount", "on_invoice_discount", "rappel", "early_payment_discount",
               "marketing_contribution", "net_sales", "cogs", "promo_support_cost"]].reset_index(drop=True)

print(len(sales), "rows | nulls outside promotion_id:", int(sales.drop(columns="promotion_id").isna().sum().sum()))
yr = sales.merge(weeks[["week_key", "year"]], on="week_key").groupby("year").agg(
    units=("units", "sum"), gross=("gross_sales", "sum"), net=("net_sales", "sum"), cogs=("cogs", "sum"))
yr["net_to_gross_pct"] = (yr["net"] / yr["gross"] * 100).round(2)
yr["margin_pct_of_net"] = ((yr["net"] - yr["cogs"]) / yr["net"] * 100).round(2)
yr[["gross", "net", "cogs"]] = (yr[["gross", "net", "cogs"]] / 1e6).round(2)
print(yr)
ch = sales.merge(cust[["customer_key", "channel_key"]], on="customer_key").groupby("channel_key")["gross_sales"].sum()
print((ch / ch.sum() * 100).round(2).to_string())
print("share of rows in promotion:", round(float(sales["promotion_id"].notna().mean() * 100), 2), "%")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Diagnostic only (nothing is written): margin % of net sales and units, by
# category, ownership and year, to check where the margin squeeze comes from.
# Uses sales, weeks and prod from cell 9g-3 (they live in memory).
# ---------------------------------------------------------------
diag = sales.merge(weeks[["week_key", "year"]], on="week_key") \
            .merge(prod[["product_key", "category", "ownership"]], on="product_key")
g = diag.groupby(["category", "ownership", "year"]).agg(units=("units", "sum"), net=("net_sales", "sum"), cogs=("cogs", "sum"))
g["margin_pct_of_net"] = ((g["net"] - g["cogs"]) / g["net"] * 100).round(2)
print(g["margin_pct_of_net"].unstack("year"))
print(g["units"].unstack("year"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Write fact_sales to the Lakehouse as a Delta table (gold layer).
# Grain: one row per week, customer and SKU with at least 1 unit sold.
# promotion_id is empty for weeks without promotion (and for the post-promotion
# dip weeks); NaN is converted to a real null before saving.
# The last lines read the table back and compare it with the in-memory data.
# ---------------------------------------------------------------
from pyspark.sql import functions as F

sdf = spark.createDataFrame(sales)
sdf = sdf.withColumn(
    "promotion_id",
    F.when(F.isnan("promotion_id"), None).otherwise(F.col("promotion_id")).cast("int"),
)

(sdf.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .format("delta")
    .saveAsTable("fact_sales"))

saved = spark.table("fact_sales")
agg = saved.agg(
    F.count("*").alias("rows"),
    F.round(F.sum("gross_sales"), 2).alias("gross"),
    F.round(F.sum("net_sales"), 2).alias("net"),
    F.sum(F.when(F.col("promotion_id").isNotNull(), 1).otherwise(0)).alias("promo_rows"),
).first()
print("fact_sales", agg["rows"], "| gross:", agg["gross"], "| net:", agg["net"], "| promo rows:", agg["promo_rows"])
print("matches memory:", agg["rows"] == len(sales)
      and abs(agg["gross"] - round(float(sales["gross_sales"].sum()), 2)) < 0.01
      and abs(agg["net"] - round(float(sales["net_sales"].sum()), 2)) < 0.01)
saved.printSchema()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Data checks on the gold tables (read only, nothing is written).
# Every check counts rows that should NOT exist, so the expected value is 0,
# except the last one, which is informational.
# ---------------------------------------------------------------
checks = {
    "sales with unknown customer":
        "SELECT COUNT(*) FROM fact_sales s LEFT ANTI JOIN dim_customer c ON s.customer_key = c.customer_key",
    "sales with unknown product":
        "SELECT COUNT(*) FROM fact_sales s LEFT ANTI JOIN dim_product p ON s.product_key = p.product_key",
    "sales with unknown week":
        "SELECT COUNT(*) FROM fact_sales s LEFT ANTI JOIN dim_date d ON s.week_key = d.week_key",
    "sales with unknown promotion":
        "SELECT COUNT(*) FROM fact_sales s LEFT ANTI JOIN fact_promotion p ON s.promotion_id = p.promotion_id "
        "WHERE s.promotion_id IS NOT NULL",
    "sales outside the customer's active weeks":
        "SELECT COUNT(*) FROM fact_sales s JOIN dim_customer c ON s.customer_key = c.customer_key "
        "WHERE s.week_key < c.start_week_key OR s.week_key > c.end_week_key",
    "duplicated customer-SKU-week rows":
        "SELECT COUNT(*) - COUNT(DISTINCT customer_key, product_key, week_key) FROM fact_sales",
    "gross-to-net arithmetic errors (> 0.011)":
        "SELECT COUNT(*) FROM fact_sales WHERE ABS(gross_sales - promo_discount - on_invoice_discount - rappel "
        "- early_payment_discount - marketing_contribution - net_sales) > 0.011",
    "non-positive units, prices, costs or net sales":
        "SELECT COUNT(*) FROM fact_sales WHERE units <= 0 OR list_price <= 0 OR unit_cost <= 0 OR net_sales <= 0",
    "sales rows without exactly one list price":
        "SELECT (SELECT COUNT(*) FROM fact_sales) - COUNT(*) FROM fact_sales s "
        "JOIN dim_customer c ON s.customer_key = c.customer_key "
        "JOIN fact_price_list p ON p.product_key = s.product_key AND p.channel_key = c.channel_key "
        "AND p.tier = c.tier AND s.week_key BETWEEN p.effective_week_key AND p.last_week_key",
    "list price different from fact_price_list":
        "SELECT COUNT(*) FROM fact_sales s JOIN dim_customer c ON s.customer_key = c.customer_key "
        "JOIN fact_price_list p ON p.product_key = s.product_key AND p.channel_key = c.channel_key "
        "AND p.tier = c.tier AND s.week_key BETWEEN p.effective_week_key AND p.last_week_key "
        "WHERE ABS(s.list_price - p.list_price) > 0.001",
    "unit cost different from fact_cost":
        "SELECT COUNT(*) FROM fact_sales s JOIN dim_date d ON s.week_key = d.week_key "
        "JOIN fact_cost fc ON fc.product_key = s.product_key AND fc.month_start = TRUNC(d.week_start, 'MM') "
        "WHERE ABS(s.unit_cost - fc.unit_cost) > 0.00005",
    "INFO: promotions without any sales row":
        "SELECT COUNT(*) FROM fact_promotion p LEFT ANTI JOIN fact_sales s ON s.promotion_id = p.promotion_id",
}

for name, query in checks.items():
    print(f"{spark.sql(query).first()[0]:>8}  {name}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Check that the seeded elasticities are visible in the data (read only).
# For each promotion event: observed uplift = average weekly units during the
# event / average weekly units in the weeks before it, both divided by the
# seasonal index. Weeks that belong to another promotion or to its post-promotion
# dip are excluded from the baseline (up to 8 weeks before the start, at least 3).
# Theoretical uplift = (1 - discount) ^ elasticity, times 1.20 if the event has
# visibility support. We compare both by channel.
# ---------------------------------------------------------------
import numpy as np
import pandas as pd

N_WEEKS = 156
s = spark.sql("""
    SELECT s.product_key, c.channel_key, s.week_key, SUM(s.units) AS units
    FROM fact_sales s JOIN dim_customer c ON s.customer_key = c.customer_key
    GROUP BY 1, 2, 3
""").toPandas()
season = spark.table("sim_param_seasonality").toPandas()
dd = spark.table("dim_date").toPandas()
dd["week_start"] = pd.to_datetime(dd["week_start"])
promos = spark.table("fact_promotion").toPandas()
prod = spark.table("dim_product").toPandas()[["product_key", "category", "ownership"]]
eps = spark.table("sim_param_elasticity").toPandas()

units = np.zeros((49, 5, N_WEEKS + 1))                       # [product_key, channel_key, week_key]
units[s["product_key"], s["channel_key"], s["week_key"]] = s["units"]

season_lookup = {(r.channel_key, r.month): r.seasonal_index for r in season.itertuples()}
seas = np.ones((5, N_WEEKS + 1))
for w, month in zip(dd["week_key"], dd["week_start"].dt.month):
    for ch in range(1, 5):
        seas[ch, w] = season_lookup[(ch, month)]
deseas = units / seas[None, :, :]

blocked = np.zeros((49, 5, N_WEEKS + 1), dtype=bool)         # promotion weeks and their 3-week dip
for p in promos.itertuples():
    blocked[p.product_key, p.channel_key, p.start_week_key:min(p.end_week_key + 3, N_WEEKS) + 1] = True

pe = promos.merge(prod, on="product_key").merge(eps, on=["category", "ownership", "channel_key"])
rows = []
for r in pe.itertuples():
    event = deseas[r.product_key, r.channel_key, r.start_week_key:r.end_week_key + 1].mean()
    base_weeks = np.arange(max(1, r.start_week_key - 8), r.start_week_key)
    base_weeks = base_weeks[~blocked[r.product_key, r.channel_key, base_weeks]]
    if len(base_weeks) < 3:
        continue
    base = deseas[r.product_key, r.channel_key, base_weeks].mean()
    if base <= 0:
        continue
    theo = (1 - r.discount_pct) ** r.elasticity * (1.20 if r.mechanic == "Price + visibility support" else 1.0)
    rows.append((r.channel_key, theo, event / base))

res = pd.DataFrame(rows, columns=["channel_key", "theoretical_uplift", "observed_uplift"])
out = res.groupby("channel_key").agg(events=("observed_uplift", "size"),
                                     theoretical=("theoretical_uplift", "mean"),
                                     observed=("observed_uplift", "mean"))
out.loc["All"] = [len(res), res["theoretical_uplift"].mean(), res["observed_uplift"].mean()]
out["observed_over_theoretical"] = out["observed"] / out["theoretical"]
out.round(2)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Prepare the monthly time axis for fact_cost.
# 1) Add month_start (first day of the month of the week's Monday) to dim_date.
# 2) Build dim_month: one row per month (36 rows), taking the month attributes
#    from dim_date, so both tables always agree.
# dim_date is overwritten with the extra column; its other columns stay as they
# were. Dates are saved as pure dates. The last lines check that every month of
# fact_cost exists in dim_month.
# ---------------------------------------------------------------
import pandas as pd

dd = spark.table("dim_date").toPandas()
dd["week_start"] = pd.to_datetime(dd["week_start"])
dd["week_end"] = pd.to_datetime(dd["week_end"])
dd["month_start"] = dd["week_start"].dt.to_period("M").dt.to_timestamp()

dim_month = dd.groupby("month_start", as_index=False).agg(
    year=("year", "first"), quarter=("quarter", "first"), month=("month", "first"),
    month_name=("month_name", "first"), year_month=("year_month", "first"),
)

for col in ["week_start", "week_end", "month_start"]:
    dd[col] = dd[col].dt.date
dim_month["month_start"] = dim_month["month_start"].dt.date

for name, pdf in {"dim_date": dd, "dim_month": dim_month}.items():
    (spark.createDataFrame(pdf)
          .write.mode("overwrite")
          .option("overwriteSchema", "true")
          .format("delta")
          .saveAsTable(name))

print("dim_date", spark.table("dim_date").count(), "| dim_month", spark.table("dim_month").count())
print("dim_date columns:", spark.table("dim_date").columns)
print("fact_cost months missing in dim_month:", spark.sql(
    "SELECT COUNT(*) FROM fact_cost f LEFT ANTI JOIN dim_month m ON f.month_start = m.month_start").first()[0])
spark.table("dim_month").orderBy("month_start").show(3)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ---------------------------------------------------------------
# Helper table for the gross-to-net waterfall on report page 1.
# The waterfall needs a column of categories (the steps), but our steps are
# measures, so we list them here: one row per step, with its order.
# The last bar (net sales) is added by the chart itself as a total, so it is
# not listed. This table has no relationship in the semantic model.
# ---------------------------------------------------------------
import pandas as pd

steps = pd.DataFrame({
    "step_order": [1, 2, 3, 4, 5, 6],
    "step": ["Gross sales", "Promotions", "On-invoice discount",
             "Volume rebate (rappel)", "Early-payment discount", "Marketing contribution"],
})

(spark.createDataFrame(steps)
      .write.mode("overwrite")
      .option("overwriteSchema", "true")
      .format("delta")
      .saveAsTable("dim_waterfall_step"))

spark.table("dim_waterfall_step").orderBy("step_order").show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 11c: read-only diagnostic - each discount layer as % of gross sales by month, to explain the Dec 2024 - Jan 2025 dip in net/gross
df = spark.sql("""
    SELECT d.month_start,
           ROUND(100 * SUM(f.promo_discount)         / SUM(f.gross_sales), 2) AS promo_pct,
           ROUND(100 * SUM(f.on_invoice_discount)    / SUM(f.gross_sales), 2) AS on_invoice_pct,
           ROUND(100 * SUM(f.rappel)                 / SUM(f.gross_sales), 2) AS rappel_pct,
           ROUND(100 * SUM(f.early_payment_discount) / SUM(f.gross_sales), 2) AS early_pct,
           ROUND(100 * SUM(f.marketing_contribution) / SUM(f.gross_sales), 2) AS marketing_pct,
           ROUND(100 * SUM(f.net_sales)              / SUM(f.gross_sales), 2) AS net_to_gross_pct
    FROM fact_sales f
    JOIN dim_date d ON f.week_key = d.week_key
    GROUP BY d.month_start
    ORDER BY d.month_start
""")
df.show(40, truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 11d: read-only diagnostic - promotions with the largest discount in Dec 2024 and Jan 2025, to explain the promo spike
df = spark.sql("""
    SELECT p.promotion_id, p.campaign, p.channel_key, p.product_key, p.mechanic, p.discount_pct,
           p.start_week_key, p.end_week_key,
           SUM(f.units)                        AS units,
           ROUND(SUM(f.gross_sales), 2)        AS gross_sales,
           ROUND(SUM(f.promo_discount), 2)     AS promo_discount
    FROM fact_sales f
    JOIN dim_date d       ON f.week_key = d.week_key
    JOIN fact_promotion p ON f.promotion_id = p.promotion_id
    WHERE d.month_start BETWEEN '2024-12-01' AND '2025-01-01'
    GROUP BY p.promotion_id, p.campaign, p.channel_key, p.product_key, p.mechanic,
             p.discount_pct, p.start_week_key, p.end_week_key
    ORDER BY promo_discount DESC
    LIMIT 15
""")
df.show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 15a: read-only check - schemas and sample rows of the tables needed for the FX and raw-cost columns
for t in ["slv_ecb_usd_eur", "fact_cost", "dim_month"]:
    print("=====", t, "=====")
    df = spark.table(t)
    df.printSchema()
    df.show(3, truncate=False)
    print("rows:", df.count())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 15b: add the monthly average USD per EUR rate (ECB) to dim_month; it feeds the FX effect of the margin bridge
import pandas as pd

dim_month = spark.table("dim_month").toPandas()
ecb = spark.table("slv_ecb_usd_eur").toPandas()

# Drop the column first so the cell can be re-run safely, then left-join on the month
dim_month = dim_month.drop(columns=["usd_per_eur"], errors="ignore").merge(ecb, on="month_start", how="left")
print("months without rate:", int(dim_month["usd_per_eur"].isna().sum()))

(spark.createDataFrame(dim_month)
      .write.format("delta").mode("overwrite")
      .option("overwriteSchema", "true")
      .saveAsTable("dim_month"))

spark.table("dim_month").orderBy("month_start").show(36, truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 15c: add raw_cogs (units x raw material cost per unit of that product and month) to fact_sales
from pyspark.sql import functions as F

sales = spark.table("fact_sales").drop("raw_cogs")          # drop first so the cell can be re-run
week_month = spark.table("dim_date").select("week_key", "month_start")
raw_cost = spark.table("fact_cost").select("product_key", "month_start", "raw_material_cost")

new_sales = (sales.join(week_month, "week_key", "left")
                  .join(raw_cost, ["product_key", "month_start"], "left")
                  .withColumn("raw_cogs", F.round(F.col("units") * F.col("raw_material_cost"), 4))
                  .select(*sales.columns, "raw_cogs"))      # keep the original column order, new column last

new_sales = new_sales.cache()
n_before, n_after = sales.count(), new_sales.count()
print("rows before:", n_before, "| rows after:", n_after)
print("rows without raw_cogs:", new_sales.filter(F.col("raw_cogs").isNull()).count())

new_sales.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("fact_sales")

chk = spark.table("fact_sales").agg(
    F.round(F.sum("gross_sales"), 2).alias("gross_sales"),
    F.round(F.sum("cogs"), 2).alias("cogs"),
    F.round(F.sum("raw_cogs"), 2).alias("raw_cogs"))
chk.show()
chk.select((100 * F.col("raw_cogs") / F.col("cogs")).alias("raw_share_pct")).show()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 15e: helper table with one row per step of the gross margin bridge (prior year to current year); no relationships, ordered by step_order
import pandas as pd

steps = pd.DataFrame({
    "step_order": [1, 2, 3, 4, 5, 6, 7, 8],
    "step": ["Prior-year margin", "Volume", "Mix", "List price", "Discounts & terms",
             "Raw material cost", "FX", "Other cost"]
})

(spark.createDataFrame(steps)
      .write.format("delta").mode("overwrite")
      .option("overwriteSchema", "true")
      .saveAsTable("dim_pvm_step"))

spark.table("dim_pvm_step").orderBy("step_order").show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 16a: read-only check - schemas and sample rows of the tables needed to build fact_promo_performance
for t in ["fact_promotion", "sim_param_elasticity", "dim_product", "dim_customer", "dim_channel"]:
    print("=====", t, "=====")
    df = spark.table(t)
    df.printSchema()
    df.show(3, truncate=False)

print("===== week range =====")
spark.sql("SELECT MIN(week_key) AS min_week, MAX(week_key) AS max_week FROM dim_date").show()

print("===== events starting in the first 4 weeks =====")
spark.sql("SELECT COUNT(*) AS events_without_full_baseline FROM fact_promotion WHERE start_week_key <= 4").show()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 16b: estimate for each promotion event the baseline (4 weeks before, excluding promo and post-promo dip weeks), the uplift during the promo and the shortfall in the 3 weeks after
import numpy as np
import pandas as pd
from pyspark.sql import functions as F

N_WEEKS, BASE_WEEKS, DIP_WEEKS = 156, 4, 3

# Weekly units and margin per channel x product (all customers of the channel together)
weekly = (spark.table("fact_sales")
          .join(spark.table("dim_customer").select("customer_key", "channel_key"), "customer_key")
          .groupBy("channel_key", "product_key", "week_key")
          .agg(F.sum("units").alias("units"),
               F.sum(F.col("net_sales") - F.col("cogs")).alias("margin"))
          .toPandas())
events = spark.table("fact_promotion").toPandas()

# One array per channel x product that has events, indexed by week_key (position 0 unused); weeks without sales stay at zero
keys = {(int(c), int(p)) for c, p in events[["channel_key", "product_key"]].to_numpy()}
units = {k: np.zeros(N_WEEKS + 2) for k in keys}
margin = {k: np.zeros(N_WEEKS + 2) for k in keys}
is_promo = {k: np.zeros(N_WEEKS + 2, dtype=bool) for k in keys}
is_dip = {k: np.zeros(N_WEEKS + 2, dtype=bool) for k in keys}

for r in weekly.itertuples(index=False):
    k = (int(r.channel_key), int(r.product_key))
    if k in units:
        units[k][int(r.week_key)] = float(r.units)
        margin[k][int(r.week_key)] = float(r.margin)

# Mark promo weeks and the DIP_WEEKS weeks after each event
for e in events.itertuples(index=False):
    k = (int(e.channel_key), int(e.product_key))
    s, t = int(e.start_week_key), int(e.end_week_key)
    is_promo[k][s:t + 1] = True
    is_dip[k][t + 1:min(t + DIP_WEEKS, N_WEEKS) + 1] = True

rows = []
for e in events.itertuples(index=False):
    k = (int(e.channel_key), int(e.product_key))
    s, t = int(e.start_week_key), int(e.end_week_key)
    duration = t - s + 1
    # Baseline weeks: the BASE_WEEKS before the start, skipping promo and dip weeks of any event of this channel x product
    window = [w for w in range(max(1, s - BASE_WEEKS), s) if not is_promo[k][w] and not is_dip[k][w]]
    post = list(range(t + 1, min(t + DIP_WEEKS, N_WEEKS) + 1))
    promo_units = units[k][s:t + 1].sum()
    post_units = units[k][post].sum() if post else 0.0
    if window:
        base_pw = units[k][window].mean()
        base_u = units[k][window].sum()
        base_mpu = margin[k][window].sum() / base_u if base_u > 0 else np.nan
    else:
        base_pw, base_mpu = np.nan, np.nan
    base_in_promo = base_pw * duration
    rows.append({
        "promotion_id": int(e.promotion_id),
        "baseline_weeks_used": len(window),
        "base_units_per_week": base_pw,
        "base_margin_per_unit": base_mpu,
        "promo_units": promo_units,
        "base_units_in_promo": base_in_promo,
        "incremental_units": promo_units - base_in_promo,
        "uplift_pct": (promo_units / base_in_promo - 1) if base_in_promo and base_in_promo > 0 else np.nan,
        "post_weeks": len(post),
        "post_units": post_units,
        "dip_units": (base_pw * len(post) - post_units) if window else np.nan,
    })

perf = pd.DataFrame(rows)

print("events:", len(perf))
print("events with at least 1 baseline week and base > 0:", int(perf["uplift_pct"].notna().sum()))
print("events with fewer than 4 baseline weeks:", int((perf["baseline_weeks_used"] < BASE_WEEKS).sum()))
print("\nuplift_pct summary (all events with baseline):")
print(perf["uplift_pct"].describe().round(4))
ok = perf.dropna(subset=["uplift_pct"])
print("\ntotal incremental units:", round(ok["incremental_units"].sum(), 1),
      "| total dip units:", round(ok["dip_units"].sum(), 1))
perf.head(5)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 16c: add actual promo money (margin, support cost) and the return calculation to the per-event baseline results, then save fact_promo_performance
import numpy as np
import pandas as pd
from pyspark.sql import functions as F

# Actual money during the promo weeks: all fact_sales rows tagged with each promotion_id
promo_money = (spark.table("fact_sales")
               .filter(F.col("promotion_id").isNotNull())
               .groupBy("promotion_id")
               .agg(F.sum("units").alias("promo_units_sales"),
                    F.sum("gross_sales").alias("promo_gross_sales"),
                    F.sum("promo_discount").alias("promo_discount"),
                    F.sum("net_sales").alias("promo_net_sales"),
                    F.sum("cogs").alias("promo_cogs"),
                    F.sum("promo_support_cost").alias("promo_support_cost"))
               .toPandas())
promo_money["promotion_id"] = promo_money["promotion_id"].astype(int)

events = spark.table("fact_promotion").toPandas()
df = (events.merge(perf, on="promotion_id", how="left")
            .merge(promo_money, on="promotion_id", how="left"))

# Consistency check: units tagged in fact_sales must equal the channel x product units of the promo weeks used in 16b
print("max difference in promo units:", float((df["promo_units"] - df["promo_units_sales"]).abs().max()))

# Return calculation (money columns stay empty when the event has no baseline)
df["has_baseline"] = df["uplift_pct"].notna()
df["promo_margin"] = df["promo_net_sales"] - df["promo_cogs"]
df["baseline_margin_in_promo"] = df["base_units_in_promo"] * df["base_margin_per_unit"]
df["incremental_margin"] = df["promo_margin"] - df["baseline_margin_in_promo"]
df["dip_margin_loss"] = df["dip_units"] * df["base_margin_per_unit"]
df["net_incremental_margin"] = df["incremental_margin"] - df["promo_support_cost"] - df["dip_margin_loss"]
df["promo_investment"] = df["promo_discount"] + df["promo_support_cost"]
df["roi"] = np.where(df["promo_investment"] > 0, df["net_incremental_margin"] / df["promo_investment"], np.nan)

cols = ["promotion_id", "campaign", "channel_key", "product_key", "mechanic", "discount_pct",
        "start_week_key", "end_week_key", "duration_weeks", "has_baseline", "baseline_weeks_used",
        "base_units_per_week", "base_margin_per_unit", "promo_units", "base_units_in_promo",
        "incremental_units", "uplift_pct", "post_weeks", "post_units", "dip_units",
        "promo_gross_sales", "promo_discount", "promo_net_sales", "promo_cogs", "promo_support_cost",
        "promo_margin", "baseline_margin_in_promo", "incremental_margin", "dip_margin_loss",
        "net_incremental_margin", "promo_investment", "roi"]
out = df[cols].copy()
money = ["promo_gross_sales", "promo_discount", "promo_net_sales", "promo_cogs", "promo_support_cost",
         "promo_margin", "baseline_margin_in_promo", "incremental_margin", "dip_margin_loss",
         "net_incremental_margin", "promo_investment"]
out[money] = out[money].round(2)

# Save: NaN values become real nulls so the semantic model sees them as blank
sdf = spark.createDataFrame(out)
for c, t in sdf.dtypes:
    if t == "double":
        sdf = sdf.withColumn(c, F.when(F.isnan(F.col(c)), F.lit(None)).otherwise(F.col(c)))
sdf.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("fact_promo_performance")

ok = out[out["has_baseline"]]
print("rows saved:", len(out), "| events analysed:", len(ok))
print("total promo discount:", round(ok["promo_discount"].sum(), 2),
      "| support cost:", round(ok["promo_support_cost"].sum(), 2))
print("total net incremental margin:", round(ok["net_incremental_margin"].sum(), 2))
print("events with negative net incremental margin:", int((ok["net_incremental_margin"] < 0).sum()), "of", len(ok))
print(ok.groupby("campaign")[["incremental_units", "promo_discount", "net_incremental_margin"]].sum().round(2))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 16d: save sim_promo_truth with the true uplift of each event (same formula as the sales
# generation, including PROMO_RESPONSE) and print the estimated-vs-true uplift comparison.
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

PROMO_RESPONSE = 4.0   # must match the value used in the sales generation cell

perf_saved = spark.table("fact_promo_performance").toPandas()
prod = spark.table("dim_product").select("product_key", "category", "ownership").toPandas()
elas = spark.table("sim_param_elasticity").toPandas()

d = (perf_saved.merge(prod, on="product_key", how="left")
               .merge(elas, on=["category", "ownership", "channel_key"], how="left"))
base_effect = (1 - d["discount_pct"]) ** d["elasticity"] * np.where(d["mechanic"].str.contains("visibility"), 1.20, 1.0)
d["true_uplift_pct"] = PROMO_RESPONSE * (base_effect - 1)

# Save the truth for all events (also those without baseline), used later to validate the estimates
(spark.createDataFrame(d[["promotion_id", "true_uplift_pct"]])
      .write.format("delta").mode("overwrite").option("overwriteSchema", "true")
      .saveAsTable("sim_promo_truth"))
print("sim_promo_truth saved:", spark.table("sim_promo_truth").count(), "rows")

ok = d[d["has_baseline"]].copy()
ok["all_events"] = "all"
ok["true_units"] = ok["base_units_in_promo"] * (1 + ok["true_uplift_pct"])
ok["error_pts"] = (ok["uplift_pct"] - ok["true_uplift_pct"]) * 100

def table(by):
    # Uplift weighted by baseline volume: estimated (from sales) vs true (from the simulation parameters)
    g = ok.groupby(by).agg(events=("promotion_id", "count"), promo_units=("promo_units", "sum"),
                           base=("base_units_in_promo", "sum"), true_units=("true_units", "sum"))
    g["est_uplift_%"] = ((g["promo_units"] / g["base"] - 1) * 100).round(2)
    g["true_uplift_%"] = ((g["true_units"] / g["base"] - 1) * 100).round(2)
    return g[["events", "est_uplift_%", "true_uplift_%"]]

report = "\n".join([
    "All events:", table("all_events").to_string(),
    "\nBy campaign:", table("campaign").to_string(),
    "\nBy channel_key:", table("channel_key").to_string(),
    "\ncorrelation per event: " + str(round(ok[["uplift_pct", "true_uplift_pct"]].corr().iloc[0, 1], 3)),
    "error per event (pts): mean " + str(round(ok["error_pts"].mean(), 2)) + " | median " + str(round(ok["error_pts"].median(), 2)),
    "dip units / incremental units: " + str(round(ok["dip_units"].sum() / ok["incremental_units"].sum(), 3)) + " (simulated: 0,30)",
])
print(report)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 16f: add the two columns that split the incremental margin (margin on extra units and discount given away on baseline units) and check they close with net_incremental_margin
from pyspark.sql import functions as F

df = (spark.table("fact_promo_performance")
           .drop("margin_on_extra_units", "discount_on_base_units"))      # drop first so the cell can be re-run

promo_margin_per_unit = F.col("promo_margin") / F.col("promo_units")
df = (df.withColumn("margin_on_extra_units", F.round(F.col("incremental_units") * promo_margin_per_unit, 2))
        .withColumn("discount_on_base_units",
                    F.round(F.col("base_units_in_promo") * (F.col("base_margin_per_unit") - promo_margin_per_unit), 2)))

df = df.cache()
print("rows:", df.count())
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("fact_promo_performance")

chk = (spark.table("fact_promo_performance").filter("has_baseline")
       .withColumn("gap", F.col("margin_on_extra_units") - F.col("discount_on_base_units")
                          - F.col("promo_support_cost") - F.col("dip_margin_loss") - F.col("net_incremental_margin")))
chk.agg(F.round(F.max(F.abs(F.col("gap"))), 2).alias("max_abs_gap_per_event"),
        F.round(F.sum("margin_on_extra_units"), 2).alias("margin_on_extra_units"),
        F.round(F.sum("discount_on_base_units"), 2).alias("discount_on_base_units"),
        F.round(F.sum("promo_support_cost"), 2).alias("promo_support_cost"),
        F.round(F.sum("dip_margin_loss"), 2).alias("dip_margin_loss"),
        F.round(F.sum("net_incremental_margin"), 2).alias("net_incremental_margin")).show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# 16g: helper table with one row per step of the promotion economics waterfall; no relationships, ordered by step_order
import pandas as pd

steps = pd.DataFrame({
    "step_order": [1, 2, 3, 4],
    "step": ["Margin on extra units", "Discount on baseline units", "Promo support cost", "Post-promo dip"]
})

(spark.createDataFrame(steps)
      .write.format("delta").mode("overwrite")
      .option("overwriteSchema", "true")
      .saveAsTable("dim_promo_step"))

spark.table("dim_promo_step").orderBy("step_order").show(truncate=False)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Cell 16h (read-only): what-if grid on promo events.
# Re-computes net incremental margin per event under alternative promo response (k)
# and discount depth (s) multipliers. Nothing is saved to the Lakehouse.
import pandas as pd
import numpy as np

perf = spark.table("fact_promo_performance").toPandas()
truth = spark.table("sim_promo_truth").toPandas()[["promotion_id", "true_uplift_pct"]]

ev = perf[perf["has_baseline"] == True].merge(truth, on="promotion_id", how="left").copy()
ev = ev[ev["promo_units"] > 0].copy()

# Per-event building blocks
B = ev["base_units_in_promo"].astype(float)            # units we would have sold anyway during the event
m = ev["base_margin_per_unit"].astype(float)           # margin per unit at normal conditions
d_unit = ev["promo_discount"] / ev["promo_units"]      # promo discount per promoted unit
g_unit = ev["promo_gross_sales"] / ev["promo_units"]   # gross sales per promoted unit
u_true = ev["true_uplift_pct"].astype(float)           # true uplift used by the simulation

DIP_SHARE = 0.30       # post-promo dip = 30% of incremental units
SUPPORT_RATE = 0.03    # support cost = 3% of promoted gross sales

def scenario(k, s):
    """Return per-event net incremental margin and investment for response k and discount scale s."""
    U = B * (1 + k * u_true)                            # promoted units
    inc = U - B                                         # incremental units
    promo_margin = U * (m - d_unit * s - SUPPORT_RATE * g_unit)
    dip_loss = DIP_SHARE * inc * m
    net = promo_margin - B * m - dip_loss
    invest = U * d_unit * s + SUPPORT_RATE * U * g_unit
    return net, invest

# Calibration: k=1, s=1 should resemble the real result
net0, inv0 = scenario(1.0, 1.0)
print("CALIBRATION (model k=1, s=1 vs real)")
print(f"  events: {len(ev)}")
print(f"  model: profitable {(net0 > 0).sum()} | sum net {net0.sum():,.0f} | ROI {net0.sum() / inv0.sum():.2%}")
print(f"  real : profitable {(ev['net_incremental_margin'] > 0).sum()} | sum net {ev['net_incremental_margin'].sum():,.0f} | ROI {ev['roi'].mul(ev['promo_investment']).sum() / ev['promo_investment'].sum():.2%}")

# Grid
ks = [1.0, 1.5, 2.0, 3.0]
ss = [1.0, 0.75, 0.5]
rows = []
for k in ks:
    for s in ss:
        net, inv = scenario(k, s)
        rows.append({"k": k, "s": s,
                     "pct_profitable": round((net > 0).mean() * 100, 2),
                     "sum_net_margin": round(net.sum(), 2),
                     "roi_pct": round(net.sum() / inv.sum() * 100, 2)})
grid = pd.DataFrame(rows)

print("\n% of events profitable")
print(grid.pivot(index="k", columns="s", values="pct_profitable").to_string())
print("\nROI % on promo spend")
print(grid.pivot(index="k", columns="s", values="roi_pct").to_string())
print("\nAverage discount per event (info)")
print(f"  mean discount as % of gross per unit: {(d_unit / g_unit).mean():.2%}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Cell 16j (read-only): extended what-if. Adds higher response (k up to 5),
# and a margin-aware cap on discount depth (discount <= cap x unit margin).
# Nothing is saved to the Lakehouse.
import pandas as pd
import numpy as np

perf = spark.table("fact_promo_performance").toPandas()
truth = spark.table("sim_promo_truth").toPandas()[["promotion_id", "true_uplift_pct"]]

ev = perf[perf["has_baseline"] == True].merge(truth, on="promotion_id", how="left").copy()
ev = ev[ev["promo_units"] > 0].copy()

B = ev["base_units_in_promo"].astype(float)
m = ev["base_margin_per_unit"].astype(float)
d_unit = ev["promo_discount"] / ev["promo_units"]
g_unit = ev["promo_gross_sales"] / ev["promo_units"]
u_true = ev["true_uplift_pct"].astype(float)

DIP_SHARE = 0.30
SUPPORT_RATE = 0.03

def scenario(k, s_vec):
    """Net incremental margin and investment; s_vec is a per-event discount scale."""
    d = d_unit * s_vec
    U = B * (1 + k * u_true)
    inc = U - B
    promo_margin = U * (m - d - SUPPORT_RATE * g_unit)
    dip_loss = DIP_SHARE * inc * m
    net = promo_margin - B * m - dip_loss
    invest = U * d + SUPPORT_RATE * U * g_unit
    return net, invest

# 1) How big is the discount relative to the unit margin?
ratio = (d_unit / m).replace([np.inf, -np.inf], np.nan)
print("DISCOUNT / UNIT MARGIN (per event)")
print(ratio.describe(percentiles=[.1, .25, .5, .75, .9]).round(2).to_string())
print(f"\nunit margin as % of gross (mean): {(m / g_unit).mean():.2%}")
print(f"events with discount >= unit margin: {(ratio >= 1).sum()} of {len(ratio)}")

# 2) By channel
tmp = ev[["channel_key"]].copy()
tmp["ratio"] = ratio.values
net3, _ = scenario(3.0, np.ones(len(ev)))
tmp["profitable_k3"] = (net3.values > 0)
print("\nBY CHANNEL (k=3, s=1)")
print(tmp.groupby("channel_key").agg(events=("ratio", "size"),
                                     mean_ratio=("ratio", "mean"),
                                     pct_profitable=("profitable_k3", "mean")).round(3).to_string())

# 3) Extended grid with margin-aware cap: s = min(1, cap * m / d_unit)
ks = [2.0, 3.0, 4.0, 5.0]
caps = [None, 0.75, 0.5, 0.35]
rows = []
for k in ks:
    for cap in caps:
        s_vec = np.ones(len(ev)) if cap is None else np.minimum(1.0, cap * m / d_unit).clip(lower=0).values
        net, inv = scenario(k, s_vec)
        rows.append({"k": k, "cap": "none" if cap is None else cap,
                     "pct_profitable": round((net > 0).mean() * 100, 2),
                     "roi_pct": round(net.sum() / inv.sum() * 100, 2)})
grid = pd.DataFrame(rows)
print("\n% of events profitable (cap = max discount as share of unit margin)")
print(grid.pivot(index="k", columns="cap", values="pct_profitable").to_string())
print("\nROI % on promo spend")
print(grid.pivot(index="k", columns="cap", values="roi_pct").to_string())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Cell 16k (read-only): what-if restricted to events whose unit margin is high enough.
# Simulates a "promote only products with enough margin" rule using the existing events.
# Nothing is saved to the Lakehouse.
import pandas as pd
import numpy as np

perf = spark.table("fact_promo_performance").toPandas()
truth = spark.table("sim_promo_truth").toPandas()[["promotion_id", "true_uplift_pct"]]

ev = perf[perf["has_baseline"] == True].merge(truth, on="promotion_id", how="left").copy()
ev = ev[ev["promo_units"] > 0].copy()

B = ev["base_units_in_promo"].astype(float)
m = ev["base_margin_per_unit"].astype(float)
d_unit = ev["promo_discount"] / ev["promo_units"]
g_unit = ev["promo_gross_sales"] / ev["promo_units"]
u_true = ev["true_uplift_pct"].astype(float)
margin_pct = m / g_unit          # unit margin as share of gross

DIP_SHARE = 0.30
SUPPORT_RATE = 0.03

def scenario(k, s_vec, mask):
    d = d_unit * s_vec
    U = B * (1 + k * u_true)
    inc = U - B
    promo_margin = U * (m - d - SUPPORT_RATE * g_unit)
    net = promo_margin - B * m - DIP_SHARE * inc * m
    invest = U * d + SUPPORT_RATE * U * g_unit
    return net[mask], invest[mask]

# 1) How many events have each margin level
print("EVENTS BY UNIT MARGIN (% of gross)")
bins = [-np.inf, 0, 0.05, 0.10, 0.20, 0.30, np.inf]
labels = ["<=0", "0-5%", "5-10%", "10-20%", "20-30%", ">30%"]
print(pd.cut(margin_pct, bins=bins, labels=labels).value_counts().reindex(labels).to_string())

# 2) Eligible subsets: minimum unit margin % required to promote
rows = []
for t in [0.0, 0.10, 0.20, 0.30]:
    mask = (margin_pct >= t).values
    for k in [2.0, 3.0, 4.0]:
        for cap in [None, 0.5]:
            s_vec = np.ones(len(ev)) if cap is None else np.minimum(1.0, cap * m / d_unit).clip(lower=0).values
            net, inv = scenario(k, s_vec, mask)
            avg_disc_pct = ((d_unit * s_vec / g_unit)[mask]).mean() * 100
            rows.append({"min_margin": t, "k": k, "cap": "none" if cap is None else cap,
                         "events": int(mask.sum()),
                         "pct_profitable": round((net > 0).mean() * 100, 2),
                         "roi_pct": round(net.sum() / inv.sum() * 100, 2),
                         "avg_discount_pct": round(avg_disc_pct, 2)})
res = pd.DataFrame(rows)
print("\nRESULTS (min_margin = minimum unit margin as share of gross to be promoted)")
print(res.to_string(index=False))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Read-only: estimate unit margin (% of gross) per product x channel from upstream tables
# (price list, unit cost, customer terms, assortment) and validate it against the
# margin observed in the existing promotion events. Nothing is saved.
import numpy as np
import pandas as pd

prod = spark.table("dim_product").toPandas()
cust = spark.table("dim_customer").toPandas()[["customer_key", "channel_key"]]

# Product x channel pairs that are actually sold (via the customer assortment)
assort = spark.table("sim_customer_assortment").toPandas().merge(cust, on="customer_key")
pairs = assort[["product_key", "channel_key"]].drop_duplicates()

# Average list price per product x channel, average unit cost per product
price = (spark.table("fact_price_list").toPandas()
         .groupby(["product_key", "channel_key"], as_index=False)["list_price"].mean())
cost = (spark.table("fact_cost").toPandas()
        .groupby("product_key", as_index=False)["unit_cost"].mean())

# Average total terms per channel (as a fraction of gross)
terms = spark.table("fact_customer_terms").toPandas().merge(cust, on="customer_key")
scale = 100.0 if terms["total_terms_pct"].max() > 1 else 1.0
terms_ch = terms.groupby("channel_key", as_index=False)["total_terms_pct"].mean()
terms_ch["terms"] = terms_ch["total_terms_pct"] / scale

m = (pairs.merge(price, on=["product_key", "channel_key"])
          .merge(cost, on="product_key")
          .merge(terms_ch[["channel_key", "terms"]], on="channel_key"))
m["margin_pct"] = (1 - m["terms"]) - m["unit_cost"] / m["list_price"]

# 1) Validation against the margin observed in the existing events
perf = spark.table("fact_promo_performance").toPandas()
perf = perf[(perf["has_baseline"] == True) & (perf["promo_units"] > 0)].copy()
perf["obs_margin_pct"] = perf["base_margin_per_unit"] / (perf["promo_gross_sales"] / perf["promo_units"])
chk = perf.merge(m[["product_key", "channel_key", "margin_pct"]], on=["product_key", "channel_key"], how="left")
print("VALIDATION (events with a computed margin):", int(chk["margin_pct"].notna().sum()), "of", len(chk))
print("  correlation observed vs computed:", round(chk[["obs_margin_pct", "margin_pct"]].corr().iloc[0, 1], 3))
print("  mean abs difference (points of gross):", round((chk["obs_margin_pct"] - chk["margin_pct"]).abs().mean() * 100, 2))

# 2) Eligibility by channel
print("\nELIGIBILITY BY CHANNEL (margin >= 20% of gross)")
rows = []
for ch, g in m.groupby("channel_key"):
    rows.append({"channel_key": ch,
                 "pairs_sold": len(g),
                 "mean_margin_pct": round(g["margin_pct"].mean() * 100, 2),
                 "eligible_20": int((g["margin_pct"] >= 0.20).sum()),
                 "eligible_30": int((g["margin_pct"] >= 0.30).sum()),
                 "margin_le_0": int((g["margin_pct"] <= 0).sum())})
print(pd.DataFrame(rows).to_string(index=False))
print("\nEvents needed per channel today: Retail(2) 144, Online(4) 60 (8+6+6 per year, no repeat in a window), O&V(3) 24, Horeca(1) 12")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Read-only sanity checks on the regenerated fact_sales: keys, nulls, activity windows,
# assortment, arithmetic identities and a few ratios by year, channel and ownership.
# Nothing is saved.
import numpy as np
import pandas as pd

s = spark.table("fact_sales").toPandas()
cust = spark.table("dim_customer").toPandas()[["customer_key", "channel_key", "start_week_key", "end_week_key"]]
prod = spark.table("dim_product").toPandas()[["product_key", "ownership"]]
dd = spark.table("dim_date").toPandas()[["week_key", "year"]]
assort = spark.table("sim_customer_assortment").toPandas()
promo = spark.table("fact_promotion").toPandas()

print("rows:", len(s), "| nulls outside promotion_id:", int(s.drop(columns="promotion_id").isna().sum().sum()))
print("orphan customers:", int((~s["customer_key"].isin(cust["customer_key"])).sum()),
      "| products:", int((~s["product_key"].isin(prod["product_key"])).sum()),
      "| weeks:", int((~s["week_key"].isin(dd["week_key"])).sum()),
      "| promotion_id:", int((~s["promotion_id"].dropna().isin(promo["promotion_id"])).sum()))

x = s.merge(cust, on="customer_key")
print("rows outside customer active weeks:",
      int(((x["week_key"] < x["start_week_key"]) | (x["week_key"] > x["end_week_key"])).sum()))
a = s[["customer_key", "product_key"]].drop_duplicates().merge(
    assort.assign(ok=1), how="left", on=["customer_key", "product_key"])
print("customer x SKU pairs outside assortment:", int(a["ok"].isna().sum()))
print("units <= 0:", int((s["units"] <= 0).sum()))

# Arithmetic identities
disc_cols = ["promo_discount", "on_invoice_discount", "rappel", "early_payment_discount", "marketing_contribution"]
net_calc = s["gross_sales"] - s[disc_cols].sum(axis=1)
print("max |units x list_price - gross_sales|:", round(float((s["units"] * s["list_price"] - s["gross_sales"]).abs().max()), 3),
      "| max |gross - discounts - net_sales|:", round(float((net_calc - s["net_sales"]).abs().max()), 3))

# Ratios by year, channel and ownership
s = (s.merge(dd, on="week_key")
      .merge(cust[["customer_key", "channel_key"]], on="customer_key")
      .merge(prod, on="product_key"))
s["terms"] = s[["on_invoice_discount", "rappel", "early_payment_discount", "marketing_contribution"]].sum(axis=1)

def ratios(df, by):
    g = df.groupby(by).agg(gross=("gross_sales", "sum"), promo=("promo_discount", "sum"),
                           terms=("terms", "sum"), net=("net_sales", "sum"), cogs=("cogs", "sum"))
    g["promo_pct_gross"] = (g["promo"] / g["gross"] * 100).round(2)
    g["terms_pct_gross"] = (g["terms"] / g["gross"] * 100).round(2)
    g["margin_pct_gross"] = ((g["net"] - g["cogs"]) / g["gross"] * 100).round(2)
    return g[["promo_pct_gross", "terms_pct_gross", "margin_pct_gross"]]

for by in ["year", "channel_key", "ownership"]:
    print("\nby", by)
    print(ratios(s, by).to_string())

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Add base_margin_pct to fact_promo_performance: unit margin before the promotion as a share
# of gross price per unit (base_margin_per_unit / promo gross sales per promoted unit).
# Used as the X axis of the promotions scatter. Null when the event has no baseline.
from pyspark.sql import functions as F

df = spark.table("fact_promo_performance").drop("base_margin_pct")      # drop first so the cell can be re-run

gross_per_unit = F.col("promo_gross_sales") / F.col("promo_units")
df = df.withColumn("base_margin_pct",
                   F.when(F.col("has_baseline") & (F.col("promo_units") > 0),
                          F.round(F.col("base_margin_per_unit") / gross_per_unit, 4)))

df = df.cache()
print("rows:", df.count())
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("fact_promo_performance")

chk = spark.table("fact_promo_performance").filter("has_baseline")
chk.agg(F.count("base_margin_pct").alias("events_with_value"),
        F.round(F.min("base_margin_pct"), 4).alias("min"),
        F.round(F.avg("base_margin_pct"), 4).alias("mean"),
        F.round(F.max("base_margin_pct"), 4).alias("max")).show()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
