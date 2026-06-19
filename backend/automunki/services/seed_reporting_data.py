"""Generate realistic demo data for client reporting tables."""

from __future__ import annotations

import random
import re
import string
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from faker import Faker
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.models.client import ClientInstallReport, ClientMachine, ClientMachineCheckin
from automunki.models.munki import Manifest, PkgInfo

# Apple factory / location prefixes seen on real Mac serials (not real devices).
_SERIAL_PREFIXES = (
    "C02",
    "C07",
    "FVF",
    "FVFC",
    "W803",
    "W804",
    "Y03",
    "CK2",
    "H9F",
    "J1G",
)

_MAC_PROFILES: list[dict[str, object]] = [
    {
        "machine_model": "Mac14,2",
        "product_name": "MacBook Air",
        "apple_image_family": "MacBook Air",
        "cpu_type": "Apple M2",
        "cpu_arch": "arm64",
        "physical_cpus": 1,
        "logical_cpus": 8,
        "ram_mb": 16384,
        "disk_size_gb": 512,
    },
    {
        "machine_model": "Mac15,7",
        "product_name": "MacBook Pro",
        "apple_image_family": "MacBook Pro",
        "cpu_type": "Apple M3 Pro",
        "cpu_arch": "arm64",
        "physical_cpus": 1,
        "logical_cpus": 12,
        "ram_mb": 18432,
        "disk_size_gb": 1024,
    },
    {
        "machine_model": "MacBookPro18,1",
        "product_name": "MacBook Pro",
        "apple_image_family": "MacBook Pro",
        "cpu_type": "Apple M1 Pro",
        "cpu_arch": "arm64",
        "physical_cpus": 1,
        "logical_cpus": 10,
        "ram_mb": 16384,
        "disk_size_gb": 512,
    },
    {
        "machine_model": "Mac13,1",
        "product_name": "Mac Studio",
        "apple_image_family": "Mac Studio",
        "cpu_type": "Apple M1 Max",
        "cpu_arch": "arm64",
        "physical_cpus": 1,
        "logical_cpus": 10,
        "ram_mb": 32768,
        "disk_size_gb": 1024,
    },
    {
        "machine_model": "Macmini9,1",
        "product_name": "Mac mini",
        "apple_image_family": "Mac mini",
        "cpu_type": "Apple M1",
        "cpu_arch": "arm64",
        "physical_cpus": 1,
        "logical_cpus": 8,
        "ram_mb": 8192,
        "disk_size_gb": 256,
    },
    {
        "machine_model": "iMac21,1",
        "product_name": "iMac",
        "apple_image_family": "iMac",
        "cpu_type": "Apple M1",
        "cpu_arch": "arm64",
        "physical_cpus": 1,
        "logical_cpus": 8,
        "ram_mb": 8192,
        "disk_size_gb": 512,
    },
]

_OS_VERSIONS = (
    ("26.4", "26A424"),
    ("26.3", "26A420"),
    ("26.2", "26A416"),
    ("26.1", "26A412"),
    ("26.0", "26A408"),
    ("15.7", "24H123"),
    ("15.6", "24G74"),
    ("15.5", "24F74"),
    ("15.4.1", "24E263"),
    ("14.7.2", "23H311"),
    ("14.6.1", "23G93"),
)

_MUNKI_VERSIONS = ("7.1.2", "7.1.1", "7.0.2", "6.6.2")

_FALLBACK_SOFTWARE: list[tuple[str, str, str, str]] = [
    ("Ghostty", "1.3.0", "com.ghostty.ghostty", "/Applications/Ghostty.app"),
    ("Obsidian", "1.1.1", "md.obsidian.obsidian", "/Applications/Obsidian.app"),
    ("Slack", "4.50.140", "com.tinyspeck.slackmacgap", "/Applications/Slack.app"),
    ("GoogleChrome", "149.0.7827.156", "com.google.Chrome", "/Applications/Google Chrome.app"),
    ("munkitools", "7.1.2.5700", "ManagedSoftwareCenter", "/Applications/Managed Software Center.app"),
]

_FAILURE_MESSAGES = (
    "Could not download item",
    "Installation failed: installer returned non-zero exit status 1",
    "Blocking application(s) running: Google Chrome",
    "Disk space insufficient for installation",
)


@dataclass(frozen=True, slots=True)
class SoftwareVersion:
    name: str
    version: str
    display_name: str
    bundle_id: str
    path: str


