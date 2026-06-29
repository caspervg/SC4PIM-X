import pytest

from sc4pimx.SC4LightingProfiles import lighting_profile, lighting_profiles


def test_bundled_profiles_load_with_expected_core_settings():
    profiles = {profile.profile_id: profile for profile in lighting_profiles()}

    assert set(profiles) == {"maxis", "simfox"}
    assert profiles["maxis"].map_width == profiles["simfox"].map_width == 32
    assert profiles["maxis"].map_height == profiles["simfox"].map_height == 32
    assert profiles["maxis"].model_shadow_amount == pytest.approx(0.4)
    assert profiles["simfox"].model_shadow_amount == pytest.approx(0.9)
    assert profiles["maxis"].flora_shadow_amount == pytest.approx(0.9)
    assert profiles["simfox"].flora_shadow_amount == pytest.approx(0.9)
    assert profiles["maxis"].shadow_color == pytest.approx((0.08, 0.06, 0.23))
    assert profiles["simfox"].shadow_color == pytest.approx((0.02, 0.0, 0.2))
    assert profiles["maxis"].shadow_strength == pytest.approx(0.4)
    assert profiles["simfox"].shadow_strength == pytest.approx(0.5)
    assert profiles["maxis"].use_environment_map
    assert profiles["simfox"].use_environment_map
    assert profiles["maxis"].environment_width == 64
    assert profiles["maxis"].environment_height == 64
    assert profiles["simfox"].environment_width == 64
    assert profiles["simfox"].environment_height == 64


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


@pytest.mark.parametrize("profile_id", ["maxis", "simfox"])
def test_graphical_night_uses_sampled_red_channel_threshold(profile_id):
    profile = lighting_profile(profile_id)

    assert profile.is_graphical_night(0, 1)
    assert not profile.is_graphical_night(12 * 60, 1)


def test_environment_map_uses_each_profiles_effective_color_data():
    maxis = lighting_profile("maxis")
    simfox = lighting_profile("simfox")

    # Both maps deliberately peak at white for flat terrain. Their directional
    # color data differs and becomes visible as soon as the normal tilts.
    assert maxis.sample_environment_color() == pytest.approx((1.0, 1.0, 1.0))
    assert simfox.sample_environment_color() == pytest.approx((1.0, 1.0, 1.0))
    maxis_color = maxis.sample_environment_color((1.0, 0.0, 0.0))
    simfox_color = simfox.sample_environment_color((1.0, 0.0, 0.0))

    assert maxis_color is not None
    assert simfox_color is not None
    assert maxis_color != pytest.approx(simfox_color)
    assert all(0.0 <= channel <= 1.0 for channel in maxis_color)
    assert all(0.0 <= channel <= 1.0 for channel in simfox_color)
