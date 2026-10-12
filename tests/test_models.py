import pytest
from datetime import date, datetime
from models import Deal, WeeklySnapshot, DealStatus, MenuItem
from utils.diff import compute_weekly_diff, WeeklyDiff


class TestModels:
    def test_deal_hash(self):
        deal = Deal(
            store_id="test",
            product_id="123",
            name="Test Product",
            category="Flower",
            original_price=50.0,
            sale_price=35.0,
            discount_pct=30.0,
            image_url="https://example.com/img.jpg",
            product_url="https://example.com/product",
        )
        assert deal.hash is not None
        assert len(deal.hash) == 16

    def test_deal_savings(self):
        deal = Deal(
            store_id="test",
            product_id="123",
            name="Test Product",
            category="Flower",
            original_price=50.0,
            sale_price=35.0,
            discount_pct=30.0,
            image_url="",
            product_url="",
        )
        assert deal.savings == 15.0

    def test_deal_discount_calculation(self):
        deal = Deal(
            store_id="test",
            product_id="123",
            name="Test Product",
            category="Flower",
            original_price=100.0,
            sale_price=75.0,
            discount_pct=0.0,
            image_url="",
            product_url="",
        )
        assert deal.discount_pct == 25.0


class TestWeeklyDiff:
    def test_compute_diff_new_items(self):
        current = [
            Deal(store_id="s1", product_id="1", name="New Product", category="Flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
            Deal(store_id="s1", product_id="2", name="Another New", category="Edibles",
                 original_price=30, sale_price=25, discount_pct=16.7, image_url="", product_url=""),
        ]
        previous = []

        diff = compute_weekly_diff(current, previous)

        assert diff.new_count == 2
        assert diff.carryover_count == 0
        assert diff.removed_count == 0
        assert all(item.status == DealStatus.NEW for item in diff.new_items)

    def test_compute_diff_carryover_items(self):
        current = [
            Deal(store_id="s1", product_id="1", name="Same Product", category="Flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
        ]
        previous = [
            Deal(store_id="s1", product_id="1", name="Same Product", category="Flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
        ]

        diff = compute_weekly_diff(current, previous)

        assert diff.new_count == 0
        assert diff.carryover_count == 1
        assert all(item.status == DealStatus.CARRYOVER for item in diff.carryover_items)

    def test_compute_diff_mixed(self):
        current = [
            Deal(store_id="s1", product_id="1", name="Old Product", category="Flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
            Deal(store_id="s1", product_id="2", name="New Product", category="Edibles",
                 original_price=30, sale_price=25, discount_pct=16.7, image_url="", product_url=""),
        ]
        previous = [
            Deal(store_id="s1", product_id="1", name="Old Product", category="Flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
            Deal(store_id="s1", product_id="3", name="Removed Product", category="Vapes",
                 original_price=40, sale_price=35, discount_pct=12.5, image_url="", product_url=""),
        ]

        diff = compute_weekly_diff(current, previous)

        assert diff.new_count == 1
        assert diff.carryover_count == 1
        assert diff.removed_count == 1
        assert diff.new_items[0].deal.name == "New Product"
        assert diff.carryover_items[0].deal.name == "Old Product"
        assert diff.removed_items[0].name == "Removed Product"

    def test_compute_diff_case_insensitive(self):
        current = [
            Deal(store_id="s1", product_id="1", name="Blue Dream", category="Flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
        ]
        previous = [
            Deal(store_id="s1", product_id="1", name="blue dream", category="flower",
                 original_price=50, sale_price=40, discount_pct=20, image_url="", product_url=""),
        ]

        diff = compute_weekly_diff(current, previous)

        assert diff.carryover_count == 1
        assert diff.new_count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])