def _version_sort_key(version: str) -> tuple:
    """Best-effort ordering for Munki version strings (semver-ish and dotted builds)."""
    parts = re.split(r"[.\-+]", version)
    key: list = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return tuple(key)


def _bundle_from_installs(
    installs: object,
    name: str,
    display_name: str | None,
) -> tuple[str, str]:
    label = display_name or name
    default_path = f"/Applications/{label}.app"
    if isinstance(installs, list):
        for item in installs:
            if not isinstance(item, dict):
                continue
            bundle = item.get("CFBundleIdentifier") or item.get("bundleid")
            path = item.get("path")
            if isinstance(bundle, str) and bundle.strip():
                return bundle.strip(), str(path) if isinstance(path, str) and path else default_path
    return "", default_path


async def load_pkginfo_catalog(session: AsyncSession) -> dict[str, list[SoftwareVersion]]:
    """Group non-deleted pkginfo rows by name, versions sorted oldest → newest."""
    rows = (
        await session.execute(
            select(PkgInfo.name, PkgInfo.version, PkgInfo.display_name, PkgInfo.installs).where(
                PkgInfo.is_deleted.is_(False)
            )
        )
    ).all()

    grouped: dict[str, list[SoftwareVersion]] = defaultdict(list)
    for name, version, display_name, installs in rows:
        bundle_id, path = _bundle_from_installs(installs, name, display_name)
        grouped[name].append(
            SoftwareVersion(
                name=name,
                version=version,
                display_name=display_name or name,
                bundle_id=bundle_id,
                path=path,
            )
        )

    for versions in grouped.values():
        versions.sort(key=lambda entry: (_version_sort_key(entry.version), entry.version))

    return dict(grouped)


def _catalog_from_fallback() -> dict[str, list[SoftwareVersion]]:
    catalog: dict[str, list[SoftwareVersion]] = {}
    for name, version, bundle_id, path in _FALLBACK_SOFTWARE:
        catalog[name] = [
            SoftwareVersion(
                name=name,
                version=version,
                display_name=name,
                bundle_id=bundle_id,
                path=path,
            )
        ]
    return catalog


