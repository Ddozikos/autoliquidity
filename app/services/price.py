"""Normalize live offers from explicitly configured marketplace providers."""
from __future__ import annotations

import concurrent.futures
import logging
import os
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)
SOURCES = (('Авито', 'AVITO'), ('Авто.ру', 'AUTORU'), ('Дром', 'DROM'), ('СберАвто', 'SBERAUTO'))


class PriceService:
    @staticmethod
    def _normalize_demand(payload):
        if not isinstance(payload, dict):
            return None
        value = payload.get('demand')
        if isinstance(value, dict):
            value = value.get('score')
        try:
            value = float(str(value).replace(',', '.'))
        except (TypeError, ValueError):
            return None
        return round(value) if 0 <= value <= 100 else None

    @staticmethod
    def _normalize_offers(source, payload):
        if isinstance(payload, list):
            offers = payload
        elif isinstance(payload, dict):
            offers = payload.get('offers', payload.get('items', payload.get('results', [])))
        else:
            offers = []
        result = []
        for offer in offers if isinstance(offers, list) else []:
            if not isinstance(offer, dict):
                continue
            raw_price = offer.get('price') or offer.get('price_rub')
            try:
                if isinstance(raw_price, str):
                    raw_price = raw_price.replace('\u00a0', '').replace(' ', '').replace('₽', '').replace(',', '.')
                price = float(raw_price)
            except (TypeError, ValueError):
                continue
            data = offer.get('data') if isinstance(offer.get('data'), dict) else {}
            link = offer.get('url') or offer.get('link') or data.get('url')
            if price > 0 and isinstance(link, str) and link.startswith(('https://', 'http://')):
                result.append({
                    'source': source,
                    'price': price,
                    'url': link,
                    'title': offer.get('title') or data.get('title') or '',
                })
        return result

    def _fetch(self, source, url, key, car):
        headers = {'Authorization': f'Bearer {key}'} if key else {}
        params = {k: v for k, v in {
            'vin': car.get('vin'), 'make': car.get('make'),
            'model': car.get('model'), 'year': car.get('year'),
        }.items() if v}
        response = httpx.get(url, params=params, headers=headers, timeout=15, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
        return {
            'offers': self._normalize_offers(source, payload),
            'demand': self._normalize_demand(payload),
        }

    def _fetch_apiad(self, source, path, key, car):
        query = ' '.join(str(x).strip() for x in (car.get('make'), car.get('model'), car.get('year')) if x)
        if not query:
            return {'offers': [], 'demand': None}
        base = os.getenv('APIAD_API_BASE_URL', 'https://apiad.ru').rstrip('/')
        response = httpx.get(
            f'{base}/api/{path}/search_transport',
            params={'apikey': key, 'query': query}, timeout=35, follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            'offers': self._normalize_offers(source, payload),
            'demand': self._normalize_demand(payload),
        }

    def lookup(self, make, model, year, vin):
        checked_at = datetime.now(timezone.utc).isoformat()
        car = {'make': make, 'model': model, 'year': year, 'vin': vin}
        configured = []
        for label, prefix in SOURCES:
            url = os.getenv(f'{prefix}_PRICE_API_URL', '').strip()
            key = os.getenv(f'{prefix}_PRICE_API_KEY', '').strip()
            if url:
                configured.append((label, url, key))
        apiad_key = os.getenv('APIAD_API_KEY', '').strip()
        apiad_enabled = os.getenv('APIAD_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
        if apiad_key and apiad_enabled:
            configured.extend([
                ('Авито · ApiAd', 'APIAD:avito', apiad_key),
                ('Дром · ApiAd', 'APIAD:drom', apiad_key),
            ])

        offers, demands, errors = [], [], []
        if configured:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(configured)) as pool:
                futures = {
                    pool.submit(
                        self._fetch_apiad, label, url.split(':', 1)[1], key, car
                    ) if url.startswith('APIAD:') else pool.submit(self._fetch, label, url, key, car): label
                    for label, url, key in configured
                }
                for future, label in futures.items():
                    try:
                        result = future.result()
                        offers.extend(result['offers'])
                        if result['demand'] is not None:
                            demands.append((label, result['demand']))
                    except Exception as exc:
                        log.warning('Market price source %s failed: %s', label, type(exc).__name__)
                        errors.append({'source': label, 'error': type(exc).__name__})

        # A listing returned by multiple sources counts only once in the price mean.
        offers = list({offer['url']: offer for offer in offers}.values())
        if not configured:
            status = 'not_configured'
        elif offers and errors:
            status = 'partial'
        elif offers:
            status = 'found'
        elif errors and len(errors) == len(configured):
            status = 'error'
        else:
            status = 'no_results'

        average = round(sum(offer['price'] for offer in offers) / len(offers)) if offers else None
        representative = min(offers, key=lambda offer: abs(offer['price'] - average)) if offers else None
        demand = round(sum(value for _, value in demands) / len(demands)) if demands else None
        return {
            'status': status,
            'checked_at': checked_at if configured else None,
            'price': average,
            'demand': demand,
            'demand_sources': [label for label, _ in demands],
            'link': representative['url'] if representative else None,
            'sources': offers,
            'errors': errors,
            'configured_sources': [label for label, _, _ in configured],
        }
