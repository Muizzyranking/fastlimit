import pytest

from fastlimit.rules import _parse_rate, rule


class TestParseRate:
    def test_per_minute(self):
        cfg = _parse_rate("10/min")
        assert cfg.limit == 10
        assert cfg.window_sec == 60

    def test_per_hour(self):
        cfg = _parse_rate("100/hour")
        assert cfg.limit == 100
        assert cfg.window_sec == 3600

    def test_per_second(self):
        cfg = _parse_rate("5/s")
        assert cfg.limit == 5
        assert cfg.window_sec == 1

    def test_per_day(self):
        cfg = _parse_rate("1000/day")
        assert cfg.limit == 1000
        assert cfg.window_sec == 86400

    def test_multiplied_unit(self):
        cfg = _parse_rate("3/5min")
        assert cfg.limit == 3
        assert cfg.window_sec == 300

    def test_multiplied_hours(self):
        cfg = _parse_rate("10/2hours")
        assert cfg.limit == 10
        assert cfg.window_sec == 7200

    def test_with_spaces(self):
        cfg = _parse_rate("10 / min")
        assert cfg.limit == 10
        assert cfg.window_sec == 60

    def test_plural_variants(self):
        assert _parse_rate("10/minutes").window_sec == 60
        assert _parse_rate("10/mins").window_sec == 60
        assert _parse_rate("10/hours").window_sec == 3600
        assert _parse_rate("10/seconds").window_sec == 1

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid rate"):
            _parse_rate("badformat")

    def test_invalid_unit(self):
        with pytest.raises(ValueError, match="Unknown time unit"):
            _parse_rate("10/fortnight")


class TestRule:
    def test_default_shorthand(self):
        r = rule("10/min")
        assert r.ip_limit is not None
        assert r.ip_limit.limit == 10
        assert r.user_limit is None

    def test_explicit_ip(self):
        r = rule(ip="10/min")
        assert r.ip_limit is not None
        assert r.user_limit is None

    def test_user_only(self):
        r = rule(user="50/min")
        assert r.ip_limit is None
        assert r.user_limit is not None
        assert r.user_limit.limit == 50

    def test_dual_bucket(self):
        r = rule(ip="10/min", user="50/min")
        assert r.ip_limit is not None
        assert r.user_limit is not None

    def test_named_rule(self):
        r = rule("10/min", name="my_rule")
        assert r.name == "my_rule"

    def test_auto_name(self):
        r = rule("10/min")
        assert r.name.startswith("rl_")
        assert len(r.name) == len("rl_") + 8

    def test_cost(self):
        r = rule("10/min", cost=5)
        assert r.cost == 5

    def test_default_and_ip_conflict(self):
        with pytest.raises(ValueError, match="Cannot set both"):
            rule("10/min", ip="5/min")

    def test_no_buckets(self):
        with pytest.raises(ValueError, match="At least one"):
            rule()

    def test_invalid_cost(self):
        with pytest.raises(ValueError, match="cost must be"):
            rule("10/min", cost=0)
