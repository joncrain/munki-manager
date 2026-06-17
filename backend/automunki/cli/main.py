"""Munki Manager CLI - management commands for import, compilation, etc."""

import asyncio
import plistlib
from datetime import UTC, datetime
from pathlib import Path

import structlog

logger = structlog.get_logger()


async def import_repo(repo_path: str):
    """Import an existing Munki repo (pkgsinfo, manifests, overrides) into the database."""
    from sqlalchemy import select

    from automunki.core.db import async_session_factory
    from automunki.models.autopkg import AutoPkgRecipe
    from automunki.models.munki import (
        Catalog,
        ItemType,
        Manifest,
        ManifestCatalog,
        ManifestInclusion,
        ManifestItem,
        PkgInfo,
        PkgInfoCatalog,
    )
    from automunki.services.audit import create_audit_entry
    from automunki.services.trust import trust_info_from_plist_parent_recipe_trust

    repo = Path(repo_path)
    if not repo.exists():
        logger.error("repo_path_not_found", path=repo_path)
        return

    async with async_session_factory() as session:
        catalog_cache: dict[str, Catalog] = {}
        manifest_cache: dict[str, Manifest] = {}

        # --- Import pkgsinfo ---
        pkgsinfo_dir = repo / "pkgsinfo"
        if pkgsinfo_dir.exists():
            plist_files = list(pkgsinfo_dir.glob("*.plist"))
            logger.info("importing_pkgsinfo", count=len(plist_files))

            for plist_file in plist_files:
                try:
                    with open(plist_file, "rb") as f:
                        data = plistlib.load(f)
                except Exception as e:
                    logger.warning("plist_parse_error", file=str(plist_file), error=str(e))
                    continue

                name = data.get("name", "")
                version = data.get("version", "")
                if not name or not version:
                    logger.warning("skipping_pkginfo_no_name_version", file=str(plist_file))
                    continue

                existing = await session.execute(
                    select(PkgInfo).where(PkgInfo.name == name, PkgInfo.version == version)
                )
                if existing.scalar_one_or_none():
                    logger.debug("pkginfo_already_exists", name=name, version=version)
                    continue

                metadata = data.get("_metadata")
                if metadata and "creation_date" in metadata:
                    metadata["creation_date"] = str(metadata["creation_date"])

                pkg = PkgInfo(
                    name=name,
                    version=version,
                    display_name=data.get("display_name"),
                    description=data.get("description"),
                    category=data.get("category"),
                    developer=data.get("developer"),
                    icon_name=data.get("icon_name"),
                    installer_item_location=data.get("installer_item_location"),
                    installer_item_hash=data.get("installer_item_hash"),
                    installer_item_size=data.get("installer_item_size"),
                    installed_size=data.get("installed_size"),
                    installer_type=data.get("installer_type"),
                    minimum_os_version=data.get("minimum_os_version"),
                    maximum_os_version=data.get("maximum_os_version"),
                    uninstall_method=data.get("uninstall_method"),
                    unattended_install=data.get("unattended_install", False),
                    unattended_uninstall=data.get("unattended_uninstall", False),
                    autoremove=data.get("autoremove", False),
                    uninstallable=data.get("uninstallable", True),
                    installs=data.get("installs"),
                    receipts=data.get("receipts"),
                    blocking_applications=data.get("blocking_applications"),
                    items_to_copy=data.get("items_to_copy"),
                    supported_architectures=data.get("supported_architectures"),
                    requires=data.get("requires"),
                    update_for=data.get("update_for"),
                    preinstall_script=data.get("preinstall_script"),
                    postinstall_script=data.get("postinstall_script"),
                    preuninstall_script=data.get("preuninstall_script"),
                    postuninstall_script=data.get("postuninstall_script"),
                    installcheck_script=data.get("installcheck_script"),
                    uninstallcheck_script=data.get("uninstallcheck_script"),
                    metadata_=metadata,
                )
                session.add(pkg)
                await session.flush()

                for cat_name in data.get("catalogs", []):
                    if cat_name not in catalog_cache:
                        existing_cat = await session.execute(select(Catalog).where(Catalog.name == cat_name))
                        cat = existing_cat.scalar_one_or_none()
                        if not cat:
                            cat = Catalog(name=cat_name)
                            session.add(cat)
                            await session.flush()
                        catalog_cache[cat_name] = cat

                    session.add(
                        PkgInfoCatalog(
                            pkg_info_id=pkg.id,
                            catalog_id=catalog_cache[cat_name].id,
                            entered_at=datetime.now(UTC),
                        )
                    )

                await session.flush()

                logger.info("imported_pkginfo", name=name, version=version)

        # --- Import manifests ---
        manifests_dir = repo / "manifests"
        if manifests_dir.exists():
            manifest_files = [f for f in manifests_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
            logger.info("importing_manifests", count=len(manifest_files))

            for manifest_file in manifest_files:
                try:
                    with open(manifest_file, "rb") as f:
                        data = plistlib.load(f)
                except Exception as e:
                    logger.warning("manifest_parse_error", file=str(manifest_file), error=str(e))
                    continue

                manifest_name = manifest_file.name
                existing = await session.execute(select(Manifest).where(Manifest.name == manifest_name))
                if existing.scalar_one_or_none():
                    logger.debug("manifest_already_exists", name=manifest_name)
                    continue

                manifest = Manifest(
                    name=manifest_name,
                    conditional_items=data.get("conditional_items"),
                )
                session.add(manifest)
                await session.flush()
                manifest_cache[manifest_name] = manifest

                for i, cat_name in enumerate(data.get("catalogs", [])):
                    if cat_name not in catalog_cache:
                        existing_cat = await session.execute(select(Catalog).where(Catalog.name == cat_name))
                        cat = existing_cat.scalar_one_or_none()
                        if not cat:
                            cat = Catalog(name=cat_name)
                            session.add(cat)
                            await session.flush()
                        catalog_cache[cat_name] = cat

                    session.add(
                        ManifestCatalog(
                            manifest_id=manifest.id,
                            catalog_id=catalog_cache[cat_name].id,
                            sort_order=i,
                        )
                    )

                item_type_map = {
                    "managed_installs": ItemType.managed_installs,
                    "managed_uninstalls": ItemType.managed_uninstalls,
                    "managed_updates": ItemType.managed_updates,
                    "optional_installs": ItemType.optional_installs,
                    "featured_items": ItemType.featured_items,
                    "default_installs": ItemType.default_installs,
                }

                for field_name, item_type in item_type_map.items():
                    for i, item_name in enumerate(data.get(field_name, [])):
                        session.add(
                            ManifestItem(
                                manifest_id=manifest.id,
                                item_name=item_name,
                                item_type=item_type,
                                sort_order=i,
                            )
                        )

                logger.info("imported_manifest", name=manifest_name)

            # Second pass for included_manifests references
            for manifest_file in manifest_files:
                try:
                    with open(manifest_file, "rb") as f:
                        data = plistlib.load(f)
                except Exception:
                    continue

                manifest_name = manifest_file.name
                if manifest_name not in manifest_cache:
                    continue

                parent = manifest_cache[manifest_name]
                for i, inc_name in enumerate(data.get("included_manifests", [])):
                    if inc_name in manifest_cache:
                        session.add(
                            ManifestInclusion(
                                parent_manifest_id=parent.id,
                                child_manifest_id=manifest_cache[inc_name].id,
                                sort_order=i,
                            )
                        )

        # --- Import recipe overrides ---
        for rel in ("autopkg_src/overrides", "AutoPkg/Overrides"):
            overrides_dir = repo / rel
            if not overrides_dir.exists():
                continue

            override_files = list(overrides_dir.glob("*.recipe"))
            logger.info("importing_overrides", dir=str(overrides_dir), count=len(override_files))

            for override_file in override_files:
                try:
                    with open(override_file, "rb") as f:
                        data = plistlib.load(f)
                except Exception as e:
                    logger.warning("override_parse_error", file=str(override_file), error=str(e))
                    continue

                identifier = data.get("Identifier", "")
                if not identifier:
                    logger.warning("override_skip_no_identifier", file=str(override_file))
                    continue

                name = data.get("Input", {}).get("NAME", override_file.stem)

                existing = await session.execute(select(AutoPkgRecipe).where(AutoPkgRecipe.identifier == identifier))
                if existing.scalar_one_or_none():
                    continue

                raw_trust = data.get("ParentRecipeTrustInfo")
                override_plist = {
                    "Identifier": identifier,
                    "ParentRecipe": data.get("ParentRecipe") or "",
                    "Input": _sanitize_plist_for_json(data.get("Input", {})),
                }
                if isinstance(raw_trust, dict):
                    override_plist["ParentRecipeTrustInfo"] = _sanitize_plist_for_json(raw_trust)

                trust_canonical = (
                    trust_info_from_plist_parent_recipe_trust(raw_trust) if isinstance(raw_trust, dict) else None
                )

                recipe = AutoPkgRecipe(
                    identifier=identifier,
                    name=name,
                    parent_recipe=data.get("ParentRecipe"),
                    is_enabled=True,
                    override_data=override_plist,
                    trust_info=trust_canonical,
                    input_variables=_sanitize_plist_for_json(data.get("Input", {})),
                )
                session.add(recipe)
                logger.info("imported_override", identifier=identifier, name=name)

        await create_audit_entry(
            session,
            action="import",
            entity_type="repository",
            entity_id=repo_path,
            entity_name="initial_import",
            notes=f"Imported from {repo_path}",
        )

        await session.commit()
        logger.info("import_complete")


async def ingest_icons(source_dir: str, overwrite: bool = False) -> None:
    """Bulk-ingest PNGs from ``source_dir`` into the ``software_icon`` table.

    Filenames become the Munki ``icon_name`` (sans ``.png``). Existing rows
    are kept unless ``--overwrite`` is passed.
    """
    from sqlalchemy import select

    from automunki.core.db import async_session_factory
    from automunki.models.software_icon import SoftwareIcon
    from automunki.services.ui_icons import sanitize_icon_basename, store_icon

    src = Path(source_dir)
    if not src.is_dir():
        logger.error("ingest_icons_source_missing", path=source_dir)
        return

    pngs = sorted(src.glob("*.png"))
    logger.info("ingest_icons_start", dir=str(src), count=len(pngs))

    imported = 0
    skipped = 0
    updated = 0
    invalid = 0

    async with async_session_factory() as session:
        for path in pngs:
            stem = path.stem
            try:
                safe = sanitize_icon_basename(stem)
            except ValueError:
                logger.warning("ingest_icons_invalid_name", file=str(path))
                invalid += 1
                continue

            existing = (
                await session.execute(select(SoftwareIcon).where(SoftwareIcon.name == safe))
            ).scalar_one_or_none()
            if existing is not None and not overwrite:
                skipped += 1
                continue

            try:
                data = path.read_bytes()
                await store_icon(session, safe, data)
            except ValueError as e:
                logger.warning("ingest_icons_reject", file=str(path), error=str(e))
                invalid += 1
                continue

            if existing is not None:
                updated += 1
            else:
                imported += 1

    logger.info(
        "ingest_icons_done",
        imported=imported,
        updated=updated,
        skipped=skipped,
        invalid=invalid,
    )


async def _seed_reporting_cli(count: int, seed: int | None, clear: bool) -> None:
    from automunki.core.db import async_session_factory
    from automunki.services.seed_reporting_data import seed_reporting_data

    async with async_session_factory() as session:
        stats = await seed_reporting_data(session, count=count, seed=seed, clear=clear)
    logger.info("seed_reporting_complete", **stats)


def _sanitize_plist_for_json(data):
    """Recursively convert plist data types to JSON-compatible types."""
    import datetime

    if isinstance(data, dict):
        return {k: _sanitize_plist_for_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_sanitize_plist_for_json(v) for v in data]
    if isinstance(data, bytes):
        return data.hex()
    if isinstance(data, datetime.datetime):
        return data.isoformat()
    return data


def app():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Munki Manager CLI")
    subparsers = parser.add_subparsers(dest="command")

    import_parser = subparsers.add_parser("import-repo", help="Import a Munki repo into the database")
    import_parser.add_argument("path", help="Path to the Munki repo root")

    ingest_icons_parser = subparsers.add_parser(
        "ingest-icons",
        help="Bulk-ingest PNG icons from a directory into the software_icon table",
    )
    ingest_icons_parser.add_argument(
        "path",
        help="Directory containing PNG files to load into the software_icon table",
    )
    ingest_icons_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing icons with the same name (default: keep existing)",
    )

    seed_reporting_parser = subparsers.add_parser(
        "seed-reporting",
        help="Insert demo data into client_machine / check-in / install report tables",
    )
    seed_reporting_parser.add_argument(
        "--count",
        type=int,
        default=25,
        help="Number of fake Macs to create (default: 25)",
    )
    seed_reporting_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible output",
    )
    seed_reporting_parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing client reporting rows before seeding",
    )

    args = parser.parse_args()

    if args.command == "import-repo":
        asyncio.run(import_repo(args.path))
    elif args.command == "ingest-icons":
        asyncio.run(ingest_icons(args.path, overwrite=args.overwrite))
    elif args.command == "seed-reporting":
        asyncio.run(_seed_reporting_cli(args.count, args.seed, args.clear))
    else:
        parser.print_help()


if __name__ == "__main__":
    app()
