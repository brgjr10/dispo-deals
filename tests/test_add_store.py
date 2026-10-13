"""Adding a dispensary at runtime from a Dutchie link.

Dutchie's `filteredDispensaries` only matches `cNameOrID` exactly — its
city/state/zip filter fields exist in the schema but never match — so a store is
added by its published link rather than by a location search. These tests cover
the pure logic (slug extraction, store resolution) and the storage that makes an
added store survive a restart.
"""

from datetime import date, timedelta

import pytest
import yaml

from api_server import DashboardHandler
from models import WeeklySnapshot
from storage.sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    # A per-test path avoids Windows file-locking on teardown.
    return SQLiteStorage(db_path=str(tmp_path / "addstore.db"))


def make_handler(storage, project_root):
    """A handler with storage attached, without creating a second database."""
    handler = DashboardHandler.__new__(DashboardHandler)
    handler.storage = storage
    handler.project_root = project_root
    return handler


class TestSlugExtraction:
    handler = make_handler(None, None)

    @pytest.mark.parametrize("url,expected", [
        ("https://dutchie.com/stores/bliss-ohio-kent", "bliss-ohio-kent"),
        ("https://dutchie.com/stores/bliss-ohio-kent/", "bliss-ohio-kent"),
        ("https://dutchie.com/stores/bliss-ohio-kent/products", "bliss-ohio-kent"),
        ("https://dutchie.com/stores/bliss-ohio-kent?ref=menu", "bliss-ohio-kent"),
        ("dutchie.com/stores/supergood-ravenna", "supergood-ravenna"),
        ("bliss-ohio-kent", "bliss-ohio-kent"),
    ])
    def test_slug_is_extracted(self, url, expected):
        assert DashboardHandler._extract_dutchie_slug(url) == expected

    @pytest.mark.parametrize("url", [
        "",
        "   ",
        "https://dutchie.com/stores/",
        "https://example.com/menu",
        "not a url at all",
    ])
    def test_no_slug(self, url):
        assert DashboardHandler._extract_dutchie_slug(url) == ""