def _pick_apps_for_machine(
    rng: random.Random,
    catalog: dict[str, list[SoftwareVersion]],
    *,
    min_apps: int = 6,
    max_apps: int = 14,
) -> list[list[SoftwareVersion]]:
    """Return version chains (oldest→newest) for apps assigned to one machine."""
    names = list(catalog.keys())
    if not names:
        return []

    multi = [n for n in names if len(catalog[n]) > 1]

    target = rng.randint(min_apps, min(max_apps, len(names)))
    # Favor apps with version history so upgrades look realistic.
    chosen: list[str] = []
    if multi:
        chosen.extend(rng.sample(multi, min(len(multi), max(2, target // 2))))
    remaining = target - len(chosen)
    pool = [n for n in names if n not in chosen]
    if remaining > 0 and pool:
        chosen.extend(rng.sample(pool, min(remaining, len(pool))))

    chains: list[list[SoftwareVersion]] = []
    for name in chosen:
        versions = catalog[name]
        if len(versions) == 1:
            chains.append(versions)
            continue
        # Keep a contiguous slice of the version timeline (never skip backward).
        span = rng.randint(1, min(5, len(versions)))
        chains.append(versions[-span:])
    return chains


def _installed_software_from_chains(chains: list[list[SoftwareVersion]]) -> list[dict[str, str]]:
    installed: list[dict[str, str]] = []
    for chain in chains:
        if not chain:
            continue
        latest = chain[-1]
        installed.append(
            {
                "name": latest.display_name,
                "version": latest.version,
                "bundle_id": latest.bundle_id,
                "path": latest.path,
            }
        )
    return installed


def _chronological_install_reports(
    rng: random.Random,
    machine_id: uuid.UUID,
    app_chains: list[list[SoftwareVersion]],
    *,
    window_start: datetime,
    window_end: datetime,
) -> list[ClientInstallReport]:
    """Build install rows where older pkginfo versions precede newer ones."""
    reports: list[ClientInstallReport] = []
    span_seconds = max(1, int((window_end - window_start).total_seconds()))

    for chain in app_chains:
        if not chain:
            continue

        # Spread the first install somewhere in the first 75% of the machine lifetime.
        base_offset = rng.randint(0, max(0, int(span_seconds * 0.75)))
        base_time = window_start + timedelta(seconds=base_offset)
        gap_days = rng.uniform(10, 40)

        for index, entry in enumerate(chain):
            install_date = base_time + timedelta(days=index * gap_days)
            if install_date > window_end:
                install_date = window_end - timedelta(hours=rng.randint(2, 96))
            if install_date < window_start:
                install_date = window_start + timedelta(hours=rng.randint(1, 48))

            reason = "managed_install" if index == 0 else "managed_update"

            # Occasional failed upgrade attempt before a successful one.
            if index > 0 and rng.random() < 0.1:
                fail_date = install_date - timedelta(hours=rng.randint(2, 36))
                if fail_date >= window_start:
                    reports.append(
                        ClientInstallReport(
                            machine_id=machine_id,
                            item_name=entry.name,
                            item_version=entry.version,
                            status="failed",
                            install_date=fail_date,
                            error_message=rng.choice(_FAILURE_MESSAGES),
                            install_reason="managed_update",
                            details={
                                "item_name": entry.name,
                                "item_version": entry.version,
                                "status": "failed",
                                "install_reason": "managed_update",
                            },
                            created_at=fail_date + timedelta(minutes=rng.randint(1, 20)),
                        )
                    )

            reports.append(
                ClientInstallReport(
                    machine_id=machine_id,
                    item_name=entry.name,
                    item_version=entry.version,
                    status="installed",
                    install_date=install_date,
                    error_message=None,
                    install_reason=reason,
                    details={
                        "item_name": entry.name,
                        "item_version": entry.version,
                        "status": "installed",
                        "install_reason": reason,
                        "unattended": rng.random() < 0.75,
                    },
                    created_at=install_date + timedelta(minutes=rng.randint(0, 30)),
                )
            )

        # Rare uninstall of an app that was upgraded in-place.
        if len(chain) > 1 and rng.random() < 0.06:
            removed = chain[-1]
            removal_date = window_end - timedelta(days=rng.randint(1, 14))
            if removal_date > base_time:
                reports.append(
                    ClientInstallReport(
                        machine_id=machine_id,
                        item_name=removed.name,
                        item_version=removed.version,
                        status="removed",
                        install_date=removal_date,
                        error_message=None,
                        install_reason="removal",
                        details={
                            "item_name": removed.name,
                            "item_version": removed.version,
                            "status": "removed",
                            "install_reason": "removal",
                        },
                        created_at=removal_date + timedelta(minutes=rng.randint(0, 15)),
                    )
                )

    reports.sort(key=lambda row: row.install_date or datetime.min.replace(tzinfo=UTC))
    return reports


def _random_apple_serial(rng: random.Random) -> str:
    """Generate a plausible Apple serial (classic 12-char or modern 10–12 alnum)."""
    if rng.random() < 0.35:
        prefix = rng.choice(_SERIAL_PREFIXES)
        body = "".join(rng.choices(string.ascii_uppercase + string.digits, k=12 - len(prefix)))
        return f"{prefix}{body}"[:12]
    length = rng.choice((10, 11, 12))
    alphabet = string.ascii_uppercase + string.digits
    return "".join(rng.choices(alphabet, k=length))


def _hostname_for_profile(rng: random.Random, fake: Faker, profile: dict[str, object]) -> str:
    product = str(profile["product_name"]).replace(" ", "")
    style = rng.randint(0, 2)
    if style == 0:
        first = fake.first_name()
        return f"{first}s-{product}"
    if style == 1:
        return f"MBP-{fake.last_name()[:3].upper()}{rng.randint(10, 99)}"
    return f"mac-{rng.randint(1000, 9999)}"


def _checkins_for_machine(
    rng: random.Random,
    machine_id: uuid.UUID,
    *,
    first_checkin: datetime,
    last_checkin: datetime,
    recent_days: int = 7,
) -> list[ClientMachineCheckin]:
    """Spread check-ins across lifetime with denser coverage in the last few days."""
    checkins: list[ClientMachineCheckin] = []
    now = datetime.now(UTC)
    lifetime_days = max(1, (last_checkin.date() - first_checkin.date()).days)

    if (now - last_checkin).days <= 7:
        total = rng.randint(25, 90)
    elif (now - last_checkin).days <= 30:
        total = rng.randint(8, 30)
    else:
        total = rng.randint(2, 10)

    for _ in range(total):
        day_offset = rng.randint(0, lifetime_days)
        checked_in_at = (first_checkin + timedelta(days=day_offset)).replace(
            hour=rng.randint(6, 22),
            minute=rng.randint(0, 59),
            second=rng.randint(0, 59),
            microsecond=0,
        )
        if checked_in_at > last_checkin:
            checked_in_at = last_checkin - timedelta(hours=rng.randint(1, 48))
        if checked_in_at < first_checkin:
            checked_in_at = first_checkin
        checkins.append(ClientMachineCheckin(machine_id=machine_id, checked_in_at=checked_in_at))

    checkins.extend(
        _recent_daily_checkins(
            rng,
            machine_id,
            days=recent_days,
            through=last_checkin,
        )
    )
    return checkins


def _recent_daily_checkins(
    rng: random.Random,
    machine_id: uuid.UUID,
    *,
    days: int,
    through: datetime | None = None,
) -> list[ClientMachineCheckin]:
    """One or two check-ins on most of the last ``days`` calendar days."""
    anchor = through or datetime.now(UTC)
    checkins: list[ClientMachineCheckin] = []
    for day_offset in range(days):
        if rng.random() > 0.88:
            continue
        day = (anchor - timedelta(days=day_offset)).date()
        for _ in range(rng.randint(1, 2)):
            checked_in_at = datetime.combine(
                day,
                time(hour=rng.randint(7, 18), minute=rng.randint(0, 59), second=rng.randint(0, 59)),
                tzinfo=UTC,
            )
            checkins.append(ClientMachineCheckin(machine_id=machine_id, checked_in_at=checked_in_at))
    return checkins


async def clear_reporting_data(session: AsyncSession) -> None:
    await session.execute(delete(ClientInstallReport))
    await session.execute(delete(ClientMachineCheckin))
    await session.execute(delete(ClientMachine))
    await session.flush()


async def enrich_reporting_data(
    session: AsyncSession,
    *,
    catalog: dict[str, list[SoftwareVersion]] | None = None,
    seed: int | None = None,
    recent_checkin_days: int = 7,
) -> dict[str, int]:
    """Backfill existing machines with recent check-ins and chronologically sane installs."""
    rng = random.Random(seed)
    if catalog is None:
        catalog = await load_pkginfo_catalog(session)
    if not catalog:
        catalog = _catalog_from_fallback()

    machines = (await session.execute(select(ClientMachine))).scalars().all()
    now = datetime.now(UTC)
    checkins_added = 0
    reports_added = 0
    machines_updated = 0

    for machine in machines:
        first = machine.first_checkin_at or (now - timedelta(days=180))
        last = machine.last_checkin_at or now

        new_checkins = _recent_daily_checkins(
            rng,
            machine.id,
            days=recent_checkin_days,
            through=now,
        )
        if new_checkins:
            session.add_all(new_checkins)
            checkins_added += len(new_checkins)
            newest = max(c.checked_in_at for c in new_checkins)
            if machine.last_checkin_at is None or newest > machine.last_checkin_at:
                machine.last_checkin_at = newest
            machines_updated += 1

        # Add upgrade history using pkginfo the machine may not already show.
        app_chains = _pick_apps_for_machine(rng, catalog, min_apps=4, max_apps=10)
        window_end = min(now, last + timedelta(days=1))
        reports = _chronological_install_reports(
            rng,
            machine.id,
            app_chains,
            window_start=first,
            window_end=window_end,
        )
        if reports:
            session.add_all(reports)
            reports_added += len(reports)

        # Refresh installed inventory to match latest versions from new chains.
        existing = machine.installed_software if isinstance(machine.installed_software, list) else []
        by_bundle: dict[str, dict[str, str]] = {}
        for item in existing:
            if isinstance(item, dict):
                key = str(item.get("bundle_id") or item.get("name") or "")
                if key:
                    by_bundle[key] = item
        for chain in app_chains:
            if not chain:
                continue
            latest = chain[-1]
            key = latest.bundle_id or latest.name
            by_bundle[key] = {
                "name": latest.display_name,
                "version": latest.version,
                "bundle_id": latest.bundle_id,
                "path": latest.path,
            }
        machine.installed_software = list(by_bundle.values())

    await session.commit()
    return {
        "machines_enriched": machines_updated,
        "checkins": checkins_added,
        "install_reports": reports_added,
    }


async def seed_reporting_data(
    session: AsyncSession,
    *,
    count: int = 25,
    seed: int | None = None,
    clear: bool = False,
    enrich: bool = False,
    recent_checkin_days: int = 7,
) -> dict[str, int]:
    """Insert demo rows into client_machine, client_machine_checkin, client_install_report."""
    if count < 0:
        raise ValueError("count must be non-negative")
    if count == 0 and not enrich:
        raise ValueError("count must be at least 1 unless --enrich is set")

    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed if seed is not None else 0)

    catalog = await load_pkginfo_catalog(session)
    if not catalog:
        catalog = _catalog_from_fallback()

    if clear:
        await clear_reporting_data(session)

    stats: dict[str, int] = {
        "machines": 0,
        "checkins": 0,
        "install_reports": 0,
        "machines_enriched": 0,
    }

    if enrich:
        enrich_stats = await enrich_reporting_data(
            session,
            catalog=catalog,
            seed=seed,
            recent_checkin_days=recent_checkin_days,
        )
        stats["machines_enriched"] = enrich_stats["machines_enriched"]
        stats["checkins"] += enrich_stats["checkins"]
        stats["install_reports"] += enrich_stats["install_reports"]

    if count == 0:
        return stats

    manifest_names = [
        row[0] for row in (await session.execute(select(Manifest.name).order_by(Manifest.name).limit(50))).all()
    ]
    if not manifest_names:
        manifest_names = ["site-default", "production", "testing", "all"]

    now = datetime.now(UTC)

    for _ in range(count):
        profile = rng.choice(_MAC_PROFILES)
        os_version, os_build = rng.choice(_OS_VERSIONS)
        serial = _random_apple_serial(rng)
        hostname = _hostname_for_profile(rng, fake, profile)
        manifest_name = rng.choice(manifest_names)
        client_identifier = manifest_name

        disk_size = int(profile["disk_size_gb"])  # type: ignore[arg-type]
        disk_free = rng.randint(max(20, disk_size // 10), max(21, disk_size - 10))

        staleness_roll = rng.random()
        if staleness_roll < 0.55:
            days_since_last = rng.randint(0, 6)
        elif staleness_roll < 0.85:
            days_since_last = rng.randint(7, 29)
        else:
            days_since_last = rng.randint(31, 120)

        lifetime_days = rng.randint(max(days_since_last + 1, 14), 365)
        first_checkin = now - timedelta(days=lifetime_days, hours=rng.randint(0, 12))
        last_checkin = now - timedelta(days=days_since_last, hours=rng.randint(0, 12))

        app_chains = _pick_apps_for_machine(rng, catalog)
        platform_uuid = str(uuid.uuid4()).upper()
        hardware_info = {
            "hostname": hostname,
            "os_version": os_version,
            "os_build": os_build,
            "machine_model": profile["machine_model"],
            "product_name": profile["product_name"],
            "cpu_type": profile["cpu_type"],
            "cpu_arch": profile["cpu_arch"],
            "physical_cpus": profile["physical_cpus"],
            "logical_cpus": profile["logical_cpus"],
            "ram_mb": profile["ram_mb"],
            "disk_size_gb": disk_size,
            "disk_free_gb": disk_free,
            "platform_uuid": platform_uuid,
            "apple_image_family": profile["apple_image_family"],
        }

        machine = ClientMachine(
            serial_number=serial,
            hostname=hostname,
            os_version=os_version,
            os_build=os_build,
            machine_model=str(profile["machine_model"]),
            cpu_type=str(profile["cpu_type"]),
            cpu_arch=str(profile["cpu_arch"]),
            physical_cpus=int(profile["physical_cpus"]),  # type: ignore[arg-type]
            logical_cpus=int(profile["logical_cpus"]),  # type: ignore[arg-type]
            ram_mb=int(profile["ram_mb"]),  # type: ignore[arg-type]
            disk_size_gb=disk_size,
            disk_free_gb=disk_free,
            munki_version=rng.choice(_MUNKI_VERSIONS),
            manifest_name=manifest_name,
            client_identifier=client_identifier,
            hardware_info=hardware_info,
            installed_software=_installed_software_from_chains(app_chains),
            first_checkin_at=first_checkin,
            last_checkin_at=last_checkin,
        )
        session.add(machine)
        await session.flush()
        stats["machines"] += 1

        checkins = _checkins_for_machine(
            rng,
            machine.id,
            first_checkin=first_checkin,
            last_checkin=last_checkin,
            recent_days=recent_checkin_days,
        )
        session.add_all(checkins)
        stats["checkins"] += len(checkins)

        reports = _chronological_install_reports(
            rng,
            machine.id,
            app_chains,
            window_start=first_checkin,
            window_end=last_checkin,
        )
        session.add_all(reports)
        stats["install_reports"] += len(reports)

    await session.commit()
    return stats
