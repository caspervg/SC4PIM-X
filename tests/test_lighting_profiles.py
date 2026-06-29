import pytest

from sc4pimx.SC4LightingProfiles import lighting_profile, lighting_profiles


def test_bundled_profiles_load_with_expected_core_settings():
    profiles = {profile.profile_id: profile for profile in lighting_profiles()}

    assert set(profiles) == {"maxis", "simfox"}
    assert profiles["maxis"].map_width == profiles["simfox"].map_width == 32
    assert profiles["maxis"].map_height == profiles["simfox"].map_height == 32
    assert profiles["maxis"].model_shadow_amount == pytest.approx(0.4)
    assert profiles["simfox"].model_shadow_amount == pytest.approx(0.9)
    assert profiles["maxis"].shadow_color == pytest.approx((0.08, 0.06, 0.23))
    assert profiles["simfox"].shadow_color == pytest.approx((0.02, 0.0, 0.2))
    assert profiles["maxis"].shadow_strength == pytest.approx(0.4)
    assert profiles["simfox"].shadow_strength == pytest.approx(0.5)


def test_midnight_global_light_comes_from_each_profile_map():
    maxis = lighting_profile("maxis")
    simfox = lighting_profile("simfox")

    assert maxis.sample_global_light(0, 1) == pytest.approx(
        (128 / 255.0, 127 / 255.0, 194 / 255.0)
    )
    assert simfox.sample_global_light(0, 1) == pytest.approx(
        (49 / 255.0, 50 / 255.0, 72 / 255.0)
    )


def test_profile_clock_is_wrapped_and_unknown_id_falls_back_to_maxis():
    profile = lighting_profile("simfox")

    assert profile.is_clock_night(20 * 60)
    assert profile.is_clock_night(0)
    assert not profile.is_clock_night(60)
    assert lighting_profile("missing").profile_id == "maxis"
