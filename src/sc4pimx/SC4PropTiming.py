"""Pure helpers for previewing SC4 prop time and simulator-date rules."""
from __future__ import annotations

import calendar
import datetime as _datetime
from dataclasses import dataclass

PROP_TIME_OF_DAY = 0x4A149631
PROP_DATE_START = 0xCA7515CC
PROP_DATE_DURATION = 0x4A764564
PROP_DATE_INTERVAL = 0x0A751675
PROP_RANDOM_CHANCE = 0x4A751AD5

MAIN_SIMULATOR_TGI = (0x6534284A, 0xE7E2C2DB, 0xE9590E52)
NIGHT_BEGIN = 0x09B73421
NIGHT_END = 0x09B73422

# Values in the Maxis SimCity_1.dat Main Simulator exemplar.  They are only
# fallbacks: SC4VirtualDat.getEntry returns the effective load-order override.
MAXIS_NIGHT_BEGIN = 20
MAXIS_NIGHT_END = 1


@dataclass(frozen=True)
class PropTemporalState:
    active: bool
    has_time_rule: bool = False
    has_date_rule: bool = False
    time_active: bool = True
    date_active: bool = True
    random_chance: int | None = None


def _first(exemplar, prop_id, default=None):
    if exemplar is None:
        return default
    try:
        values = exemplar.GetProp(prop_id)
    except Exception:
        return default
    if not values:
        return default
    return values[0]


def is_wrapped_range(value, start, end, modulus):
    """Return whether *value* is in the wrapped half-open range [start, end)."""
    value = float(value) % modulus
    start = float(start) % modulus
    end = float(end) % modulus
    span = (end - start) % modulus
    return ((value - start) % modulus) < span


def is_night(minutes, begin=MAXIS_NIGHT_BEGIN, end=MAXIS_NIGHT_END):
    """Apply cSC424HourClock's integer-hour, wrapped night test."""
    hour = (int(minutes) // 60) % 24
    return is_wrapped_range(hour, int(begin), int(end), 24)


def effective_night_hours(virtual_dat):
    """Read the effective Main Simulator night window from a virtual DAT."""
    begin, end = MAXIS_NIGHT_BEGIN, MAXIS_NIGHT_END
    if virtual_dat is None:
        return begin, end
    entry = None
    exemplar = None
    temporary = False
    try:
        entry = virtual_dat.getEntry(*MAIN_SIMULATOR_TGI)
        exemplar = getattr(entry, "exemplar", None) if entry is not None else None
        if entry is not None and exemplar is None:
            # Standard and uncategorized exemplars are deliberately released by
            # SC4VirtualDat.Finalize to keep the full plugin scan small. Decode
            # this one effective entry on demand, then release its payload again.
            from .SC4DatTools import SC4Exemplar

            entry.read_file(None, True, True)
            exemplar = SC4Exemplar(entry, virtual_dat)
            temporary = True
        raw_begin = _first(exemplar, NIGHT_BEGIN)
        raw_end = _first(exemplar, NIGHT_END)
        if raw_begin is not None and 0 <= int(raw_begin) < 24:
            begin = int(raw_begin)
        if raw_end is not None and 0 <= int(raw_end) < 24:
            end = int(raw_end)
    except Exception:
        pass
    finally:
        if temporary:
            try:
                exemplar.free()
            except Exception:
                pass
            entry.rawContent = None
            entry.content = None
    return begin, end


def _valid_date(year, month, day):
    try:
        return _datetime.date(int(year), int(month), int(day))
    except (TypeError, ValueError, OverflowError):
        return None


def _date_rule_active(exemplar, preview_date):
    try:
        start = exemplar.GetProp(PROP_DATE_START)
        duration = exemplar.GetProp(PROP_DATE_DURATION)
        interval = exemplar.GetProp(PROP_DATE_INTERVAL)
    except Exception:
        return False, True

    has_rule = bool(start or duration or interval)
    if not has_rule:
        return False, True

    # Partial/malformed schedules are displayed rather than silently hiding
    # the object. A meaningful SC4 schedule needs a start and positive duration.
    if not start or len(start) < 2 or not duration:
        return True, True
    start_date = _valid_date(1, start[0], start[1])
    try:
        active_days = int(duration[0])
    except (TypeError, ValueError, IndexError):
        return True, True
    if start_date is None or active_days <= 0:
        return True, True

    # The exemplar stores only month/day. Evaluate it on one non-leap annual
    # ring so December intervals can remain active into January without
    # inventing a simulator year that the property does not contain.
    current = _valid_date(1, preview_date.month, preview_date.day)
    if current is None:
        return True, True
    year_days = 365
    elapsed = (current.toordinal() - start_date.toordinal()) % year_days

    try:
        repeat_days = int(interval[0]) if interval else 0
    except (TypeError, ValueError, IndexError):
        repeat_days = 0
    if repeat_days > 0:
        return True, (elapsed % repeat_days) < active_days
    return True, elapsed < active_days


def prop_temporal_state(exemplar, preview_date, minutes):
    """Evaluate deterministic time/date visibility for one prop exemplar.

    Random chance is reported but deliberately not rolled: a calendar position
    cannot determine the simulator's random outcome.
    """
    time_values = None
    try:
        time_values = exemplar.GetProp(PROP_TIME_OF_DAY) if exemplar is not None else None
    except Exception:
        pass
    has_time = bool(time_values and len(time_values) >= 2)
    time_active = True
    if has_time:
        start, end = float(time_values[0]), float(time_values[1])
        if not (start == 0.0 and end == 0.0):
            time_active = is_wrapped_range(float(minutes) / 60.0, start, end, 24.0)

    if not isinstance(preview_date, _datetime.date):
        preview_date = _datetime.date(1, 1, 1)
    has_date, date_active = _date_rule_active(exemplar, preview_date)

    chance = _first(exemplar, PROP_RANDOM_CHANCE)
    try:
        chance = max(0, min(100, int(chance))) if chance is not None else None
    except (TypeError, ValueError):
        chance = None

    return PropTemporalState(
        active=time_active and date_active,
        has_time_rule=has_time,
        has_date_rule=has_date,
        time_active=time_active,
        date_active=date_active,
        random_chance=chance,
    )


def _has_timer_rule(state):
    return state.has_time_rule or state.has_date_rule


def timer_hides_prop(state, state_count):
    """Whether a prop disappears because its deterministic timer rules are off.

    Mirrors cSC4PropOccupant: when the time/date timer mask is not fully
    satisfied the occupant is switched to state 1, not removed. A prop with
    only one model state has no alternate, so it visually disappears; a
    two-state ("semiseasonal") prop instead shows its dormant state 1 and is
    therefore never hidden.
    """
    if state_count >= 2:
        return False
    return _has_timer_rule(state) and not state.active


def timer_state_index(state, state_count):
    """Model state index a prop displays for the deterministic timer rules.

    State 0 while the timer rules are satisfied; the alternate state 1 (the
    dormant/off model) when they are not, matching the game's
    cSC4PropOccupant::SetPropTimerState, where every timer bit must be set for
    state 0 and any unmet rule falls through to state 1. Props without a second
    state stay at 0 (and are hidden via timer_hides_prop when inactive).
    """
    if state_count >= 2 and _has_timer_rule(state) and not state.active:
        return 1
    return 0


def clamp_date(month, day):
    """Clamp month/day and return the preview date on a non-leap annual ring."""
    year = 1
    month = max(1, min(12, int(month)))
    last_day = calendar.monthrange(year, month)[1]
    day = max(1, min(last_day, int(day)))
    return _datetime.date(year, month, day)
