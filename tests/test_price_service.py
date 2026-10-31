import unittest
from unittest.mock import patch

from app.services.price import PriceService


class PriceServiceTests(unittest.TestCase):
    def test_average_and_representative_offer_are_real_results(self):
        service = PriceService()
        offers = [
            {'source': 'Авито', 'price': 1_000_000, 'url': 'https://example.test/1', 'title': 'Объявление 1'},
            {'source': 'Дром', 'price': 1_200_000, 'url': 'https://example.test/2', 'title': 'Объявление 2'},
        ]
        results = [
            {'offers':offers[:1],'demand':90},
            {'offers':offers[1:],'demand':70},
        ]
        with patch.dict('os.environ', {'AVITO_PRICE_API_URL': 'https://api.example.test/a', 'DROM_PRICE_API_URL': 'https://api.example.test/d', 'APIAD_ENABLED': 'false'}):
            with patch.object(service, '_fetch', side_effect=results):
                result = service.lookup('Audi', 'Q5', '2019', None)
        self.assertEqual(result['price'], 1_100_000)
        self.assertEqual(len(result['sources']), 2)
        self.assertIn(result['link'], {offer['url'] for offer in offers})
        self.assertEqual(result['demand'], 80)
        self.assertEqual(result['demand_sources'], ['Авито', 'Дром'])
        self.assertEqual(result['status'], 'found')
        self.assertTrue(result['checked_at'].endswith('+00:00'))

    def test_no_configured_provider_does_not_make_up_price_or_demand(self):
        env = {f'{name}_PRICE_API_URL': '' for name in ('AVITO', 'AUTORU', 'DROM', 'SBERAUTO')}
        env.update({'APIAD_API_KEY': '', 'APIAD_ENABLED': 'false'})
        with patch.dict('os.environ', env):
            result = PriceService().lookup('Audi', 'Q5', '2019', None)
        self.assertIsNone(result['price'])
        self.assertIsNone(result['demand'])
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['configured_sources'], [])
        self.assertEqual(result['status'],'not_configured')
        self.assertIsNone(result['checked_at'])

    def test_demand_is_only_accepted_as_numeric_provider_metric(self):
        self.assertEqual(PriceService._normalize_demand({'demand':'73'}),73)
        self.assertEqual(PriceService._normalize_demand({'demand':{'score':81}}),81)
        self.assertIsNone(PriceService._normalize_demand({'demand':'Высокий'}))
        self.assertIsNone(PriceService._normalize_demand({'demand':120}))


if __name__ == '__main__':
    unittest.main()