DUTCHIE_RESPONSE = {
    "data": {
        "filteredDispensaries": [
            {
                "id": "64bac95faf74b00009287438",
                "name": "Culture - Akron",
                "cName": "culture-cannabis-club-akron",
                "address": "1568 Archwood Avenue, Akron, OH 44306, USA",
                "phone": "(804) 806-5240",
                "status": "open",
                "location": {"city": "Akron", "state": "OH", "country": "United States"},
            }
        ]
    }
}


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class TestResolveStore:
    def test_resolves_name_id_and_address(self, tmp_path):
        calls = []

        class FakeRequests:
            @staticmethod
            def post(endpoint, json=None, headers=None, timeout=None):
                calls.append((endpoint, json))
                return FakeResponse(200, DUTCHIE_RESPONSE)

        import api_server
        original = api_server.requests
        api_server.requests = FakeRequests
        try:
            handler = make_handler(None, tmp_path)
            store = handler.resolve_dutchie_store(
                "https://dutchie.com/stores/culture-cannabis-club-akron"
            )
        finally:
            api_server.requests = original

        assert store is not None
        assert store["id"] == "64bac95faf74b00009287438"
        assert store["name"] == "Culture - Akron"
        assert store["cname"] == "culture-cannabis-club-akron"
        assert "Akron" in store["address"]
        assert store["url"] == "https://dutchie.com/stores/culture-cannabis-club-akron"
        assert store["city"] == "Akron"
        assert store["state"] == "OH"

    def test_slug_is_passed_as_the_lookup_variable(self, tmp_path):
        calls = []

        class FakeRequests:
            @staticmethod
            def post(endpoint, json=None, headers=None, timeout=None):
                calls.append(json)
                return FakeResponse(200, DUTCHIE_RESPONSE)

        import api_server
        original = api_server.requests
        api_server.requests = FakeRequests
        try:
            handler = make_handler(None, tmp_path)
            handler.resolve_dutchie_store(
                "https://dutchie.com/stores/culture-cannabis-club-akron/products"
            )
        finally:
            api_server.requests = original

        assert calls[0]["variables"]["cNameOrID"] == "culture-cannabis-club-akron"

    def test_unknown_store_returns_none(self, tmp_path):
        class FakeRequests:
            @staticmethod
            def post(endpoint, json=None, headers=None, timeout=None):
                return FakeResponse(200, {"data": {"filteredDispensaries": []}})

        import api_server
        original = api_server.requests
        api_server.requests = FakeRequests
        try:
            handler = make_handler(None, tmp_path)
            assert handler.resolve_dutchie_store("https://dutchie.com/stores/nope") is None
        finally:
            api_server.requests = original

    def test_unreachable_dutchie_returns_none(self, tmp_path):
        class FakeRequests:
            @staticmethod
            def post(endpoint, json=None, headers=None, timeout=None):
                raise ConnectionError("no network")

        import api_server
        original = api_server.requests
        api_server.requests = FakeRequests
        try:
            handler = make_handler(None, tmp_path)
            assert handler.resolve_dutchie_store("https://dutchie.com/stores/nope") is None
        finally:
            api_server.requests = original

    def test_prefers_exact_cname_over_a_looser_match(self, tmp_path):
        # Dutchie can return several dispensaries for a slug; the exact cName is
        # the one the user's link actually pointed at.
        payload = {
            "data": {
                "filteredDispensaries": [
                    {"id": "other", "name": "Somewhere Else", "cName": "other-store"},
                    {
                        "id": "right",
                        "name": "Culture - Akron",
                        "cName": "culture-cannabis-club-akron",
                        "address": "Akron, OH",
                    },
                ]
            }
        }

        class FakeRequests:
            @staticmethod
            def post(endpoint, json=None, headers=None, timeout=None):
                return FakeResponse(200, payload)

        import api_server
        original = api_server.requests
        api_server.requests = FakeRequests
        try:
            handler = make_handler(None, tmp_path)
            store = handler.resolve_dutchie_store(
                "https://dutchie.com/stores/culture-cannabis-club-akron"
            )
        finally:
            api_server.requests = original

        assert store["id"] == "right"


class TestKnownStoreStorage:
    def _store(self, sid="store-1", name="Culture - Akron"):
        return {
            "id": sid,
            "name": name,
            "cname": "culture-cannabis-club-akron",
            "url": "https://dutchie.com/stores/culture-cannabis-club-akron",
            "logo_url": "/api/logo/store-1",
            "address": "1568 Archwood Avenue, Akron, OH 44306, USA",
            "phone": "(804) 806-5240",
        }

    def test_save_and_list(self, storage):
        assert storage.save_known_store(self._store()) is True
        stored = storage.list_known_stores()
        assert len(stored) == 1
        assert stored[0]["name"] == "Culture - Akron"
        assert stored[0]["cname"] == "culture-cannabis-club-akron"
        assert stored[0]["address"].startswith("1568")

    def test_re_saving_updates_rather_than_duplicating(self, storage):
        # The id is the stable key, so re-adding a store refreshes its row.
        storage.save_known_store(self._store())
        storage.save_known_store(self._store(name="Culture Cannabis Club — Akron"))
        stored = storage.list_known_stores()
        assert len(stored) == 1
        assert stored[0]["name"] == "Culture Cannabis Club — Akron"

    def test_count_store_products(self, storage):
        assert storage.count_store_products("store-1") == 0
        # A store with no deals still reports zero rather than erroring.
        assert storage.save_known_store(self._store()) is True
        assert storage.count_store_products("store-1") == 0

    def test_count_ignores_other_stores(self, storage, tmp_path):
        from models import Deal

        storage.save_known_store(self._store(sid="store-1"))
        deal = Deal(
            store_id="store-1",
            product_id="p1",
            name="Blue Dream",
            category="Flower",
            original_price=50.0,
            sale_price=35.0,
            discount_pct=0.0,
            image_url="",
            product_url="",
        )
        storage.save_seen_deal(deal)
        assert storage.count_store_products("store-1") == 1
        assert storage.count_store_products("store-2") == 0

    def test_added_store_survives_a_new_instance(self, tmp_path):
        # The dashboard reads known stores on every request, so they must be
        # durable rather than living in process memory.
        db_path = str(tmp_path / "shared.db")
        first = SQLiteStorage(db_path=db_path)
        first.save_known_store(self._store())

        second = SQLiteStorage(db_path=db_path)
        stored = second.list_known_stores()
        assert len(stored) == 1
        assert stored[0]["id"] == "store-1"


