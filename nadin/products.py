import json
import re

import numpy as np
import pandas as pd

from nadin.models.project import ProjectPriceLevel

STRING_COLUMNS = ["name", "sku", "measurement", "description"]
MANDATORY_COLUMNS = ["name", "sku", "price", "cat_id"]


def option_columns_to_json(row: pd.Series) -> str:
    def parse_column(value: str) -> "list[str]":
        return sorted(list({s.strip() for s in str(value).split(",")})) if value else None

    result = {k: parse_column(v) for k, v in row.items() if v}
    return json.dumps(result, ensure_ascii=False) if result else ""


def price_columns_to_json(row: pd.Series) -> str:
    result = {}
    for col in [f"prices_{col.name}" for col in ProjectPriceLevel]:
        price_col = col.replace("prices_", "")
        if col not in row:
            continue
        result[price_col] = float(row[col] if row[col] else 0.0)
    return json.dumps(result)


def process_product_tags(product_ids: dict[str, int], df_tags: pd.DataFrame) -> pd.DataFrame:

    result = (
        df_tags.assign(
            product_id=df_tags["sku"].apply(product_ids.get),
            tag=df_tags["tags"].str.split(","),
        )
        .dropna(subset=["product_id"])
        .drop(df_tags.columns, axis=1)
        .explode("tag")
        .drop_duplicates()
        .assign(
            product_id=lambda x: x["product_id"].astype(int),
            tag=lambda x: x["tag"].str.lower().str.strip()[:128],
        )
        .replace("", np.nan)
        .dropna(subset=["tag"])
        .reset_index(drop=True)
    )

    print(result)

    return result


def clean_column_name(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower().strip())


def extra_columns_to_options(df: pd.DataFrame, known_columns: list[str]) -> pd.DataFrame:
    extra_columns = list(df.columns.difference(known_columns))
    if extra_columns:
        return df.assign(
            options=df[extra_columns].apply(option_columns_to_json, axis=1).replace("", None),
        ).drop(
            extra_columns,
            axis=1,
        )
    else:
        return df.drop("options", errors="ignore")


def process_price_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy(deep=False)
    price_columns = [f"prices_{col.name}" for col in ProjectPriceLevel]
    if "price" in df.columns:
        result["price"] = df["price"].apply(pd.to_numeric, errors="coerce")
    if any(col in df.columns for col in price_columns):
        result["prices"] = df.apply(price_columns_to_json, axis=1)
        result.drop(price_columns, axis=1, inplace=True, errors="ignore")
    return result


def process_category_column(df: pd.DataFrame, categories: "dict[str:int]") -> pd.DataFrame:
    if "category" in df.columns:
        return df.assign(cat_id=df["category"].str.lower().map(categories)).drop("category", axis=1)
    else:
        return df.drop("cat_id", axis=1, errors="ignore")


def process_images_column(df: pd.DataFrame) -> pd.DataFrame:
    if "images" in df.columns:
        return df.assign(
            images=df["images"].apply(lambda x: json.dumps([img.strip() for img in str(x).split(",")]) if x else None)
        )
    else:
        return df


def process_string_columns(df: pd.DataFrame, string_columns: list[str]) -> pd.DataFrame:
    result = df.copy(deep=False)
    for column in string_columns:
        if column not in df.columns:
            continue
        result[column] = (
            df[column].astype(str).str.slice(0, 128) if column == "name" else df[column].astype(str).str.slice(0, 512)
        )
    return result


def process_products(
    new_products: pd.DataFrame, existing_products: pd.DataFrame, categories: "dict[str:int]"
) -> pd.DataFrame:

    existing_products.drop(columns=["id", "vendor_id"], inplace=True, errors="ignore")
    existing_products.drop_duplicates(subset="sku", keep="last", inplace=True)

    new_products.columns = [clean_column_name(name) for name in new_products.columns]
    new_products = process_category_column(new_products, categories)
    new_products = process_price_columns(new_products)
    new_products = extra_columns_to_options(new_products, existing_products.columns)
    new_products = process_images_column(new_products)
    new_products = process_string_columns(new_products, STRING_COLUMNS)

    new_products.drop_duplicates(subset="sku", keep="last", inplace=True)

    df_combined = pd.merge(existing_products, new_products, on="sku", how="outer", suffixes=("_df1", "_df2"))

    for col in existing_products.columns.difference(["sku"]):
        col1 = f"{col}_df1"
        col2 = f"{col}_df2"
        if not (col1 in df_combined.columns and col2 in df_combined.columns):
            continue
        df_combined[col] = df_combined[f"{col}_df2"].combine_first(df_combined[f"{col}_df1"])

    # Drop the temporary columns

    df_combined.drop(columns=df_combined.columns.difference(existing_products.columns), inplace=True)

    df_combined.dropna(subset=MANDATORY_COLUMNS, inplace=True)
    return df_combined.fillna(np.nan).replace([np.nan], [None])
