"""Bundled SC4 lighting profiles and native map sampling."""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from .paths import asset_path


@dataclass(frozen=True)
class LightingProfile:
    profile_id: str
    display_name: str
    directory: Path
    night_begin_hour: int
    night_end_hour: int
    day_color: tuple[float, float, float]
    night_color: tuple[float, float, float]
    night_threshold: float
    terrain_shadow_amount: float
    model_shadow_amount: float
    flora_shadow_amount: float
    shadow_color: tuple[float, float, float]
    shadow_strength: float
    use_environment_map: bool
    map_width: int
    map_height: int
    map_pixels: tuple[tuple[int, int, int], ...]
    environment_width: int
    environment_height: int
    environment_pixels: tuple[tuple[int, int, int], ...]

    def sample_global_light(self, minutes: int, month: int) -> tuple[float, float, float]:
        """Sample the profile's time/month map using SC4's horizontal lerp.

        SC4 maps time to X as ``width * time / 24`` and selects the nearest
        month row from ``height * (month_index + 0.5) / 12``. The original
        routine only interpolates horizontally.
        """
        if not self.map_pixels or self.map_width <= 0 or self.map_height <= 0:
            return self.night_color if self.is_clock_night(minutes) else self.day_color

        time_fraction = (int(minutes) % 1440) / 1440.0
        x = self.map_width * time_fraction
        left = min(self.map_width - 1, max(0, int(math.floor(x))))
        right = min(self.map_width - 1, left + 1)
        amount = min(1.0, max(0.0, x - left))

        month_index = min(11, max(0, int(month) - 1))
        y = int(math.floor(self.map_height * ((month_index + 0.5) / 12.0) + 0.5))
        y = min(self.map_height - 1, max(0, y))

        a = self.map_pixels[y * self.map_width + left]
        b = self.map_pixels[y * self.map_width + right]
        return tuple(
            ((1.0 - amount) * a[channel] + amount * b[channel]) / 255.0
            for channel in range(3)
        )

    def is_clock_night(self, minutes: int) -> bool:
        hour = (int(minutes) // 60) % 24
        span = (self.night_end_hour - self.night_begin_hour) % 24
        return ((hour - self.night_begin_hour) % 24) < span

    def is_graphical_night(self, minutes: int, month: int) -> bool:
        """Return SC4's lighting-manager night state for this map sample."""
        return self.sample_global_light(minutes, month)[0] <= self.night_threshold

    def sample_environment_color(
        self, normal: tuple[float, float, float] = (0.0, 1.0, 0.0),
    ) -> tuple[float, float, float] | None:
        """Sample SC4's paired environment map for an X/Z normal.

        The game takes the lookup dimensions from 0917660C and the RGB data
        from 0917660D. Lot-preview model light uses the flat terrain normal,
        which resolves to the centre pixel.
        """
        if (
            not self.use_environment_map
            or not self.environment_pixels
            or self.environment_width <= 0
            or self.environment_height <= 0
        ):
            return None

        x_normal = min(1.0, max(-1.0, float(normal[0])))
        z_normal = min(1.0, max(-1.0, float(normal[2])))
        x = int(self.environment_width * ((x_normal + 1.0) * 0.5))
        y = int(self.environment_height * ((z_normal + 1.0) * 0.5))
        x = min(self.environment_width - 1, max(0, x))
        y = min(self.environment_height - 1, max(0, y))
        color = self.environment_pixels[y * self.environment_width + x]
        return tuple(channel / 255.0 for channel in color)


def _float3(value, default) -> tuple[float, float, float]:
    try:
        if len(value) == 3:
            return tuple(float(component) for component in value)
    except (TypeError, ValueError):
        pass
    return tuple(float(component) for component in default)


def _load_map(path: Path) -> tuple[int, int, tuple[tuple[int, int, int], ...]]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        return image.width, image.height, tuple(image.get_flattened_data())


def _load_profile(path: Path) -> LightingProfile:
    with open(path, "rb") as handle:
        data = tomllib.load(handle)

    clock = data.get("clock", {})
    global_light = data.get("global_light", {})
    terrain = data.get("terrain_shading", {})
    shadow = data.get("shadow", {})
    directory = path.parent
    map_path = directory / str(data.get("global_light_map", ""))
    width, height, pixels = _load_map(map_path)
    use_environment_map = bool(global_light.get("use_environment_map", False))
    environment_width = environment_height = 0
    environment_pixels = ()
    if use_environment_map:
        shape_path = directory / str(data.get("environment_shape_map", ""))
        color_path = directory / str(data.get("environment_color_map", ""))
        environment_width, environment_height, _shape_pixels = _load_map(shape_path)
        color_width, color_height, environment_pixels = _load_map(color_path)
        if (color_width, color_height) != (environment_width, environment_height):
            raise ValueError(
                f"Environment-map dimensions differ in {directory}: "
                f"0917660C is {environment_width}x{environment_height}, "
                f"0917660D is {color_width}x{color_height}"
            )

    return LightingProfile(
        profile_id=str(data.get("id", directory.name)),
        display_name=str(data.get("display_name", directory.name)),
        directory=directory,
        night_begin_hour=int(clock.get("night_begin_hour", 20)) % 24,
        night_end_hour=int(clock.get("night_end_hour", 1)) % 24,
        day_color=_float3(global_light.get("day_color"), (1.0, 1.0, 1.0)),
        night_color=_float3(global_light.get("night_color"), (0.5, 0.5, 0.5)),
        night_threshold=float(global_light.get("night_threshold", 0.8)),
        terrain_shadow_amount=float(terrain.get("terrain_amount", 0.8)),
        model_shadow_amount=float(terrain.get("model_amount", 0.4)),
        flora_shadow_amount=float(terrain.get("flora_amount", 0.9)),
        shadow_color=_float3(shadow.get("color"), (0.08, 0.06, 0.23)),
        shadow_strength=float(shadow.get("strength", 0.4)),
        use_environment_map=use_environment_map,
        map_width=width,
        map_height=height,
        map_pixels=pixels,
        environment_width=environment_width,
        environment_height=environment_height,
        environment_pixels=environment_pixels,
    )


@lru_cache(maxsize=1)
def lighting_profiles() -> tuple[LightingProfile, ...]:
    root = asset_path("lighting")
    profiles = tuple(_load_profile(path) for path in sorted(root.glob("*/profile.toml")))
    if not profiles:
        raise FileNotFoundError("No bundled lighting profiles were found")
    return profiles


def lighting_profile(profile_id: str, fallback: str = "maxis") -> LightingProfile:
    profiles = lighting_profiles()
    by_id = {profile.profile_id: profile for profile in profiles}
    return by_id.get(str(profile_id), by_id.get(fallback, profiles[0]))
