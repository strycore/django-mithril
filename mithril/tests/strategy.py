# (c) 2012 Urban Airship and Contributors

from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import HttpResponseForbidden 
from django.test import TestCase
from mithril.models import Whitelist, CachedWhitelist
from mithril.strategy import Strategy, CachedStrategy
from mithril.tests.utils import fmt_ip
import random
import mithril

USER_COUNT = 0


class StrategyTestCase(TestCase):
    def fake_request(self, expect):
        global USER_COUNT

        USER_COUNT += 1
        return type('Req', (object,), {
            'META':{'REMOTE_ADDR':expect, 'LOL':0},
            'user':User.objects.create_user('random-%d'%USER_COUNT)
        })()

    def tearDown(self):
        mithril.set_current_ip(None)

    def test_super_user_exempt(self):
        """
            Make sure that superuser is exempt from IP whitelists.
        """

        expected = '10.112.12.12'
        req = self.fake_request(expected)
        req.user.is_superuser = False

        whitelist = Whitelist.objects.create(name='asdf', slug='asdf')
        whitelist.range_set.create(ip='127.0.0.1', cidr=32)

        strat = Strategy()
        strat.return_one = lambda *a, **kw: whitelist.pk
        strat.actions = [['return_one', 'pk']]

        self.assertTrue(
                isinstance(strat.process_view(req, None, (), {}),
                    HttpResponseForbidden)
        )

        req.user.is_superuser = True

        self.assertEqual(
            strat.process_view(req, None, (), {}),
            None
        )

    def test_get_ip_from_request(self):
        strat = Strategy()

        expected = random.randint(1, 10)
        req = self.fake_request(expected)

        strat.request_ip_headers = ['REMOTE_ADDR', 'LOL']

        self.assertEqual(strat.get_ip_from_request(req), expected)

        strat.request_ip_headers = ['LOL']
        self.assertEqual(strat.get_ip_from_request(req), 0)

        strat.request_ip_headers = ['LOL', 'REMOTE_ADDR']
        self.assertEqual(strat.get_ip_from_request(req), 0)

        strat.request_ip_headers = ['DNE']
        self.assertEqual(strat.get_ip_from_request(req), None)

    def test_process_view_skips_methods_returning_none(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = Strategy()

        strat.return_none = lambda *a, **kw: None
        strat.actions = [['return_none', 'anything']]

        self.assertEqual(
            strat.process_view(req, None, (), {}),
            None
        )


    def test_process_view_skips_lookups_raising_fielderror(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = Strategy()

        strat.return_one = lambda *a, **kw: 1
        strat.actions = [['return_one', 'anything']]

        self.assertEqual(
            strat.process_view(req, None, (), {}),
            None
        )

    def test_process_view_skips_methods_returning_no_whitelists(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = Strategy()

        # make sure that the cache is empty...
        cache.delete('whitelist:pk:1')

        # there are no whitelists at this point,
        # so a 'pk' lookup will return nothing!
        strat.return_one = lambda *a, **kw: 1
        strat.actions = [['return_one', 'pk']]

        self.assertEqual(
            strat.process_view(req, None, (), {}),
            None
        )

    def test_process_view_passes_forbidden_response_class(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = Strategy()

        wl = Whitelist.objects.create(
            name='okay',
            slug='okay'
        )

        wl.range_set.create(
            ip='0.0.0.0',
            cidr=32
        )

        strat.return_one = lambda *a, **kw: wl.pk
        strat.actions = [['return_one', 'pk']]
        self.assertTrue(
            isinstance(strat.process_view(req, None, (), {}),
                HttpResponseForbidden)
        )

    def test_process_view_passes_curried_mithril_reset_view(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = Strategy()

        wl = Whitelist.objects.create(
            name='okay',
            slug='okay'
        )

        wl.range_set.create(
            ip='0.0.0.0',
            cidr=32
        )

        strat.return_one = lambda *a, **kw: wl.pk
        strat.actions = [['return_one', 'pk']]

        view = lambda:None
        view.mithril_reset = \
            lambda request, view, args, kwargs: check(
                    request, view, args, kwargs)

        def check(request, target_view, target_args, target_kwargs):
            self.assertTrue(request is req)
            self.assertEqual(target_view, view)
            return expected

        self.assertEqual(
            strat.process_view(req, view, (), {}),
            expected
        )

    def test_whitelist_ip_automatically_fails_on_no_ip(self):
        strat = Strategy()
        self.assertEqual(strat.whitelist_ip(None, [], lambda:None), None)

    def test_whitelist_ip_returns_response_fn_on_not_okay(self):
        strat = Strategy()
        ip = fmt_ip(random.randint(1, 0xFFFFFFFF))

        whitelist = Whitelist.objects.create(name='asdf', slug='asdf')
        whitelist.range_set.create(
            ip='0.0.0.0',
            cidr=32
        )

        Expected = object()
        self.assertEqual(
            strat.whitelist_ip(ip, [whitelist], lambda:Expected),
            Expected
        )

    def test_get_authentication_backend_meta(self):
        base_backend = type('Any', (object,), {})
        new_backend = Strategy.get_authentication_backend(base_backend)

        self.assertTrue(isinstance(new_backend(), base_backend))
        self.assertEqual(new_backend().__module__, base_backend.__module__)
        self.assertEqual(new_backend().__class__, base_backend)

    def test_get_authentication_backend_authenticate(self):
        Expected = object()

        class MyStrategy(Strategy):
            partial_credential_lookup = (
                ('pk', 'pk'),
            )

        def authenticate(*args, **kwargs):
            return Expected

        base_backend = type('Any', (object,), {'authenticate':authenticate})
        new_backend = MyStrategy.get_authentication_backend(base_backend)

        backend = new_backend()

        whitelist = Whitelist.objects.create(name='asdf', slug='asdf')
        whitelist.range_set.create(
            ip='0.0.0.0',
            cidr=32
        )

        # when the key isn't there.
        self.assertEqual(backend.authenticate(), None)

        # when the key is there and it fails.
        mithril.set_current_ip(fmt_ip(random.randint(1, 10)))
        self.assertEqual(backend.authenticate(pk=whitelist.pk), None)

        # when the key is there and it succeeds.
        mithril.set_current_ip(fmt_ip(0))
        self.assertEqual(backend.authenticate(pk=whitelist.pk), Expected)

        # when the key is there, but there are no whitelists
        mithril.set_current_ip(fmt_ip(0))
        self.assertEqual(backend.authenticate(pk=whitelist.pk+1), Expected)

class CachedStrategyTestCase(StrategyTestCase):

    def test_super_user_exempt(self):
        """
            Make sure that superuser is exempt from IP whitelists.
        """

        expected = '10.112.12.12'
        req = self.fake_request(expected)
        req.user.is_superuser = False

        whitelist = CachedWhitelist.objects.create(name='asdf', slug='asdf')
        whitelist.range_set.create(ip='127.0.0.1', cidr=32)

        strat = CachedStrategy()
        strat.return_one = lambda *a, **kw: whitelist.pk
        strat.actions = [['return_one', 'pk']]

        resp = strat.process_view(req, None, (), {})

        self.assertTrue(
            isinstance(resp, HttpResponseForbidden)
        )

        req.user.is_superuser = True

        self.assertEqual(
            strat.process_view(req, None, (), {}),
            None
        )

    def test_get_ip_from_request(self):
        strat = CachedStrategy()

        expected = random.randint(1, 10)
        req = self.fake_request(expected)

        strat.request_ip_headers = ['REMOTE_ADDR', 'LOL']

        self.assertEqual(strat.get_ip_from_request(req), expected)

        strat.request_ip_headers = ['LOL']
        self.assertEqual(strat.get_ip_from_request(req), 0)

        strat.request_ip_headers = ['LOL', 'REMOTE_ADDR']
        self.assertEqual(strat.get_ip_from_request(req), 0)

        strat.request_ip_headers = ['DNE']
        self.assertEqual(strat.get_ip_from_request(req), None)

    def test_process_view_skips_methods_returning_none(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = CachedStrategy()

        strat.return_none = lambda *a, **kw: None
        strat.actions = [['return_none', 'anything']]

        self.assertEqual(
            strat.process_view(req, None, (), {}),
            None
        )


    def test_process_view_skips_lookups_raising_fielderror(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = CachedStrategy()

        strat.return_one = lambda *a, **kw: 1
        strat.actions = [['return_one', 'anything']]

        self.assertEqual(
            strat.process_view(req, None, (), {}),
            None
        )

    def test_process_view_skips_methods_returning_no_whitelists(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = CachedStrategy()

        # make sure that the cache is empty...
        cache.delete('whitelist:pk:1')

        # there are no whitelists at this point,
        # so a 'pk' lookup will return nothing!
        strat.return_one = lambda *a, **kw: 1
        strat.actions = [['return_one', 'pk']]

        self.assertEqual(
            strat.process_view(req, None, (), {}),
            None
        )

    def test_process_view_passes_forbidden_response_class(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = CachedStrategy()

        wl = CachedWhitelist.objects.create(
            name='okay',
            slug='okay'
        )

        wl.range_set.create(
            ip='0.0.0.0',
            cidr=32
        )

        strat.return_one = lambda *a, **kw: wl.pk
        strat.actions = [['return_one', 'pk']]
        self.assertTrue(
            isinstance(strat.process_view(req, None, (), {}),
                HttpResponseForbidden)
        )

    def test_process_view_passes_curried_mithril_reset_view(self):
        expected = fmt_ip(random.randint(1, 0xFFFFFFFF)) 
        req = self.fake_request(expected)

        strat = CachedStrategy()

        wl = CachedWhitelist.objects.create(
            name='okay',
            slug='okay'
        )

        wl.range_set.create(
            ip='0.0.0.0',
            cidr=32
        )

        strat.return_one = lambda *a, **kw: wl.pk
        strat.actions = [['return_one', 'pk']]

        view = lambda:None
        view.mithril_reset = \
            lambda request, view, args, kwargs: check(
                    request, view, args, kwargs)

        def check(request, target_view, target_args, target_kwargs):
            self.assertTrue(request is req)
            self.assertEqual(target_view, view)
            return expected

        self.assertEqual(
            strat.process_view(req, view, (), {}),
            expected
        )

    def test_whitelist_ip_automatically_fails_on_no_ip(self):
        strat = CachedStrategy()
        self.assertEqual(strat.whitelist_ip(None, [], lambda:None), None)

    def test_whitelist_ip_returns_response_fn_on_not_okay(self):
        strat = CachedStrategy()
        ip = fmt_ip(random.randint(1, 0xFFFFFFFF))

        whitelist = CachedWhitelist.objects.create(name='asdf', slug='asdf')
        whitelist.range_set.create(
            ip='0.0.0.0',
            cidr=32
        )

        Expected = object()

        self.assertEqual(
            strat.whitelist_ip(ip, [whitelist], lambda:Expected),
            Expected
        )

    def test_get_authentication_backend_meta(self):
        base_backend = type('Any', (object,), {})
        new_backend = CachedStrategy.get_authentication_backend(base_backend)

        self.assertTrue(isinstance(new_backend(), base_backend))
        self.assertEqual(new_backend().__module__, base_backend.__module__)
        self.assertEqual(new_backend().__class__, base_backend)

    def test_get_authentication_backend_authenticate(self):
        Expected = object()

        class MyStrategy(CachedStrategy):
            partial_credential_lookup = (
                ('pk', 'pk'),
            )

        def authenticate(*args, **kwargs):
            return Expected

        base_backend = type('Any', (object,), {'authenticate':authenticate})
        new_backend = MyStrategy.get_authentication_backend(base_backend)

        backend = new_backend()

        whitelist = CachedWhitelist.objects.create(name='asdf', slug='asdf')
        whitelist.range_set.create(
            ip='0.0.0.0',
            cidr=32
        )

        # when the key isn't there.
        self.assertEqual(backend.authenticate(), None)

        # when the key is there and it fails.
        mithril.set_current_ip(fmt_ip(random.randint(1, 10)))
        self.assertEqual(backend.authenticate(pk=whitelist.pk), None)

        # when the key is there and it succeeds.
        mithril.set_current_ip(fmt_ip(0))
        self.assertEqual(backend.authenticate(pk=whitelist.pk), Expected)

        # when the key is there, but there are no whitelists
        mithril.set_current_ip(fmt_ip(0))
        self.assertEqual(backend.authenticate(pk=whitelist.pk+1), Expected)
