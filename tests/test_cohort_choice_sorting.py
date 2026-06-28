from types import SimpleNamespace

from sc4pimx.SC4PIMApp import _cohort_choice_sort_key


def test_duplicate_cohort_names_are_sorted_by_tgi_without_comparing_entries():
    later = SimpleNamespace(tgi=(0x05342861, 0xFFFFFFFF, 0x00000002))
    earlier = SimpleNamespace(tgi=(0x05342861, 0xFFFFFFFF, 0x00000001))
    choices = [["Duplicate name", later], ["Duplicate name", earlier]]

    choices.sort(key=_cohort_choice_sort_key)

    assert choices == [["Duplicate name", earlier], ["Duplicate name", later]]
