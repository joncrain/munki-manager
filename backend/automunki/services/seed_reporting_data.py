"""Generate realistic demo data for client reporting tables."""

from __future__ import annotations

import random
import string
import uuid
from datetime import UTC, datetime, timedelta

from faker import Faker
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from automunki.models.client import ClientInstallReport, ClientMachine, ClientMachineCheckin
from automunki.models.munki import Manifest

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

_SOFTWARE_CATALOG: list[tuple[str, str, str]] = [
    ("Ghostty", "1.3.0", "com.ghostty.ghostty"),
    ("Obsidian", "1.1.1", "md.obsidian.obsidian"),
    ("Cursor", "3.7.36", "com.cursor.ide"),
    ("GoogleChrome", "149.0.7827.156", "com.google.Chrome"),
    ("Slack", "4.50.140", "com.tinyspeck.slackmacgap"),
    ("Zoom", "6.3.11.50104", "us.zoom.xos"),
    ("Munki", "7.1.2", "ManagedSoftwareCenter"),
]

_INSTALL_REASONS = (
    "managed_install",
    "managed_update",
    "optional_install",
    "apple_software_update",
)

_FAILURE_MESSAGES = (
    "Could not download item",
    "Installation failed: installer returned non-zero exit status 1",
    "Blocking application(s) running: Google Chrome",
    "Disk space insufficient for installation",
)


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


def _installed_software(rng: random.Random) -> list[dict[str, str]]:
    count = rng.randint(6, min(12, len(_SOFTWARE_CATALOG)))
    apps = rng.sample(_SOFTWARE_CATALOG, count)
    return [
        {
            "name": name,
            "version": version,
            "bundle_id": bundle_id,
            "path": f"/Applications/{name}.app",
        }
        for name, version, bundle_id in apps
    ]


def _install_reports_for_machine(
    rng: random.Random,
    machine_id: uuid.UUID,
    *,
    first_checkin: datetime,
    last_checkin: datetime,
    count: int,
) -> list[ClientInstallReport]:
    reports: list[ClientInstallReport] = []
    span_seconds = max(1, int((last_checkin - first_checkin).total_seconds()))
    for _ in range(count):
        name, version, _bundle = rng.choice(_SOFTWARE_CATALOG)
        status_roll = rng.random()
        if status_roll < 0.78:
            status = "installed"
            error_message = None
            reason = rng.choice(_INSTALL_REASONS)
        elif status_roll < 0.88:
            status = "failed"
            error_message = rng.choice(_FAILURE_MESSAGES)
            reason = "problem_install"
        elif status_roll < 0.95:
            status = "removed"
            error_message = None
            reason = "removal"
        else:
            status = "removal_failed"
            error_message = "Removal script returned non-zero exit status"
            reason = "removal"

        offset = rng.randint(0, span_seconds)
        install_date = first_checkin + timedelta(seconds=offset)
        created_at = install_date + timedelta(minutes=rng.randint(0, 30))

        reports.append(
            ClientInstallReport(
                machine_id=machine_id,
                item_name=name,
                item_version=version,
                status=status,
                install_date=install_date,
                error_message=error_message,
                install_reason=reason,
                details={
                    "item_name": name,
                    "item_version": version,
                    "status": status,
                    "install_reason": reason,
                    "unattended": rng.random() < 0.7,
                },
                created_at=created_at,
            )
        )
    return reports


def _checkins_for_machine(
    rng: random.Random,
    machine_id: uuid.UUID,
    *,
    first_checkin: datetime,
    last_checkin: datetime,
) -> list[ClientMachineCheckin]:
    """Spread check-ins across the machine lifetime (heavier weight in last 30 days)."""
    checkins: list[ClientMachineCheckin] = []
    now = datetime.now(UTC)
    lifetime_days = max(1, (last_checkin.date() - first_checkin.date()).days)

    # Daily-ish check-ins for active machines; sparse for stale ones.
    if (now - last_checkin).days <= 7:
        total = rng.randint(20, 90)
    elif (now - last_checkin).days <= 30:
        total = rng.randint(5, 25)
    else:
        total = rng.randint(1, 8)

    for _ in range(total):
        day_offset = rng.randint(0, lifetime_days)
        hour = rng.randint(6, 22)
        minute = rng.randint(0, 59)
        checked_in_at = (first_checkin + timedelta(days=day_offset)).replace(
            hour=hour, minute=minute, second=rng.randint(0, 59), microsecond=0
        )
        if checked_in_at > last_checkin:
            checked_in_at = last_checkin - timedelta(hours=rng.randint(1, 48))
        if checked_in_at < first_checkin:
            checked_in_at = first_checkin
        checkins.append(ClientMachineCheckin(machine_id=machine_id, checked_in_at=checked_in_at))

    # Ensure at least one check-in on last_checkin day for chart consistency.
    checkins.append(
        ClientMachineCheckin(
            machine_id=machine_id,
            checked_in_at=last_checkin.replace(hour=rng.randint(8, 17), minute=rng.randint(0, 59)),
        )
    )
    return checkins


async def clear_reporting_data(session: AsyncSession) -> None:
    await session.execute(delete(ClientInstallReport))
    await session.execute(delete(ClientMachineCheckin))
    await session.execute(delete(ClientMachine))
    await session.flush()


async def seed_reporting_data(
    session: AsyncSession,
    *,
    count: int = 25,
    seed: int | None = None,
    clear: bool = False,
) -> dict[str, int]:
    """Insert demo rows into client_machine, client_machine_checkin, client_install_report."""
    if count < 1:
        raise ValueError("count must be at least 1")

    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed if seed is not None else 0)

    if clear:
        await clear_reporting_data(session)

    manifest_names = [
        row[0] for row in (await session.execute(select(Manifest.name).order_by(Manifest.name).limit(50))).all()
    ]
    if not manifest_names:
        manifest_names = ["site-default", "production", "testing", "all"]

    now = datetime.now(UTC)
    machines_created = 0
    checkins_created = 0
    reports_created = 0

    for _ in range(count):
        profile = rng.choice(_MAC_PROFILES)
        os_version, os_build = rng.choice(_OS_VERSIONS)
        serial = _random_apple_serial(rng)
        hostname = _hostname_for_profile(rng, fake, profile)
        manifest_name = rng.choice(manifest_names)
        client_identifier = manifest_name

        disk_size = int(profile["disk_size_gb"])  # type: ignore[arg-type]
        disk_free = rng.randint(max(20, disk_size // 10), max(21, disk_size - 10))

        # Mix of fresh, recent, and stale last check-ins for compliance charts.
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
            installed_software=_installed_software(rng),
            first_checkin_at=first_checkin,
            last_checkin_at=last_checkin,
        )
        session.add(machine)
        await session.flush()
        machines_created += 1

        checkins = _checkins_for_machine(
            rng,
            machine.id,
            first_checkin=first_checkin,
            last_checkin=last_checkin,
        )
        session.add_all(checkins)
        checkins_created += len(checkins)

        report_count = rng.randint(3, 18)
        reports = _install_reports_for_machine(
            rng,
            machine.id,
            first_checkin=first_checkin,
            last_checkin=last_checkin,
            count=report_count,
        )
        session.add_all(reports)
        reports_created += len(reports)

    await session.commit()
    return {
        "machines": machines_created,
        "checkins": checkins_created,
        "install_reports": reports_created,
    }
