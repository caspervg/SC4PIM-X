import datetime
from types import SimpleNamespace

from sc4pimx.SC4PropTiming import (
    MAIN_SIMULATOR_TGI,
    effective_night_hours,
    is_night,
    prop_temporal_state,
    timer_hides_prop,
    timer_state_index,
)


class Exemplar:
    def __init__(self, properties=None):
        self.properties = properties or {}

    def GetProp(self, prop_id):
        return self.properties.get(prop_id)


def test_maxis_night_window_is_wrapped_and_end_exclusive():
    assert not is_night(19 * 60 + 59)
    assert is_night(20 * 60)
    assert is_night(23 * 60 + 59)
    assert is_night(0)
    assert not is_night(60)


def test_effective_night_hours_uses_loaded_main_simulator_override():
    exemplar = Exemplar({0x09B73421: [17], 0x09B73422: [6]})
    entry = SimpleNamespace(exemplar=exemplar)
    virtual_dat = SimpleNamespace(
        getEntry=lambda *tgi: entry if tgi == MAIN_SIMULATOR_TGI else None,
    )

    assert effective_night_hours(virtual_dat) == (17, 6)
    assert is_night(17 * 60, *effective_night_hours(virtual_dat))
    assert not is_night(6 * 60, *effective_night_hours(virtual_dat))


def test_effective_night_hours_decodes_released_exemplar_on_demand(monkeypatch):
    from sc4pimx import SC4DatTools

    released = []

    class TemporaryExemplar(Exemplar):
        def __init__(self, entry, virtual_dat):
            super().__init__({0x09B73421: [18], 0x09B73422: [5]})

        def free(self):
            released.append(True)

    entry = SimpleNamespace(
        rawContent=b"raw",
        content=b"decoded",
        read_file=lambda *args: None,
    )
    virtual_dat = SimpleNamespace(getEntry=lambda *tgi: entry)
    monkeypatch.setattr(SC4DatTools, "SC4Exemplar", TemporaryExemplar)

    assert effective_night_hours(virtual_dat) == (18, 5)
    assert released == [True]
    assert entry.rawContent is None
    assert entry.content is None


def test_time_of_day_supports_daytime_and_overnight_windows():
    daytime = Exemplar({0x4A149631: [8.0, 17.0]})
    overnight = Exemplar({0x4A149631: [22.0, 5.0]})
    date = datetime.date(1, 1, 1)

    assert prop_temporal_state(daytime, date, 8 * 60).active
    assert not prop_temporal_state(daytime, date, 17 * 60).active
    assert prop_temporal_state(overnight, date, 23 * 60).active
    assert prop_temporal_state(overnight, date, 4 * 60 + 59).active
    assert not prop_temporal_state(overnight, date, 5 * 60).active


def test_zero_time_window_means_always_visible():
    exemplar = Exemplar({0x4A149631: [0.0, 0.0]})
    assert prop_temporal_state(exemplar, datetime.date(1, 1, 1), 12 * 60).active


def test_date_duration_and_interval_repeat_from_start_date():
    exemplar = Exemplar({
        0xCA7515CC: [1, 3],
        0x4A764564: [2],
        0x0A751675: [5],
    })

    assert prop_temporal_state(exemplar, datetime.date(1, 1, 3), 720).active
    assert prop_temporal_state(exemplar, datetime.date(1, 1, 4), 720).active
    assert not prop_temporal_state(exemplar, datetime.date(1, 1, 5), 720).active
    assert prop_temporal_state(exemplar, datetime.date(1, 1, 8), 720).active


def test_annual_date_preview_wraps_december_interval_into_january():
    exemplar = Exemplar({
        0xCA7515CC: [12, 31],  # Stored order is month, day.
        0x4A764564: [3],
        0x0A751675: [365],
    })

    assert prop_temporal_state(exemplar, datetime.date(1, 12, 31), 720).active
    assert prop_temporal_state(exemplar, datetime.date(1, 1, 1), 720).active
    assert prop_temporal_state(exemplar, datetime.date(1, 1, 2), 720).active
    assert not prop_temporal_state(exemplar, datetime.date(1, 1, 3), 720).active


def test_random_chance_is_reported_but_not_randomly_hidden():
    exemplar = Exemplar({0x4A751AD5: [25]})
    state = prop_temporal_state(exemplar, datetime.date(1, 1, 1), 720)

    assert state.active
    assert state.random_chance == 25


# Real BSC MEGA Props - CP Vol02 "Russian Olive - semiseasonal": a two-state
# RKT4 prop whose simulator-date schedule swaps the leafy state 0 model for a
# dormant state 1 model rather than hiding it.
def _semiseasonal_olive():
    return Exemplar({
        0xCA7515CC: [3, 8],   # PropStartingDate: month 3, day 8
        0x4A764564: [234],    # PropDuration days
        0x0A751675: [365],    # PropInterval: yearly
    })


def test_two_state_prop_shows_dormant_state_out_of_season():
    olive = _semiseasonal_olive()
    in_season = prop_temporal_state(olive, datetime.date(1, 6, 1), 720)
    out_season = prop_temporal_state(olive, datetime.date(1, 1, 1), 720)

    assert in_season.active and not out_season.active
    # In season -> leafy state 0; out of season -> dormant state 1, never hidden.
    assert timer_state_index(in_season, 2) == 0
    assert timer_state_index(out_season, 2) == 1
    assert not timer_hides_prop(in_season, 2)
    assert not timer_hides_prop(out_season, 2)


def test_single_state_prop_hides_when_inactive():
    olive = _semiseasonal_olive()
    out_season = prop_temporal_state(olive, datetime.date(1, 1, 1), 720)

    # No alternate model: stays at state 0 and disappears while inactive.
    assert timer_state_index(out_season, 1) == 0
    assert timer_hides_prop(out_season, 1)


def test_time_of_day_two_state_prop_swaps_outside_window():
    overnight = Exemplar({0x4A149631: [22.0, 5.0]})
    night = prop_temporal_state(overnight, datetime.date(1, 1, 1), 23 * 60)
    day = prop_temporal_state(overnight, datetime.date(1, 1, 1), 12 * 60)

    assert timer_state_index(night, 2) == 0
    assert timer_state_index(day, 2) == 1
    assert not timer_hides_prop(day, 2)


def test_prop_without_timer_rule_never_switches_or_hides():
    plain = prop_temporal_state(Exemplar(), datetime.date(1, 1, 1), 720)

    assert timer_state_index(plain, 2) == 0
    assert not timer_hides_prop(plain, 1)
    assert not timer_hides_prop(plain, 2)
