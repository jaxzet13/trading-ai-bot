import datetime as dt

from soccer import laliga as L


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def test_kickoff_is_three_hours_before_the_recorded_time():
    ko = 1_800_000_000
    assert L.kickoff_of({"occurrence_datetime": _iso(ko + 3 * 3600)}) == ko


def test_window_is_28_to_45_minutes_before_kickoff():
    ko = 1_800_000_000
    assert L.in_window(ko, ko - 40 * 60)
    assert not L.in_window(ko, ko - 60 * 60)
    assert not L.in_window(ko, ko - 10 * 60)
    assert not L.in_window(None, ko)


def test_band_is_20_to_30_cents_with_two_cents_of_slack():
    assert L.in_band(0.25) and L.in_band(0.19) and L.in_band(0.32)
    assert not L.in_band(0.15) and not L.in_band(0.40) and not L.in_band(None)
