"""Weekly menu digest behaviour: when it fires and how the once-per-week guard works.

The digest is a separate stream from new-deal alerts, so the things worth
pinning down are the gating rules (weekday, previous week, one per week) and
the new/carryover markers that the payload is built from.
"""

from datetime import date, timedelta

import pytest

from config import Config, WeeklyMenuConfig
from main import DispoDeals
from models import (
    Deal,
    NotificationMode,
    Strain,
    StoreConfig,
    WeeklySnapshot,
)
from storage.sqlite import SQLiteStorage
from utils.diff import compute_weekly_diff


@pytest.fixture
def storage(tmp_path):
    # A per-test path avoids Windows file-locking on teardown.
    return SQLiteStorage(db_path=str(tmp_path / "weekly.db"))


@pytest.fixture
def store():
    return StoreConfig(
        id="culture-akron",
        name="Culture Cannabis Club — Akron",
        url="https://dutchie.com/stores/culture-cannabis-club-akron",
        scraper="dutchie",
        logo_url="",
        notification_mode=NotificationMode.PER_STORE,
        webhook_enabled=True,
    )


def make_deal(name, price=50.0, sale=35.0):
    """A Deal whose hash is stable per (product_id, sale_price)."""
    return Deal(
        store_id="culture-akron",
        product_id=name,
        name=name,
        category="Flower",
        original_price=price,
        sale_price=sale,
        discount_pct=0.0,
        image_url="",
        product_url="",
    )


def week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


class TestClaimWeeklySummary:
    def test_first_claim_wins(self, storage):
        week = week_start_for(date.today())
        assert storage.claim_weekly_summary("culture-akron", week) is True

    def test_second_claim_same_week_is_refused(self, storage):
        week = week_start_for(date.today())
        assert storage.claim_weekly_summary("culture-akron", week) is True
        assert storage.claim_weekly_summary("culture-akron", week) is False

    def test_claim_is_per_store(self, storage):
        week = week_start_for(date.today())
        assert storage.claim_weekly_summary("culture-akron", week) is True
        assert storage.claim_weekly_summary("supergood-ravenna", week) is True

    def test_claim_is_per_week(self, storage):
        this_week = week_start_for(date.today())
        last_week = this_week - timedelta(weeks=1)
        assert storage.claim_weekly_summary("culture-akron", last_week) is True
        assert storage.claim_weekly_summary("culture-akron", this_week) is True

    def test_claim_survives_a_new_storage_instance(self, tmp_path):
        # The claim has to be durable: a restart mid-week must not resend.
        db_path = str(tmp_path / "shared.db")
        week = week_start_for(date.today())

        first = SQLiteStorage(db_path=db_path)
        assert first.claim_weekly_summary("culture-akron", week) is True

        second = SQLiteStorage(db_path=db_path)
        assert second.claim_weekly_summary("culture-akron", week) is False


class FakeNotifier:
    """Records digest sends so the gating rules can be observed."""

    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def send_weekly_summary(self, store, weekly_diff):
        self.sent.append((store.id, weekly_diff.new_count, weekly_diff.carryover_count))
        return not self.fail


def build_app(monkeypatch, storage, weekly_config=None, notifier=None):
    """Assemble a DispoDeals without touching the network or a config file."""
    store = StoreConfig(
        id="culture-akron",
        name="Culture Akron",
        url="https://dutchie.com/stores/culture-cannabis-club-akron",
        scraper="dutchie",
        logo_url="",
        notification_mode=NotificationMode.PER_STORE,
        webhook_enabled=True,
    )
    config = Config(stores=[store], webhook_url="http://example.invalid/hook")
    if weekly_config:
        for key, value in weekly_config.items():
            setattr(config.weekly_menu, key, value)

    app = DispoDeals.__new__(DispoDeals)
    app.config = config
    app.storage = storage
    app.notifier = notifier or FakeNotifier()
    app.running = True
    app.strain_resolver = None
    return app


def save_snapshot(storage, store_id, week_start, deals):
    storage.save_weekly_snapshot(
        WeeklySnapshot(store_id=store_id, week_start=week_start, items=list(deals))
    )


