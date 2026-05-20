from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def asset_path(*parts: str) -> Path:
    return project_root().joinpath("assets", *parts)


def package_data_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name
