#!/usr/bin/env python3
"""
Example sku, price, currency, availability extraction code using "extruct" and "price-parser" libraries.
Code is meant as a baseline and not perfect.
"""
import gzip
import json
from numbers import Number
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import extruct
from price_parser import Price


def extract(html: str) -> Dict:
    data = extruct.extract(
        html,
        uniform=True,
        syntaxes=['microdata', 'opengraph', 'json-ld'],
        errors='log',
    )
    item = {}
    for syntax, fn in [
            ('opengraph', from_og),
            ('json-ld', from_microdata),
            ('microdata', from_microdata),
            ]:
        item.update(clean_dict(fn(data[syntax])))
    availability = item.get('availability') or 'InStock'
    if availability:
        item[availability] = availability
    return item


def from_og(data: List[Dict]) -> Dict:
    if not data:
        return {}
    microdata = data[0]
    microdata = lowercase_top_level_keys(microdata)
    price = (microdata.get('og:price:amount') or
             microdata.get('product:price:amount'))
    currency = (microdata.get('og:price:currency') or
                microdata.get('product:price:currency'))
    availability = availability_from_og(microdata)
    sku = extract_first_of(microdata, ['og:sku', 'product:sku'])
    price, currency = parse_price(price, currency)
    return {
        'price': price,
        'currency': currency,
        'availability': availability,
        'sku': sku,
    }


def parse_price(price: Any, currency: Any) -> Tuple[Optional[str], Optional[str]]:
    price = _to_string_or_None(price)
    currency = _to_string_or_None(currency)
    parsed_price = Price.fromstring(price, currency_hint=currency)
    if parsed_price.amount is not None:
        if parsed_price.amount is not None:
            return str(parsed_price.amount_float), parsed_price.currency
    return None, None


def _to_string_or_None(value) -> Optional[str]:
    if isinstance(value, str):
        return value or None
    elif isinstance(value, Number):
        return str(value)
    elif value is None:
        return None
    else:
        raise ValueError


def availability_from_og(microdata: Dict) -> Optional[str]:
    availability = (microdata.get('og:availability', '') or
                    microdata.get('product:availability', '')).lower()
    if availability in {'instock', 'in stock', 'presale'}:
        return 'InStock'
    elif availability in {'out of stock', 'outofstock', 'discontinued'}:
        return 'OutOfStock'
    else:
        return None


def lowercase_top_level_keys(data: Dict) -> Dict:
    return {key.lower(): value for key, value in data.items()}


def clean_dict(data: Dict) -> Dict:
    return {k: str(v) for k, v in data.items() if v not in [None, '']}
    

def extract_first_of(data, keys):
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value


def from_microdata(data: List[Dict]) -> Dict:
    if not data:
        return {}
    microdata = _find_microdata_product_data(data)
    if not microdata:
        return {}
    microdata = lowercase_top_level_keys(microdata)
    sku = extract_first_of(microdata, ['sku', 'productid'])
    offers = microdata.get('offers', [])
    if isinstance(offers, dict):
        offers = [offers]
    offer = offers[0] if offers else {}
    price = offer.get('price') or \
            offer.get('highPrice') or \
            offer.get('lowPrice')
    currency = offer.get('priceCurrency')
    price, currency = parse_price(price, currency)
    availability = _normalize_availability(offer.get('availability'))
    return {
        'price': price,
        'currency': currency,
        'availability': availability,
        'sku': sku,
    }



INSTOCK_SUFFIX = ('instock', 'in_stock', 'limitedavailability',
                  'limited_availability', 'presale', 'preorder',
                  'instoreonly', 'in_store_only')
OUTOFSTOCK_SUFFIX = ('outofstock', 'out_of_stock', 'sold_out',
                     'discontinued', 'soldout')


def _normalize_availability(val: Optional[str]) -> Optional[str]:
    if val and val.lower().endswith(INSTOCK_SUFFIX):
        return 'InStock'
    elif val and val.lower().endswith(OUTOFSTOCK_SUFFIX):
        return 'OutOfStock'


def _find_microdata_product_data(microdata: List[Dict]) -> Optional[Dict]:
    product_data = [x for x in microdata if _is_product(x)]
    if product_data:
        return product_data[0]
    product_data = [x for x in microdata if x.get('@type') == 'ItemPage']
    if product_data:
        return product_data[0].get('mainEntity')
    return None


def _is_product(microdata_item: Dict) -> bool:
    for k in ['@type', 'additionalType']:
        v = microdata_item.get(k)
        try:
            if 'Product' in v:
                return True
        except TypeError:
            pass
    return False


def main():
    output = {}
    for path in (Path('dataset') / 'html').glob('*.html.gz'):
        with gzip.open(path, 'rt', encoding='utf8') as f:
            html = f.read()
        item_id = path.stem.split('.')[0]
        output[item_id] = extract(html)
    (Path('dataset') / 'output' / 'extruct.json').write_text(
        json.dumps(output, sort_keys=True, ensure_ascii=False, indent=4),
        encoding='utf8')


if __name__ == '__main__':
    main()
