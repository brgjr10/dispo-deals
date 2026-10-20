"""Duplicate product listings.

Dutchie sometimes carries the same product under two ids: the same name, image
and prices, but a different product id and product url. Left alone, that product
is counted and shown twice, so a store's product count and its menu both
double-count it.

The dedupe key has to be strict enough not to merge genuinely different
products: a stock photo is shared by unrelated items across a catalogue, so an
image alone would be wrong.
"""

from api_server import _product_dedupe_key, dedupe_products


class TestDedupeKey:
    def test_same_name_and_image_is_one_product(self):
        a = {"store_id": "s", "name": "Rove Punch 1g Cart (S)",
             "image_key": "abc123", "image_url": "https://images.dutchie.com/abc123",
             "sale_price": 45.0, "original_price": 50.0}
        b = dict(a, product_id="68af17e2", product_url="https://dutchie.com/stores/s/products/68af17e2")
        assert _product_dedupe_key(a) == _product_dedupe_key(b)

    def test_a_shared_stock_photo_does_not_merge_two_products(self):
        # The same photo, different products: these must stay separate.
        base = {"store_id": "s", "image_key": "shared", "image_url": "https://x/shared"}
        a = dict(base, name="GMO Cookies", sale_price=30.0, original_price=40.0)
        b = dict(base, name="Blue Dream", sale_price=30.0, original_price=40.0)
        assert _product_dedupe_key(a) != _product_dedupe_key(b)

    def test_same_name_at_a_different_price_is_a_different_listing(self):
        a = {"store_id": "s", "name": "Item", "sale_price": 30.0, "original_price": 40.0}
        b = dict(a, sale_price=25.0)
        assert _product_dedupe_key(a) != _product_dedupe_key(b)

    def test_different_stores_are_never_merged(self):
        a = {"store_id": "a", "name": "Item", "image_key": "img"}
        b = {"store_id": "b", "name": "Item", "image_key": "img"}
        assert _product_dedupe_key(a) != _product_dedupe_key(b)

    def test_no_image_falls_back_to_the_price_pair(self):
        a = {"store_id": "s", "name": "Item", "sale_price": 30.0, "original_price": 40.0}
        b = dict(a, product_id="different")
        assert _product_dedupe_key(a) == _product_dedupe_key(b)

    def test_a_blank_name_has_no_key(self):
        # Without a name there is nothing to identify, so the row is kept.
        assert _product_dedupe_key({"store_id": "s", "name": ""}) is None
        assert _product_dedupe_key({"store_id": "s"}) is None


class TestDedupeProducts:
    def _product(self, name, pid, image="img"):
        return {
            "store_id": "s", "name": name, "product_id": pid,
            "image_key": image, "image_url": f"https://images/{image}",
            "sale_price": 45.0, "original_price": 50.0,
        }

    def test_duplicate_listing_is_collapsed(self):
        products = [
            self._product("Rove Punch 1g Cart (S)", "pid-1"),
            self._product("Rove Punch 1g Cart (S)", "pid-2"),
        ]
        result = dedupe_products(products)
        assert len(result) == 1

    def test_the_first_listing_is_kept(self):
        # Which copy survives has to be stable, or the menu would shuffle.
        products = [
            self._product("Rove Punch 1g Cart (S)", "pid-1"),
            self._product("Rove Punch 1g Cart (S)", "pid-2"),
        ]
        result = dedupe_products(products)
        assert result[0]["product_id"] == "pid-1"

    def test_distinct_products_are_all_kept(self):
        products = [
            self._product("Rove Punch 1g Cart (S)", "pid-1"),
            self._product("Rove Punch 1g Cart (H)", "pid-2"),
            self._product("Pure Ohio Hell On Wheels", "pid-3"),
        ]
        assert len(dedupe_products(products)) == 3

    def test_same_name_across_stores_is_kept(self):
        a = self._product("Item", "pid-1")
        b = dict(self._product("Item", "pid-2"), store_id="other")
        assert len(dedupe_products([a, b])) == 2

    def test_rows_without_a_name_are_kept(self):
        products = [{"store_id": "s"}, {"store_id": "s"}]
        assert len(dedupe_products(products)) == 2

    def test_order_is_preserved(self):
        products = [
            self._product("Alpha", "pid-1"),
            self._product("Beta", "pid-2"),
            self._product("Alpha", "pid-3"),
            self._product("Gamma", "pid-4"),
        ]
        result = dedupe_products(products)
        assert [p["name"] for p in result] == ["Alpha", "Beta", "Gamma"]

    def test_empty_input(self):
        assert dedupe_products([]) == []