class TestAddStore:
    """The full add path, with Dutchie and the scraper replaced by doubles."""
    def _patch(self, monkeypatch, resolve_result=None, deals=None, logo=b"img"):
        import api_server
        import scrapers as scrapers_pkg

        class FakeScraper:
            def __init__(self, store_config, config):
                self.store_config = store_config

            def fetch_menu(self):
                return deals if deals is not None else []

            def fetch_logo(self):
                return logo

        stored_stores = []

        class FakeNotifierStorage:
            pass

        monkeypatch.setattr(api_server.DashboardHandler, "resolve_dutchie_store",
                            lambda self, url: resolve_result)
        monkeypatch.setattr(scrapers_pkg, "create_scraper",
                            lambda store, config: FakeScraper(store, config))
        monkeypatch.setattr("storage.sqlite.SQLiteStorage.save_known_store",
                            lambda self, store: stored_stores.append(store) or True)
        return stored_stores

    RESOLVED = {
        "id": "64bac95faf74b00009287438",
        "name": "Culture - Akron",
        "cname": "culture-cannabis-club-akron",
        "url": "https://dutchie.com/stores/culture-cannabis-club-akron",
        "address": "1568 Archwood Avenue, Akron, OH 44306",
        "phone": "(804) 806-5240",
    }

    def test_unknown_store_raises(self, tmp_path, monkeypatch):
        self._patch(monkeypatch, resolve_result=None)
        handler = make_handler(SQLiteStorage(db_path=str(tmp_path / "a.db")), tmp_path)
        with pytest.raises(ValueError):
            handler.add_store("https://dutchie.com/stores/nope")

    def test_records_store_and_returns_products(self, tmp_path, monkeypatch):
        from models import Deal

        deals = [
            Deal(
                store_id=self.RESOLVED["id"], product_id=f"p{i}", name=f"Product {i}",
                category="Flower", original_price=50.0, sale_price=35.0,
                discount_pct=0.0, image_url="", product_url="",
            )
            for i in range(3)
        ]
        stored_stores = self._patch(monkeypatch, resolve_result=self.RESOLVED, deals=deals)
        handler = make_handler(SQLiteStorage(db_path=str(tmp_path / "b.db")), tmp_path)

        result = handler.add_store("https://dutchie.com/stores/culture-cannabis-club-akron")

        assert result["product_count"] == 3
        assert result["already_added"] is False
        assert stored_stores and stored_stores[0]["id"] == self.RESOLVED["id"]
        # The logo is served locally once saved.
        assert result["store"]["logo_url"].startswith("/api/logo/")

    def test_second_add_is_idempotent(self, tmp_path, monkeypatch):
        from models import Deal

        deals = [
            Deal(
                store_id=self.RESOLVED["id"], product_id="p0", name="Product",
                category="Flower", original_price=50.0, sale_price=35.0,
                discount_pct=0.0, image_url="", product_url="",
            )
        ]
        self._patch(monkeypatch, resolve_result=self.RESOLVED, deals=deals)
        handler = make_handler(SQLiteStorage(db_path=str(tmp_path / "c.db")), tmp_path)
        url = "https://dutchie.com/stores/culture-cannabis-club-akron"

        handler.add_store(url)
        second = handler.add_store(url)

        assert second["already_added"] is True
        assert second["product_count"] == 1

    def test_empty_menu_still_records_the_store(self, tmp_path, monkeypatch):
        stored_stores = self._patch(monkeypatch, resolve_result=self.RESOLVED, deals=[])
        handler = make_handler(SQLiteStorage(db_path=str(tmp_path / "d.db")), tmp_path)

        result = handler.add_store("https://dutchie.com/stores/culture-cannabis-club-akron")
        assert result["product_count"] == 0
        assert stored_stores