class TestWeeklySummaryGating:
    def test_skipped_when_disabled(self, storage):
        app = build_app(None, storage, weekly_config={"enabled": False})
        notifier = app.notifier

        week = week_start_for(date.today())
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        app._maybe_send_weekly_summary({"culture-akron": {"deals": [], "error": None}})
        assert notifier.sent == []

    def test_skipped_on_a_day_other_than_send_day(self, storage):
        today = date.today()
        other_day = (today.weekday() + 1) % 7
        app = build_app(
            None,
            storage,
            weekly_config={"send_day": other_day, "enabled": True},
        )
        notifier = app.notifier

        week = week_start_for(today)
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        app._maybe_send_weekly_summary({"culture-akron": {"deals": [], "error": None}})
        assert notifier.sent == []

    def test_sends_on_send_day(self, storage):
        app = build_app(
            None,
            storage,
            weekly_config={"send_day": date.today().weekday()},
        )
        notifier = app.notifier

        week = week_start_for(date.today())
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        app._maybe_send_weekly_summary({"culture-akron": {"deals": [], "error": None}})
        assert notifier.sent == [("culture-akron", 1, 1)]

    def test_skipped_without_a_previous_snapshot(self, storage):
        # First week: every item would be new, so there is nothing to compare.
        app = build_app(
            None,
            storage,
            weekly_config={"send_day": date.today().weekday(), "require_previous_week": True},
        )
        notifier = app.notifier

        week = week_start_for(date.today())
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        app._maybe_send_weekly_summary({"culture-akron": {"deals": [], "error": None}})
        assert notifier.sent == []

    def test_first_week_sends_when_not_required(self, storage):
        app = build_app(
            None,
            storage,
            weekly_config={
                "send_day": date.today().weekday(),
                "require_previous_week": False,
            },
        )
        notifier = app.notifier

        week = week_start_for(date.today())
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        app._maybe_send_weekly_summary({"culture-akron": {"deals": [], "error": None}})
        assert notifier.sent == [("culture-akron", 2, 0)]

    def test_skipped_when_the_scrape_failed(self, storage):
        app = build_app(
            None,
            storage,
            weekly_config={"send_day": date.today().weekday()},
        )
        notifier = app.notifier

        week = week_start_for(date.today())
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        app._maybe_send_weekly_summary(
            {"culture-akron": {"deals": [], "error": "No deals found"}}
        )
        assert notifier.sent == []

    def test_unchanged_menu_still_reports_carryover_only(self, storage):
        # A weekly digest describes the current menu, so an unchanged menu is
        # all carryover rather than nothing to say.
        app = build_app(
            None,
            storage,
            weekly_config={"send_day": date.today().weekday()},
        )
        notifier = app.notifier

        week = week_start_for(date.today())
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream")])

        app._maybe_send_weekly_summary({"culture-akron": {"deals": [], "error": None}})
        assert notifier.sent == [("culture-akron", 0, 1)]

    def test_skipped_when_the_menu_is_empty(self, storage):
        app = build_app(
            None,
            storage,
            weekly_config={"send_day": date.today().weekday()},
        )
        notifier = app.notifier

        week = week_start_for(date.today())
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [])

        app._maybe_send_weekly_summary({"culture-akron": {"deals": [], "error": None}})
        assert notifier.sent == []

    def test_only_sends_once_on_the_send_day(self, storage):
        # The run happens several times a day, so a repeat within the same week
        # must not repeat the digest.
        app = build_app(
            None,
            storage,
            weekly_config={"send_day": date.today().weekday()},
        )
        notifier = app.notifier

        week = week_start_for(date.today())
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        results = {"culture-akron": {"deals": [], "error": None}}
        app._maybe_send_weekly_summary(results)
        app._maybe_send_weekly_summary(results)
        app._maybe_send_weekly_summary(results)
        assert len(notifier.sent) == 1

    def test_failed_send_is_not_retried_the_same_week(self, storage):
        # The claim is taken before the send, so a failed webhook is not
        # retried by the next run the same day.
        app = build_app(
            None,
            storage,
            weekly_config={"send_day": date.today().weekday()},
            notifier=FakeNotifier(fail=True),
        )
        notifier = app.notifier

        week = week_start_for(date.today())
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        results = {"culture-akron": {"deals": [], "error": None}}
        app._maybe_send_weekly_summary(results)
        app._maybe_send_weekly_summary(results)
        assert len(notifier.sent) == 1


class TestWeeklyDiffMarkers:
    def test_new_and_carryover_are_separated(self):
        previous = [make_deal("Blue Dream"), make_deal("GMO")]
        current = [make_deal("GMO"), make_deal("Slurricane")]

        diff = compute_weekly_diff(current, previous)
        assert [d.deal.name for d in diff.new_items] == ["Slurricane"]
        assert [d.deal.name for d in diff.carryover_items] == ["GMO"]
        assert [d.name for d in diff.removed_items] == ["Blue Dream"]

    def test_markers_survive_round_trip_through_storage(self, storage):
        # Snapshots are persisted as JSON, so the markers must be recomputed
        # from stored data rather than carried in the payload.
        week = week_start_for(date.today())
        prev = week - timedelta(weeks=1)
        save_snapshot(storage, "culture-akron", prev, [make_deal("Blue Dream")])
        save_snapshot(storage, "culture-akron", week, [make_deal("Blue Dream"), make_deal("GMO")])

        current = storage.get_weekly_snapshot("culture-akron", week)
        previous = storage.get_weekly_snapshot("culture-akron", prev)
        diff = compute_weekly_diff(current.items, previous.items)

        assert diff.new_count == 1
        assert diff.carryover_count == 1
        assert [d.deal.name for d in diff.new_items] == ["GMO"]
        assert [d.deal.name for d in diff.carryover_items] == ["Blue Dream"]
