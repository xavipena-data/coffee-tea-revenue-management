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