class TestCanonicalStoreId:
    """The duplicate-store bug, pinned down.

    Adding a store with Dutchie's internal id while config.yaml names the same
    dispensary `bliss-kent` produced two rows for one dispensary. The id has to
    come from whatever entry already points at that cName.
    """

    CONFIG = {
        "stores": [
            {"id": "bliss-kent", "name": "Bliss Ohio — Kent",
             "url": "https://dutchie.com/stores/bliss-ohio-kent/products",
             "enabled": True},
            {"id": "culture-akron", "name": "Culture Cannabis Club — Akron",
             "url": "https://dutchie.com/stores/culture-cannabis-club-akron",
             "enabled": True},
        ]
    }

    def _handler(self, storage, tmp_path, config=None):
        (tmp_path / "config.yaml").write_text(
            yaml.safe_dump(config if config is not None else self.CONFIG),
            encoding="utf-8",
        )
        return make_handler(storage, tmp_path)

    def test_reuses_the_config_id_for_the_same_cname(self, tmp_path):
        import yaml

        handler = self._handler(SQLiteStorage(db_path=str(tmp_path / "a.db")), tmp_path)
        assert handler._canonical_store_id("bliss-ohio-kent") == "bliss-kent"

    def test_falls_back_to_the_slug_for_an_unknown_store(self, tmp_path):
        import yaml

        handler = self._handler(SQLiteStorage(db_path=str(tmp_path / "b.db")), tmp_path)
        assert handler._canonical_store_id("some-new-dispensary") == "some-new-dispensary"

    def test_reuses_an_added_store_id(self, tmp_path):
        import yaml

        storage = SQLiteStorage(db_path=str(tmp_path / "c.db"))
        storage.save_known_store({
            "id": "bliss-kent", "name": "Bliss Ohio — Kent",
            "cname": "bliss-ohio-kent", "url": "https://dutchie.com/stores/bliss-ohio-kent",
        })
        handler = self._handler(storage, tmp_path)
        assert handler._canonical_store_id("bliss-ohio-kent") == "bliss-kent"

    def test_slug_is_normalised(self, tmp_path):
        import yaml

        handler = self._handler(SQLiteStorage(db_path=str(tmp_path / "d.db")), tmp_path)
        assert handler._canonical_store_id("Some New Store!") == "some-new-store"

    def test_a_disabled_config_entry_is_still_matched(self, tmp_path):
        import yaml

        config = {
            "stores": [
                {"id": "bliss-kent", "name": "Bliss Ohio — Kent",
                 "url": "https://dutchie.com/stores/bliss-ohio-kent/products",
                 "enabled": False},
            ]
        }
        handler = self._handler(SQLiteStorage(db_path=str(tmp_path / "e.db")), tmp_path, config)
        # Reuse the id even though the entry is disabled: using a fresh id would
        # put the same dispensary in the dashboard twice, and re-enabling the
        # entry later would then create a second set of products alongside it.
        assert handler._canonical_store_id("bliss-ohio-kent") == "bliss-kent"

    def test_missing_config_still_yields_a_slug(self, tmp_path):
        handler = make_handler(SQLiteStorage(db_path=str(tmp_path / "f.db")), tmp_path)
        assert handler._canonical_store_id("some-new-dispensary") == "some-new-dispensary"


class TestRemoveStore:
    def _store(self, sid="store-1", name="Bliss Ohio - Kent"):
        return {
            "id": sid, "name": name, "cname": "bliss-ohio-kent",
            "url": "https://dutchie.com/stores/bliss-ohio-kent",
            "logo_url": "/api/logo/store-1",
        }

    def test_deletes_every_trace(self, storage):
        from models import Deal

        storage.save_known_store(self._store())
        storage.save_seen_deal(Deal(
            store_id="store-1", product_id="p1", name="Blue Dream", category="Flower",
            original_price=50.0, sale_price=35.0, discount_pct=0.0,
            image_url="", product_url="",
        ))
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        storage.save_weekly_snapshot(
            WeeklySnapshot(store_id="store-1", week_start=week_start, items=[])
        )
        assert storage.claim_weekly_summary("store-1", week_start) is True

        assert storage.delete_store_data("store-1") is True
        assert storage.list_known_stores() == []
        assert storage.count_store_products("store-1") == 0
        assert storage.get_weekly_snapshot("store-1", week_start) is None
        # A claimed week that was deleted can be claimed again.
        assert storage.claim_weekly_summary("store-1", week_start) is True

    def test_leaves_other_stores_alone(self, storage):
        from models import Deal

        storage.save_known_store(self._store(sid="store-1"))
        storage.save_known_store(self._store(sid="store-2", name="Culture Akron"))
        storage.save_seen_deal(Deal(
            store_id="store-2", product_id="p2", name="GMO", category="Flower",
            original_price=50.0, sale_price=35.0, discount_pct=0.0,
            image_url="", product_url="",
        ))

        storage.delete_store_data("store-1")

        remaining = {k["id"] for k in storage.list_known_stores()}
        assert remaining == {"store-2"}
        assert storage.count_store_products("store-2") == 1

    def test_delete_is_idempotent(self, storage):
        assert storage.delete_store_data("never-existed") is True
        assert storage.delete_store_data("never-existed") is True

    def test_is_added_store(self, storage):
        storage.save_known_store(self._store())
        assert storage.is_added_store("store-1") is True
        assert storage.is_added_store("store-2") is False


class TestApiErrorsAreJson:
    """API failures must be JSON so the dashboard can show the real reason.

    `send_error` returns an HTML page the frontend cannot parse, which would
    hide the message behind a generic status code.
    """

    class FakeWFile:
        def __init__(self):
            self.data = b""

        def write(self, payload):
            self.data += payload

        @property
        def text(self):
            return self.data.decode("utf-8")

        @property
        def body(self):
            """The response body, with the header block stripped off.

            `send_response` and `send_header` write into the same file object
            as the payload, so the body is whatever follows the blank line.
            """
            _, _, body = self.text.partition("\r\n\r\n")
            return body

    def _handler(self):
        handler = DashboardHandler.__new__(DashboardHandler)
        handler.wfile = self.FakeWFile()
        # send_response() logs the request line, which a bare handler lacks.
        handler.requestline = "POST /api/stores/add HTTP/1.1"
        handler.request_version = "HTTP/1.1"
        handler.command = "POST"
        return handler

    def test_json_error_shape(self):
        import json

        handler = self._handler()
        handler._send_json_error(400, "A Dutchie store URL is required")
        assert json.loads(handler.wfile.body) == {"error": "A Dutchie store URL is required"}

    def test_error_status_is_preserved(self):
        handler = self._handler()
        handler._send_json_error(404, "Not found")
        assert handler.wfile.text.startswith("HTTP/1.0 404")

    def test_error_body_is_json_not_html(self):
        handler = self._handler()
        handler._send_json_error(400, "bad input")
        assert handler.wfile.body.startswith("{")
        assert not handler.wfile.body.startswith("<!DOCTYPE")

